import time
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.embeddings import embedding_service
from app.core.embeddings.reindexer import reindex_tenant_embeddings
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
from app.memory.importance import importance_scorer
from app.memory.semantic import semantic_memory, EntityTriple, FactExtractionResult
from app.memory.working import working_memory, SubTaskSpec
from app.memory.procedural import procedural_memory, ActionStepSpec

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])



class FactUpsertRequest(BaseModel):
    tenant_id: Optional[str] = None
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    episode_id: Optional[str] = "ep_manual"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    cardinality: str = "SINGLE"
    subject_type: str = "Entity"
    object_type: str = "Entity"
    user_id: Optional[str] = None
    timestamp: Optional[float] = Field(default=None, description="Explicit event timestamp; None = system time.time()")



class HippoRAGRequest(BaseModel):
    tenant_id: Optional[str] = None
    seed_entities: Optional[List[str]] = None
    query: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=50)
    damping: float = Field(default=0.85, ge=0.1, le=0.99)
    max_hops: int = Field(default=2, ge=1, le=3)
    as_of: Optional[float] = None
    user_id: Optional[str] = None


class EpisodeCreateRequest(BaseModel):
    tenant_id: Optional[str] = None
    session_id: str
    parent_session_id: Optional[str] = None
    content: str
    role: str = "user"
    actor_id: str = "user"
    status: str = "SUCCESS"
    structured_payload: Optional[Dict[str, Any]] = None
    importance_score: Optional[float] = None
    utility_score: Optional[float] = None
    vcache_threshold: float = 0.78
    token_count: Optional[int] = None
    user_id: Optional[str] = None


class EpisodeSearchRequest(BaseModel):
    tenant_id: Optional[str] = None
    query: str
    session_id: Optional[str] = None
    cross_session: bool = False
    candidate_limit: int = 10
    min_similarity: Optional[float] = None
    user_id: Optional[str] = None


class ReindexRequest(BaseModel):
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    batch_size: int = 50


class EpisodeFeedbackRequest(BaseModel):
    tenant_id: Optional[str] = None
    episode_id: str
    reward: float
    alpha: float = 0.2
    user_id: Optional[str] = None


class ImportanceEvaluateRequest(BaseModel):
    content: str
    role: str = "user"
    status: str = "SUCCESS"
    structured_payload: Optional[Dict[str, Any]] = None


class EpisodeRetrieveRequest(BaseModel):
    tenant_id: Optional[str] = None
    query: str
    session_id: Optional[str] = None
    top_k: int = 5
    candidate_limit: int = 25
    cross_session: bool = False
    alpha: float = 1.0
    beta: float = 1.0
    gamma: float = 1.0
    decay_lambda: float = 0.0001925
    strict_vcache: bool = False
    touch_recall: bool = True
    user_id: Optional[str] = None
    isolation_mode: Optional[str] = "tenant_shared"


