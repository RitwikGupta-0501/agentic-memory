"""Self-healing re-indexing engine for model migration and dimension alignment."""

import logging
import time
from typing import Any, Dict

from app.core.embeddings.factory import embedding_service
from app.core.falkor_client import falkor_router

logger = logging.getLogger("aegis.embeddings.reindexer")


def reindex_tenant_embeddings(
    tenant_id: str,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """Rebuilds the vector index and re-embeds all episodes on a tenant graph using the active model.
    
    Resolves both model switch edge cases:
    1. Dimension mismatch between old vector index and new embedding provider.
    2. Latent manifold drift from different models sharing same dimension.
    """
    start_t = time.perf_counter()
    graph = falkor_router.get_graph(tenant_id)
    new_model = embedding_service.provider.model_name
    new_dim = embedding_service.provider.dimension
    now = time.time()

    logger.info(f"Starting vector re-indexing on tenant '{tenant_id}' using model '{new_model}' (dim={new_dim})...")

    # 1. Safely drop existing vector index
    try:
        graph.query("DROP INDEX FOR (ep:Episode) ON (ep.embedding)")
        logger.info(f"Dropped legacy vector index on ({tenant_id}:Episode.embedding).")
    except Exception as e:
        logger.debug(f"Note dropping index on ({tenant_id}:Episode.embedding): {e}")

    # 2. Re-create vector index with new dimension
    create_index_query = (
        f"CREATE VECTOR INDEX FOR (ep:Episode) ON (ep.embedding) "
        f"OPTIONS {{dimension: {new_dim}, similarityFunction: 'cosine'}}"
    )
    try:
        graph.query(create_index_query)
        logger.info(f"Created fresh vector index on ({tenant_id}:Episode.embedding) with dim={new_dim}.")
    except Exception as e:
        logger.warning(f"Vector index recreation notice: {e}")

    # 3. Retrieve all raw episode contents (source of truth)
    res = graph.query("MATCH (ep:Episode) RETURN ep.id AS id, ep.content AS content")
    episodes = res.result_set or []
    total_episodes = len(episodes)

    if total_episodes == 0:
        return {
            "status": "NOOP",
            "tenant_id": tenant_id,
            "message": f"Tenant '{tenant_id}' has no episodes to reindex.",
            "reindexed_count": 0,
            "new_model": new_model,
            "dimension": new_dim,
            "duration_ms": round((time.perf_counter() - start_t) * 1000, 2),
        }

    # 4. Batch re-embed and update nodes
    for i in range(0, total_episodes, batch_size):
        chunk = episodes[i:i + batch_size]
        ep_ids = [row[0] for row in chunk]
        contents = [row[1] if row[1] is not None else "" for row in chunk]

        vectors = embedding_service.embed_batch(contents)

        for ep_id, vec in zip(ep_ids, vectors):
            update_query = """
            MATCH (ep:Episode {id: $id})
            SET ep.embedding = vecf32($vec),
                ep.embedding_model = $model,
                ep.embedding_dim = $dim,
                ep.reindexed_at = $now
            """
            graph.query(
                update_query,
                {"id": ep_id, "vec": vec, "model": new_model, "dim": new_dim, "now": now},
            )

    # 5. Update GraphMetadata singleton on the tenant graph
    metadata_query = """
    MERGE (m:GraphMetadata {tenant_id: $tenant_id})
    SET m.active_embedding_model = $model,
        m.active_dimension = $dim,
        m.last_reindexed_at = $now,
        m.episodes_reindexed = $count
    """
    graph.query(
        metadata_query,
        {
            "tenant_id": tenant_id,
            "model": new_model,
            "dim": new_dim,
            "now": now,
            "count": total_episodes,
        },
    )

    duration_ms = round((time.perf_counter() - start_t) * 1000, 2)
    logger.info(f"Re-indexing completed for tenant '{tenant_id}': {total_episodes} episodes in {duration_ms}ms.")

    return {
        "status": "SUCCESS",
        "tenant_id": tenant_id,
        "reindexed_count": total_episodes,
        "new_model": new_model,
        "dimension": new_dim,
        "duration_ms": duration_ms,
    }
