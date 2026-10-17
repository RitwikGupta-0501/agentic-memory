"""Tests for Working Memory task specifications, atomic claims, dependency locking, and MemRL feedback."""

import time
import pytest
from app.core.falkor_client import falkor_router
from app.memory.working import working_memory, SubTaskSpec
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory


@pytest.fixture(scope="module")
def ensure_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live working memory tests.")


def test_subtask_spec_creation():
    """Verifies default initialization and field validation of SubTaskSpec."""
    st = SubTaskSpec(
        title="Check DB",
        description="Verify database configuration",
        depends_on=["st_prev_1"],
    )
    assert st.title == "Check DB"
    assert st.depends_on == ["st_prev_1"]
    assert st.id.startswith("st_")


def test_atomic_claim_dependency_ordering(ensure_falkor):
    """TEST-WORK-DEP-01: Verifies that downstream subtasks cannot be claimed until ALL dependencies are COMPLETED."""
    tenant = "test-working-dep-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    task_id = "task_dep_01"
    st1 = SubTaskSpec(id="st_1", title="Extract Triples", description="Parse text")
    st2 = SubTaskSpec(id="st_2", title="Vector Search", description="Find candidates")
    st3 = SubTaskSpec(id="st_3", title="Merge Context", description="Synthesize", depends_on=["st_1", "st_2"])

    init_res = working_memory.initialize_task_dag(
        tenant_id=tenant,
        goal="Synthesize database migration context",
        subtasks=[st1, st2, st3],
        task_id=task_id,
    )
    assert init_res["subtask_count"] == 3

    # 1. Agent Alpha claims first available
    c1 = working_memory.claim_next_subtask(tenant, task_id, "Agent_Alpha")
    assert c1 is not None
    assert c1["subtask_id"] in ("st_1", "st_2")

    # 2. Agent Beta claims second available
    c2 = working_memory.claim_next_subtask(tenant, task_id, "Agent_Beta")
    assert c2 is not None
    assert c2["subtask_id"] in ("st_1", "st_2")
    assert c2["subtask_id"] != c1["subtask_id"]

    # 3. Agent Gamma attempts to claim -> must be None because st_3 requires BOTH st_1 and st_2 to be COMPLETED
    c3 = working_memory.claim_next_subtask(tenant, task_id, "Agent_Gamma")
    assert c3 is None

    # 4. Agent Alpha completes first subtask
    ok1 = working_memory.complete_subtask(tenant, c1["subtask_id"], "Agent_Alpha", "Done step 1")
    assert ok1 is True

    # 5. Agent Gamma still cannot claim st_3 (since step 2 is still IN_PROGRESS)
    c3_again = working_memory.claim_next_subtask(tenant, task_id, "Agent_Gamma")
    assert c3_again is None

    # 6. Agent Beta completes second subtask
    ok2 = working_memory.complete_subtask(tenant, c2["subtask_id"], "Agent_Beta", "Done step 2")
    assert ok2 is True

    # 7. Now st_3 must be atomically claimable by Agent Gamma
    c3_final = working_memory.claim_next_subtask(tenant, task_id, "Agent_Gamma")
    assert c3_final is not None
    assert c3_final["subtask_id"] == "st_3"
    assert c3_final["locked_by"] == "Agent_Gamma"


def test_subtask_failure_and_cascading_block(ensure_falkor):
    """TEST-WORK-FAIL-02: Verifies that failing a subtask cascades BLOCKED status to all dependents."""
    tenant = "test-working-fail-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    task_id = "task_fail_01"
    st_a = SubTaskSpec(id="st_a", title="Preflight Validation", description="Check access")
    st_b = SubTaskSpec(id="st_b", title="Execute Cutover", description="Run schema migration", depends_on=["st_a"])
    st_c = SubTaskSpec(id="st_c", title="Health Check", description="Verify latency", depends_on=["st_b"])

    working_memory.initialize_task_dag(tenant, "Migrate Prod DB", [st_a, st_b, st_c], task_id=task_id)

    # Claim st_a
    claim = working_memory.claim_next_subtask(tenant, task_id, "Worker_1")
    assert claim["subtask_id"] == "st_a"

    # Worker_1 fails st_a
    fail_res = working_memory.fail_subtask(
        tenant_id=tenant,
        subtask_id="st_a",
        agent_id="Worker_1",
        error_message="Authentication failed: invalid token",
    )
    assert fail_res["status"] == "FAILED"
    assert fail_res["blocked_count"] >= 1

    # Check task DAG status
    status = working_memory.get_task_status(tenant, task_id)
    assert status is not None
    subtask_map = {s["id"]: s for s in status["subtasks"]}
    assert subtask_map["st_a"]["status"] == "FAILED"
    assert subtask_map["st_b"]["status"] == "BLOCKED"

    # No agent can claim anything from this DAG
    assert working_memory.claim_next_subtask(tenant, task_id, "Worker_2") is None


