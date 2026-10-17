"""End-to-End tests for Wave 4: Multi-Agent Reflexion Loop & Working/Procedural REST APIs."""

import asyncio
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.falkor_client import falkor_router
from app.main import app
from app.memory.episodic import episodic_memory
from app.memory.working import working_memory, SubTaskSpec
from app.memory.procedural import procedural_memory, ActionStepSpec
from app.agents.orchestrator import multi_agent_engine


@pytest.fixture
def test_tenant() -> str:
    """Provides a fresh isolated tenant graph for each test."""
    t_id = f"test_refl_{uuid.uuid4().hex[:8]}"
    yield t_id
    try:
        falkor_router.get_client().select_graph(
            falkor_router.get_graph_key(tenant_id=t_id, shared=True)
        ).delete()
    except Exception:
        pass


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_orchestrator_reflexion_self_correction_two_turns(test_tenant):
    """TEST-ORCH-REFL-01: Verifies multi-agent Reflexion loop across two successive turns.

    Turn 1: Tool failure -> logs error episode -> compiles guardrail with [:TRIGGERED_BY] -> retries and succeeds.
    Turn 2: Detects pre-existing guardrail -> enforces WAL checkpoint on first attempt without error.
    """
    t_id = test_tenant
    session_id = f"sess_{uuid.uuid4().hex[:6]}"

    # Turn 1: Initial run without guardrails
    turn1_events = []
    async for event in multi_agent_engine.execute_task_stream(
        tenant_id=t_id,
        session_id=session_id,
        user_prompt="Migrate legacy PostgreSQL database to high-throughput FalkorDB cluster.",
    ):
        turn1_events.append(event)

    turn1_types = [e.get("type") for e in turn1_events]
    assert "agent_event" in turn1_types
    assert "blackboard_event" in turn1_types
    assert "reflexion_event" in turn1_types
    assert "task_completed" in turn1_types

    # Verify Reflexion event details in Turn 1
    refl_ev = next(e for e in turn1_events if e.get("type") == "reflexion_event")
    assert "ERR_NO_WAL_CHECKPOINT" in refl_ev.get("message", "")

    # Invariant: Provenance link (g:Guardrail)-[:TRIGGERED_BY]->(ep:Episode) exists in FalkorDB
    prov_q = """
    MATCH (g:Guardrail)-[:TRIGGERED_BY]->(ep:Episode)
    RETURN g.error_signature AS sig, g.rule_text AS rule, ep.role AS role, ep.importance_score AS importance
    """
    prov_res = falkor_router.query(prov_q, tenant_id=t_id)
    assert prov_res and len(prov_res.result_set) >= 1
    row = prov_res.result_set[0]
    assert row[0] == "ERR_NO_WAL_CHECKPOINT"
    assert "wal" in row[1].lower()
    assert row[2] == "tool"
    assert row[3] >= 0.85

    # Verify procedure outcome counts after Turn 1
    proc_check = procedural_memory.retrieve_procedure(
        tenant_id=t_id,
        procedure_name="Database_Migration",
    )
    assert proc_check is not None
    assert proc_check["procedure"]["fail_count"] >= 1
    assert proc_check["procedure"]["success_count"] >= 1
    assert len(proc_check["guardrails"]) >= 1

    # Turn 2: Secondary execution on the same tenant graph
    turn2_events = []
    async for event in multi_agent_engine.execute_task_stream(
        tenant_id=t_id,
        session_id=session_id,
        user_prompt="Execute secondary database migration verification and cutover.",
    ):
        turn2_events.append(event)

    turn2_types = [e.get("type") for e in turn2_events]
    # Invariant: Guardrail hit event emitted on first attempt
    assert "procedural_event" in turn2_types
    proc_ev = next(e for e in turn2_events if e.get("type") == "procedural_event")
    assert proc_ev.get("phase") == "guardrail_hit"
    assert "WAL checkpoint flag on first attempt" in proc_ev.get("message", "")

    # Invariant: Turn 2 NEVER triggered a reflexion failure or retry
    assert "reflexion_event" not in turn2_types

    # Invariant: Turn 2 incremented procedure success count again
    proc_after = procedural_memory.retrieve_procedure(
        tenant_id=t_id,
        procedure_name="Database_Migration",
    )
    assert proc_after["procedure"]["success_count"] >= 2


