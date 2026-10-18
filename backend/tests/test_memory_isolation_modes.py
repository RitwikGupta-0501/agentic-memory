"""Tests for Enterprise Memory Isolation (Model B) and Judge Testing Console Modes.

Verifies:
1. tenant_shared (Enterprise Model B - Default):
   - Private user episodic chat turns (Bob cannot retrieve Alice's raw chats).
   - Shared semantic knowledge (Bob can retrieve tenant facts introduced by Alice).
2. user_strict (Strict Zero-Knowledge Sandbox):
   - Bob cannot retrieve Alice's chats OR Alice's entities.
3. team_open (Open Team Collaboration):
   - All tenant chat turns and entities are mutually accessible.
"""

import time
import uuid
import pytest
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory


@pytest.fixture
def isolation_tenant():
    t_id = f"test_iso_{uuid.uuid4().hex[:8]}"
    yield t_id
    try:
        falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)
    except Exception:
        pass


def test_episodic_isolation_tenant_shared_vs_team_open(isolation_tenant):
    """Verifies that in tenant_shared, Bob cannot retrieve Alice's private chat episodes,
    while in team_open, Bob can access Alice's chat episodes."""
    t_id = isolation_tenant
    alice_session = f"sess_alice_{uuid.uuid4().hex[:6]}"
    bob_session = f"sess_bob_{uuid.uuid4().hex[:6]}"

    # Alice records a private episode
    alice_ep = episodic_memory.record_episode(
        tenant_id=t_id,
        session_id=alice_session,
        content="Secret Alice project is codenamed Chimera.",
        role="user",
        user_id="alice",
    )
    assert alice_ep["id"] is not None

    # 1. Bob searches under tenant_shared (Enterprise Model B)
    bob_results_shared = episodic_memory.retrieve_episodes(
        tenant_id=t_id,
        query="What is the secret project codename Chimera?",
        session_id=bob_session,
        cross_session=True,
        user_id="bob",
        isolation_mode="tenant_shared",
    )
    # Bob should receive ZERO results from Alice's private chats
    assert len(bob_results_shared) == 0

    # 2. Alice searches under tenant_shared
    alice_results = episodic_memory.retrieve_episodes(
        tenant_id=t_id,
        query="What is the secret project codename Chimera?",
        session_id=alice_session,
        cross_session=True,
        user_id="alice",
        isolation_mode="tenant_shared",
    )
    # Alice CAN retrieve her own episode
    assert len(alice_results) >= 1
    assert alice_results[0]["episode"]["id"] == alice_ep["id"]

    # 3. Bob searches under team_open (Open Team Collaboration)
    bob_results_open = episodic_memory.retrieve_episodes(
        tenant_id=t_id,
        query="What is the secret project codename Chimera?",
        session_id=bob_session,
        cross_session=True,
        user_id="bob",
        isolation_mode="team_open",
    )
    # In team_open, Bob CAN retrieve Alice's episode
    assert len(bob_results_open) >= 1
    assert bob_results_open[0]["episode"]["id"] == alice_ep["id"]


def test_semantic_knowledge_sharing_and_strict_sandbox(isolation_tenant):
    """Verifies that in tenant_shared, Alice's semantic facts are accessible to Bob,
    whereas in user_strict mode, Bob has a zero-knowledge sandbox."""
    t_id = isolation_tenant
    alice_ep_id = f"ep_alice_{uuid.uuid4().hex[:6]}"

    # Alice introduces a company factual assertion
    semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject="Payment_Gateway",
        predicate="USES_TECH",
        new_object="PostgreSQL_Cluster",
        episode_id=alice_ep_id,
        confidence=1.0,
        cardinality="SINGLE",
        subject_type="Service",
        object_type="Database",
        user_id="alice",
    )

    # 1. Bob executes HippoRAG associative retrieval under tenant_shared (Model B)
    hippo_shared = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        query="Payment_Gateway database tech",
        seed_entities=["Payment_Gateway"],
        user_id="bob",
        isolation_mode="tenant_shared",
    )
    assert hippo_shared.status == "SUCCESS"
    matched_entity_names = [e.name for e in hippo_shared.ranked_entities]
    assert "Payment_Gateway" in matched_entity_names
    # Semantic relation is visible to Bob in tenant_shared
    assert len(hippo_shared.active_subgraph_edges) >= 1

    # 2. Bob executes HippoRAG under user_strict (Strict per-user sandbox)
    hippo_strict = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        query="Payment_Gateway database tech",
        seed_entities=["Payment_Gateway"],
        user_id="bob",
        isolation_mode="user_strict",
    )
    # In user_strict, Bob cannot traverse edges created by Alice
    assert len(hippo_strict.active_subgraph_edges) == 0


