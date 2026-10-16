"""Tests for Semantic Memory Phase 5: High-Concurrency Chaos, Benchmarks & Multi-Agent Orchestrator Wiring.

Verifies:
- TEST-SEM-CONC-01: 20 concurrent coroutines executing bi-temporal invalidation on identical entities simultaneously.
  Guarantees zero deadlocks, exactly 1 active edge (valid_to IS NULL), and 20 historical edges.
- TEST-SEM-ISOL-02: Multi-tenant boundary isolation under high concurrency (50 facts per tenant concurrently).
- TEST-SEM-TIME-03: Multi-epoch historical time-travel consistency across 5 migration milestones.
- TEST-SEM-HIPPO-04: 100-node synthetic scale-free knowledge graph HippoRAG performance benchmark (< 35ms).
- TEST-SEM-FALL-05: Degraded LLM fallback resilience with zero unhandled exceptions.
- TEST-SEM-ORCH-06: Multi-agent orchestrator dual cognitive recall and zero-copy Working Memory context pinning.
- TEST-SEM-API-07: REST coordination (/agents/run, /agents/stream) and semantic endpoints.
"""

import asyncio
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory
from app.agents.orchestrator import multi_agent_engine

client = TestClient(app)


@pytest.fixture(scope="module")
def ensure_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live concurrency stress tests.")


@pytest.mark.asyncio
async def test_concurrent_bitemporal_invalidations(ensure_falkor):
    """TEST-SEM-CONC-01: 20 concurrent coroutines invalidating the same entity simultaneously."""
    t_id = "test-sem-conc-01"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    base_t = 1000.0
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s_base",
        episode_id="ep_base",
        content="Baseline database deployment",
        timestamp=base_t,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="DatabaseEngine_Baseline",
        episode_id="ep_base",
        cardinality="SINGLE",
        timestamp=base_t,
        resolve_entities=False,
    )

    # 20 distinct variant names to prevent any fuzzy alias collision
    variants = [f"DatabaseEngine_Variant_{i:02d}" for i in range(20)]

    async def worker(idx: int, variant: str):
        t = base_t + (idx + 1) * 10.0
        ep_id = f"ep_worker_{idx}"
        episodic_memory.record_episode(
            tenant_id=t_id,
            session_id=f"s_{idx}",
            episode_id=ep_id,
            content=f"Migrated to {variant}",
            timestamp=t,
        )
        return await asyncio.to_thread(
            semantic_memory.upsert_fact,
            tenant_id=t_id,
            subject="Prod_DB",
            predicate="USES_TECH",
            new_object=variant,
            episode_id=ep_id,
            cardinality="SINGLE",
            timestamp=t,
            resolve_entities=False,
        )

    results = await asyncio.gather(*(worker(i, var) for i, var in enumerate(variants)))
    assert len(results) == 20

    # 1. Exactly 1 active edge remains
    res_active = falkor_router.query(
        "MATCH (s:Entity {name: 'Prod_DB'})-[r:RELATES_TO {predicate: 'USES_TECH'}]->(o:Entity) WHERE r.valid_to IS NULL RETURN count(r) AS cnt, o.name AS obj",
        tenant_id=t_id,
    )
    assert res_active.result_set[0][0] == 1, f"Expected 1 active edge, got {res_active.result_set[0][0]}"

    # 2. Exactly 20 historical edges exist (1 baseline + 19 superseded)
    res_hist = falkor_router.query(
        "MATCH (s:Entity {name: 'Prod_DB'})-[r:RELATES_TO {predicate: 'USES_TECH'}]->(o:Entity) WHERE r.valid_to IS NOT NULL RETURN count(r) AS cnt",
        tenant_id=t_id,
    )
    assert res_hist.result_set[0][0] == 20, f"Expected 20 historical edges, got {res_hist.result_set[0][0]}"

    # 3. Total edges = 21
    res_all = falkor_router.query(
        "MATCH (s:Entity {name: 'Prod_DB'})-[r:RELATES_TO {predicate: 'USES_TECH'}]->(o:Entity) RETURN count(r) AS cnt",
        tenant_id=t_id,
    )
    assert res_all.result_set[0][0] == 21


