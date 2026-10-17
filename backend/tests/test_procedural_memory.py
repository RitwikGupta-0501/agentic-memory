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
    """TEST-PROC-OUTCOME-05: Verifies recording success and failure outcomes, Bayesian rate, and MemRL utility score."""
    tenant = "test-proc-outcome-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_single", step_order=1, tool_name="noop")
    procedural_memory.register_procedure(tenant, "Simple_Proc", "trigger", [step])

    res1 = procedural_memory.record_procedure_outcome(tenant, "Simple_Proc", success=True)
    assert res1["success"] is True
    assert res1["success_count"] == 1
    assert res1["fail_count"] == 0
    assert res1["bayesian_success_rate"] == 0.667
    assert res1["utility_score"] == 0.6

    res2 = procedural_memory.record_procedure_outcome(tenant, "Simple_Proc", success=False)
    assert res2["success"] is True
    assert res2["success_count"] == 1
    assert res2["fail_count"] == 1
    assert res2["bayesian_success_rate"] == 0.5
    assert res2["utility_score"] == 0.48

    res = falkor_router.query(
        "MATCH (p:Procedure {name: 'Simple_Proc'}) RETURN p.success_count, p.fail_count, p.bayesian_success_rate, p.utility_score",
        tenant_id=tenant,
    )
    assert res and res.result_set
    assert res.result_set[0][0] == 1
    assert res.result_set[0][1] == 1
    assert res.result_set[0][2] == 0.5
    assert res.result_set[0][3] == 0.48


def test_procedural_retrieval_grouping_and_step_ordering(ensure_falkor):
    """TEST-PROC-AUDIT-01: Verifies retrieval returns single aggregated row with correctly ordered steps and no proc in steps."""
    tenant = "test-proc-audit-grouping"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    steps = [
        ActionStepSpec(id="step_audit_1", step_order=1, tool_name="tool_1"),
        ActionStepSpec(id="step_audit_2", step_order=2, tool_name="tool_2"),
        ActionStepSpec(id="step_audit_3", step_order=3, tool_name="tool_3"),
    ]
    procedural_memory.register_procedure(tenant, "Multi_Step_Proc", "Multi-step workflow", steps)

    procedural_memory.attach_guardrail(
        tenant_id=tenant,
        step_id="step_audit_2",
        rule_text="Step 2 guardrail",
        error_signature="ERR_STEP_2",
        fix_instruction="Fix step 2",
    )

    proc_data = procedural_memory.retrieve_procedure(tenant, "Multi_Step_Proc")
    assert proc_data is not None
    assert proc_data["procedure"]["name"] == "Multi_Step_Proc"

    # Invariant 1: Steps count is exactly 3 and in order 1, 2, 3
    assert len(proc_data["steps"]) == 3
    orders = [s["step_order"] for s in proc_data["steps"]]
    assert orders == [1, 2, 3]

    # Invariant 2: Procedure is not mixed into steps
    step_ids = [s["id"] for s in proc_data["steps"]]
    assert proc_data["procedure"]["id"] not in step_ids
    assert step_ids == ["step_audit_1", "step_audit_2", "step_audit_3"]

    # Invariant 3: Guardrail collected correctly
    assert len(proc_data["guardrails"]) == 1
    assert proc_data["guardrails"][0]["error_signature"] == "ERR_STEP_2"


def test_case_insensitive_and_fuzzy_intent_retrieval(ensure_falkor):
    """TEST-PROC-AUDIT-02: Verifies case-insensitive name matching and trigger_description intent retrieval."""
    tenant = "test-proc-audit-intent"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_mig_1", step_order=1, tool_name="migrate")
    procedural_memory.register_procedure(
        tenant_id=tenant,
        name="Database_Migration",
        trigger_description="Automated database migration and cutover",
        steps=[step],
    )

    # 1. Exact match
    p1 = procedural_memory.retrieve_procedure(tenant, "Database_Migration")
    assert p1 is not None and p1["procedure"]["name"] == "Database_Migration"

    # 2. Case-insensitive name match
    p2 = procedural_memory.retrieve_procedure(tenant, "database_migration")
    assert p2 is not None and p2["procedure"]["name"] == "Database_Migration"

    # 3. Intent match on trigger_description (case-insensitive substring)
    p3 = procedural_memory.retrieve_procedure(tenant, "Unknown_Name", intent="cutover")
    assert p3 is not None and p3["procedure"]["name"] == "Database_Migration"


def test_guardrail_natural_key_idempotency(ensure_falkor):
    """TEST-PROC-AUDIT-04: Verifies repeated failures merge on error_signature without duplicate Guardrail nodes."""
    tenant = "test-proc-audit-idempotency"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_idem_1", step_order=1, tool_name="idem_tool")
    procedural_memory.register_procedure(tenant, "Idem_Proc", "test idempotency", [step])

    # Attach guardrail for the first time
    gr1 = procedural_memory.attach_guardrail(
        tenant_id=tenant,
        step_id="step_idem_1",
        rule_text="Enforce flag=True",
        error_signature="ERR_FLAG_MISSING",
        fix_instruction="Set flag=True",
    )

    # Attach guardrail second time with identical error_signature but different rule wording
    gr2 = procedural_memory.attach_guardrail(
        tenant_id=tenant,
        step_id="step_idem_1",
        rule_text="Always enforce flag=True updated",
        error_signature="ERR_FLAG_MISSING",
        fix_instruction="Set flag=True updated",
    )

    # Invariant: Guardrail ID is preserved and exactly 1 Guardrail node exists
    assert gr1["guardrail_id"] == gr2["guardrail_id"]

    count_res = falkor_router.query(
        "MATCH (g:Guardrail {error_signature: 'ERR_FLAG_MISSING'}) RETURN count(g), g.hit_count",
        tenant_id=tenant,
    )
    assert count_res and count_res.result_set
    assert count_res.result_set[0][0] == 1  # Exactly 1 node
    assert count_res.result_set[0][1] == 2  # Hit count incremented to 2


def test_guardrail_reset_functionality(ensure_falkor):
    """TEST-PROC-AUDIT-05: Verifies reset_guardrails deletes guardrails for judge repeatability."""
    tenant = "test-proc-audit-reset"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    step = ActionStepSpec(id="step_reset_1", step_order=1, tool_name="tool_reset")
    procedural_memory.register_procedure(tenant, "Reset_Proc", "trigger", [step])

    procedural_memory.attach_guardrail(
        tenant_id=tenant,
        step_id="step_reset_1",
        rule_text="Rule 1",
        error_signature="ERR_RESET_1",
        fix_instruction="Fix 1",
    )

    # Verify 1 guardrail exists
    proc_before = procedural_memory.retrieve_procedure(tenant, "Reset_Proc")
    assert len(proc_before["guardrails"]) == 1

    # Reset guardrails
    deleted = procedural_memory.reset_guardrails(tenant)
    assert deleted == 1

    # Verify 0 guardrails exist
    proc_after = procedural_memory.retrieve_procedure(tenant, "Reset_Proc")
    assert len(proc_after["guardrails"]) == 0