def test_memrl_utility_feedback_on_subtask_completion(ensure_falkor):
    """TEST-WORK-UTIL-03: Verifies that complete_subtask with reward updates utility_score of pinned context."""
    tenant = "test-working-util-tenant"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant)

    task_id = "task_util_01"
    st1 = SubTaskSpec(id="st_u1", title="Triage", description="Find facts")
    working_memory.initialize_task_dag(tenant, "Optimize Memory", [st1], task_id=task_id)

    # Pre-record an episode and entity
    ep = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id="sess_1",
        episode_id="ep_pinned_01",
        content="Critical Redis connection info",
        importance_score=0.50,
        utility_score=0.50,
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=tenant,
        subject="Redis_Service",
        predicate="RUNS_ON",
        new_object="AWS_ECS",
        episode_id="ep_pinned_01",
        cardinality="SINGLE",
        timestamp=1000.0,
        resolve_entities=False,
    )

    # Claim and pin both episode and entity to the subtask
    claim = working_memory.claim_next_subtask(tenant, task_id, "Agent_Triage")
    assert claim["subtask_id"] == "st_u1"

    working_memory.pin_context(tenant, "st_u1", "ep_pinned_01", "Source requirement")
    working_memory.pin_context(tenant, "st_u1", "Redis_Service", "Target service entity")

    # Complete subtask with positive reward 1.0 (alpha=0.2)
    # Expected utility: 0.5 + 0.2 * (1.0 - 0.5) = 0.60
    ok = working_memory.complete_subtask(
        tenant_id=tenant,
        subtask_id="st_u1",
        agent_id="Agent_Triage",
        result_summary="Target service located",
        reward=1.0,
        alpha=0.2,
    )
    assert ok is True

    # Verify episode utility updated
    res = falkor_router.query(
        "MATCH (ep:Episode {id: 'ep_pinned_01'}) RETURN ep.utility_score, ep.access_count",
        tenant_id=tenant,
    )
    assert res and res.result_set
    new_u, acc = res.result_set[0]
    assert 0.59 <= float(new_u) <= 0.61
    assert int(acc) >= 1


def test_multitenant_blackboard_isolation(ensure_falkor):
    """TEST-WORK-ISOL-04: Verifies strict tenant isolation across Working Memory task DAGs."""
    t_alpha = "tenant-wm-alpha"
    t_beta = "tenant-wm-beta"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_alpha)
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_beta)

    st_a = SubTaskSpec(id="st_alpha_1", title="Alpha Task", description="Alpha work")
    st_b = SubTaskSpec(id="st_beta_1", title="Beta Task", description="Beta work")

    working_memory.initialize_task_dag(t_alpha, "Alpha Goal", [st_a], task_id="task_alpha")
    working_memory.initialize_task_dag(t_beta, "Beta Goal", [st_b], task_id="task_beta")

    # Agent in tenant alpha cannot claim from task_beta
    assert working_memory.claim_next_subtask(t_alpha, "task_beta", "Agent_Alpha") is None

    # Agent in tenant beta cannot claim from task_alpha
    assert working_memory.claim_next_subtask(t_beta, "task_alpha", "Agent_Beta") is None

    # Status check is isolated
    status_alpha = working_memory.get_task_status(t_alpha, "task_alpha")
    assert status_alpha is not None
    assert status_alpha["task_id"] == "task_alpha"
    assert len(status_alpha["subtasks"]) == 1
    assert status_alpha["subtasks"][0]["id"] == "st_alpha_1"

    assert working_memory.get_task_status(t_alpha, "task_beta") is None


