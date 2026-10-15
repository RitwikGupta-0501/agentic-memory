"""Integration test for model switch, query gating, and self-healing re-indexing."""

import pytest
from app.core.falkor_client import falkor_router
from app.core.embeddings import (
    DeterministicMockProvider,
    embedding_service,
    reindex_tenant_embeddings,
)
from app.core.cypher_catalog import EPISODE_VECTOR_SEARCH_CANDIDATES


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping migration tests.")


def test_embedding_model_drift_and_reindex(check_falkor):
    tenant = "test-migration-tenant"
    graph = falkor_router.get_graph(tenant)

    original_provider = embedding_service.provider
    try:
        # 1. Setup Model A and seed 2 episodes
        provider_a = DeterministicMockProvider(dimension=768, model_name="mock/model-a-768")
        embedding_service.set_provider(provider_a)

        ep1_text = "Deploying payment microservice on Kubernetes cluster"
        ep2_text = "Database failover configuration with streaming replication"

        vec1_a = provider_a.embed_text(ep1_text)
        vec2_a = provider_a.embed_text(ep2_text)

        graph.query("""
            MERGE (ep1:Episode {id: 'ep_mig_01'})
            SET ep1.content = $t1, ep1.session_id = 'session_mig',
                ep1.embedding = vecf32($v1), ep1.embedding_model = 'mock/model-a-768',
                ep1.embedding_dim = 768, ep1.vcache_threshold = 0.50
            MERGE (ep2:Episode {id: 'ep_mig_02'})
            SET ep2.content = $t2, ep2.session_id = 'session_mig',
                ep2.embedding = vecf32($v2), ep2.embedding_model = 'mock/model-a-768',
                ep2.embedding_dim = 768, ep2.vcache_threshold = 0.50
        """, {"t1": ep1_text, "v1": vec1_a, "t2": ep2_text, "v2": vec2_a})

        # Under Model A, search for ep1 finds ep1
        res_a = graph.query(EPISODE_VECTOR_SEARCH_CANDIDATES, {
            "candidate_limit": 5,
            "query_vec": vec1_a,
            "session_id": "session_mig",
            "cross_session": False,
            "current_model": "mock/model-a-768",
        })
        assert len(res_a.result_set) >= 1
        assert res_a.result_set[0][0].properties["id"] == "ep_mig_01"

        # 2. Simulate User Switching to Model B
        provider_b = DeterministicMockProvider(dimension=768, model_name="mock/model-b-768")
        embedding_service.set_provider(provider_b)

        # Query Gating: Search under Model B should NOT return Model A vectors
        vec1_b = provider_b.embed_text(ep1_text)
        res_b_before = graph.query(EPISODE_VECTOR_SEARCH_CANDIDATES, {
            "candidate_limit": 5,
            "query_vec": vec1_b,
            "session_id": "session_mig",
            "cross_session": False,
            "current_model": "mock/model-b-768",
        })
        # Since all stored nodes are mock/model-a-768, query gating safely returns 0
        assert len(res_b_before.result_set) == 0, "Query gating failed: cross-model vector was leaked"

        # 3. Trigger Self-Healing Re-Indexing
        reindex_res = reindex_tenant_embeddings(tenant_id=tenant)
        assert reindex_res["status"] == "SUCCESS"
        assert reindex_res["reindexed_count"] >= 2
        assert reindex_res["new_model"] == "mock/model-b-768"

        # 4. Verify that nodes are now searchable under Model B!
        res_b_after = graph.query(EPISODE_VECTOR_SEARCH_CANDIDATES, {
            "candidate_limit": 5,
            "query_vec": vec1_b,
            "session_id": "session_mig",
            "cross_session": False,
            "current_model": "mock/model-b-768",
        })
        assert len(res_b_after.result_set) >= 1
        assert res_b_after.result_set[0][0].properties["id"] == "ep_mig_01"
        assert res_b_after.result_set[0][0].properties["embedding_model"] == "mock/model-b-768"
    finally:
        embedding_service.set_provider(original_provider)
        # Clean up test nodes
        graph.query("MATCH (ep:Episode) WHERE ep.id IN ['ep_mig_01', 'ep_mig_02'] DETACH DELETE ep")
