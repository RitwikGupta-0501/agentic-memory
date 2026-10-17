"""Regression tests for the 4 architectural OpenCypher & Python deserialization defect fixes:
1. Issue #6: Re-asserting active facts preserves valid_from timestamp without reading from deleted edge.
2. Issue #7: Isolated seed entities return clean empty lists [] instead of [None] in time-travel subgraph.
3. Issue #8: Invalidation in HippoRAG bipartite episode grounding is scoped to entity-involved relations.
4. Issue #9: Multi-session parent linking does not produce duplicate parallel relationships on re-linking.
"""

import time
import uuid
import pytest

from app.core.falkor_client import falkor_router
from app.core.cypher_catalog import (
    SESSION_ENSURE_AND_LINK,
    MULTI_SESSION_LINEAGE_QUERY,
)
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory


@pytest.fixture
def test_tenant() -> str:
    """Provides a fresh isolated tenant graph for each test."""
    t_id = f"test_defect_{uuid.uuid4().hex[:8]}"
    yield t_id
    try:
        falkor_router.get_client().select_graph(
            falkor_router.get_graph_key(tenant_id=t_id, shared=True)
        ).delete()
    except Exception:
        pass


def test_session_parent_link_deduplication(test_tenant):
    """TEST-DEFECT-09: Verifies repeated SESSION_ENSURE_AND_LINK calls create exactly 1 PARENT_SESSION edge."""
    t_id = test_tenant

    # Ensure parent session exists
    falkor_router.query(
        SESSION_ENSURE_AND_LINK,
        {
            "session_id": "session_parent",
            "tenant_id": t_id,
            "user_id": "u1",
            "parent_session_id": None,
            "now": 1000.0,
        },
        tenant_id=t_id,
    )

    # Link child to parent 3 times with different timestamps
    for ts in [1100.0, 1200.0, 1300.0]:
        falkor_router.query(
            SESSION_ENSURE_AND_LINK,
            {
                "session_id": "session_child",
                "tenant_id": t_id,
                "user_id": "u1",
                "parent_session_id": "session_parent",
                "now": ts,
            },
            tenant_id=t_id,
        )

    # Invariant 1: Exactly 1 PARENT_SESSION edge between child and parent
    edge_res = falkor_router.query(
        "MATCH (c:Session {id: 'session_child'})-[r:PARENT_SESSION]->(p:Session {id: 'session_parent'}) RETURN count(r)",
        tenant_id=t_id,
    )
    assert edge_res and edge_res.result_set[0][0] == 1

    # Invariant 2: MULTI_SESSION_LINEAGE_QUERY returns exactly 2 ancestor rows (child and parent, no duplicates)
    lin_res = falkor_router.query(
        MULTI_SESSION_LINEAGE_QUERY,
        {"session_id": "session_child"},
        tenant_id=t_id,
    )
    assert lin_res and len(lin_res.result_set) == 2
    session_ids = [row[0] for row in lin_res.result_set]
    assert session_ids == ["session_parent", "session_child"]


def test_upsert_fact_active_timestamp_preservation(test_tenant):
    """TEST-DEFECT-06: Verifies re-asserting an active fact preserves its original valid_from timestamp."""
    t_id = test_tenant

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_init",
        content="Initial fact assertion",
        timestamp=1000.0,
    )

    # First assertion at t=1000.0
    res1 = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Payment_Gateway",
        predicate="USES_PROVIDER",
        new_object="Stripe_v3",
        episode_id="ep_init",
        confidence=0.85,
        cardinality="SINGLE",
        timestamp=1000.0,
    )
    assert res1["valid_from"] == 1000.0

    # Second assertion at t=2000.0 with updated confidence
    res2 = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Payment_Gateway",
        predicate="USES_PROVIDER",
        new_object="Stripe_v3",
        episode_id="ep_init",
        confidence=0.99,
        cardinality="SINGLE",
        timestamp=2000.0,
    )
    # Invariant: valid_from must remain 1000.0 (not overwritten with 2000.0)
    assert res2["valid_from"] == 1000.0

    # Direct Cypher check in FalkorDB
    q_edge = """
    MATCH (s:Entity {name: 'Payment_Gateway'})-[r:RELATES_TO {predicate: 'USES_PROVIDER'}]->(o:Entity {name: 'Stripe_v3'})
    RETURN r.valid_from, r.confidence, count(r)
    """
    edge_res = falkor_router.query(q_edge, tenant_id=t_id)
    assert edge_res and len(edge_res.result_set) == 1
    assert edge_res.result_set[0][0] == 1000.0
    assert edge_res.result_set[0][1] == 0.99
    assert edge_res.result_set[0][2] == 1  # Exactly 1 active edge, no duplicate


