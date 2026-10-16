"""Tests that all centralized Cypher catalog queries are properly structured."""

import pytest
from app.core.cypher_catalog import CYPHER_CATALOG


def test_cypher_catalog_completeness():
    """Verifies that all essential queries defined in the PRD exist in the catalog."""
    expected_queries = [
        "EPISODE_INSERT_AND_CHAIN",
        "EPISODE_INSERT_ROOT",
        "BITEMPORAL_INVALIDATE_AND_UPSERT",
        "HIPPORAG_HYBRID_RETRIEVAL",
        "TASK_DAG_CREATE",
        "SUBTASK_CREATE",
        "SUBTASK_ADD_DEPENDENCY",
        "WORKING_MEMORY_ATOMIC_CLAIM",
        "WORKING_MEMORY_COMPLETE_SUBTASK",
        "WORKING_MEMORY_PIN_CONTEXT",
        "PROCEDURE_CREATE",
        "ACTION_STEP_APPEND",
        "PROCEDURAL_RETRIEVAL_WITH_GUARDRAILS",
        "PROCEDURAL_GUARDRAIL_ATTACH",
        "CONSOLIDATION_RETENTION_QUERY",
        "CONSOLIDATION_INSIGHT_CREATE",
        "VISUALIZE_ALL_GRAPH",
    ]

    for q_name in expected_queries:
        assert q_name in CYPHER_CATALOG, f"Missing required Cypher query: {q_name}"
        query_text = CYPHER_CATALOG[q_name].strip()
        assert len(query_text) > 10, f"Query {q_name} is unexpectedly short or empty"


def test_bitemporal_query_syntax():
    """Verifies bi-temporal query contains required invalidation and upsert clauses."""
    query = CYPHER_CATALOG["BITEMPORAL_INVALIDATE_AND_UPSERT"]
    assert "old_r.valid_to IS NULL" in query
    assert "SET old_r.valid_to = $now" in query
    assert "valid_from: $now" in query
    assert "[:DERIVED_FROM]->(ep)" in query


def test_working_memory_atomic_claim_syntax():
    """Verifies atomic subtask claiming enforces dependency checks."""
    query = CYPHER_CATALOG["WORKING_MEMORY_ATOMIC_CLAIM"]
    assert "status: 'PENDING'" in query
    assert "NOT (st)-[:DEPENDS_ON]->(:SubTask {status: 'PENDING'})" in query
    assert "SET st.status = 'IN_PROGRESS'" in query
    assert "st.locked_by = $agent_id" in query


def test_semantic_alias_and_resolution_query_syntax():
    """Verifies entity alias lookup, append, and vector similarity Cypher syntax."""
    alias_q = CYPHER_CATALOG["SEMANTIC_ENTITY_FIND_BY_ALIAS"]
    assert "e.canonical_name = $slug" in alias_q
    assert "$raw_name IN coalesce(e.aliases, [])" in alias_q
    assert "toLower(e.name) = toLower($raw_name)" in alias_q

    append_q = CYPHER_CATALOG["SEMANTIC_ENTITY_APPEND_ALIAS"]
    assert "e.aliases = CASE" in append_q
    assert "coalesce(e.aliases, []) + $raw_name" in append_q

    vec_q = CYPHER_CATALOG["SEMANTIC_ENTITY_VECTOR_SIMILARITY"]
    assert "CALL db.idx.vector.queryNodes('Entity', 'embedding'" in vec_q
    assert "(1.0 - score) AS similarity" in vec_q
    assert "similarity >= $threshold" in vec_q


def test_semantic_time_travel_cypher_syntax():
    """Verifies that point-in-time and cytoscape queries contain strict interval and null guards."""
    snapshot_q = CYPHER_CATALOG["SEMANTIC_TIME_TRAVEL_SNAPSHOT"]
    assert "r.valid_from <= $as_of" in snapshot_q
    assert "r.valid_to IS NULL OR r.valid_to > $as_of" in snapshot_q

    timeline_q = CYPHER_CATALOG["SEMANTIC_ENTITY_EVOLUTION_TIMELINE"]
    assert "s.name = $entity_name OR s.canonical_name = $slug" in timeline_q
    assert "CASE WHEN r.valid_to IS NULL THEN 'ACTIVE' ELSE 'SUPERSEDED' END AS status" in timeline_q

    subgraph_q = CYPHER_CATALOG["SEMANTIC_TIME_TRAVEL_SUBGRAPH"]
    assert "CASE WHEN r IS NOT NULL THEN" in subgraph_q
    assert "CASE WHEN neighbor IS NOT NULL THEN neighbor.name ELSE NULL END" in subgraph_q

    cyto_q = CYPHER_CATALOG["SEMANTIC_CYTOSCAPE_TIME_TRAVEL"]
    assert "CASE WHEN r IS NOT NULL THEN" in cyto_q
    assert "$include_invalidated = true" in cyto_q



