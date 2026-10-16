"""Tests for Semantic Memory Phase 2: OpenIE Fact Extraction & Entity Disambiguation."""

import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.falkor_client import falkor_router
from app.main import app
from app.memory.prompts import (
    OPENIE_SYSTEM_PROMPT,
    CANONICAL_PREDICATES,
    SINGLE_VALUED_PREDICATES,
    MULTI_VALUED_PREDICATES,
    infer_predicate_cardinality,
)
from app.memory.semantic import (
    semantic_memory,
    FactExtractionResult,
    SemanticTriple,
)


@pytest.fixture
def test_tenant() -> str:
    """Provides a fresh isolated tenant graph for each test."""
    t_id = f"test_openie_{uuid.uuid4().hex[:8]}"
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


def test_openie_prompt_invariants_and_ontology():
    """Verifies that the OpenIE prompt contract and ontology definitions conform to specifications."""
    assert len(CANONICAL_PREDICATES) >= 8
    assert "USES_TECH" in CANONICAL_PREDICATES
    assert "RUNS_ON" in CANONICAL_PREDICATES
    assert "CONNECTS_TO" in CANONICAL_PREDICATES
    assert "DEPENDS_ON" in CANONICAL_PREDICATES
    assert "MONITORED_BY" in CANONICAL_PREDICATES
    assert "HAS_REPLICA" in CANONICAL_PREDICATES
    assert "CONFIGURED_WITH" in CANONICAL_PREDICATES

    # Cardinality invariants
    assert infer_predicate_cardinality("USES_TECH") == "SINGLE"
    assert infer_predicate_cardinality("RUNS_ON") == "SINGLE"
    assert infer_predicate_cardinality("CONNECTS_TO") == "MULTI"
    assert infer_predicate_cardinality("DEPENDS_ON") == "MULTI"
    assert infer_predicate_cardinality("MONITORED_BY") == "MULTI"
    assert infer_predicate_cardinality("HAS_REPLICA") == "MULTI"

    # Invariants in prompt text
    assert "Directionality Invariant" in OPENIE_SYSTEM_PROMPT
    assert "Canonical Predicate Closed Ontology" in OPENIE_SYSTEM_PROMPT
    assert "Negative Control" in OPENIE_SYSTEM_PROMPT


def test_openie_extraction_real_world_narratives():
    """R2.1: Verifies structured OpenIE extraction across varied real-world technical assertions."""
    # 1. Tech migration
    text1 = "We completed the production cutover for Prod_DB, migrating from PostgreSQL to FalkorDB for real-time memory graph processing."
    res1 = semantic_memory.extract_facts(text1)
    assert isinstance(res1, FactExtractionResult)
    assert len(res1.triples) >= 1
    t1 = res1.triples[0]
    assert t1.subject == "Prod_DB"
    assert t1.predicate == "USES_TECH"
    assert t1.object == "FalkorDB"
    assert t1.cardinality == "SINGLE"
    entity_names1 = [e.name for e in res1.entities]
    assert "Prod_DB" in entity_names1
    assert "FalkorDB" in entity_names1

    # 2. Multi-service architecture and networking
    text2 = "The checkout-worker microservice runs on our AWS_EKS cluster and connects to Stripe_Gateway and Inventory_DB."
    res2 = semantic_memory.extract_facts(text2)
    assert len(res2.triples) >= 2
    predicates2 = [t.predicate for t in res2.triples]
    objects2 = [t.object for t in res2.triples]
    assert "RUNS_ON" in predicates2
    assert "AWS_EKS" in objects2
    assert "CONNECTS_TO" in predicates2
    assert any(o in objects2 for o in ["Stripe_Gateway", "Inventory_DB"])

    # 3. Infrastructure upgrade & configuration
    text3 = "Kubernetes cluster upgraded to v1.30 with Calico CNI"
    res3 = semantic_memory.extract_facts(text3)
    assert len(res3.triples) >= 1
    assert any(t.object == "v1.30" for t in res3.triples)

    # 4. Observability and dependencies
    text4 = "Billing_Service depends on Auth_Service and is monitored by Prometheus"
    res4 = semantic_memory.extract_facts(text4)
    pred_map = {t.predicate: t.object for t in res4.triples}
    assert pred_map.get("DEPENDS_ON") == "Auth_Service"
    assert pred_map.get("MONITORED_BY") == "Prometheus"

    # Backward compatibility with extract_triples_from_text
    legacy_triples = semantic_memory.extract_triples_from_text(text1)
    assert len(legacy_triples) >= 1
    assert legacy_triples[0].subject == "Prod_DB"
    assert legacy_triples[0].object == "FalkorDB"


def test_openie_negative_controls_conversational_filtering():
    """R2.3: Verifies that conversational greetings and troubleshooting inquiries return 0 triples."""
    # Greetings
    greetings = [
        "Hello!",
        "Good morning",
        "Hi team, how is everyone?",
        "Hey",
    ]
    for g in greetings:
        res = semantic_memory.extract_facts(g)
        assert len(res.triples) == 0, f"Expected 0 triples for greeting: '{g}'"
        assert len(res.entities) == 0

    # Operational troubleshooting questions without declarative changes
    questions = [
        "Why did the database latency spike during the last run?",
        "Can you check what errors occurred in the checkout worker?",
        "How is the CPU utilization on the worker nodes?",
        "Is there any memory leak in the billing pod?",
    ]
    for q in questions:
        res = semantic_memory.extract_facts(q)
        assert len(res.triples) == 0, f"Expected 0 triples for question: '{q}'"
        assert len(res.entities) == 0