def test_session_history_isolation(isolation_tenant):
    """Verifies that GET session history respects user ownership."""
    t_id = isolation_tenant
    alice_session = f"sess_alice_{uuid.uuid4().hex[:6]}"

    episodic_memory.record_episode(
        tenant_id=t_id,
        session_id=alice_session,
        content="Alice confidential message",
        role="user",
        user_id="alice",
    )

    # Bob requests Alice's session in tenant_shared
    bob_view = episodic_memory.get_session_history(
        tenant_id=t_id,
        session_id=alice_session,
        user_id="bob",
        isolation_mode="tenant_shared",
    )
    assert len(bob_view) == 0

    # Alice requests her session in tenant_shared
    alice_view = episodic_memory.get_session_history(
        tenant_id=t_id,
        session_id=alice_session,
        user_id="alice",
        isolation_mode="tenant_shared",
    )
    assert len(alice_view) == 1
    assert alice_view[0]["content"] == "Alice confidential message"

    # Bob requests Alice's session in team_open
    bob_open_view = episodic_memory.get_session_history(
        tenant_id=t_id,
        session_id=alice_session,
        user_id="bob",
        isolation_mode="team_open",
    )
    assert len(bob_open_view) == 1


def test_api_graph_and_sessions_isolation(isolation_tenant):
    """Verifies GET /api/v1/memory/graph and GET /api/v1/memory/sessions endpoints."""
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    t_id = isolation_tenant
    alice_session = f"sess_alice_{uuid.uuid4().hex[:6]}"
    bob_session = f"sess_bob_{uuid.uuid4().hex[:6]}"

    # Alice creates a session and turn
    client.post(
        "/api/v1/memory/episode",
        json={
            "tenant_id": t_id,
            "session_id": alice_session,
            "content": "Alice turn in graph",
            "user_id": "alice",
        },
    )

    # Bob creates a session and turn
    client.post(
        "/api/v1/memory/episode",
        json={
            "tenant_id": t_id,
            "session_id": bob_session,
            "content": "Bob turn in graph",
            "user_id": "bob",
        },
    )

    # Alice adds a semantic fact
    client.post(
        "/api/v1/memory/semantic/fact",
        json={
            "tenant_id": t_id,
            "subject": "Cache_Layer",
            "predicate": "USES_TECH",
            "object": "Redis_Cluster",
            "episode_id": "ep_alice_test",
            "user_id": "alice",
        },
    )

    # Test GET /sessions under tenant_shared
    res_alice_sessions = client.get(f"/api/v1/memory/sessions?tenant_id={t_id}&user_id=alice&isolation_mode=tenant_shared")
    assert res_alice_sessions.status_code == 200
    alice_sids = [s["id"] for s in res_alice_sessions.json()]
    assert alice_session in alice_sids
    assert bob_session not in alice_sids

    res_bob_sessions = client.get(f"/api/v1/memory/sessions?tenant_id={t_id}&user_id=bob&isolation_mode=tenant_shared")
    assert res_bob_sessions.status_code == 200
    bob_sids = [s["id"] for s in res_bob_sessions.json()]
    assert bob_session in bob_sids
    assert alice_session not in bob_sids

    # Test GET /sessions under team_open
    res_open_sessions = client.get(f"/api/v1/memory/sessions?tenant_id={t_id}&user_id=bob&isolation_mode=team_open")
    assert res_open_sessions.status_code == 200
    open_sids = [s["id"] for s in res_open_sessions.json()]
    assert alice_session in open_sids
    assert bob_session in open_sids

    # Test GET /graph under tenant_shared for Bob:
    # Bob should see the shared Cache_Layer entity, but NOT Alice's Episode/Session
    res_bob_graph = client.get(f"/api/v1/memory/graph?tenant_id={t_id}&user_id=bob&isolation_mode=tenant_shared")
    assert res_bob_graph.status_code == 200
    bob_nodes = res_bob_graph.json()["nodes"]
    bob_labels = [n["data"]["label"] for n in bob_nodes]
    bob_scopes = [n["data"].get("scope") for n in bob_nodes]

    # Shared entity is visible
    assert any("Cache_Layer" in l for l in bob_labels)
    # Alice's private turn is hidden
    assert not any("Alice turn" in l for l in bob_labels)
    # Bob's private turn is visible
    assert any("Bob turn" in l for l in bob_labels)