def test_isolated_entity_time_travel_empty_collections(test_tenant):
    """TEST-DEFECT-07: Verifies isolated seed entity returns strictly empty lists [] for relationships and neighbors."""
    t_id = test_tenant

    # Create isolated entity with zero relationships
    falkor_router.query(
        "CREATE (e:Entity {id: 'iso_1', name: 'Isolated_Node', canonical_name: 'isolated_node', type: 'Concept', aliases: ['Isolated_Node'], created_at: 1000.0})",
        tenant_id=t_id,
    )

    subgraph = semantic_memory.get_time_travel_subgraph(
        tenant_id=t_id,
        seed_entity="Isolated_Node",
        as_of=1500.0,
    )

    assert subgraph["seed"] == "Isolated_Node"
    # Invariant: Relationships and neighbors must be strictly empty lists [] (never [None])
    assert subgraph["relationships"] == []
    assert subgraph["neighbors"] == []
    assert None not in subgraph["relationships"]
    assert None not in subgraph["neighbors"]


def test_hipporag_coexisting_facts_in_same_episode(test_tenant):
    """TEST-DEFECT-08: Verifies episode with both superseded and active facts is preserved for the active entity."""
    t_id = test_tenant

    # Episode 1 records TWO facts:
    # 1. Prod_DB USES_TECH PostgreSQL
    # 2. Prod_DB HOSTED_ON AWS_RDS
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_bundle_01",
        content="Prod_DB provisioned on AWS_RDS with PostgreSQL engine.",
        importance_score=0.95,
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="PostgreSQL",
        episode_id="ep_bundle_01",
        cardinality="SINGLE",
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="HOSTED_ON",
        new_object="AWS_RDS",
        episode_id="ep_bundle_01",
        cardinality="SINGLE",
        timestamp=1000.0,
    )

    # Episode 2 migrates USES_TECH to FalkorDB at t=2000.0 (invalidating PostgreSQL, but HOSTED_ON remains active)
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id="ep_cutover_02",
        content="Migrated Prod_DB to FalkorDB graph engine.",
        importance_score=0.95,
        timestamp=2000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_cutover_02",
        cardinality="SINGLE",
        timestamp=2000.0,
    )

    # Query HippoRAG at t=2500.0 for AWS_RDS:
    # Invariant 1: AWS_RDS was asserted in ep_bundle_01 and NEVER superseded -> ep_bundle_01 MUST be grounded!
    res_rds = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["AWS_RDS"],
        as_of=2500.0,
    )
    grounded_rds = [ep.episode_id for ep in res_rds.ranked_episodes]
    assert "ep_bundle_01" in grounded_rds

    # Query HippoRAG at t=2500.0 for PostgreSQL:
    # Invariant 2: PostgreSQL's fact was superseded -> ep_bundle_01 MUST be excluded for PostgreSQL!
    res_pg = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["PostgreSQL"],
        as_of=2500.0,
    )
    grounded_pg = [ep.episode_id for ep in res_pg.ranked_episodes]
    assert "ep_bundle_01" not in grounded_pg

    # Query HippoRAG at t=2500.0 for Prod_DB:
    # Invariant 3: Prod_DB has active fact in ep_bundle_01 (HOSTED_ON) and ep_cutover_02 (USES_TECH) -> both grounded
    res_db = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Prod_DB"],
        as_of=2500.0,
    )
    grounded_db = [ep.episode_id for ep in res_db.ranked_episodes]
    assert "ep_cutover_02" in grounded_db
    assert "ep_bundle_01" in grounded_db