def test_api_working_and_procedural_endpoints(client, test_tenant):
    """TEST-API-WORK-PROC-02: Validates all REST endpoints for Working & Procedural Memory."""
    t_id = test_tenant

    # ==========================
    # Working Memory REST Tests
    # ==========================
    dag_payload = {
        "tenant_id": t_id,
        "goal": "E-Commerce Microservice Deployment",
        "subtasks": [
            {
                "id": f"{t_id}_st1",
                "title": "Validate Kubernetes manifests",
                "description": "Run kubeval on ingress and deployments",
                "depends_on": [],
            },
            {
                "id": f"{t_id}_st2",
                "title": "Deploy canary pod",
                "description": "Deploy to canary namespace",
                "depends_on": [f"{t_id}_st1"],
            },
        ],
    }
    # 1. POST /working/dag
    dag_res = client.post("/api/v1/memory/working/dag", json=dag_payload)
    assert dag_res.status_code == 200
    dag_data = dag_res.json()
    assert dag_data["status"] == "SUCCESS"
    task_id = dag_data["task_id"]

    # 2. GET /working/task/{task_id}
    status_res = client.get(f"/api/v1/memory/working/task/{task_id}?tenant_id={t_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["task"]["task_id"] == task_id
    assert status_data["task"]["subtask_count"] == 2

    # 3. POST /working/claim (Agent A claims st1)
    claim_res = client.post(
        "/api/v1/memory/working/claim",
        json={"tenant_id": t_id, "task_id": task_id, "agent_id": "Agent_Infra"},
    )
    assert claim_res.status_code == 200
    claim_data = claim_res.json()
    assert claim_data["status"] == "SUCCESS"
    assert claim_data["subtask"]["id"] == f"{t_id}_st1"

    # Invariant: Agent B tries to claim while st1 is IN_PROGRESS -> blocked
    claim_block_res = client.post(
        "/api/v1/memory/working/claim",
        json={"tenant_id": t_id, "task_id": task_id, "agent_id": "Agent_Deploy"},
    )
    assert claim_block_res.status_code == 200
    assert claim_block_res.json()["status"] == "NO_ELIGIBLE_SUBTASK"

    # 4. POST /working/pin (Attach context to st1)
    pin_res = client.post(
        "/api/v1/memory/working/pin",
        json={
            "tenant_id": t_id,
            "subtask_id": f"{t_id}_st1",
            "target_id": "K8s_Cluster_Prod",
            "reason": "Cluster environment target",
        },
    )
    assert pin_res.status_code == 200
    assert pin_res.json()["status"] == "SUCCESS"

    # 5. POST /working/complete (Complete st1 with reward)
    comp_res = client.post(
        "/api/v1/memory/working/complete",
        json={
            "tenant_id": t_id,
            "subtask_id": f"{t_id}_st1",
            "agent_id": "Agent_Infra",
            "result_summary": "Manifests validated successfully.",
            "reward": 1.0,
        },
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "SUCCESS"

    # 6. POST /working/claim (Agent B now claims st2 since st1 completed)
    claim_st2_res = client.post(
        "/api/v1/memory/working/claim",
        json={"tenant_id": t_id, "task_id": task_id, "agent_id": "Agent_Deploy"},
    )
    assert claim_st2_res.status_code == 200
    assert claim_st2_res.json()["status"] == "SUCCESS"
    assert claim_st2_res.json()["subtask"]["id"] == f"{t_id}_st2"

    # 7. POST /working/fail (Agent B fails st2)
    fail_res = client.post(
        "/api/v1/memory/working/fail",
        json={
            "tenant_id": t_id,
            "subtask_id": f"{t_id}_st2",
            "agent_id": "Agent_Deploy",
            "error_message": "ImagePullBackOff on canary registry",
        },
    )
    assert fail_res.status_code == 200
    assert fail_res.json()["status"] == "SUCCESS"

    # ============================
    # Procedural Memory REST Tests
    # ============================
    proc_payload = {
        "tenant_id": t_id,
        "name": "Canary_Rollout_Procedure",
        "trigger_description": "Standard canary rollout workflow",
        "steps": [
            {"id": f"{t_id}_pstep1", "step_order": 1, "tool_name": "check_cluster_capacity"},
            {"id": f"{t_id}_pstep2", "step_order": 2, "tool_name": "deploy_canary_slice"},
            {"id": f"{t_id}_pstep3", "step_order": 3, "tool_name": "monitor_sli_metrics"},
        ],
    }
    # 8. POST /procedural/register
    reg_res = client.post("/api/v1/memory/procedural/register", json=proc_payload)
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert reg_data["status"] == "SUCCESS"
    assert reg_data["procedure"]["name"] == "Canary_Rollout_Procedure"
    assert reg_data["procedure"]["steps_count"] == 3

    # 9. POST /procedural/retrieve
    ret_res = client.post(
        "/api/v1/memory/procedural/retrieve",
        json={"tenant_id": t_id, "procedure_name": "Canary_Rollout_Procedure"},
    )
    assert ret_res.status_code == 200
    ret_data = ret_res.json()
    assert ret_data["status"] == "SUCCESS"
    assert len(ret_data["procedure"]["steps"]) == 3

    # 10. POST /procedural/guardrail
    guard_res = client.post(
        "/api/v1/memory/procedural/guardrail",
        json={
            "tenant_id": t_id,
            "step_id": f"{t_id}_pstep2",
            "rule_text": "Verify image digest matches notarized signature before deploy",
            "error_signature": "ERR_UNVERIFIED_IMAGE_DIGEST",
            "fix_instruction": "Run cosign verify prior to helm apply",
        },
    )
    assert guard_res.status_code == 200
    assert guard_res.json()["status"] == "SUCCESS"

    # 11. POST /procedural/compile-reflexion with Episode link
    # Pre-record an episode to ground the failure
    ep = episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="sess_fail",
        content="Deployment failure: ImagePullBackOff on registry mirror.",
        importance_score=0.92,
    )
    refl_compile_res = client.post(
        "/api/v1/memory/procedural/compile-reflexion",
        json={
            "tenant_id": t_id,
            "step_id": f"{t_id}_pstep2",
            "error_signature": "ERR_REGISTRY_MIRROR_TIMEOUT",
            "rule_text": "Always fallback to upstream registry on mirror timeout",
            "fix_instruction": "Configure multi-registry mirror fallback",
            "episode_id": ep["id"],
        },
    )
    assert refl_compile_res.status_code == 200
    assert refl_compile_res.json()["status"] == "SUCCESS"
    assert refl_compile_res.json()["guardrail"]["episode_id"] == ep["id"]

    # 12. POST /procedural/outcome (Verifies MemRL metrics in response)
    outcome_res = client.post(
        "/api/v1/memory/procedural/outcome",
        json={"tenant_id": t_id, "procedure_name": "Canary_Rollout_Procedure", "success": True},
    )
    assert outcome_res.status_code == 200
    assert outcome_res.json()["status"] == "SUCCESS"
    assert outcome_res.json()["updated"] is True
    assert "result" in outcome_res.json()
    assert outcome_res.json()["result"]["bayesian_success_rate"] == 0.667
    assert outcome_res.json()["result"]["utility_score"] == 0.6

    # 13. POST /procedural/guardrail/reset (and alias /reset-guardrails)
    reset_res = client.post(
        "/api/v1/memory/procedural/guardrail/reset",
        json={"tenant_id": t_id, "procedure_name": "Canary_Rollout_Procedure"},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["status"] == "SUCCESS"
    assert reset_res.json()["deleted_count"] >= 1

    # Invariant: Guardrails cleared
    ret_after_reset = client.post(
        "/api/v1/memory/procedural/retrieve",
        json={"tenant_id": t_id, "procedure_name": "Canary_Rollout_Procedure"},
    )
    assert ret_after_reset.status_code == 200
    assert len(ret_after_reset.json()["procedure"]["guardrails"]) == 0


@pytest.mark.asyncio
async def test_working_memory_concurrent_claims_race_condition(test_tenant):
    """TEST-WORK-PARALLEL-03: Verifies atomic locking prevents double-claims when 10 agents race."""
    t_id = test_tenant
    task_id = f"task_race_{uuid.uuid4().hex[:6]}"

    # Initialize a task with a single pending subtask
    working_memory.initialize_task_dag(
        tenant_id=t_id,
        goal="Atomic Race Condition Benchmark",
        subtasks=[
            SubTaskSpec(
                id=f"{task_id}_st1",
                title="Singleton Task to Claim",
                description="Only one agent must acquire lock.",
                depends_on=[],
            ),
        ],
        task_id=task_id,
    )

    # 10 agents concurrently try to claim the singleton subtask
    async def try_claim(agent_idx: int):
        await asyncio.sleep(0.01)
        return working_memory.claim_next_subtask(
            tenant_id=t_id,
            task_id=task_id,
            agent_id=f"Agent_{agent_idx}",
        )

    results = await asyncio.gather(*[try_claim(i) for i in range(10)])

    # Invariants: Exactly one claim succeeded, 9 failed (returned None)
    successful_claims = [r for r in results if r is not None]
    failed_claims = [r for r in results if r is None]

    assert len(successful_claims) == 1, f"Expected 1 winner, got {len(successful_claims)}"
    assert len(failed_claims) == 9

    winner = successful_claims[0]
    assert winner["id"] == f"{task_id}_st1"
    assert winner["status"] == "IN_PROGRESS"
    assert winner["locked_by"].startswith("Agent_")
