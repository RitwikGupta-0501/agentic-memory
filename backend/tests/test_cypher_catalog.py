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

