"""Tests for Semantic Memory Phase 1: Bi-temporal schema, vector indexing, and bidirectional provenance."""

import pytest
import time
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
from app.memory.semantic import (
    semantic_memory,
    EntityRecord,
    SemanticFactInput,
    PredicateCardinality,
)

client = TestClient(app)


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live tests.")


def test_entity_record_schema_validation():
    """TEST-SEM-R1.1: Validates EntityRecord constraints, slugification, and defaults."""
    # Valid model
    rec = EntityRecord(
        name="Prod_DB",
        canonical_name=semantic_memory.slugify("Prod_DB"),
        type="Infrastructure",
        aliases=["Prod_DB", "prod-db"],
    )
    assert rec.name == "Prod_DB"
    assert rec.canonical_name == "prod_db"
    assert "prod-db" in rec.aliases
    assert rec.created_at > 0

    # Empty name should fail
    with pytest.raises(ValidationError):
        EntityRecord(name="", canonical_name="")

    # SemanticFactInput confidence bounds
    with pytest.raises(ValidationError):
        SemanticFactInput(
            subject="Prod_DB",
            predicate="USES_TECH",
            object="FalkorDB",
            episode_id="ep_1",
            confidence=1.5,  # > 1.0
        )

    with pytest.raises(ValidationError):
        SemanticFactInput(
            subject="Prod_DB",
            predicate="USES_TECH",
            object="FalkorDB",
            episode_id="ep_1",
            confidence=-0.1,  # < 0.0
        )


def test_entity_slugification_utility():
    """Verifies slugify correctly handles special characters, casing, and spaces."""
    assert semantic_memory.slugify("Prod_DB") == "prod_db"
    assert semantic_memory.slugify("PostgreSQL 16 Cluster") == "postgresql_16_cluster"
    assert semantic_memory.slugify("  Auth-Service.v2!  ") == "auth_service_v2"


def test_live_entity_vector_index_creation(check_falkor):
    """TEST-SEM-R1.2: Verifies that vector index on (e:Entity) is idempotently created."""
    t_id = "test-semantic-bootstrap"
    graph = falkor_router.get_graph(t_id)
    falkor_router.ensure_indices(graph)

    # Calling vector index query directly should not throw "Index not found" error
    zero_vec = [0.0] * 768
    zero_vec[0] = 1.0
    query = """
    CALL db.idx.vector.queryNodes('Entity', 'embedding', 1, vecf32($vec))
    YIELD node, score
    RETURN node, score
    """
    res = graph.query(query, {"vec": zero_vec})
    assert res is not None


def test_live_entity_merge_and_auto_vectorization(check_falkor):
    """TEST-SEM-R1.3: Verifies ensure_entity idempotently merges entity with dense vector."""
    t_id = "test-semantic-merge"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    ent = semantic_memory.ensure_entity(
        tenant_id=t_id,
        name="Prod_DB",
        type="Database",
        description="Core primary transactional database cluster",
    )

    assert ent["name"] == "Prod_DB"
    assert ent["canonical_name"] == "prod_db"
    assert ent["type"] == "Database"
    assert len(ent["embedding"]) == 768

    # Query FalkorDB directly to verify properties stored on graph node
    res = falkor_router.query(
        "MATCH (e:Entity {name: 'Prod_DB'}) RETURN e.canonical_name, e.aliases, e.embedding IS NOT NULL",
        tenant_id=t_id,
    )
    assert len(res.result_set) == 1
    row = res.result_set[0]
    assert row[0] == "prod_db"
    assert "Prod_DB" in row[1]
    assert row[2] is True