def test_entity_disambiguation_slug_and_aliases(test_tenant: str):
    """R2.2: Verifies that alias variations resolve to the canonical entity and update aliases."""
    # 1. Create canonical entity "Prod_DB"
    ent = semantic_memory.ensure_entity(
        tenant_id=test_tenant,
        name="Prod_DB",
        type="Infrastructure",
        description="Production primary transactional database",
    )
    assert ent["name"] == "Prod_DB"

    # 2. Resolve via slug exact match ("prod-db", "prod_db", "PROD_DB")
    resolved_1 = semantic_memory.resolve_entity(test_tenant, "prod-db")
    assert resolved_1 == "Prod_DB"

    resolved_2 = semantic_memory.resolve_entity(test_tenant, "prod_db")
    assert resolved_2 == "Prod_DB"

    resolved_3 = semantic_memory.resolve_entity(test_tenant, "PROD_DB")
    assert resolved_3 == "Prod_DB"

    # 3. Resolve via lexical/vector similarity ("production database")
    detailed = semantic_memory.resolve_entity_detailed(test_tenant, "production database")
    assert detailed["canonical_name"] == "Prod_DB"
    assert detailed["resolved"] is True
    assert detailed["method"] in ("exact_match", "vector_similarity", "lexical_jaccard")

    # 4. Check that aliases array on the node now contains the new alias
    graph = falkor_router.get_graph(test_tenant, shared=True)
    q_check = graph.query("MATCH (e:Entity {name: 'Prod_DB'}) RETURN e.aliases")
    assert q_check.result_set
    aliases = q_check.result_set[0][0]
    assert "production database" in aliases

    # 5. Subsequent lookup on "production database" now matches Step 1 exact alias match!
    second_lookup = semantic_memory.resolve_entity_detailed(test_tenant, "production database")
    assert second_lookup["canonical_name"] == "Prod_DB"
    assert second_lookup["method"] == "exact_match"


def test_consecutive_writes_with_alias_variations_prevent_fragmentation(test_tenant: str):
    """R2.2: Unit test asserting that consecutive writes with alias variations produce exactly 1 :Entity node."""
    # Write 1: "Prod_DB" USES_TECH "PostgreSQL"
    semantic_memory.upsert_fact(
        tenant_id=test_tenant,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="PostgreSQL",
        episode_id="ep_001",
        confidence=1.0,
        cardinality="SINGLE",
        subject_type="Infrastructure",
        object_type="Database",
    )

    # Write 2: "prod-db" USES_TECH "FalkorDB" (Supersedes PostgreSQL)
    semantic_memory.upsert_fact(
        tenant_id=test_tenant,
        subject="prod-db",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_002",
        confidence=1.0,
        cardinality="SINGLE",
        subject_type="Infrastructure",
        object_type="Database",
    )

    # Write 3: "production database" MONITORED_BY "Datadog"
    semantic_memory.upsert_fact(
        tenant_id=test_tenant,
        subject="production database",
        predicate="MONITORED_BY",
        new_object="Datadog",
        episode_id="ep_003",
        confidence=0.95,
        cardinality="MULTI",
        subject_type="Infrastructure",
        object_type="Tool",
    )

    # Verify Knowledge Graph integrity: Exactly 1 primary entity node exists
    graph = falkor_router.get_graph(test_tenant, shared=True)
    count_res = graph.query(
        "MATCH (e:Entity) WHERE e.canonical_name = 'prod_db' OR e.name = 'Prod_DB' RETURN count(e), collect(e.name)"
    )
    assert count_res.result_set
    ent_count = count_res.result_set[0][0]
    ent_names = count_res.result_set[0][1]
    assert ent_count == 1, f"Expected exactly 1 Prod_DB entity, but found {ent_count}: {ent_names}"

    # Verify aliases are deduplicated and tracked
    alias_res = graph.query("MATCH (e:Entity {name: 'Prod_DB'}) RETURN e.aliases")
    aliases = alias_res.result_set[0][0]
    assert len(aliases) >= 2
    assert "production database" in aliases or "prod-db" in aliases

    # Verify bi-temporal relations on Prod_DB
    active_rel_res = graph.query(
        """
        MATCH (s:Entity {name: 'Prod_DB'})-[r:RELATES_TO]->(o:Entity)
        WHERE r.valid_to IS NULL
        RETURN r.predicate AS predicate, o.name AS target
        """
    )
    active_facts = {(row[0], row[1]) for row in active_rel_res.result_set}
    assert ("USES_TECH", "FalkorDB") in active_facts
    assert ("MONITORED_BY", "Datadog") in active_facts
    # Superseded PostgreSQL should NOT be active
    assert ("USES_TECH", "PostgreSQL") not in active_facts


def test_api_semantic_extract_and_resolve_endpoints(client: TestClient, test_tenant: str):
    """Verifies POST /api/v1/memory/semantic/extract and /semantic/resolve REST endpoints."""
    # 1. Test /semantic/extract with persist=True
    extract_payload = {
        "tenant_id": test_tenant,
        "text": "The worker service runs on Kubernetes and connects to Redis_Cache",
        "persist": True,
        "episode_id": "ep_api_test_01",
    }
    resp = client.post("/api/v1/memory/semantic/extract", json=extract_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert len(data["result"]["triples"]) >= 2
    assert len(data["persisted_facts"]) >= 2

    # 2. Test /semantic/resolve
    resolve_payload = {
        "tenant_id": test_tenant,
        "name": "redis-cache",
        "type": "Database",
    }
    resp_resolve = client.post("/api/v1/memory/semantic/resolve", json=resolve_payload)
    assert resp_resolve.status_code == 200
    resolve_data = resp_resolve.json()
    assert resolve_data["status"] == "SUCCESS"
    assert resolve_data["resolution"]["canonical_name"] == "Redis_Cache"