@router.get("/graph")
def get_graph_data(
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
    isolation_mode: str = Query(default="tenant_shared"),
    include_invalidated: bool = Query(default=True),
) -> Dict[str, Any]:
    """Returns all nodes and edges formatted for Cytoscape.js rendering."""
    # Query all nodes and edges
    query = """
    MATCH (n)
    OPTIONAL MATCH (n)-[r]->(m)
    RETURN n, id(n) AS nid, labels(n) AS nlabels,
           r, id(r) AS rid, type(r) AS rtype, id(m) AS target_id
    """
    try:
        res = falkor_router.query(query, tenant_id=tenant_id, user_id=user_id)
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    nodes_map = {}
    edges_list = []

    if res and res.result_set:
        for row in res.result_set:
            node = row[0]
            nid = str(row[1])
            labels = row[2] or []
            rel = row[3]
            rid = str(row[4]) if row[4] is not None else None
            rtype = row[5]
            target_id = str(row[6]) if row[6] is not None else None

            # Skip internal bookkeeping metadata nodes from visualizer
            if "GraphMetadata" in labels:
                continue

            props = getattr(node, "properties", {}) if node else {}
            node_user = props.get("user_id")

            # Memory Isolation filtering for Graph Visualizer:
            if isolation_mode == "user_strict":
                if user_id and node_user and node_user != user_id:
                    continue
            elif isolation_mode == "tenant_shared":
                # In tenant_shared: Episodes and Sessions are private to the author.
                # Semantic entities, Procedures, and Working memory are shared across the tenant.
                if ("Episode" in labels or "Session" in labels) and user_id and node_user and node_user != user_id:
                    continue

            # Determine Tier category for color coding
            tier = "unknown"
            node_label = "Node"

            # Compute scope badge
            if "Episode" in labels or "Session" in labels:
                scope = f"private:{node_user or 'user'}"
            else:
                scope = "shared"

            if "TaskRun" in labels or "SubTask" in labels:
                tier = "working"  # Yellow
                title = props.get("title") or props.get("goal") or props.get("id", "Task")
                node_label = (title[:24] + "…") if len(title) > 24 else title
            elif "Episode" in labels or "Session" in labels:
                tier = "episodic"  # Blue
                if "Session" in labels:
                    count = props.get("episode_count", 0)
                    sid = str(props.get("id", ""))
                    short_id = sid[-6:] if len(sid) >= 6 else sid
                    node_label = f"Session: {short_id} ({count} turns)"
                else:
                    role = str(props.get("role", "turn")).capitalize()
                    content = str(props.get("content", "")).strip()
                    if content:
                        preview = (content[:22] + "…") if len(content) > 22 else content
                        node_label = f"{role}: \"{preview}\""
                    else:
                        node_label = f"{role} Turn"
            elif "Entity" in labels:
                tier = "semantic"  # Green
                name = props.get("name") or props.get("canonical_name") or "Entity"
                etype = props.get("type")
                node_label = f"{name} ({etype})" if etype else name
            elif "Procedure" in labels or "ActionStep" in labels or "Guardrail" in labels:
                tier = "procedural"  # Purple
                name = props.get("name") or props.get("rule_text") or props.get("id", "Guardrail")
                node_label = (name[:24] + "…") if len(name) > 24 else name
            elif "ConsolidatedInsight" in labels:
                tier = "consolidated"
                node_label = f"Insight: {props.get('id', '')}"

            if nid not in nodes_map and node is not None:
                nodes_map[nid] = {
                    "data": {
                        "id": nid,
                        "label": node_label,
                        "tier": tier,
                        "labels": labels,
                        "properties": props,
                        "user_id": node_user,
                        "scope": scope,
                    }
                }

            if rel is not None and target_id is not None:
                r_props = getattr(rel, "properties", {})
                valid_to = r_props.get("valid_to")
                is_superseded = valid_to is not None

                # Filter out superseded edges if include_invalidated is false
                if not include_invalidated and is_superseded:
                    continue

                edges_list.append({
                    "data": {
                        "id": f"e_{rid}",
                        "source": nid,
                        "target": target_id,
                        "label": rtype,
                        "predicate": r_props.get("predicate", rtype),
                        "valid_from": r_props.get("valid_from"),
                        "valid_to": valid_to,
                        "is_superseded": is_superseded,
                    }
                })

    # Only retain edges whose endpoints are both in nodes_map
    valid_edges = [
        e for e in edges_list
        if e["data"]["source"] in nodes_map and e["data"]["target"] in nodes_map
    ]

    return {
        "tenant_id": tenant_id,
        "isolation_mode": isolation_mode,
        "nodes": list(nodes_map.values()),
        "edges": valid_edges,
    }


