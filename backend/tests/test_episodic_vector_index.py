"""Integration tests for FalkorDB dynamic vector index creation and candidate queries."""

import pytest
from app.core.falkor_client import falkor_router
from app.core.embeddings import DeterministicMockProvider, embedding_service
from app.core.cypher_catalog import EPISODE_VECTOR_SEARCH_CANDIDATES


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping vector index tests.")


def test_live_vector_index_creation(check_falkor):
    """Verifies that FalkorDB has the vector index for Episode.embedding."""
    tenant = "test-vec-tenant"
    graph = falkor_router.get_graph(tenant)

    indexes = falkor_router.get_indexes(tenant)
    # Check that Episode has a VECTOR index on embedding
    has_vector_idx = False
    for idx_row in indexes:
        label = idx_row[0]
        properties = idx_row[1]
        types_map = idx_row[2] if len(idx_row) > 2 else {}
        if label == "Episode" and "embedding" in properties:
            if types_map.get("embedding") == ["VECTOR"]:
                has_vector_idx = True
                break

    assert has_vector_idx, f"Episode vector index not found in {indexes}"


def test_live_vector_insertion_and_search(check_falkor):
    """Verifies inserting a node with vecf32 embedding and querying it back."""
    tenant = "test-vec-tenant"
    graph = falkor_router.get_graph(tenant)

    # Insert test episode with embedding
    test_id = "ep_test_vec_live_01"
    text = "Kubernetes ingress controller configuration for payment gateway"
    vec = embedding_service.embed_text(text)
    active_model = embedding_service.provider.model_name
    active_dim = embedding_service.provider.dimension

    insert_q = """
    MERGE (ep:Episode {id: $id})
    SET ep.session_id = 'session_test_vec',
        ep.content = $content,
        ep.embedding = vecf32($vec),
        ep.embedding_model = $model,
        ep.embedding_dim = $dim,
        ep.vcache_threshold = 0.70
    RETURN ep
    """
    graph.query(
        insert_q,
        {
            "id": test_id,
            "content": text,
            "vec": vec,
            "model": active_model,
            "dim": active_dim,
        },
    )

    # Query with exact embedding
    res = graph.query(
        EPISODE_VECTOR_SEARCH_CANDIDATES,
        {
            "candidate_limit": 5,
            "query_vec": vec,
            "session_id": "session_test_vec",
            "cross_session": False,
            "current_model": active_model,
        },
    )

    assert res and res.result_set, "Vector search returned no results"
    retrieved_ep = res.result_set[0][0]
    score = res.result_set[0][1]

    props = getattr(retrieved_ep, "properties", {})
    assert props.get("id") == test_id
    assert props.get("embedding_model") == active_model
    # Cosine distance should be 0 (score >= 0.99 similarity)
    assert score is not None

    # Clean up
    graph.query("MATCH (ep:Episode {id: $id}) DETACH DELETE ep", {"id": test_id})


def test_drift_detection(check_falkor):
    """Verifies that check_graph_embedding_drift detects match and drift."""
    tenant = "test-drift-tenant"
    # Ensure fresh graph with metadata
    graph = falkor_router.get_graph(tenant)
    original_provider = embedding_service.provider

    try:
        # Match case
        drift_match = falkor_router.check_graph_embedding_drift(tenant)
        assert drift_match["status"] == "MATCH"
        assert drift_match["drift_detected"] is False

        # Simulate provider change
        temp_provider = DeterministicMockProvider(dimension=768, model_name="mock/other-model")
        embedding_service.set_provider(temp_provider)

        drift_detected = falkor_router.check_graph_embedding_drift(tenant)
        assert drift_detected["status"] == "DRIFT_DETECTED"
        assert drift_detected["drift_detected"] is True
    finally:
        embedding_service.set_provider(original_provider)
