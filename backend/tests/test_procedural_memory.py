"""Tests for Procedural Memory Layer: Skill DAGs, ActionStep chaining, and Reflexion Guardrails."""

import pytest
from app.core.falkor_client import falkor_router
from app.memory.procedural import procedural_memory, ActionStepSpec
from app.memory.episodic import episodic_memory


@pytest.fixture(scope="module")
def ensure_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live procedural memory tests.")


def test_procedure_creation_and_automatic_step_chaining(ensure_falkor):
    """TEST-PROC-CHAIN-01: Verifies that ACTION_STEP_APPEND automatically chains :FIRST_STEP and :NEXT_STEP in Cypher."""
    tenant = "test-proc-chain-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    steps = [
        ActionStepSpec(id="step_preflight", step_order=1, tool_name="check_preflight", param_schema="{'check': 'db'}"),
        ActionStepSpec(id="step_lock", step_order=2, tool_name="acquire_lock", param_schema="{'timeout_ms': 5000}"),
        ActionStepSpec(id="step_cutover", step_order=3, tool_name="execute_cutover", param_schema="{'mode': 'zero_downtime'}"),
        ActionStepSpec(id="step_verify", step_order=4, tool_name="verify_health", param_schema="{'latency_ms': 50}"),
    ]

    reg = procedural_memory.register_procedure(
        tenant_id=tenant,
        name="Database_Migration",
        trigger_description="Execute production database technology cutover",
        steps=steps,
    )
    assert reg["name"] == "Database_Migration"
    assert reg["steps_count"] == 4

    # 1. Verify FIRST_STEP edge
    first_res = falkor_router.query(
        "MATCH (p:Procedure {name: 'Database_Migration'})-[:FIRST_STEP]->(s:ActionStep) RETURN s.id, s.step_order",
        tenant_id=tenant,
    )
    assert first_res and len(first_res.result_set) == 1
    assert first_res.result_set[0][0] == "step_preflight"
    assert first_res.result_set[0][1] == 1

    # 2. Verify complete 4-step sequence via NEXT_STEP path
    path_res = falkor_router.query(
        """
        MATCH path = (p:Procedure {name: 'Database_Migration'})-[:FIRST_STEP|NEXT_STEP*1..5]->(last:ActionStep)
        WHERE NOT (last)-[:NEXT_STEP]->()
        RETURN [n IN nodes(path) WHERE n:ActionStep | n.id] AS step_ids
        """,
        tenant_id=tenant,
    )
    assert path_res and path_res.result_set
    step_ids = path_res.result_set[0][0]
    assert step_ids == ["step_preflight", "step_lock", "step_cutover", "step_verify"]


def test_guardrail_attachment_and_episode_provenance(ensure_falkor):
    """TEST-PROC-GUARD-02: Verifies that attaching a guardrail with episode_id materializes [:TRIGGERED_BY]->(:Episode)."""
    tenant = "test-proc-guard-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    # 1. Register base procedure
    step1 = ActionStepSpec(id="step_cutover_01", step_order=1, tool_name="execute_cutover")
    procedural_memory.register_procedure(
        tenant_id=tenant,
        name="Database_Migration",
        trigger_description="Run cutover",
        steps=[step1],
    )

    # 2. Record historical failure episode
    fail_ep = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id="sess_fail_01",
        episode_id="ep_deadlock_fail_101",
        content="Cutover failed: deadlock detected on schema mutation",
        importance_score=0.90,
        timestamp=1000.0,
    )
    assert fail_ep["id"] == "ep_deadlock_fail_101"

    # 3. Attach guardrail grounded in the failure episode
    gr = procedural_memory.attach_guardrail(
        tenant_id=tenant,
        step_id="step_cutover_01",
        rule_text="Acquire exclusive lock before altering schema to prevent deadlocks",
        error_signature="deadlock detected",
        fix_instruction="Execute acquire_lock with timeout_ms=5000 prior to cutover",
        episode_id="ep_deadlock_fail_101",
    )
    assert gr["guardrail_id"].startswith("gr_")
    assert gr["episode_id"] == "ep_deadlock_fail_101"

    # 4. Verify [:TRIGGERED_BY] graph edge exists
    edge_res = falkor_router.query(
        "MATCH (g:Guardrail)-[:TRIGGERED_BY]->(ep:Episode) RETURN g.id, ep.id",
        tenant_id=tenant,
    )
    assert edge_res and len(edge_res.result_set) == 1
    assert edge_res.result_set[0][0] == gr["guardrail_id"]
    assert edge_res.result_set[0][1] == "ep_deadlock_fail_101"


def test_procedural_retrieval_with_guardrails(ensure_falkor):
    """TEST-PROC-RETRIEVE-03: Verifies retrieve_procedure fetches procedure DAG and active guardrails."""
    tenant = "test-proc-retrieve-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_live_cutover", step_order=1, tool_name="execute_cutover")
    procedural_memory.register_procedure(
        tenant_id=tenant,
        name="Database_Migration",
        trigger_description="Database migration cutover",
        steps=[step],
    )

    procedural_memory.attach_guardrail(
        tenant_id=tenant,
        step_id="step_live_cutover",
        rule_text="Pre-check connection pool health",
        error_signature="pool exhausted",
        fix_instruction="Drain idle connections",
    )

    proc = procedural_memory.retrieve_procedure(
        tenant_id=tenant,
        procedure_name="Database_Migration",
        intent="migration cutover",
    )
    assert proc is not None
    assert proc["procedure"]["name"] == "Database_Migration"
    assert len(proc["steps"]) == 1
    assert len(proc["guardrails"]) == 1
    assert proc["guardrails"][0]["error_signature"] == "pool exhausted"


def test_reflexion_guardrail_compiler(ensure_falkor):
    """TEST-PROC-REFL-04: Verifies compile_guardrail_from_failure compiles failure trace into preventive guardrail."""
    tenant = "test-proc-refl-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_redis_flush", step_order=1, tool_name="flush_cache")
    procedural_memory.register_procedure(
        tenant_id=tenant,
        name="Cache_Invalidation",
        trigger_description="Flush cache",
        steps=[step],
    )

    res = procedural_memory.compile_guardrail_from_failure(
        tenant_id=tenant,
        step_id="step_redis_flush",
        error_signature="OOM during BGSAVE",
        rule_text="Verify available swap memory before cache flush",
        fix_instruction="Ensure free memory > 2GB before issuing BGSAVE",
    )
    assert res["rule_text"] == "Verify available swap memory before cache flush"

    proc = procedural_memory.retrieve_procedure(tenant, "Cache_Invalidation")
    assert len(proc["guardrails"]) == 1
    assert proc["guardrails"][0]["error_signature"] == "OOM during BGSAVE"


def test_procedure_outcome_recording(ensure_falkor):
    """TEST-PROC-OUTCOME-05: Verifies recording success and failure outcomes on Procedure nodes."""
    tenant = "test-proc-outcome-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_single", step_order=1, tool_name="noop")
    procedural_memory.register_procedure(tenant, "Simple_Proc", "trigger", [step])

    ok1 = procedural_memory.record_procedure_outcome(tenant, "Simple_Proc", success=True)
    assert ok1 is True
    ok2 = procedural_memory.record_procedure_outcome(tenant, "Simple_Proc", success=False)
    assert ok2 is True

    res = falkor_router.query(
        "MATCH (p:Procedure {name: 'Simple_Proc'}) RETURN p.success_count, p.fail_count",
        tenant_id=tenant,
    )
    assert res and res.result_set
    assert res.result_set[0][0] == 1
    assert res.result_set[0][1] == 1