@pytest.mark.asyncio
async def test_cross_tenant_isolation_under_concurrency(ensure_falkor):
    """TEST-SEM-ISOL-02: 50 concurrent writes per tenant verifying zero cross-tenant contamination."""
    t1 = "test-tenant-acme"
    t2 = "test-tenant-nebula"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t1)
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t2)

    async def worker_acme(i: int):
        ep_id = f"ep_acme_{i}"
        return await asyncio.to_thread(
            semantic_memory.upsert_fact,
            tenant_id=t1,
            subject=f"Service_Acme_{i:02d}",
            predicate="CONNECTS_TO",
            new_object=f"Database_Acme_{i:02d}",
            episode_id=ep_id,
            cardinality="MULTI",
            timestamp=1000.0 + i,
            resolve_entities=False,
        )

    async def worker_nebula(i: int):
        ep_id = f"ep_nebula_{i}"
        return await asyncio.to_thread(
            semantic_memory.upsert_fact,
            tenant_id=t2,
            subject=f"Service_Nebula_{i:02d}",
            predicate="CONNECTS_TO",
            new_object=f"Database_Nebula_{i:02d}",
            episode_id=ep_id,
            cardinality="MULTI",
            timestamp=1000.0 + i,
            resolve_entities=False,
        )

    await asyncio.gather(
        *(worker_acme(i) for i in range(50)),
        *(worker_nebula(i) for i in range(50)),
    )

    # Verify acme-payments tenant isolation
    res_acme = falkor_router.query("MATCH (e:Entity) RETURN count(e) AS cnt, collect(e.name) AS names", tenant_id=t1)
    acme_names = set(res_acme.result_set[0][1])
    assert len(acme_names) == 100
    assert not any("Nebula" in name for name in acme_names)

    # Verify nebula-cloud tenant isolation
    res_nebula = falkor_router.query("MATCH (e:Entity) RETURN count(e) AS cnt, collect(e.name) AS names", tenant_id=t2)
    nebula_names = set(res_nebula.result_set[0][1])
    assert len(nebula_names) == 100
    assert not any("Acme" in name for name in nebula_names)


def test_multi_epoch_timetravel_consistency(ensure_falkor):
    """TEST-SEM-TIME-03: Multi-epoch historical time-travel consistency across 5 migration milestones."""
    t_id = "test-sem-time-03"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    milestones = [
        (1000.0, "PostgreSQL"),
        (2000.0, "MySQL"),
        (3000.0, "MongoDB"),
        (4000.0, "Redis"),
        (5000.0, "FalkorDB"),
    ]

    for ts, db_name in milestones:
        ep_id = f"ep_{int(ts)}"
        episodic_memory.record_episode(
            tenant_id=t_id,
            session_id="s1",
            episode_id=ep_id,
            content=f"Migrated Prod_DB to {db_name}",
            timestamp=ts,
        )
        semantic_memory.upsert_fact(
            tenant_id=t_id,
            subject="Prod_DB",
            predicate="USES_TECH",
            new_object=db_name,
            episode_id=ep_id,
            cardinality="SINGLE",
            timestamp=ts,
        )

    # Query snapshots at midpoints
    test_epochs = [
        (1500.0, "PostgreSQL"),
        (2500.0, "MySQL"),
        (3500.0, "MongoDB"),
        (4500.0, "Redis"),
        (5500.0, "FalkorDB"),
    ]

    for epoch, expected_db in test_epochs:
        snap = semantic_memory.get_snapshot(tenant_id=t_id, as_of=epoch)
        prod_facts = [f for f in snap if f["subject"] == "Prod_DB" and f["predicate"] == "USES_TECH"]
        assert len(prod_facts) == 1, f"Expected 1 fact at epoch {epoch}, got {len(prod_facts)}"
        assert prod_facts[0]["object"] == expected_db, f"Expected {expected_db} at epoch {epoch}, got {prod_facts[0]['object']}"


