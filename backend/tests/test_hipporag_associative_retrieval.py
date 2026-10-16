"""Tests for Semantic Memory Phase 4: HippoRAG Personalized PageRank (PPR) Associative Recall.

Verifies:
- TEST-HIPPORAG-01: Mathematical Proximity Decay (monotonic decay on star/chain topologies without hub penalty)
- TEST-HIPPORAG-02: Stale Fact Pruning / Temporal Gating (superseded relations strictly excluded)
- TEST-HIPPORAG-03: Bipartite Episode Grounding Convergence (obsolete episodes receive zero activation mass)
- TEST-HIPPORAG-04: Hybrid Natural Language Seed Discovery (alias matching and seed extraction)
- TEST-HIPPORAG-05: Time-Travel Associative Recall (exact historical reconstruction at arbitrary epochs)
- TEST-HIPPORAG-06: Cold-Start / Zero-Seed Fallback (disjoint query safely returns NO_SEEDS_FOUND)
- TEST-HIPPORAG-07: REST API Endpoints & Backward Compatibility (query-driven and legacy endpoint support)
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory

client = TestClient(app)


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live HippoRAG tests.")


def test_mathematical_proximity_decay(check_falkor):
    """TEST-HIPPORAG-01: Verifies monotonic decay on multi-hop star/chain topologies without hub penalty."""
    t_id = "test-hipporag-01"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # Pre-record anchor episode
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_arch_init",
        content="Core system architecture established with multi-tier storage.",
        importance_score=0.9,
        timestamp=1000.0,
    )

    # Ingest facts:
    # Prod_DB -> FalkorDB -> Redis_Engine (2-hop chain)
    # Prod_DB -> Prometheus (1-hop leaf)
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_arch_init",
        cardinality="MULTI",
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="FalkorDB",
        predicate="CONNECTS_TO",
        new_object="Redis_Engine",
        episode_id="ep_arch_init",
        cardinality="MULTI",
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="MONITORED_BY",
        new_object="Prometheus",
        episode_id="ep_arch_init",
        cardinality="MULTI",
        timestamp=1000.0,
    )

    # Execute HippoRAG associative retrieval from seed 'Prod_DB'
    res = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Prod_DB"],
        max_hops=2,
        as_of=1500.0,
    )

    assert res.status == "SUCCESS"
    assert res.seeds == ["Prod_DB"]
    scores = {e.name: e.degree_normalized_score for e in res.ranked_entities}

    # Invariant: Seed > 1-hop > 2-hop > 0
    assert "Prod_DB" in scores
    assert "FalkorDB" in scores
    assert "Redis_Engine" in scores
    assert "Prometheus" in scores

    assert scores["Prod_DB"] > scores["FalkorDB"]
    assert scores["FalkorDB"] > scores["Redis_Engine"]
    assert scores["Redis_Engine"] > 0.0
    assert scores["Prod_DB"] > scores["Prometheus"]
    assert scores["Prometheus"] > 0.0

    # Dict subscripting backward compatibility
    assert res["seeds"] == ["Prod_DB"]
    assert len(res["matches"]) >= 3


def test_stale_fact_pruning_temporal_gating(check_falkor):
    """TEST-HIPPORAG-02: Verifies superseded relations are strictly pruned during graph walk."""
    t_id = "test-hipporag-02"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_v1",
        content="Configured primary database on PostgreSQL 16.",
        importance_score=0.8,
        timestamp=1000.0,
    )
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_v2",
        content="Migrated primary database to FalkorDB graph store.",
        importance_score=0.9,
        timestamp=2000.0,
    )

    # Ingest v1: Prod_DB USES_TECH PostgreSQL (SINGLE) at t=1000
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="PostgreSQL",
        episode_id="ep_v1",
        cardinality="SINGLE",
        timestamp=1000.0,
    )

    # Ingest v2: Prod_DB USES_TECH FalkorDB (SINGLE) at t=2000 (invalidates PostgreSQL)
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_v2",
        cardinality="SINGLE",
        timestamp=2000.0,
    )

    # Query at t=2500.0
    res = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Prod_DB"],
        as_of=2500.0,
    )

    assert res.status == "SUCCESS"
    scores = {e.name: e.degree_normalized_score for e in res.ranked_entities}

    # Active entity FalkorDB receives positive mass
    assert "FalkorDB" in scores
    assert scores["FalkorDB"] > 0.0

    # Superseded entity PostgreSQL is not in active subgraph
    assert "PostgreSQL" not in scores or scores.get("PostgreSQL", 0.0) == 0.0


def test_bipartite_episode_grounding_convergence(check_falkor):
    """TEST-HIPPORAG-03: Verifies obsolete episodes receive zero grounding mass."""
    t_id = "test-hipporag-03"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_legacy",
        content="Initial rollout using PostgreSQL.",
        importance_score=0.95,
        timestamp=1000.0,
    )
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_modern",
        content="Database cutover to FalkorDB completed.",
        importance_score=0.95,
        timestamp=2000.0,
    )

    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="PostgreSQL",
        episode_id="ep_legacy",
        cardinality="SINGLE",
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_modern",
        cardinality="SINGLE",
        timestamp=2000.0,
    )

    # Retrieve at t=2500.0 with seed 'Prod_DB'
    res = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Prod_DB"],
        as_of=2500.0,
    )

    assert res.status == "SUCCESS"
    grounded_ep_ids = [ep.episode_id for ep in res.ranked_episodes]

    # Modern episode must be ranked #1
    assert len(grounded_ep_ids) >= 1
    assert grounded_ep_ids[0] == "ep_modern"

    # Legacy episode whose fact was invalidated must receive 0 grounding score (excluded)
    assert "ep_legacy" not in grounded_ep_ids


def test_hybrid_natural_language_seed_discovery(check_falkor):
    """TEST-HIPPORAG-04: Verifies natural language query resolves to entity via alias matching."""
    t_id = "test-hipporag-04"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_init",
        content="Primary database node operational.",
        importance_score=0.8,
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_init",
        cardinality="SINGLE",
        timestamp=1000.0,
    )

    # Attach alias 'primary db' to Prod_DB
    semantic_memory.append_entity_alias(
        tenant_id=t_id,
        canonical_name="Prod_DB",
        raw_alias="primary db",
    )

    # Execute HippoRAG retrieval with freeform natural language query
    res = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        query="Check database latency on primary DB",
        as_of=1500.0,
    )

    assert res.status == "SUCCESS"
    # Seed must be automatically identified as Prod_DB via alias match
    assert "Prod_DB" in res.seeds

    # Spreading activation propagates to FalkorDB
    entity_names = [e.name for e in res.ranked_entities]
    assert "Prod_DB" in entity_names
    assert "FalkorDB" in entity_names


def test_timetravel_associative_recall(check_falkor):
    """TEST-HIPPORAG-05: Verifies exact point-in-time associative recall across migration epochs."""
    t_id = "test-hipporag-05"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_1",
        content="Version 1: Running on PostgreSQL 16.",
        importance_score=0.85,
        timestamp=1000.0,
    )
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_2",
        content="Version 2: Migrated to FalkorDB graph database.",
        importance_score=0.95,
        timestamp=2000.0,
    )

    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="PostgreSQL",
        episode_id="ep_1",
        cardinality="SINGLE",
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_2",
        cardinality="SINGLE",
        timestamp=2000.0,
    )

    # Point-in-time 1: tau_1 = 1500.0 (Pre-migration)
    res_t1 = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Prod_DB"],
        as_of=1500.0,
    )
    assert res_t1.status == "SUCCESS"
    names_t1 = {e.name for e in res_t1.ranked_entities}
    episodes_t1 = [ep.episode_id for ep in res_t1.ranked_episodes]

    assert "PostgreSQL" in names_t1
    assert "FalkorDB" not in names_t1
    assert "ep_1" in episodes_t1
    assert "ep_2" not in episodes_t1  # Future episode never leaks!

    # Point-in-time 2: tau_2 = 2500.0 (Post-migration)
    res_t2 = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Prod_DB"],
        as_of=2500.0,
    )
    assert res_t2.status == "SUCCESS"
    names_t2 = {e.name for e in res_t2.ranked_entities}
    episodes_t2 = [ep.episode_id for ep in res_t2.ranked_episodes]

    assert "FalkorDB" in names_t2
    assert "PostgreSQL" not in names_t2
    assert "ep_2" in episodes_t2
    assert "ep_1" not in episodes_t2  # Superseded episode pruned!


def test_cold_start_zero_seed_fallback(check_falkor):
    """TEST-HIPPORAG-06: Verifies disjoint / cold-start queries safely return NO_SEEDS_FOUND."""
    t_id = "test-hipporag-06"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_setup",
        content="Configured Redis cache for session storage.",
        importance_score=0.8,
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Auth_Service",
        predicate="USES_TECH",
        new_object="Redis",
        episode_id="ep_setup",
        cardinality="SINGLE",
        timestamp=1000.0,
    )

    # Query with completely disjoint technical domain
    res = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        query="quantum teleportation entanglement",
        as_of=1500.0,
    )

    assert res.status == "NO_SEEDS_FOUND"
    assert res.seeds == []
    assert res.ranked_entities == []
    assert res.ranked_episodes == []
    assert res.active_subgraph_edges == []


def test_rest_api_endpoints_and_backward_compatibility(check_falkor):
    """TEST-HIPPORAG-07: Verifies HTTP 200 responses across primary and legacy endpoints."""
    t_id = "test-hipporag-07"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_api_test",
        content="Deployment on Kubernetes cluster.",
        importance_score=0.9,
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="K8s_Cluster",
        predicate="USES_TECH",
        new_object="Calico_CNI",
        episode_id="ep_api_test",
        cardinality="SINGLE",
        timestamp=1000.0,
    )
    semantic_memory.append_entity_alias(
        tenant_id=t_id,
        canonical_name="K8s_Cluster",
        raw_alias="k8s production",
    )

    # 1. Query new endpoint: POST /api/v1/memory/semantic/hipporag
    resp1 = client.post(
        "/api/v1/memory/semantic/hipporag",
        json={
            "tenant_id": t_id,
            "query": "Check network plugin on k8s production",
            "top_k": 5,
        },
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["status"] == "SUCCESS"
    assert "K8s_Cluster" in data1["seeds"]
    assert len(data1["matches"]) >= 1
    assert "result" in data1

    # 2. Query legacy endpoint: POST /api/v1/memory/hipporag with seed_entities
    resp2 = client.post(
        "/api/v1/memory/hipporag",
        json={
            "tenant_id": t_id,
            "seed_entities": ["K8s_Cluster"],
            "top_k": 3,
        },
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["status"] == "SUCCESS"
    assert data2["seeds"] == ["K8s_Cluster"]
    assert len(data2["matches"]) >= 1
