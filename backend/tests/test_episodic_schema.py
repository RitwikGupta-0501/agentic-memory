"""Comprehensive unit and integration tests for hardened Episodic Memory Schema and API endpoints."""

import json
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from app.main import app
from app.memory.episodic import EpisodeRecord, episodic_memory
from app.core.falkor_client import falkor_router
from app.core.embeddings import embedding_service


client = TestClient(app)


# ==========================================
# 1. Pydantic Schema Validation Tests
# ==========================================


def test_episode_record_defaults():
    """Verifies default values and field generation in EpisodeRecord."""
    rec = EpisodeRecord(
        session_id="sess_default",
        content="User checked out cart",
    )
    assert rec.id.startswith("ep_")
    assert rec.role == "user"
    assert rec.actor_id == "user"
    assert rec.status == "SUCCESS"
    assert rec.importance_score == 0.5
    assert rec.utility_score == 0.5
    assert rec.vcache_threshold == 0.78
    assert rec.access_count == 0
    assert rec.archived is False
    assert rec.token_count == 0
    assert rec.structured_payload is None


def test_episode_record_payload_serialization():
    """Verifies structured payload can hold rich JSON structures."""
    payload = {
        "event": "refund_issued",
        "amount": 49.99,
        "currency": "USD",
        "tags": ["stripe", "chargeback"],
    }
    rec = EpisodeRecord(
        session_id="sess_payload",
        content="Refund processed",
        role="tool",
        actor_id="stripe_gateway",
        structured_payload=payload,
    )
    assert rec.structured_payload == payload
    dumped = rec.model_dump()
    assert dumped["structured_payload"]["amount"] == 49.99


def test_episode_record_validation_constraints():
    """Verifies that out-of-range values and invalid roles raise validation errors."""
    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", role="hacker")

    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", importance_score=1.5)

    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", importance_score=-0.1)

    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", utility_score=2.0)

    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", vcache_threshold=-0.5)

    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", access_count=-1)

    with pytest.raises(ValidationError):
        EpisodeRecord(session_id="s1", content="Test", token_count=-5)


# ==========================================
# 2. Episodic Memory Manager Live Tests
# ==========================================


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live episodic memory tests.")


def test_live_episode_chaining_and_retrieval(check_falkor):
    """Tests inserting root and chained episodes with auto-vectorization and rich retrieval."""
    tenant = "test-episodic-schema-tenant"
    session_id = "sess_chain_001"
    graph = falkor_router.get_graph(tenant)

    # Clean previous run
    graph.query(
        "MATCH (ep:Episode {session_id: $session_id}) DETACH DELETE ep",
        {"session_id": session_id},
    )

    # 1. Insert Root Episode
    ep1 = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        content="User initiated refund request for transaction tx_9988",
        role="user",
        actor_id="customer_service",
        importance_score=0.8,
        structured_payload={"tx_id": "tx_9988", "reason": "duplicate"},
    )
    assert ep1["id"].startswith("ep_")
    assert ep1["role"] == "user"
    assert ep1["importance_score"] == 0.8
    assert ep1["utility_score"] == 0.8  # inherits importance_score if utility_score not explicitly given
    assert ep1["token_count"] > 0
    assert ep1["embedding_model"] is not None
    assert ep1["embedding_dim"] is not None
    assert len(ep1["embedding"]) == ep1["embedding_dim"]
    assert "latency_ms" in ep1

    # 2. Insert Chained Episode
    ep2 = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        content="Payment agent verified duplicate charge and executed refund via Stripe",
        role="agent",
        actor_id="refund_agent",
        status="SUCCESS",
        importance_score=0.9,
        utility_score=0.95,
        vcache_threshold=0.82,
        structured_payload={"gateway": "stripe", "status": "settled"},
    )
    assert ep2["id"].startswith("ep_")
    assert ep2["role"] == "agent"
    assert ep2["utility_score"] == 0.95
    assert ep2["vcache_threshold"] == 0.82

    # 3. Retrieve Session History
    history = episodic_memory.get_session_history(tenant_id=tenant, session_id=session_id)
    assert len(history) == 2
    assert history[0]["id"] == ep1["id"]
    assert history[0]["role"] == "user"
    assert history[0]["structured_payload"] == {"tx_id": "tx_9988", "reason": "duplicate"}
    assert history[1]["id"] == ep2["id"]
    assert history[1]["role"] == "agent"
    assert history[1]["structured_payload"] == {"gateway": "stripe", "status": "settled"}
    assert history[1]["utility_score"] == 0.95

    # 4. Search Episode Candidates via Vector Search (vCache boundary verification)
    search_res = episodic_memory.search_episodes(
        tenant_id=tenant,
        query="Payment agent verified duplicate charge and executed refund via Stripe",
        session_id=session_id,
        candidate_limit=5,
    )
    assert len(search_res) >= 1
    top_result = search_res[0]
    assert "similarity_score" in top_result
    assert top_result["similarity_score"] >= 0.80
    assert top_result["session_id"] == session_id

    # Test filtering out when similarity is below min_similarity
    search_filtered = episodic_memory.search_episodes(
        tenant_id=tenant,
        query="Payment agent verified duplicate charge and executed refund via Stripe",
        session_id=session_id,
        candidate_limit=5,
        min_similarity=1.05,
    )
    assert len(search_filtered) == 0

    # Clean up
    graph.query(
        "MATCH (ep:Episode {session_id: $session_id}) DETACH DELETE ep",
        {"session_id": session_id},
    )