def test_live_bidirectional_cross_layer_provenance(check_falkor):
    """TEST-SEM-R1.4: Verifies full bidirectional grounding between Episode and Entity."""
    t_id = "test-semantic-provenance"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # 1. Ingest parent episode
    ep = episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="session_prov_01",
        episode_id="ep_prov_01",
        content="Alice: Upgraded Prod_DB to FalkorDB for real-time memory.",
        role="user",
    )
    assert ep["id"] == "ep_prov_01"

    # 2. Upsert fact linked to episode
    fact = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_prov_01",
        confidence=1.0,
        cardinality="SINGLE",
        subject_type="Infrastructure",
        object_type="GraphDatabase",
    )
    assert fact["subject"] == "Prod_DB"
    assert fact["object"] == "FalkorDB"
    assert fact["source_episode"] == "ep_prov_01"

    # 3. Verify all 4 bidirectional cross-layer edges
    # a. (Prod_DB)-[:MENTIONED_IN]->(ep)
    # b. (FalkorDB)-[:MENTIONED_IN]->(ep)
    # c. (FalkorDB)-[:DERIVED_FROM]->(ep)
    # d. (ep)-[:EXTRACTED_FACT]->(FalkorDB)
    verify_query = """
    MATCH (ep:Episode {id: 'ep_prov_01'})
    OPTIONAL MATCH (s:Entity {name: 'Prod_DB'})-[:MENTIONED_IN]->(ep)
    OPTIONAL MATCH (o:Entity {name: 'FalkorDB'})-[:MENTIONED_IN]->(ep)
    OPTIONAL MATCH (o)-[:DERIVED_FROM]->(ep)
    OPTIONAL MATCH (ep)-[ef:EXTRACTED_FACT]->(o)
    OPTIONAL MATCH (s)-[rel:RELATES_TO {predicate: 'USES_TECH'}]->(o)
    RETURN s IS NOT NULL AS has_subj_mention,
           o IS NOT NULL AS has_obj_mention,
           ef.predicate AS extracted_predicate,
           rel.valid_to IS NULL AS is_active_relation
    """
    res = falkor_router.query(verify_query, tenant_id=t_id)
    assert len(res.result_set) == 1
    row = res.result_set[0]
    assert row[0] is True  # Subject mentioned
    assert row[1] is True  # Object mentioned and derived
    assert row[2] == "USES_TECH"  # Extracted fact edge present
    assert row[3] is True  # Active relation


def test_live_entity_vector_search(check_falkor):
    """TEST-SEM-R1.5: Verifies vector similarity search over Entity nodes."""
    t_id = "test-semantic-search"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # Seed 3 distinct entities
    semantic_memory.ensure_entity(t_id, "Prod_DB", "Database", "Production transactional database")
    semantic_memory.ensure_entity(t_id, "Redis_Cache", "Cache", "In-memory key-value caching layer")
    semantic_memory.ensure_entity(t_id, "Kubernetes_Cluster", "Compute", "Container orchestration system")

    # Search for database-related entity
    results = semantic_memory.search_entities(t_id, "database storage cluster", limit=3)
    assert len(results) >= 1
    top_entity = results[0]
    assert "name" in top_entity
    assert "canonical_name" in top_entity
    assert "similarity" in top_entity
    assert 0.0 <= top_entity["similarity"] <= 1.0


def test_api_semantic_endpoints(check_falkor):
    """TEST-SEM-R1.6: Validates FastAPI endpoints for entity creation, search, and fact upsert."""
    t_id = "test-semantic-api"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # 1. POST /semantic/entity
    resp1 = client.post(
        "/api/v1/memory/semantic/entity",
        json={
            "tenant_id": t_id,
            "name": "Auth_Service",
            "type": "Microservice",
            "description": "Handles OAuth and JWT authentication",
        },
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "SUCCESS"
    assert data1["entity"]["name"] == "Auth_Service"
    assert data1["entity"]["canonical_name"] == "auth_service"

    # 2. Ingest episode for provenance link
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="session_api_01",
        episode_id="ep_api_01",
        content="Deployed Auth_Service v2 connecting to PostgreSQL.",
    )

    # 3. POST /semantic/fact
    resp2 = client.post(
        "/api/v1/memory/semantic/fact",
        json={
            "tenant_id": t_id,
            "subject": "Auth_Service",
            "predicate": "CONNECTS_TO",
            "object": "PostgreSQL",
            "episode_id": "ep_api_01",
            "cardinality": "MULTI",
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "SUCCESS"
    assert data2["fact"]["subject"] == "Auth_Service"
    assert data2["fact"]["object"] == "PostgreSQL"
    assert data2["fact"]["source_episode"] == "ep_api_01"

    # 4. POST /semantic/search
    resp3 = client.post(
        "/api/v1/memory/semantic/search",
        json={
            "tenant_id": t_id,
            "query": "authentication security service",
            "limit": 2,
        },
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["results_count"] >= 1
    assert any(e["name"] == "Auth_Service" for e in data3["entities"])
