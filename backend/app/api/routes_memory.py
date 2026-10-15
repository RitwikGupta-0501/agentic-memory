"""API endpoints for 4-tier cognitive memory graph retrieval and mutations."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.embeddings import embedding_service
from app.core.embeddings.reindexer import reindex_tenant_embeddings
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
from app.memory.importance import importance_scorer
from app.memory.semantic import semantic_memory, EntityTriple

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


class FactUpsertRequest(BaseModel):
    tenant_id: Optional[str] = None
    subject: str
    predicate: str
    object: str
    episode_id: Optional[str] = "ep_manual"
    confidence: float = 1.0


class HippoRAGRequest(BaseModel):
    tenant_id: Optional[str] = None
    seed_entities: List[str]


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


@router.get("/graph")
def get_graph_data(
    tenant_id: str = Query(default=settings.default_tenant_id),
    user_id: Optional[str] = Query(default=None),
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

            # Determine Tier category for color coding
            tier = "unknown"
            node_label = "Node"
            props = getattr(node, "properties", {}) if node else {}

            if "TaskRun" in labels or "SubTask" in labels:
                tier = "working"  # Yellow
                node_label = props.get("title", props.get("id", "Task"))
            elif "Episode" in labels or "Session" in labels:
                tier = "episodic"  # Blue
                if "Session" in labels:
                    node_label = f"Session: {props.get('id', '')}"
                else:
                    node_label = f"Ep: {props.get('id', '')}"
            elif "Entity" in labels:
                tier = "semantic"  # Green
                node_label = props.get("name", "Entity")
            elif "Procedure" in labels or "ActionStep" in labels or "Guardrail" in labels:
                tier = "procedural"  # Purple
                node_label = props.get("name", props.get("rule_text", props.get("id", "Proc")))
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

    return {
        "tenant_id": tenant_id,
        "nodes": list(nodes_map.values()),
        "edges": edges_list,
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
    )
    return res


@router.post("/hipporag")
def hipporag_retrieval(req: HippoRAGRequest) -> Dict[str, Any]:
    """Runs HippoRAG hybrid retrieval."""
    t_id = req.tenant_id or settings.default_tenant_id
    return semantic_memory.hipporag_retrieve(tenant_id=t_id, seed_entities=req.seed_entities)


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


@router.get("/episodes")
def get_episodes(
    session_id: str = Query(..., description="Session identifier for chronological history"),
    tenant_id: str = Query(default=settings.default_tenant_id),
    limit: int = Query(default=50, ge=1, le=500),
    user_id: Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    """Retrieves chronological episodes for a session."""
    return episodic_memory.get_session_history(
        tenant_id=tenant_id,
        session_id=session_id,
        limit=limit,
        user_id=user_id,
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
    )
    return {
        "tenant_id": t_id,
        "query": req.query,
        "top_k": req.top_k,
        "results_count": len(results),
        "episodes": results,
    }