@router.post("/fact")
def upsert_semantic_fact(req: FactUpsertRequest) -> Dict[str, Any]:
    """Executes bi-temporal conflict resolution and inserts a fact."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject=req.subject,
        predicate=req.predicate,
        new_object=req.object,
        episode_id=req.episode_id or "ep_manual",
        confidence=req.confidence,
        cardinality=req.cardinality,
        subject_type=req.subject_type,
        object_type=req.object_type,
        user_id=req.user_id,
        timestamp=req.timestamp,
    )
    return res



@router.post("/hipporag")
@router.post("/semantic/hipporag")
def hipporag_retrieval(req: HippoRAGRequest) -> Dict[str, Any]:
    """Executes HippoRAG neurobiologically-inspired associative recall."""
    t_id = req.tenant_id or settings.default_tenant_id
    result = semantic_memory.hipporag_retrieve(
        tenant_id=t_id,
        query=req.query,
        seed_entities=req.seed_entities,
        top_k=req.top_k,
        damping=req.damping,
        max_hops=req.max_hops,
        as_of=req.as_of,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": result.status,
        "result": result.model_dump(),
        "seeds": result.seeds,
        "matches": [e.model_dump() for e in result.ranked_entities],
    }


@router.get("/embedding-status")
def get_embedding_status(
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Returns active embedding provider info and FalkorDB drift status."""
    provider_info = embedding_service.get_info()
    drift_info = falkor_router.check_graph_embedding_drift(tenant_id=tenant_id, user_id=user_id)
    return {
        "tenant_id": tenant_id,
        "provider": provider_info,
        "drift": drift_info,
    }


@router.post("/reindex")
def reindex_embeddings(req: ReindexRequest) -> Dict[str, Any]:
    """Reindexes all episodic nodes in a tenant's graph using the current active embedding provider."""
    t_id = req.tenant_id or settings.default_tenant_id
    summary = reindex_tenant_embeddings(
        tenant_id=t_id,
        batch_size=req.batch_size,
    )
    return {
        "status": "SUCCESS",
        "summary": summary,
    }


@router.post("/episode")
def create_episode(req: EpisodeCreateRequest) -> Dict[str, Any]:
    """Ingests an episode into the episodic memory graph with vector embedding and chaining."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = episodic_memory.record_episode(
        tenant_id=t_id,
        session_id=req.session_id,
        content=req.content,
        role=req.role,
        actor_id=req.actor_id,
        status=req.status,
        structured_payload=req.structured_payload,
        importance_score=req.importance_score,
        utility_score=req.utility_score,
        vcache_threshold=req.vcache_threshold,
        token_count=req.token_count,
        user_id=req.user_id,
        parent_session_id=req.parent_session_id,
    )
    return res


@router.get("/sessions")
def list_sessions(
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
    isolation_mode: str = Query(default="tenant_shared"),
    limit: int = Query(default=50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    """Lists available conversation sessions for a tenant/user ordered by activity."""
    if isolation_mode == "team_open":
        query = """
        MATCH (s:Session)
        RETURN s.id AS id,
               s.created_at AS created_at,
               s.updated_at AS updated_at,
               s.episode_count AS episode_count,
               s.user_id AS user_id,
               s.tenant_id AS tenant_id
        ORDER BY s.updated_at DESC
        LIMIT $limit
        """
        params = {"limit": limit}
    else:
        query = """
        MATCH (s:Session)
        WHERE ($user_id IS NULL OR s.user_id = $user_id OR s.user_id IS NULL)
        RETURN s.id AS id,
               s.created_at AS created_at,
               s.updated_at AS updated_at,
               s.episode_count AS episode_count,
               s.user_id AS user_id,
               s.tenant_id AS tenant_id
        ORDER BY s.updated_at DESC
        LIMIT $limit
        """
        params = {"user_id": user_id, "limit": limit}

    try:
        res = falkor_router.query(
            query,
            tenant_id=tenant_id,
            user_id=user_id,
            params=params,
        )
        sessions = []
        if res and res.result_set:
            for row in res.result_set:
                sessions.append({
                    "id": str(row[0]),
                    "created_at": row[1],
                    "updated_at": row[2],
                    "episode_count": row[3] or 0,
                    "user_id": row[4],
                    "tenant_id": row[5],
                })
        return sessions
    except Exception as e:
        return []


class SessionLinkRequest(BaseModel):
    child_session_id: str
    parent_session_id: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/sessions/link")
def link_sessions(req: SessionLinkRequest) -> Dict[str, Any]:
    """Explicitly links a child session to a parent session with [:PARENT_SESSION]."""
    t_id = req.tenant_id or settings.default_tenant_id
    query = """
    MERGE (child:Session {id: $child_id})
    MERGE (parent:Session {id: $parent_id})
    MERGE (child)-[r:PARENT_SESSION]->(parent)
    ON CREATE SET r.linked_at = timestamp() / 1000.0
    RETURN child.id AS child_id, parent.id AS parent_id, type(r) AS rel_type
    """
    try:
        res = falkor_router.query(
            query,
            tenant_id=t_id,
            user_id=req.user_id,
            params={"child_id": req.child_session_id, "parent_id": req.parent_session_id},
        )
        return {
            "status": "SUCCESS",
            "child_session_id": req.child_session_id,
            "parent_session_id": req.parent_session_id,
            "relationship": "PARENT_SESSION",
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


@router.get("/episodes")
def get_episodes(
    session_id: str = Query(..., description="Session identifier for chronological history"),
    tenant_id: str = Query(default=settings.default_tenant_id),
    limit: int = Query(default=50, ge=1, le=500),
    user_id: Optional[str] = Query(default=None),
    isolation_mode: str = Query(default="tenant_shared"),
) -> List[Dict[str, Any]]:
    """Retrieves chronological episodes for a session."""
    return episodic_memory.get_session_history(
        tenant_id=tenant_id,
        session_id=session_id,
        limit=limit,
        user_id=user_id,
        isolation_mode=isolation_mode,
    )


@router.get("/sessions/lineage")
def get_session_lineage_endpoint(
    session_id: str = Query(..., description="Target session identifier"),
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Returns session hierarchy ancestry tree and head/tail anchors in O(1) pointer hops."""
    t_id = tenant_id or settings.default_tenant_id
    lineage = episodic_memory.get_session_lineage(
        tenant_id=t_id,
        session_id=session_id,
        user_id=user_id,
    )
    return {
        "tenant_id": t_id,
        "session_id": session_id,
        "lineage_count": len(lineage),
        "ancestors": lineage,
    }