# ==========================================
# 3. Memory API Route Endpoints Tests
# ==========================================


def test_api_embedding_status():
    """Tests GET /api/v1/memory/embedding-status."""
    response = client.get("/api/v1/memory/embedding-status?tenant_id=test-api-tenant")
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "test-api-tenant"
    assert "provider" in data
    assert "model_name" in data["provider"]
    assert "dimension" in data["provider"]
    assert "drift" in data


def test_api_reindex_endpoint(check_falkor):
    """Tests POST /api/v1/memory/reindex."""
    response = client.post(
        "/api/v1/memory/reindex",
        json={"tenant_id": "test-api-tenant", "batch_size": 25},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "summary" in data
    assert data["summary"]["tenant_id"] == "test-api-tenant"


def test_api_episode_create_and_query(check_falkor):
    """Tests POST /api/v1/memory/episode, GET /api/v1/memory/episodes, and POST /api/v1/memory/episodes/search."""
    tenant = "test-api-tenant"
    session_id = "sess_api_test_001"
    graph = falkor_router.get_graph(tenant)
    graph.query(
        "MATCH (ep:Episode {session_id: $session_id}) DETACH DELETE ep",
        {"session_id": session_id},
    )

    # 1. Create episode via API
    create_payload = {
        "tenant_id": tenant,
        "session_id": session_id,
        "content": "Deploying container pod to Kubernetes cluster in production",
        "role": "agent",
        "actor_id": "k8s_deployer",
        "status": "SUCCESS",
        "importance_score": 0.85,
        "utility_score": 0.90,
        "vcache_threshold": 0.75,
        "structured_payload": {"cluster": "prod-us-east", "replicas": 3},
    }
    res_create = client.post("/api/v1/memory/episode", json=create_payload)
    assert res_create.status_code == 200
    created = res_create.json()
    assert created["session_id"] == session_id
    assert created["actor_id"] == "k8s_deployer"
    assert created["token_count"] > 0
    assert created["utility_score"] == 0.90
    assert created["vcache_threshold"] == 0.75

    # 2. Retrieve history via API
    res_get = client.get(f"/api/v1/memory/episodes?tenant_id={tenant}&session_id={session_id}")
    assert res_get.status_code == 200
    episodes = res_get.json()
    assert len(episodes) == 1
    assert episodes[0]["id"] == created["id"]
    assert episodes[0]["actor_id"] == "k8s_deployer"
    assert episodes[0]["structured_payload"] == {"cluster": "prod-us-east", "replicas": 3}

    # 3. Search via API
    search_payload = {
        "tenant_id": tenant,
        "session_id": session_id,
        "query": "Deploying container pod to Kubernetes cluster in production",
        "candidate_limit": 5,
    }
    res_search = client.post("/api/v1/memory/episodes/search", json=search_payload)
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["results_count"] >= 1
    assert search_data["episodes"][0]["id"] == created["id"]

    # Also test search via API with min_similarity filter
    res_filtered = client.post(
        "/api/v1/memory/episodes/search",
        json={
            "tenant_id": tenant,
            "session_id": session_id,
            "query": "Deploying container pod to Kubernetes cluster in production",
            "candidate_limit": 5,
            "min_similarity": 1.05,
        },
    )
    assert res_filtered.status_code == 200
    assert res_filtered.json()["results_count"] == 0

    # Clean up
    graph.query(
        "MATCH (ep:Episode {session_id: $session_id}) DETACH DELETE ep",
        {"session_id": session_id},
    )
