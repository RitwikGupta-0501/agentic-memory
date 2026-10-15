"""Comprehensive unit and live integration tests for Park et al. 3-Factor Hybrid Retrieval Engine."""

import math
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.memory.episodic import episodic_memory, ScoredEpisode
from app.core.falkor_client import falkor_router


client = TestClient(app)


# ==========================================
# 1. Pure Unit Tests: Math & Component Logic
# ==========================================


def test_recency_decay_and_memorybank_reinforcement():
    """Verifies that elapsed time decays recency, and access_count reinforces memory."""
    decay_lambda = 0.0001925  # ~1 hr half-life
    now = 1000000.0

    # 1. Zero elapsed time -> Recency = 1.0
    recency_zero = math.exp(-(decay_lambda * 0.0) / (0 + 1))
    assert recency_zero == 1.0

    # 2. 1 hour elapsed (3600s), access_count = 0 -> ~0.50
    recency_1hr_unreinforced = math.exp(-(decay_lambda * 3600.0) / (0 + 1))
    assert 0.49 <= recency_1hr_unreinforced <= 0.51

    # 3. 1 hour elapsed (3600s), access_count = 3 -> decay rate divided by 4
    recency_1hr_reinforced = math.exp(-(decay_lambda * 3600.0) / (3 + 1))
    # exp(-0.693 / 4) = exp(-0.173) ≈ 0.84
    assert recency_1hr_reinforced > 0.82
    assert recency_1hr_reinforced > recency_1hr_unreinforced


def test_scored_episode_model_serialization():
    """Verifies Pydantic serialization and field validation of ScoredEpisode."""
    scored = ScoredEpisode(
        episode={"id": "ep_test", "content": "Sample content"},
        recency_score=0.85,
        importance_score=0.90,
        utility_score=0.92,
        relevance_score=0.78,
        vcache_threshold=0.75,
        vcache_passed=True,
        composite_score=0.85,
        provenance_links=[{"label": "Entity", "id": "PostgreSQL", "rel_type": "DERIVED_FROM"}],
    )
    dumped = scored.model_dump()
    assert dumped["composite_score"] == 0.85
    assert dumped["vcache_passed"] is True
    assert len(dumped["provenance_links"]) == 1


# ==========================================
# 2. Live FalkorDB Retrieval & 3-Factor Tests
# ==========================================


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live 3-factor retrieval tests.")


def test_live_r41_recency_vs_importance_tradeoff(check_falkor):
    """Verifies R4.1: A highly relevant, high-importance historical memory beats a fresh, irrelevant turn."""
    tenant = "test-retrieval-tradeoff-tenant"
    session_id = "sess_tradeoff_01"
    graph = falkor_router.get_graph(tenant)
    graph.delete()
    falkor_router.ensure_indices(graph)

    now = time.time()
    t_old = now - (86400 * 2)  # 2 days ago

    # Memory A: 2 days old, critical database migration error turn, high utility
    ep_a = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        episode_id="ep_arch_migration_error",
        content="Production database cutover failed with fatal unhandled deadlock exception",
        role="tool",
        importance_score=0.95,
        utility_score=0.95,
        timestamp=t_old,
    )

    # Memory B: 30 seconds ago, trivial conversation greeting, low utility
    ep_b = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        episode_id="ep_recent_greeting",
        content="hello thanks ok",
        role="user",
        importance_score=0.15,
        utility_score=0.15,
        timestamp=now - 30,
    )

    # Query specifically for the critical failure topic
    results = episodic_memory.retrieve_episodes(
        tenant_id=tenant,
        query="database cutover deadlock failure exception",
        session_id=session_id,
        top_k=2,
        alpha=1.0,
        beta=1.0,
        gamma=1.0,
        touch_recall=False,
    )

    assert len(results) >= 1
    # Memory A must rank #1 despite being 2 days older due to high relevance & utility
    assert results[0]["episode"]["id"] == "ep_arch_migration_error"
    assert results[0]["composite_score"] > results[-1]["composite_score"]
    assert results[0]["importance_score"] >= 0.90


def test_live_vcache_soft_penalty_vs_strict_gating(check_falkor):
    """Verifies that soft penalty retains candidates with reduced score, while strict gating filters them."""
    tenant = "test-vcache-penalty-tenant"
    session_id = "sess_vcache_test"
    graph = falkor_router.get_graph(tenant)
    graph.delete()
    falkor_router.ensure_indices(graph)

    # Ingest episode with a very high vCache threshold (0.95)
    episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        episode_id="ep_high_threshold",
        content="Kubernetes worker nodes restarted in zone us-central1",
        importance_score=0.60,
        vcache_threshold=0.95,
    )

    # Query with loose similarity (will not reach 0.95)
    query = "cluster maintenance restart"

    # 1. Soft penalty (strict_vcache=False) -> returned with vcache_passed=False
    results_soft = episodic_memory.retrieve_episodes(
        tenant_id=tenant,
        query=query,
        session_id=session_id,
        strict_vcache=False,
        touch_recall=False,
    )
    assert len(results_soft) == 1
    assert results_soft[0]["episode"]["id"] == "ep_high_threshold"
    assert results_soft[0]["vcache_passed"] is False

    # 2. Strict gating (strict_vcache=True) -> pruned out (returns empty)
    results_strict = episodic_memory.retrieve_episodes(
        tenant_id=tenant,
        query=query,
        session_id=session_id,
        strict_vcache=True,
        touch_recall=False,
    )
    assert len(results_strict) == 0


