"""Comprehensive tests for the Cognitive Agent Engine and FalkorDB 4-tier memory integration."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.falkor_client import falkor_router
from app.main import app
from app.agents.orchestrator import multi_agent_engine, CognitiveAgentEngine


@pytest.fixture
def test_tenant() -> str:
    """Provides a fresh isolated tenant graph for each test."""
    t_id = f"test_cog_{uuid.uuid4().hex[:8]}"
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
async def test_cognitive_agent_answers_user_query_stream(test_tenant):
    """Verifies that the cognitive agent streams events and answers general user queries."""
    t_id = test_tenant
    session_id = f"sess_{uuid.uuid4().hex[:6]}"
    user_prompt = "What database technologies are recommended for low-latency cognitive graph memory?"

    events = []
    async for event in multi_agent_engine.execute_task_stream(
        tenant_id=t_id,
        session_id=session_id,
        user_prompt=user_prompt,
    ):
        events.append(event)

    event_types = [e.get("type") for e in events]
    assert "agent_event" in event_types
    assert "blackboard_event" in event_types
    assert "episodic_retrieval_event" in event_types
    assert "hipporag_event" in event_types
    assert "agent_answer" in event_types
    assert "task_completed" in event_types

    # Invariant: agent answer is generated and not empty
    answer_ev = next(e for e in events if e.get("type") == "agent_answer")
    assert len(answer_ev.get("answer", "").strip()) > 0

    # Invariant: episodic turn recorded in FalkorDB
    ep_check = falkor_router.query(
        "MATCH (ep:Episode {role: 'user'}) RETURN count(ep)",
        tenant_id=t_id,
    )
    assert ep_check and ep_check.result_set[0][0] >= 1


@pytest.mark.asyncio
async def test_cognitive_agent_error_when_model_unavailable(test_tenant, monkeypatch):
    """Enforces requirement: 'if model is not available, return an error. no fake answers'."""
    t_id = test_tenant
    session_id = f"sess_{uuid.uuid4().hex[:6]}"

    engine = CognitiveAgentEngine()
    # Force _get_llm to return None (model unavailable)
    monkeypatch.setattr(engine, "_get_llm", lambda: None)

    events = []
    async for event in engine.execute_task_stream(
        tenant_id=t_id,
        session_id=session_id,
        user_prompt="Explain the architecture of our payment system.",
    ):
        events.append(event)

    # Invariant: An error event is emitted and NO fake answers are generated
    event_types = [e.get("type") for e in events]
    assert "error" in event_types
    assert "agent_answer" not in event_types
    assert "task_completed" not in event_types

    err_ev = next(e for e in events if e.get("type") == "error")
    assert "LLM model is not available" in err_ev.get("message", "")
    assert err_ev.get("status") == "ERROR"


def test_cognitive_agent_sync_api_endpoint(client, test_tenant):
    """Verifies POST /api/v1/agents/run with the new cognitive agent."""
    t_id = test_tenant
    res = client.post(
        "/api/v1/agents/run",
        json={
            "tenant_id": t_id,
            "prompt": "Summarize the primary components of our infrastructure.",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUCCESS"
    assert "answer" in data
    assert data["answer"] is not None
    assert len(data["answer"]) > 0
    assert len(data["events"]) >= 6