@router.post("/episodes/search")
def search_episodes(req: EpisodeSearchRequest) -> Dict[str, Any]:
    """Performs vector similarity search on episodic memory candidates."""
    t_id = req.tenant_id or settings.default_tenant_id
    results = episodic_memory.search_episodes(
        tenant_id=t_id,
        query=req.query,
        session_id=req.session_id,
        candidate_limit=req.candidate_limit,
        cross_session=req.cross_session,
        min_similarity=req.min_similarity,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "query": req.query,
        "results_count": len(results),
        "episodes": results,
    }


@router.post("/episode/feedback")
def update_episode_feedback_endpoint(req: EpisodeFeedbackRequest) -> Dict[str, Any]:
    """Updates an episode's utility score (MemRL) and decision threshold (vCache) post-execution."""
    t_id = req.tenant_id or settings.default_tenant_id
    return episodic_memory.update_episode_feedback(
        tenant_id=t_id,
        episode_id=req.episode_id,
        reward=req.reward,
        alpha=req.alpha,
        user_id=req.user_id,
    )


@router.post("/importance/evaluate")
def evaluate_importance_endpoint(req: ImportanceEvaluateRequest) -> Dict[str, Any]:
    """Evaluates cognitive importance score using Stage 1 heuristics and Stage 2 LLM/entropy reflection."""
    return importance_scorer.evaluate(
        content=req.content,
        role=req.role,
        status=req.status,
        structured_payload=req.structured_payload,
    )


@router.post("/episodes/retrieve")
def retrieve_episodes_endpoint(req: EpisodeRetrieveRequest) -> Dict[str, Any]:
    """Retrieves ranked episodic memories using Stanford Generative Agents 3-factor composite scoring."""
    t_id = req.tenant_id or settings.default_tenant_id
    results = episodic_memory.retrieve_episodes(
        tenant_id=t_id,
        query=req.query,
        session_id=req.session_id,
        top_k=req.top_k,
        candidate_limit=req.candidate_limit,
        cross_session=req.cross_session,
        alpha=req.alpha,
        beta=req.beta,
        gamma=req.gamma,
        decay_lambda=req.decay_lambda,
        strict_vcache=req.strict_vcache,
        touch_recall=req.touch_recall,
        user_id=req.user_id,
        isolation_mode=req.isolation_mode or "tenant_shared",
    )
    return {
        "tenant_id": t_id,
        "query": req.query,
        "top_k": req.top_k,
        "results_count": len(results),
        "episodes": results,
    }


