"""Comprehensive unit and integration tests for Dynamic Importance Scoring and MemRL/vCache Feedback."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.memory.importance import ImportanceScorer, importance_scorer
from app.memory.episodic import episodic_memory
from app.memory.working import working_memory, SubTaskSpec
from app.core.falkor_client import falkor_router


client = TestClient(app)


# ==========================================
# 1. Stage 1 Heuristics & Word-Boundary Tests
# ==========================================


def test_stage1_critical_error_heuristics():
    """Verifies that critical error signatures score >= 0.85 via Stage 1."""
    scorer = ImportanceScorer()

    # Text pattern errors
    res1 = scorer.evaluate("Fatal traceback: connection reset by peer in postgresql driver")
    assert res1["score"] >= 0.85
    assert res1["stage"] == "STAGE_1_HEURISTIC"

    res2 = scorer.evaluate("Unhandled exception: out of memory deadlock detected")
    assert res2["score"] >= 0.85

    # Status errors
    res3 = scorer.evaluate("Task execution failed", status="ERROR")
    assert res3["score"] == 0.92
    assert res3["stage"] == "STAGE_1_HEURISTIC"

    # Warning status
    res4 = scorer.evaluate("High memory pressure detected", status="WARNING")
    assert res4["score"] == 0.75

    # Structured payload errors
    res5 = scorer.evaluate(
        "Tool executed",
        structured_payload={"status": "FAILURE", "error": "ERR_NO_WAL_CHECKPOINT"},
    )
    assert res5["score"] >= 0.88


def test_stage1_devops_mutation_heuristics():
    """Verifies that DevOps and architecture mutations score >= 0.80."""
    scorer = ImportanceScorer()

    res1 = scorer.evaluate("Migrated PostgreSQL database to FalkorDB successfully")
    assert res1["score"] >= 0.80
    assert res1["stage"] == "STAGE_1_HEURISTIC"

    res2 = scorer.evaluate("Rolled back schema migration due to constraint conflict")
    assert res2["score"] >= 0.80

    res3 = scorer.evaluate("Compiled new guardrail into Procedural Memory")
    assert res3["score"] >= 0.80


def test_stage1_trivial_greetings_and_boundary_safeguards():
    """Verifies that standalone greetings score <= 0.25 without corrupting token/rollback/architecture."""
    scorer = ImportanceScorer()

    # Pure greetings should score 0.15
    greetings = [
        "hello",
        "Hi!",
        "hey",
        "thanks",
        "thank you",
        "ok",
        "OKAY",
        "ack",
        "acknowledged",
        "good morning",
        "got it",
        "cool",
        "done",
    ]
    for g in greetings:
        res = scorer.evaluate(g)
        assert res["score"] <= 0.25, f"Expected greeting score <= 0.25 for '{g}', got {res['score']}"
        assert res["stage"] == "STAGE_1_HEURISTIC"

    # Crucial Word-Boundary Safeguards:
    # 'ok' must NEVER match 'token'
    res_token = scorer.evaluate("Please refresh the authentication token for user")
    assert res_token["score"] > 0.25
    assert "token" not in res_token.get("reason", "").lower() or res_token["stage"] != "STAGE_1_HEURISTIC" or res_token["score"] >= 0.40

    # 'ack' must NEVER match 'rollback'
    res_rollback = scorer.evaluate("Triggering rollback of active transaction")
    assert res_rollback["score"] >= 0.80  # DevOps mutation pattern

    # 'hi' must NEVER match 'architecture'
    res_arch = scorer.evaluate("Reviewing architecture topology and schema design")
    assert res_arch["score"] >= 0.45


def test_stage2_reflection_and_entropy_fallback():
    """Verifies Stage 2 evaluation on ambiguous turns."""
    scorer = ImportanceScorer()
    # Ambiguous informational statement
    res = scorer.evaluate("The worker daemon processed 42 event batches in queue.")
    assert 0.05 <= res["score"] <= 1.0
    assert res["stage"] in ("STAGE_2_LLM_REFLECTION", "STAGE_2_ENTROPY_FALLBACK")

    # Direct entropy testing
    score_low = scorer._compute_entropy_heuristic("a a a a a", role="user")
    score_high = scorer._compute_entropy_heuristic(
        "Distributed consensus protocol synchronizing multi-region partitions",
        role="agent",
    )
    assert score_high > score_low


# ==========================================
# 2. Live FalkorDB Auto-Scoring & Feedback Tests
# ==========================================


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live scoring and feedback tests.")


def test_live_episode_auto_scoring(check_falkor):
    """Verifies that record_episode auto-calculates importance when omitted."""
    tenant = "test-importance-auto-tenant"
    session_id = "sess_auto_score_01"
    graph = falkor_router.get_graph(tenant)
    graph.delete()

    # Episode 1: Critical error turn without explicit score
    ep_err = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        content="Fatal exception occurred: database connection refused",
    )
    assert ep_err["importance_score"] >= 0.85
    assert ep_err["utility_score"] == ep_err["importance_score"]

    # Episode 2: Trivial greeting without explicit score
    ep_greet = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        content="hello",
    )
    assert ep_greet["importance_score"] <= 0.25
    assert ep_greet["utility_score"] == ep_greet["importance_score"]


def test_live_episode_feedback_memrl_and_vcache(check_falkor):
    """Verifies online reward feedback, MemRL Q-update, vCache threshold shift, and clamps."""
    tenant = "test-feedback-memrl-tenant"
    session_id = "sess_feedback_01"
    graph = falkor_router.get_graph(tenant)
    graph.delete()

    # Create base episode with known utility 0.50 and threshold 0.78
    ep = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        content="Standard query executed",
        importance_score=0.50,
        utility_score=0.50,
        vcache_threshold=0.78,
    )
    ep_id = ep["id"]

    # 1. Positive feedback (+1.0) with alpha=0.2
    # Expected utility: 0.50 + 0.2 * (1.0 - 0.50) = 0.60
    # Expected threshold: 0.78 - 0.02 = 0.76
    fb1 = episodic_memory.update_episode_feedback(
        tenant_id=tenant,
        episode_id=ep_id,
        reward=1.0,
        alpha=0.2,
    )
    assert fb1["status"] == "SUCCESS"
    assert fb1["episode_id"] == ep_id
    assert abs(fb1["new_utility"] - 0.60) < 0.01
    assert abs(fb1["new_threshold"] - 0.76) < 0.01
    assert fb1["access_count"] == 1

    # 2. Negative feedback (-1.0) with alpha=0.2
    # Expected utility: 0.60 + 0.2 * (-1.0 - 0.60) = 0.28
    # Expected threshold: 0.76 + 0.05 = 0.81
    fb2 = episodic_memory.update_episode_feedback(
        tenant_id=tenant,
        episode_id=ep_id,
        reward=-1.0,
        alpha=0.2,
    )
    assert fb2["status"] == "SUCCESS"
    assert abs(fb2["new_utility"] - 0.28) < 0.01
    assert abs(fb2["new_threshold"] - 0.81) < 0.01
    assert fb2["access_count"] == 2

    # 3. Test Clamp at lower bound (0.05) under repeated negative rewards
    for _ in range(10):
        episodic_memory.update_episode_feedback(
            tenant_id=tenant,
            episode_id=ep_id,
            reward=-1.0,
            alpha=0.5,
        )

    # Verify clamp prevents drop below 0.05 and threshold doesn't exceed 0.98
    res = graph.query(
        "MATCH (ep:Episode {id: $id}) RETURN ep.utility_score, ep.vcache_threshold",
        {"id": ep_id},
    )
    assert res.result_set[0][0] >= 0.05
    assert res.result_set[0][1] <= 0.98

    # 4. Test Clamp at upper bound (1.00) under repeated positive rewards
    for _ in range(15):
        episodic_memory.update_episode_feedback(
            tenant_id=tenant,
            episode_id=ep_id,
            reward=1.0,
            alpha=0.5,
        )

    res_upper = graph.query(
        "MATCH (ep:Episode {id: $id}) RETURN ep.utility_score, ep.vcache_threshold",
        {"id": ep_id},
    )
    assert res_upper.result_set[0][0] <= 1.00
    assert res_upper.result_set[0][1] >= 0.50


def test_live_working_memory_pinned_context_reinforcement(check_falkor):
    """Verifies that completing a subtask with reward updates pinned context memory nodes."""
    tenant = "test-pinned-reinforce-tenant"
    task_id = "task_pin_01"
    graph = falkor_router.get_graph(tenant)
    graph.delete()

    # Create an episode to be pinned
    ep = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id="sess_pin_01",
        content="Configuration context",
        importance_score=0.50,
        utility_score=0.50,
    )
    ep_id = ep["id"]

    # Initialize subtask and claim it
    subtask = SubTaskSpec(id="st_pin_01", title="Verify config", description="Check settings")
    working_memory.initialize_task_dag(tenant, goal="Configure cluster", subtasks=[subtask], task_id=task_id)
    working_memory.claim_next_subtask(tenant, task_id=task_id, agent_id="WorkerAgent")

    # Pin context to the episode
    working_memory.pin_context(tenant, subtask_id="st_pin_01", target_id=ep_id, reason="Requires config")

    # Complete subtask with positive reward
    success = working_memory.complete_subtask(
        tenant_id=tenant,
        subtask_id="st_pin_01",
        agent_id="WorkerAgent",
        result_summary="Config validated",
        reward=1.0,
        alpha=0.2,
    )
    assert success is True

    # Pinned episode utility should have updated from 0.50 to 0.60
    res = graph.query("MATCH (ep:Episode {id: $id}) RETURN ep.utility_score, ep.access_count", {"id": ep_id})
    assert abs(res.result_set[0][0] - 0.60) < 0.01
    assert res.result_set[0][1] == 1


# ==========================================
# 3. REST API Endpoint Tests
# ==========================================


def test_api_importance_evaluate():
    """Verifies POST /api/v1/memory/importance/evaluate."""
    # Heuristic test
    resp1 = client.post(
        "/api/v1/memory/importance/evaluate",
        json={"content": "Fatal memory corruption panic"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["score"] >= 0.85
    assert data1["stage"] == "STAGE_1_HEURISTIC"

    # Greeting test
    resp2 = client.post(
        "/api/v1/memory/importance/evaluate",
        json={"content": "thanks"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["score"] <= 0.25


def test_api_episode_feedback(check_falkor):
    """Verifies POST /api/v1/memory/episode/feedback endpoint."""
    tenant = "test-api-feedback-tenant"
    graph = falkor_router.get_graph(tenant)
    graph.delete()

    # Create episode via API without importance_score (auto-scoring test)
    create_resp = client.post(
        "/api/v1/memory/episode",
        json={
            "tenant_id": tenant,
            "session_id": "sess_api_fb",
            "content": "Fatal server crash reported",
        },
    )
    assert create_resp.status_code == 200
    ep_data = create_resp.json()
    assert ep_data["importance_score"] >= 0.85
    ep_id = ep_data["id"]

    # Send feedback via API
    fb_resp = client.post(
        "/api/v1/memory/episode/feedback",
        json={
            "tenant_id": tenant,
            "episode_id": ep_id,
            "reward": 1.0,
            "alpha": 0.2,
        },
    )
    assert fb_resp.status_code == 200
    fb_data = fb_resp.json()
    assert fb_data["status"] == "SUCCESS"
    assert fb_data["new_utility"] > 0.85