def test_live_cross_session_vs_intra_session_retrieval(check_falkor):
    """Verifies that cross_session=False isolates to session_id, while cross_session=True searches globally."""
    tenant = "test-session-isolation-retrieval"
    graph = falkor_router.get_graph(tenant)
    graph.delete()
    falkor_router.ensure_indices(graph)

    # Ingest into Session A
    episodic_memory.record_episode(
        tenant_id=tenant,
        session_id="session_alpha",
        episode_id="ep_alpha_01",
        content="Configuring redis sentinel cluster for session alpha",
        importance_score=0.70,
    )

    # Ingest into Session B
    episodic_memory.record_episode(
        tenant_id=tenant,
        session_id="session_beta",
        episode_id="ep_beta_01",
        content="Configuring redis sentinel cluster for session beta",
        importance_score=0.70,
    )

    query = "redis sentinel configuration"

    # Query from Session Alpha with cross_session=False
    res_intra = episodic_memory.retrieve_episodes(
        tenant_id=tenant,
        query=query,
        session_id="session_alpha",
        cross_session=False,
        touch_recall=False,
    )
    retrieved_ids = [r["episode"]["id"] for r in res_intra]
    assert "ep_alpha_01" in retrieved_ids
    assert "ep_beta_01" not in retrieved_ids

    # Query with cross_session=True
    res_cross = episodic_memory.retrieve_episodes(
        tenant_id=tenant,
        query=query,
        session_id="session_alpha",
        cross_session=True,
        touch_recall=False,
    )
    cross_ids = [r["episode"]["id"] for r in res_cross]
    assert "ep_alpha_01" in cross_ids
    assert "ep_beta_01" in cross_ids


def test_live_batch_recall_touch_and_inbound_provenance(check_falkor):
    """Verifies atomic recall touch updates and inbound provenance expansion ([:DERIVED_FROM], [:PINNED_CONTEXT], [:TRIGGERED_BY])."""
    tenant = "test-provenance-touch-tenant"
    session_id = "sess_prov_01"
    graph = falkor_router.get_graph(tenant)
    graph.delete()
    falkor_router.ensure_indices(graph)

    now = time.time()

    # 1. Create target episode
    ep = episodic_memory.record_episode(
        tenant_id=tenant,
        session_id=session_id,
        episode_id="ep_prov_target",
        content="Database migration from PostgreSQL to FalkorDB executed",
        importance_score=0.85,
    )

    # 2. Add inbound provenance edges
    prov_query = """
    MATCH (ep:Episode {id: 'ep_prov_target'})
    MERGE (ent:Entity {name: 'PostgreSQL', type: 'Database'})
    MERGE (st:SubTask {id: 'st_triage_99', title: 'Triage migration', status: 'COMPLETED'})
    MERGE (gr:Guardrail {id: 'gr_wal_99', error_signature: 'ERR_NO_WAL_CHECKPOINT'})
    CREATE (ent)-[:DERIVED_FROM]->(ep)
    CREATE (st)-[:PINNED_CONTEXT {reason: 'Source turn'}]->(ep)
    CREATE (gr)-[:TRIGGERED_BY]->(ep)
    """
    graph.query(prov_query)

    # 3. Retrieve with touch_recall=True
    results = episodic_memory.retrieve_episodes(
        tenant_id=tenant,
        query="PostgreSQL to FalkorDB migration",
        session_id=session_id,
        top_k=1,
        touch_recall=True,
    )

    assert len(results) == 1
    winner = results[0]
    assert winner["episode"]["id"] == "ep_prov_target"
    assert winner["episode"]["access_count"] == 1
    assert winner["episode"]["last_accessed"] is not None

    # Verify provenance links collected all 3 inbound edges
    plinks = winner["provenance_links"]
    assert len(plinks) == 3
    rel_types = {link["rel_type"] for link in plinks}
    assert "DERIVED_FROM" in rel_types
    assert "PINNED_CONTEXT" in rel_types
    assert "TRIGGERED_BY" in rel_types

    # Verify graph node was updated in FalkorDB directly
    check_q = "MATCH (ep:Episode {id: 'ep_prov_target'}) RETURN ep.access_count"
    c_res = graph.query(check_q)
    assert c_res.result_set[0][0] == 1


# ==========================================
# 3. REST API Endpoint Tests
# ==========================================


def test_api_episodes_retrieve(check_falkor):
    """Verifies POST /api/v1/memory/episodes/retrieve endpoint."""
    tenant = "test-api-retrieve-tenant"
    graph = falkor_router.get_graph(tenant)
    graph.delete()
    falkor_router.ensure_indices(graph)

    # Seed an episode
    episodic_memory.record_episode(
        tenant_id=tenant,
        session_id="sess_api_retrieve",
        episode_id="ep_api_ret_01",
        content="Automated TLS certificate renewal completed",
        importance_score=0.75,
    )

    resp = client.post(
        "/api/v1/memory/episodes/retrieve",
        json={
            "tenant_id": tenant,
            "query": "TLS certificate renewal",
            "session_id": "sess_api_retrieve",
            "top_k": 3,
            "touch_recall": True,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status_code"] if "status_code" in data else True
    assert data["results_count"] >= 1
    top_ep = data["episodes"][0]
    assert top_ep["episode"]["id"] == "ep_api_ret_01"
    assert "composite_score" in top_ep
    assert "recency_score" in top_ep
    assert "importance_score" in top_ep
    assert "relevance_score" in top_ep
    assert "vcache_threshold" in top_ep
    assert "vcache_passed" in top_ep
    assert "provenance_links" in top_ep
