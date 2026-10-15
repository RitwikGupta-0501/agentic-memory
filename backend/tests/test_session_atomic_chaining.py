"""Tests for Phase 2: Zero-Race Atomic Chaining & Multi-Session Topology."""

import asyncio
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory

client = TestClient(app)


@pytest.fixture(scope="module")
def ensure_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live concurrency test.")


@pytest.mark.asyncio
async def test_concurrent_20_episode_atomic_chaining(ensure_falkor):
    """Spawns 20 concurrent coroutines appending to the same session and verifies a single linear chain."""
    tenant_id = "test-concurrency-tenant"
    session_id = "sess_race_test_01"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant_id)

    async def worker(idx: int):
        return await asyncio.to_thread(
            episodic_memory.record_episode,
            tenant_id=tenant_id,
            session_id=session_id,
            content=f"Concurrent agent event #{idx}",
            role="agent",
            actor_id=f"agent_{idx}",
        )

    results = await asyncio.gather(*(worker(i) for i in range(20)))
    assert len(results) == 20
    # Verify each result has seq_num and id
    for r in results:
        assert r["id"].startswith("ep_")
        assert r["seq_num"] >= 1

    # 1. Verify exactly 20 episodes exist in this session
    cnt_res = falkor_router.query(
        "MATCH (ep:Episode {session_id: $sid}) RETURN count(ep)",
        {"sid": session_id},
        tenant_id=tenant_id,
    )
    assert cnt_res.result_set[0][0] == 20

    # 2. Verify zero bifurcations (no episode has >1 outgoing NEXT_EPISODE edge)
    fork_res = falkor_router.query(
        """
        MATCH (ep:Episode {session_id: $sid})-[r:NEXT_EPISODE]->()
        WITH ep, count(r) AS out_deg
        WHERE out_deg > 1
        RETURN count(ep)
        """,
        {"sid": session_id},
        tenant_id=tenant_id,
    )
    assert fork_res.result_set[0][0] == 0

    # 3. Verify Session Head -> Session Tail path length is exactly 19 hops (20 nodes)
    path_res = falkor_router.query(
        """
        MATCH (s:Session {id: $sid})-[:SESSION_HEAD]->(head:Episode),
              (s)-[:SESSION_TAIL]->(tail:Episode),
              path = (head)-[:NEXT_EPISODE*19]->(tail)
        RETURN length(path), s.episode_count
        """,
        {"sid": session_id},
        tenant_id=tenant_id,
    )
    assert len(path_res.result_set) == 1
    assert path_res.result_set[0][0] == 19
    assert path_res.result_set[0][1] == 20

    # Clean up
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant_id)


def test_parent_session_lineage_and_head_tail(ensure_falkor):
    """Verifies parent session linking and multi-session ancestry traversal in O(1) pointer hops."""
    tenant_id = "test-session-lineage-tenant"
    parent_sess = "sess_parent_order_01"
    child_sess = "sess_child_delivery_01"
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant_id)

    # 1. Ingest 3 episodes into Parent Session
    ep_p1 = episodic_memory.record_episode(
        tenant_id=tenant_id,
        session_id=parent_sess,
        content="Order #9001 placed for item A",
        role="user",
    )
    episodic_memory.record_episode(
        tenant_id=tenant_id,
        session_id=parent_sess,
        content="Payment processed for order #9001",
        role="agent",
    )
    ep_p3 = episodic_memory.record_episode(
        tenant_id=tenant_id,
        session_id=parent_sess,
        content="Order #9001 packed and sent to fulfillment center",
        role="agent",
    )

    # 2. Ingest 2 episodes into Child Session linked via parent_session_id
    episodic_memory.record_episode(
        tenant_id=tenant_id,
        session_id=child_sess,
        parent_session_id=parent_sess,
        content="Delivery dispatch driver assigned for order #9001",
        role="agent",
    )
    episodic_memory.record_episode(
        tenant_id=tenant_id,
        session_id=child_sess,
        parent_session_id=parent_sess,
        content="Package delivered to customer doorstep",
        role="agent",
    )

    # 3. Query Lineage from Child Session
    lineage = episodic_memory.get_session_lineage(tenant_id=tenant_id, session_id=child_sess)
    assert len(lineage) >= 2  # child and parent

    # Find the parent in lineage
    parent_entry = next((item for item in lineage if item["session_id"] == parent_sess), None)
    assert parent_entry is not None
    assert parent_entry["episode_count"] == 3
    assert parent_entry["head_episode_id"] == ep_p1["id"]
    assert parent_entry["tail_episode_id"] == ep_p3["id"]
    assert "packed and sent to fulfillment" in parent_entry["tail_summary"]

    # 4. Test REST API endpoint
    response = client.get(
        f"/api/v1/memory/sessions/lineage?tenant_id={tenant_id}&session_id={child_sess}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == child_sess
    assert data["lineage_count"] >= 2

    # 5. Test Cytoscape rendering for :Session nodes
    graph_res = client.get(f"/api/v1/memory/graph?tenant_id={tenant_id}")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    session_nodes = [
        n for n in graph_data["nodes"]
        if "Session" in n["data"].get("labels", [])
    ]
    assert len(session_nodes) >= 2
    for sn in session_nodes:
        assert sn["data"]["tier"] == "episodic"
        assert sn["data"]["label"].startswith("Session: ")

    # Clean up
    falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=tenant_id)