def test_synthetic_100_node_hipporag_ppr_benchmark(ensure_falkor):
    """TEST-SEM-HIPPO-04: 100-node synthetic knowledge graph benchmark measuring PPR runtime (< 35ms)."""
    t_id = "test-sem-hippo-04"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    now = 1000.0
    edges = []
    # Node_00 is hub connected to 14 nodes
    for i in range(1, 15):
        edges.append({"source": "Node_00", "target": f"Node_{i:02d}"})
    # Remaining nodes connected in scale-free mesh
    for i in range(1, 99):
        edges.append({"source": f"Node_{i:02d}", "target": f"Node_{i+1:02d}"})
        if i % 3 == 0 and i + 5 < 100:
            edges.append({"source": f"Node_{i:02d}", "target": f"Node_{i+5:02d}"})
        if i % 7 == 0 and i + 10 < 100:
            edges.append({"source": f"Node_{i:02d}", "target": f"Node_{i+10:02d}"})

    # Single batched Cypher insertion (< 25ms setup)
    batch_q = """
    UNWIND $edges AS e
    MERGE (s:Entity {name: e.source})
    ON CREATE SET s.id = e.source, s.created_at = $now
    MERGE (t:Entity {name: e.target})
    ON CREATE SET t.id = e.target, t.created_at = $now
    CREATE (s)-[:RELATES_TO {
        predicate: 'CONNECTS_TO',
        cardinality: 'MULTI',
        confidence: 1.0,
        valid_from: $now,
        valid_to: NULL
    }]->(t)
    """
    falkor_router.query(batch_q, {"edges": edges, "now": now}, tenant_id=t_id)

    # Time ONLY the HippoRAG associative retrieval call
    t0 = time.perf_counter()
    res = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        seed_entities=["Node_00"],
        max_hops=2,
        as_of=now + 500.0,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert res.status == "SUCCESS"
    assert len(res.ranked_entities) > 0
    assert res.ranked_entities[0].name == "Node_00"
    # Seed score exceeds downstream nodes
    assert res.ranked_entities[0].degree_normalized_score > res.ranked_entities[1].degree_normalized_score
    # Subgraph contains edges
    assert len(res.active_subgraph_edges) >= 14
    # Execution time must be < 35ms
    assert elapsed_ms < 35.0, f"HippoRAG took {elapsed_ms:.2f}ms on 100-node graph (expected < 35ms)"


def test_degraded_llm_fallback_resilience(ensure_falkor):
    """TEST-SEM-FALL-05: Ingest facts in heuristic/fallback mode with zero unhandled exceptions."""
    t_id = "test-sem-fall-05"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    text = "PaymentService microservice runs on AWS_ECS and connects to Redis_Cluster and PostgresDB."
    facts = semantic_memory.extract_facts(text)
    assert len(facts.triples) >= 2

    ep_id = "ep_fallback_01"
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s1",
        episode_id=ep_id,
        content=text,
        timestamp=1000.0,
    )

    for tr in facts.triples:
        res = semantic_memory.upsert_fact(
            tenant_id=t_id,
            subject=tr.subject,
            predicate=tr.predicate,
            new_object=tr.object,
            episode_id=ep_id,
            confidence=tr.confidence,
            cardinality=tr.cardinality,
            subject_type=tr.subject_type,
            object_type=tr.object_type,
            timestamp=1000.0,
        )
        assert res["subject"] == tr.subject

    snap = semantic_memory.get_snapshot(tenant_id=t_id, as_of=1500.0)
    assert len(snap) >= 2