class EntityCreateRequest(BaseModel):
    tenant_id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=128)
    type: str = "Concept"
    description: Optional[str] = None
    embedding: Optional[List[float]] = None
    user_id: Optional[str] = None


class EntitySearchRequest(BaseModel):
    tenant_id: Optional[str] = None
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=50)
    user_id: Optional[str] = None


class SemanticFactRequest(BaseModel):
    tenant_id: Optional[str] = None
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    episode_id: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    cardinality: str = "SINGLE"
    subject_type: str = "Entity"
    object_type: str = "Entity"
    user_id: Optional[str] = None
    timestamp: Optional[float] = Field(default=None, description="Explicit event timestamp; None = system time.time()")



@router.post("/semantic/entity")
def create_entity_endpoint(req: EntityCreateRequest) -> Dict[str, Any]:
    """Ensures an Entity exists with canonical slug and dense vector embedding."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = semantic_memory.ensure_entity(
        tenant_id=t_id,
        name=req.name,
        type=req.type,
        description=req.description,
        embedding=req.embedding,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "entity": res,
    }


@router.post("/semantic/search")
def search_entities_endpoint(req: EntitySearchRequest) -> Dict[str, Any]:
    """Performs vector similarity search on Entity nodes."""
    t_id = req.tenant_id or settings.default_tenant_id
    results = semantic_memory.search_entities(
        tenant_id=t_id,
        query=req.query,
        limit=req.limit,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "query": req.query,
        "limit": req.limit,
        "results_count": len(results),
        "entities": results,
    }


@router.post("/semantic/fact")
def upsert_semantic_fact_v2(req: SemanticFactRequest) -> Dict[str, Any]:
    """Upserts a fact with bi-temporal invalidation and bidirectional provenance linking."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = semantic_memory.upsert_fact(
        tenant_id=t_id,
        subject=req.subject,
        predicate=req.predicate,
        new_object=req.object,
        episode_id=req.episode_id,
        confidence=req.confidence,
        cardinality=req.cardinality,
        subject_type=req.subject_type,
        object_type=req.object_type,
        user_id=req.user_id,
        timestamp=req.timestamp,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "fact": res,
    }


class SemanticExtractRequest(BaseModel):
    tenant_id: Optional[str] = None
    text: str = Field(..., min_length=1)
    persist: bool = Field(default=False, description="Whether to immediately upsert extracted facts into the graph")
    episode_id: Optional[str] = Field(default=None, description="Episode ID to anchor facts to if persisting")
    user_id: Optional[str] = None


class EntityResolveRequest(BaseModel):
    tenant_id: Optional[str] = None
    name: str = Field(..., min_length=1)
    type: str = Field(default="Concept")
    user_id: Optional[str] = None


@router.post("/semantic/extract")
def extract_semantic_facts_endpoint(req: SemanticExtractRequest) -> Dict[str, Any]:
    """Extracts structured OpenIE facts using real LLM or multi-domain fallback."""
    t_id = req.tenant_id or settings.default_tenant_id
    result = semantic_memory.extract_facts(req.text)

    persisted_facts = []
    if req.persist:
        ep_id = req.episode_id or f"ep_{uuid.uuid4().hex[:8]}"
        for t in result.triples:
            fact_res = semantic_memory.upsert_fact(
                tenant_id=t_id,
                subject=t.subject,
                predicate=t.predicate,
                new_object=t.object,
                episode_id=ep_id,
                confidence=t.confidence,
                cardinality=t.cardinality,
                subject_type=t.subject_type,
                object_type=t.object_type,
                user_id=req.user_id,
            )
            persisted_facts.append(fact_res)

    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "result": result.model_dump(),
        "persisted_facts": persisted_facts,
    }


@router.post("/semantic/resolve")
def resolve_entity_endpoint(req: EntityResolveRequest) -> Dict[str, Any]:
    """Resolves an entity mention to its canonical identity using 3-step resolution."""
    t_id = req.tenant_id or settings.default_tenant_id
    resolution = semantic_memory.resolve_entity_detailed(
        tenant_id=t_id,
        raw_name=req.name,
        entity_type=req.type,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "resolution": resolution,
    }


