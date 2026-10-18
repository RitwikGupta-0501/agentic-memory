"""Cognitive agent tools for querying FalkorDB memory and executing system actions."""

import logging
from typing import Any, Dict, List, Optional
from app.core.falkor_client import falkor_router
from app.memory.semantic import semantic_memory
from app.memory.episodic import episodic_memory

logger = logging.getLogger("aegis.agents.tools")


def query_knowledge_graph(
    tenant_id: str,
    query_entity: str,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Queries active entities and relationships in Semantic Memory."""
    try:
        resolved = semantic_memory.resolve_entity(tenant_id, query_entity, user_id=user_id)
        cypher = """
        MATCH (e:Entity {name: $name})-[r:RELATES_TO]->(target:Entity)
        WHERE r.valid_to IS NULL
        RETURN e.name AS entity, r.predicate AS predicate, target.name AS target, r.confidence AS confidence
        """
        res = falkor_router.query(cypher, {"name": resolved}, tenant_id=tenant_id, user_id=user_id)
        relations = []
        if res and res.result_set:
            for row in res.result_set:
                relations.append({
                    "entity": row[0],
                    "predicate": row[1],
                    "target": row[2],
                    "confidence": row[3],
                })
        return {
            "status": "SUCCESS",
            "entity": resolved,
            "relations_count": len(relations),
            "relations": relations,
        }
    except Exception as e:
        logger.error(f"Error querying knowledge graph: {e}")
        return {"status": "ERROR", "error": str(e)}


def search_memory_episodes(
    tenant_id: str,
    query: str,
    top_k: int = 5,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieves relevant episodic memories using Park et al. 3-factor composite ranking."""
    try:
        episodes = episodic_memory.retrieve_episodes(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            cross_session=True,
            user_id=user_id,
        )
        return {
            "status": "SUCCESS",
            "count": len(episodes),
            "episodes": [
                {
                    "id": ep["episode"]["id"],
                    "content": ep["episode"]["content"],
                    "role": ep["episode"]["role"],
                    "composite_score": ep["composite_score"],
                }
                for ep in episodes
            ],
        }
    except Exception as e:
        logger.error(f"Error searching episodes: {e}")
        return {"status": "ERROR", "error": str(e)}


def inspect_entity(
    tenant_id: str,
    entity_name: str,
    as_of: Optional[float] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspects an entity's current or historical neighborhood."""
    try:
        resolved = semantic_memory.resolve_entity(tenant_id, entity_name, user_id=user_id)
        view = semantic_memory.get_neighborhood_view(
            tenant_id=tenant_id,
            seed_entity=resolved,
            as_of=as_of,
            user_id=user_id,
        )
        return {"status": "SUCCESS", "view": view}
    except Exception as e:
        logger.error(f"Error inspecting entity: {e}")
        return {"status": "ERROR", "error": str(e)}


# -------------------------------------------------------------------------
# Action Execution Tools with Guardrail and Reflexion Support
# -------------------------------------------------------------------------

def query_database_config(db_name: str) -> Dict[str, Any]:
    """Queries current database configuration."""
    return {
        "status": "SUCCESS",
        "database": db_name,
        "max_connections": 500,
        "ssl_enabled": True,
        "active_nodes": ["primary-us-east-1", "replica-us-east-2"],
    }


def run_database_migration(
    source_db: str,
    target_db: str,
    require_wal_checkpoint: bool = False,
) -> Dict[str, Any]:
    """Database migration tool with failure trap for testing Reflexion."""
    if not require_wal_checkpoint:
        return {
            "status": "ERROR",
            "error_signature": "ERR_NO_WAL_CHECKPOINT",
            "error_message": (
                "Migration blocked: WAL checkpoint must be enforced before cutover to prevent replication drift."
            ),
            "suggested_fix": "Set require_wal_checkpoint=True in migration parameters.",
        }

    return {
        "status": "SUCCESS",
        "source": source_db,
        "target": target_db,
        "migrated_records": 1420500,
        "checksum_verified": True,
        "message": f"Successfully migrated from {source_db} to {target_db} with WAL checkpoint verification.",
    }


def restart_service(service_name: str) -> Dict[str, Any]:
    """Restarts a service."""
    return {
        "status": "SUCCESS",
        "service": service_name,
        "action": "graceful_restart",
        "uptime_seconds": 0,
        "health": "SERVING",
    }


def verify_service_health(service_name: str) -> Dict[str, Any]:
    """Health check probe for a service."""
    return {
        "status": "SUCCESS",
        "service": service_name,
        "p99_latency_ms": 1.2,
        "error_rate": 0.0001,
        "healthy": True,
    }