@pytest.mark.asyncio
async def test_orchestrator_dual_cognitive_recall_and_context_pinning(ensure_falkor):
    """TEST-SEM-ORCH-06: Verifies orchestrator dual cognitive recall and zero-copy Working Memory context pinning."""
    t_id = "test-sem-orch-06"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # Pre-seed historical episode and semantic relation
    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id="s_arch",
        episode_id="ep_arch_01",
        content="Primary infrastructure: Prod_DB running on FalkorDB graph engine.",
        importance_score=0.95,
        timestamp=1000.0,
    )
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Prod_DB",
        predicate="USES_TECH",
        new_object="FalkorDB",
        episode_id="ep_arch_01",
        cardinality="SINGLE",
        timestamp=1000.0,
    )

    # Run multi-agent execution stream
    events = []
    async for event in multi_agent_engine.execute_task_stream(
        tenant_id=t_id,
        session_id="s_live",
        user_prompt="Check database latency on Prod_DB and verify FalkorDB connection.",
    ):
        events.append(event)

    event_types = [e.get("type") for e in events]
    assert "episodic_retrieval_event" in event_types
    assert "hipporag_event" in event_types

    # Verify HippoRAG event contents
    hippo_ev = next(e for e in events if e.get("type") == "hipporag_event")
    assert "Prod_DB" in hippo_ev.get("seeds", [])
    assert len(hippo_ev.get("ranked_entities", [])) >= 1

    # Verify SubTask 2 inherited context
    st2_ev = next(
        e for e in events
        if e.get("type") == "agent_event" and e.get("phase") == "claim" and "SubTask 2" in e.get("message", "")
    )
    assert "inherited_context" in st2_ev
    assert len(st2_ev["inherited_context"]) >= 2

    # Verify Working Memory blackboard [:PINNED_CONTEXT] edges exist
    pinned_res = falkor_router.query(
        "MATCH (st:SubTask)-[:PINNED_CONTEXT]->(target) RETURN target.id AS id, target.name AS name",
        tenant_id=t_id,
    )
    assert pinned_res and len(pinned_res.result_set) >= 2
    all_pinned_identifiers = [str(val) for row in pinned_res.result_set for val in row if val]
    assert any("ep_" in ident for ident in all_pinned_identifiers)
    assert any("Prod_DB" in ident for ident in all_pinned_identifiers)



def test_routes_coordination_and_semantic_endpoints(ensure_falkor):
    """TEST-SEM-API-07: Validates /agents/run, /agents/stream, /semantic/fact, and /fact endpoints."""
    t_id = "test-sem-api-07"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)

    # 1. POST /api/v1/memory/semantic/fact
    r_fact = client.post(
        "/api/v1/memory/semantic/fact",
        json={
            "tenant_id": t_id,
            "subject": "Payment_Service",
            "predicate": "CONNECTS_TO",
            "object": "Stripe_API",
            "episode_id": "ep_api_01",
            "cardinality": "MULTI",
        },
    )
    assert r_fact.status_code == 200
    assert r_fact.json()["status"] == "SUCCESS"

    # 2. POST /api/v1/memory/fact (legacy)
    r_fact_legacy = client.post(
        "/api/v1/memory/fact",
        json={
            "tenant_id": t_id,
            "subject": "Order_Service",
            "predicate": "USES_TECH",
            "object": "Kafka",
            "episode_id": "ep_api_02",
            "cardinality": "SINGLE",
        },
    )
    assert r_fact_legacy.status_code == 200

    # 3. POST /api/v1/agents/run
    r_agent = client.post(
        "/api/v1/agents/run",
        json={
            "tenant_id": t_id,
            "prompt": "Check database status for Payment_Service.",
        },
    )
    assert r_agent.status_code == 200
    data = r_agent.json()
    assert data["status"] == "SUCCESS"
    assert len(data["events"]) >= 5

    # 4. POST /api/v1/agents/stream
    r_stream = client.post(
        "/api/v1/agents/stream",
        json={
            "tenant_id": t_id,
            "prompt": "Check status.",
        },
    )
    assert r_stream.status_code == 200
    assert "text/event-stream" in r_stream.headers["content-type"]