class TimeTravelSubgraphRequest(BaseModel):
    tenant_id: Optional[str] = None
    seed_entity: str = Field(..., min_length=1)
    as_of: Optional[float] = None
    depth: int = Field(default=1, ge=1, le=2)
    user_id: Optional[str] = None


@router.get("/semantic/snapshot")
def get_semantic_snapshot_endpoint(
    tenant_id: str = Query(default=settings.default_tenant_id),
    as_of: Optional[float] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Returns the complete point-in-time snapshot of active facts at timestamp as_of."""
    facts = semantic_memory.get_snapshot(tenant_id=tenant_id, as_of=as_of, user_id=user_id)
    return {
        "tenant_id": tenant_id,
        "as_of": as_of if as_of is not None else time.time(),
        "fact_count": len(facts),
        "facts": facts,
    }


@router.get("/semantic/history/{entity_name}")
def get_entity_history_endpoint(
    entity_name: str,
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Returns the full chronological evolution of all relationships an entity participated in."""
    history = semantic_memory.get_entity_history(tenant_id=tenant_id, entity_name=entity_name, user_id=user_id)
    return {
        "tenant_id": tenant_id,
        "status": "SUCCESS",
        "history": history,
    }


@router.post("/semantic/time-travel")
def time_travel_subgraph_endpoint(req: TimeTravelSubgraphRequest) -> Dict[str, Any]:
    """Returns the point-in-time neighborhood around a seed entity as of historical timestamp as_of."""
    t_id = req.tenant_id or settings.default_tenant_id
    subgraph = semantic_memory.get_time_travel_subgraph(
        tenant_id=t_id,
        seed_entity=req.seed_entity,
        as_of=req.as_of,
        depth=req.depth,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "subgraph": subgraph,
    }


@router.get("/semantic/cytoscape")
def get_cytoscape_time_travel_endpoint(
    tenant_id: str = Query(default=settings.default_tenant_id),
    as_of: Optional[float] = Query(default=None),
    include_invalidated: bool = Query(default=True),
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Returns Cytoscape-formatted graph elements with time-travel active and invalidated edges."""
    elements = semantic_memory.get_cytoscape_elements_as_of(
        tenant_id=tenant_id,
        as_of=as_of,
        include_invalidated=include_invalidated,
        user_id=user_id,
    )
    return {
        "tenant_id": tenant_id,
        "as_of": as_of if as_of is not None else time.time(),
        "elements": elements,
    }


# ==========================================
# Working Memory (Layer 3A) REST Endpoints
# ==========================================

class SubTaskSpecInput(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=1)
    description: str = ""
    depends_on: List[str] = Field(default_factory=list)


class WorkingDagCreateRequest(BaseModel):
    tenant_id: Optional[str] = None
    goal: str = Field(..., min_length=1)
    subtasks: List[SubTaskSpecInput]
    task_id: Optional[str] = None
    user_id: Optional[str] = None


class WorkingClaimRequest(BaseModel):
    tenant_id: Optional[str] = None
    task_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    user_id: Optional[str] = None


class WorkingCompleteRequest(BaseModel):
    tenant_id: Optional[str] = None
    subtask_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    result_summary: str = ""
    user_id: Optional[str] = None
    reward: float = 1.0


class WorkingFailRequest(BaseModel):
    tenant_id: Optional[str] = None
    subtask_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    error_message: str = Field(..., min_length=1)
    user_id: Optional[str] = None


class WorkingPinRequest(BaseModel):
    tenant_id: Optional[str] = None
    subtask_id: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    reason: str = ""
    user_id: Optional[str] = None


@router.post("/working/dag")
def create_working_task_dag_endpoint(req: WorkingDagCreateRequest) -> Dict[str, Any]:
    """Initializes a coordinated multi-agent task DAG on the FalkorDB blackboard."""
    t_id = req.tenant_id or settings.default_tenant_id
    subtask_specs = [
        SubTaskSpec(
            id=st.id or f"st_{uuid.uuid4().hex[:6]}",
            title=st.title,
            description=st.description,
            depends_on=st.depends_on,
        )
        for st in req.subtasks
    ]
    dag_res = working_memory.initialize_task_dag(
        tenant_id=t_id,
        goal=req.goal,
        subtasks=subtask_specs,
        task_id=req.task_id,
        user_id=req.user_id,
    )
    task_id = dag_res["task_id"] if isinstance(dag_res, dict) else dag_res
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "task_id": task_id,
        "subtasks_count": len(subtask_specs),
    }


@router.get("/working/task/{task_id}")
def get_working_task_endpoint(
    task_id: str,
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Retrieves current blackboard DAG status and all subtask lock states."""
    task_status = working_memory.get_task_status(tenant_id=tenant_id, task_id=task_id, user_id=user_id)
    if not task_status:
        return {"tenant_id": tenant_id, "status": "NOT_FOUND", "task": None}
    return {
        "tenant_id": tenant_id,
        "status": "SUCCESS",
        "task": task_status,
    }


@router.post("/working/claim")
def claim_working_subtask_endpoint(req: WorkingClaimRequest) -> Dict[str, Any]:
    """Atomically claims next pending subtask whose upstream dependencies are satisfied."""
    t_id = req.tenant_id or settings.default_tenant_id
    claim = working_memory.claim_next_subtask(
        tenant_id=t_id,
        task_id=req.task_id,
        agent_id=req.agent_id,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS" if claim else "NO_ELIGIBLE_SUBTASK",
        "subtask": claim,
    }


@router.post("/working/complete")
def complete_working_subtask_endpoint(req: WorkingCompleteRequest) -> Dict[str, Any]:
    """Marks subtask complete and propagates MemRL utility score feedback to pinned context."""
    t_id = req.tenant_id or settings.default_tenant_id
    success = working_memory.complete_subtask(
        tenant_id=t_id,
        subtask_id=req.subtask_id,
        agent_id=req.agent_id,
        result_summary=req.result_summary,
        user_id=req.user_id,
        reward=req.reward,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS" if success else "FAILED",
        "subtask_id": req.subtask_id,
    }


@router.post("/working/fail")
def fail_working_subtask_endpoint(req: WorkingFailRequest) -> Dict[str, Any]:
    """Marks subtask failed and cascades BLOCKED status to all downstream dependent subtasks."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = working_memory.fail_subtask(
        tenant_id=t_id,
        subtask_id=req.subtask_id,
        agent_id=req.agent_id,
        error_message=req.error_message,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "result": res,
    }


@router.post("/working/pin")
def pin_working_context_endpoint(req: WorkingPinRequest) -> Dict[str, Any]:
    """Attaches a zero-copy [:PINNED_CONTEXT] pointer from a subtask to an Entity or Episode."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = working_memory.pin_context(
        tenant_id=t_id,
        subtask_id=req.subtask_id,
        target_id=req.target_id,
        reason=req.reason,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "subtask_id": req.subtask_id,
        "target_id": req.target_id,
        "pinned": res,
    }


# ==========================================
# Procedural Memory (Layer 3B) REST Endpoints
# ==========================================

class ActionStepSpecInput(BaseModel):
    id: Optional[str] = None
    step_order: int
    tool_name: str
    param_schema: str = "{}"


class ProcedureRegisterRequest(BaseModel):
    tenant_id: Optional[str] = None
    name: str = Field(..., min_length=1)
    trigger_description: str = Field(..., min_length=1)
    steps: List[ActionStepSpecInput]
    user_id: Optional[str] = None


class ProcedureRetrieveRequest(BaseModel):
    tenant_id: Optional[str] = None
    procedure_name: str = Field(..., min_length=1)
    intent: Optional[str] = ""
    user_id: Optional[str] = None


class GuardrailAttachRequest(BaseModel):
    tenant_id: Optional[str] = None
    step_id: str = Field(..., min_length=1)
    rule_text: str = Field(..., min_length=1)
    error_signature: str = Field(..., min_length=1)
    fix_instruction: str = Field(..., min_length=1)
    episode_id: Optional[str] = None
    user_id: Optional[str] = None


class ReflexionCompileRequest(BaseModel):
    tenant_id: Optional[str] = None
    step_id: str = Field(..., min_length=1)
    error_signature: str = Field(..., min_length=1)
    rule_text: str = Field(..., min_length=1)
    fix_instruction: str = Field(..., min_length=1)
    episode_id: Optional[str] = None
    user_id: Optional[str] = None


class ProcedureOutcomeRequest(BaseModel):
    tenant_id: Optional[str] = None
    procedure_name: str = Field(..., min_length=1)
    success: bool
    user_id: Optional[str] = None


@router.post("/procedural/register")
def register_procedure_endpoint(req: ProcedureRegisterRequest) -> Dict[str, Any]:
    """Registers a reusable skill DAG with ordered action steps in FalkorDB."""
    t_id = req.tenant_id or settings.default_tenant_id
    step_specs = [
        ActionStepSpec(
            id=s.id or f"step_{uuid.uuid4().hex[:6]}",
            step_order=s.step_order,
            tool_name=s.tool_name,
            param_schema=s.param_schema,
        )
        for s in req.steps
    ]
    res = procedural_memory.register_procedure(
        tenant_id=t_id,
        name=req.name,
        trigger_description=req.trigger_description,
        steps=step_specs,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "procedure": res,
    }


@router.post("/procedural/retrieve")
def retrieve_procedure_endpoint(req: ProcedureRetrieveRequest) -> Dict[str, Any]:
    """Retrieves a skill DAG and all attached learned Guardrails."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = procedural_memory.retrieve_procedure(
        tenant_id=t_id,
        procedure_name=req.procedure_name,
        intent=req.intent or "",
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS" if res else "NOT_FOUND",
        "procedure": res,
    }


@router.post("/procedural/guardrail")
def attach_guardrail_endpoint(req: GuardrailAttachRequest) -> Dict[str, Any]:
    """Attaches a learned Guardrail to an ActionStep with optional Episode provenance link."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = procedural_memory.attach_guardrail(
        tenant_id=t_id,
        step_id=req.step_id,
        rule_text=req.rule_text,
        error_signature=req.error_signature,
        fix_instruction=req.fix_instruction,
        episode_id=req.episode_id,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "guardrail": res,
    }


