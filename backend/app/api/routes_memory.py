"""API endpoints for 4-tier cognitive memory graph retrieval and mutations."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.config import settings
from app.core.falkor_client import falkor_router
from app.memory.episodic import episodic_memory
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
            elif "Episode" in labels:
                tier = "episodic"  # Blue
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
