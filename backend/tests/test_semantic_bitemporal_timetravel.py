"""Tests for Semantic Memory Phase 3: Cardinality-Aware Invalidation & Time-Travel Query Engine.

Verifies:
- TEST-TIMETRAVEL-01: Functional invalidation, edge refresh idempotency, and subject-tracked [:INVALIDATED_RELATION]
- TEST-TIMETRAVEL-02: Multi-valued predicate concurrent coexistence without invalidation
- TEST-TIMETRAVEL-03: Point-in-time snapshot reconstruction at arbitrary epochs
- TEST-TIMETRAVEL-04: Entity historical evolution timeline with status classification
- TEST-TIMETRAVEL-05: Cytoscape dual-edge time-travel serializer with phantom null guards
- TEST-TIMETRAVEL-06: Boundary collision handling and half-open [ts, te) interval semantics
- TEST-TIMETRAVEL-07: REST API endpoints for snapshot, history, time-travel, and cytoscape
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
        pytest.skip("FalkorDB is offline; skipping live time-travel tests.")


def test_functional_invalidation_and_idempotency(check_falkor):
    """TEST-TIMETRAVEL-01: Verifies functional invalidation, edge refresh idempotency, and subject tracking."""
    t_id = "test-timetravel-01"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # Pre-record episodes
    episodic_memory.record_episode(tenant_id=t_id, session_id="s1", episode_id="ep_1", content="Init with Postgres")
    episodic_memory.record_episode(tenant_id=t_id, session_id="s1", episode_id="ep_2", content="Migrate to FalkorDB")
    episodic_memory.record_episode(tenant_id=t_id, session_id="s1", episode_id="ep_3", content="Re-assert FalkorDB")

    # Ingest 1: Prod_DB USES_TECH PostgreSQL at t=1000.0
    res1 = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="PostgreSQL",
        episode_id="ep_1",
        cardinality="SINGLE",
        timestamp=1000.0,
    )
    assert res1["invalidated_count"] == 0
    assert res1["valid_from"] == 1000.0

    # Ingest 2: Migration to FalkorDB at t=2000.0
    res2 = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_2",
        cardinality="SINGLE",
        timestamp=2000.0,
    )
    assert res2["invalidated_count"] == 1
    assert res2["valid_from"] == 2000.0

    # Ingest 3: Re-assert identical fact (FalkorDB) at t=3000.0 (idempotent refresh)
    res3 = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_3",
        cardinality="SINGLE",
        timestamp=3000.0,
    )
    assert res3["invalidated_count"] == 0
    # Must preserve original valid_from: 2000.0
    assert res3["valid_from"] == 2000.0

    # Invariant: Exactly 1 active edge to FalkorDB
    active_q = falkor_router.query(
        """
        MATCH (s:Entity {name: 'Prod_DB'})-[r:RELATES_TO {predicate: 'USES_TECH'}]->(o:Entity)
        WHERE r.valid_to IS NULL
        RETURN o.name, r.valid_from, count(r)
        """,
        tenant_id=t_id,
    )
    assert len(active_q.result_set) == 1
    assert active_q.result_set[0][0] == "FalkorDB"
    assert active_q.result_set[0][1] == 2000.0
    assert active_q.result_set[0][2] == 1

    # Invariant: PostgreSQL edge is invalidated with valid_to == 2000.0
    superseded_q = falkor_router.query(
        """
        MATCH (s:Entity {name: 'Prod_DB'})-[r:RELATES_TO {predicate: 'USES_TECH'}]->(o:Entity {name: 'PostgreSQL'})
        RETURN r.valid_to, r.invalidated_by_episode
        """,
        tenant_id=t_id,
    )
    assert len(superseded_q.result_set) == 1
    assert superseded_q.result_set[0][0] == 2000.0
    assert superseded_q.result_set[0][1] == "ep_2"

    # Invariant: [:INVALIDATED_RELATION] connects ep_2 to PostgreSQL with subject tracking
    inv_rel_q = falkor_router.query(
        """
        MATCH (ep:Episode {id: 'ep_2'})-[r:INVALIDATED_RELATION]->(old_o:Entity)
        RETURN r.subject, r.predicate, old_o.name
        """,
        tenant_id=t_id,
    )
    assert len(inv_rel_q.result_set) == 1
    assert inv_rel_q.result_set[0][0] == "Prod_DB"
    assert inv_rel_q.result_set[0][1] == "USES_TECH"
    assert inv_rel_q.result_set[0][2] == "PostgreSQL"


def test_multi_valued_coexistence(check_falkor):
    """TEST-TIMETRAVEL-02: Verifies multi-valued predicates allow concurrent active parallel relations."""
    t_id = "test-timetravel-02"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # Ingest 3 CONNECTS_TO relations
    for i, target in enumerate(["Stripe_Gateway", "Inventory_Service", "Redis_Cache"], start=1):
        res = semantic_memory.upsert_fact(
            tenant_id=t_id,
            subject="Checkout_API",
            predicate="CONNECTS_TO",
            new_object=target,
            episode_id=f"ep_multi_{i}",
            cardinality="MULTI",
            timestamp=1000.0 * i,
        )
        assert res["invalidated_count"] == 0

    # Invariant: All 3 relations remain concurrently active
    active_q = falkor_router.query(
        """
        MATCH (s:Entity {name: 'Checkout_API'})-[r:RELATES_TO {predicate: 'CONNECTS_TO'}]->(o:Entity)
        WHERE r.valid_to IS NULL
        RETURN collect(o.name) AS targets
        """,
        tenant_id=t_id,
    )
    targets = set(active_q.result_set[0][0])
    assert targets == {"Stripe_Gateway", "Inventory_Service", "Redis_Cache"}


def test_point_in_time_reconstruction(check_falkor):
    """TEST-TIMETRAVEL-03: Reconstructs exact historical graph snapshots across a progression."""
    t_id = "test-timetravel-03"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # State 1 at t=1000.0: PostgreSQL
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "PostgreSQL", "ep_1", cardinality="SINGLE", timestamp=1000.0)
    # State 2 at t=2000.0: FalkorDB
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "FalkorDB", "ep_2", cardinality="SINGLE", timestamp=2000.0)
    # State 3 at t=3000.0: CockroachDB
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "CockroachDB", "ep_3", cardinality="SINGLE", timestamp=3000.0)

    # Query before inception: tau = 500.0
    snap_500 = semantic_memory.get_snapshot(t_id, as_of=500.0)
    assert len(snap_500) == 0

    # Query at tau = 1500.0 (PostgreSQL era)
    snap_1500 = semantic_memory.get_snapshot(t_id, as_of=1500.0)
    assert len(snap_1500) == 1
    assert snap_1500[0]["object"] == "PostgreSQL"
    assert snap_1500[0]["valid_from"] == 1000.0
    assert snap_1500[0]["valid_to"] == 2000.0

    # Query at tau = 2500.0 (FalkorDB era)
    snap_2500 = semantic_memory.get_snapshot(t_id, as_of=2500.0)
    assert len(snap_2500) == 1
    assert snap_2500[0]["object"] == "FalkorDB"
    assert snap_2500[0]["valid_from"] == 2000.0
    assert snap_2500[0]["valid_to"] == 3000.0

    # Query at tau = 3500.0 (CockroachDB era)
    snap_3500 = semantic_memory.get_snapshot(t_id, as_of=3500.0)
    assert len(snap_3500) == 1
    assert snap_3500[0]["object"] == "CockroachDB"
    assert snap_3500[0]["valid_from"] == 3000.0
    assert snap_3500[0]["valid_to"] is None


def test_entity_evolution_timeline(check_falkor):
    """TEST-TIMETRAVEL-04: Validates full chronological transitions for an entity."""
    t_id = "test-timetravel-04"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # 3 sequential migrations on Prod_DB
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "PostgreSQL", "ep_1", cardinality="SINGLE", timestamp=1000.0)
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "FalkorDB", "ep_2", cardinality="SINGLE", timestamp=2000.0)
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "CockroachDB", "ep_3", cardinality="SINGLE", timestamp=3000.0)

    history = semantic_memory.get_entity_history(t_id, "Prod_DB")
    assert history["entity_name"] == "Prod_DB"
    assert history["total_transitions"] == 3
    assert history["active_facts_count"] == 1
    assert history["superseded_facts_count"] == 2

    timeline = history["timeline"]
    assert timeline[0]["object"] == "PostgreSQL"
    assert timeline[0]["status"] == "SUPERSEDED"
    assert timeline[0]["valid_to"] == 2000.0
    assert timeline[0]["invalidated_by_episode"] == "ep_2"

    assert timeline[1]["object"] == "FalkorDB"
    assert timeline[1]["status"] == "SUPERSEDED"
    assert timeline[1]["valid_to"] == 3000.0
    assert timeline[1]["invalidated_by_episode"] == "ep_3"

    assert timeline[2]["object"] == "CockroachDB"
    assert timeline[2]["status"] == "ACTIVE"
    assert timeline[2]["valid_to"] is None


def test_cytoscape_visual_dual_edge_and_null_guard(check_falkor):
    """TEST-TIMETRAVEL-05: Verifies Cytoscape serializer, dual styling, and leaf-node null guards."""
    t_id = "test-timetravel-05"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "PostgreSQL", "ep_1", cardinality="SINGLE", timestamp=1000.0)
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "FalkorDB", "ep_2", cardinality="SINGLE", timestamp=2000.0)

    # 1. include_invalidated=True at tau=2500.0
    cyto_all = semantic_memory.get_cytoscape_elements_as_of(t_id, as_of=2500.0, include_invalidated=True)
    nodes = cyto_all["nodes"]
    edges = cyto_all["edges"]

    # All nodes must have valid ids and labels
    node_ids = {n["data"]["id"] for n in nodes}
    assert "Prod_DB" in node_ids
    assert "PostgreSQL" in node_ids
    assert "FalkorDB" in node_ids

    # Edges must contain zero phantom null edges (e.g. leaf nodes with target=None)
    for edge in edges:
        ed = edge["data"]
        assert ed["source"] is not None
        assert ed["target"] is not None
        assert ed["label"] == "USES_TECH"

    # Must contain exactly 1 active solid green edge and 1 invalidated dashed red edge
    active_edges = [e for e in edges if e["data"]["status"] == "ACTIVE"]
    inv_edges = [e for e in edges if e["data"]["status"] == "INVALIDATED"]

    assert len(active_edges) == 1
    assert active_edges[0]["data"]["target"] == "FalkorDB"
    assert active_edges[0]["data"]["line_style"] == "solid"
    assert active_edges[0]["data"]["color"] == "#10b981"

    assert len(inv_edges) == 1
    assert inv_edges[0]["data"]["target"] == "PostgreSQL"
    assert inv_edges[0]["data"]["line_style"] == "dashed"
    assert inv_edges[0]["data"]["color"] == "#ef4444"

    # 2. include_invalidated=False must filter out invalidated edges
    cyto_active_only = semantic_memory.get_cytoscape_elements_as_of(t_id, as_of=2500.0, include_invalidated=False)
    assert len(cyto_active_only["edges"]) == 1
    assert cyto_active_only["edges"][0]["data"]["status"] == "ACTIVE"


def test_subsecond_precision_and_boundary_collisions(check_falkor):
    """TEST-TIMETRAVEL-06: Verifies half-open [ts, te) interval semantics at exact cutover boundary."""
    t_id = "test-timetravel-06"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # Cutover precisely at 2000.0
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "PostgreSQL", "ep_1", cardinality="SINGLE", timestamp=1000.0)
    semantic_memory.upsert_fact(t_id, "Prod_DB", "USES_TECH", "FalkorDB", "ep_2", cardinality="SINGLE", timestamp=2000.0)

    # In [ts, te) semantics:
    # At tau = 1999.999: PostgreSQL is ACTIVE (valid_to is 2000.0 > 1999.999)
    snap_before = semantic_memory.get_snapshot(t_id, as_of=1999.999)
    assert len(snap_before) == 1
    assert snap_before[0]["object"] == "PostgreSQL"

    # At exact cutover tau = 2000.0: PostgreSQL ceases to be active (valid_to = 2000.0 is not > 2000.0),
    # and FalkorDB becomes active (valid_from = 2000.0 <= 2000.0)
    snap_at = semantic_memory.get_snapshot(t_id, as_of=2000.0)
    assert len(snap_at) == 1
    assert snap_at[0]["object"] == "FalkorDB"

    # Zero duplicate active facts at the boundary
    objects_at = [f["object"] for f in snap_at]
    assert len(objects_at) == 1


def test_semantic_time_travel_rest_endpoints(check_falkor):
    """TEST-TIMETRAVEL-07: Validates REST endpoints for snapshot, history, time-travel, and cytoscape."""
    t_id = "test-timetravel-07"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # 1. POST /semantic/fact
    r1 = client.post(
        "/api/v1/memory/semantic/fact",
        json={
            "tenant_id": t_id,
            "subject": "Analytics_Engine",
            "predicate": "RUNS_ON",
            "object": "AWS_ECS",
            "episode_id": "ep_infra_01",
            "cardinality": "SINGLE",
            "timestamp": 1000.0,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "SUCCESS"

    r2 = client.post(
        "/api/v1/memory/semantic/fact",
        json={
            "tenant_id": t_id,
            "subject": "Analytics_Engine",
            "predicate": "RUNS_ON",
            "object": "GCP_GKE",
            "episode_id": "ep_infra_02",
            "cardinality": "SINGLE",
            "timestamp": 2000.0,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "SUCCESS"

    # 2. GET /semantic/snapshot
    snap_resp = client.get(f"/api/v1/memory/semantic/snapshot?tenant_id={t_id}&as_of=1500.0")
    assert snap_resp.status_code == 200
    snap_data = snap_resp.json()
    assert snap_data["fact_count"] == 1
    assert snap_data["facts"][0]["object"] == "AWS_ECS"

    # 3. GET /semantic/history/{entity_name}
    hist_resp = client.get(f"/api/v1/memory/semantic/history/Analytics_Engine?tenant_id={t_id}")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["status"] == "SUCCESS"
    assert hist_data["history"]["total_transitions"] == 2

    # 4. POST /semantic/time-travel
    sg_resp = client.post(
        "/api/v1/memory/semantic/time-travel",
        json={
            "tenant_id": t_id,
            "seed_entity": "Analytics_Engine",
            "as_of": 2500.0,
        },
    )
    assert sg_resp.status_code == 200
    sg_data = sg_resp.json()
    assert sg_data["status"] == "SUCCESS"
    assert "GCP_GKE" in sg_data["subgraph"]["neighbors"]

    # 5. GET /semantic/cytoscape
    cyto_resp = client.get(f"/api/v1/memory/semantic/cytoscape?tenant_id={t_id}&as_of=2500.0&include_invalidated=true")
    assert cyto_resp.status_code == 200
    cyto_data = cyto_resp.json()
    assert len(cyto_data["elements"]["nodes"]) >= 2
    assert len(cyto_data["elements"]["edges"]) == 2

    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