@router.post("/procedural/compile-reflexion")
def compile_reflexion_endpoint(req: ReflexionCompileRequest) -> Dict[str, Any]:
    """Compiles an agent tool failure trace into a preventive Guardrail with [:TRIGGERED_BY] provenance."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = procedural_memory.compile_guardrail_from_failure(
        tenant_id=t_id,
        step_id=req.step_id,
        error_signature=req.error_signature,
        rule_text=req.rule_text,
        fix_instruction=req.fix_instruction,
        episode_id=req.episode_id,
        user_id=req.user_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "guardrail": res,
    }


@router.post("/procedural/outcome")
def record_procedure_outcome_endpoint(req: ProcedureOutcomeRequest) -> Dict[str, Any]:
    """Records reinforcement success or failure outcome counts for a Procedure."""
    t_id = req.tenant_id or settings.default_tenant_id
    res = procedural_memory.record_procedure_outcome(
        tenant_id=t_id,
        procedure_name=req.procedure_name,
        success=req.success,
        user_id=req.user_id,
    )
    is_success = bool(res.get("success", False)) if isinstance(res, dict) else bool(res)
    return {
        "tenant_id": t_id,
        "status": "SUCCESS" if is_success else "FAILED",
        "result": res,
        "updated": is_success,
    }


class GuardrailResetRequest(BaseModel):
    tenant_id: Optional[str] = None
    procedure_name: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/procedural/guardrail/reset")
@router.post("/reset-guardrails")
def reset_guardrails_endpoint(
    req: Optional[GuardrailResetRequest] = None,
    tenant_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """Resets/clears learned Guardrail nodes for testing and judge repeatability."""
    t_id = (req.tenant_id if req and req.tenant_id else None) or tenant_id or settings.default_tenant_id
    proc_name = req.procedure_name if req else None
    u_id = req.user_id if req else None
    deleted_count = procedural_memory.reset_guardrails(
        tenant_id=t_id,
        procedure_name=proc_name,
        user_id=u_id,
    )
    return {
        "tenant_id": t_id,
        "status": "SUCCESS",
        "deleted_count": deleted_count,
        "procedure_name": proc_name,
    }







