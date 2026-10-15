"""Consolidation Layer: Slow-stream decay scoring, node retention, and episode compression."""

import math
import time
import uuid
from typing import Any, Dict, List, Optional

from app.core.cypher_catalog import (
    CONSOLIDATION_RETENTION_QUERY,
    CONSOLIDATION_INSIGHT_CREATE,
)
from app.core.falkor_client import falkor_router


class ConsolidationEngine:
    """Computes retention scores and compresses stale episodic chains into insights."""

    def __init__(self, router=falkor_router):
        self.router = router

    def calculate_retention_scores(
        self,
        tenant_id: str,
        decay_lambda: float = 0.001,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Computes retention score: Degree(n) * exp(-lambda * (now - last_accessed))."""
        res = self.router.query(
            CONSOLIDATION_RETENTION_QUERY,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        scores = []
        now = time.time()

        if res and res.result_set:
            for row in res.result_set:
                node = row[0]
                degree = row[1]
                props = getattr(node, "properties", {})
                last_t = props.get("last_accessed", props.get("timestamp", now))
                delta_t = max(0.0, now - last_t)
                utility = float(props.get("utility_score", props.get("importance_score", 0.5)))
                access_strength = int(props.get("access_count", 0)) + 1
                retention = (degree + 1) * utility * math.exp(-(decay_lambda * delta_t) / access_strength)

                scores.append({
                    "id": props.get("id", props.get("name", "unknown")),
                    "degree": degree,
                    "retention_score": round(retention, 4),
                })

        return scores

    def trigger_consolidation_cycle(
        self,
        tenant_id: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compresses old unarchived episodes into a ConsolidatedInsight node."""
        now = time.time()
        start_t = time.perf_counter()

        # Find unarchived episodes
        find_query = """
        MATCH (ep:Episode)
        WHERE (ep.archived IS NULL OR ep.archived = false)
        RETURN ep.id AS id, ep.content AS content, ep.role AS role
        LIMIT 10
        """
        res = self.router.query(find_query, tenant_id=tenant_id, user_id=user_id)

        episodes = []
        if res and res.result_set:
            for row in res.result_set:
                episodes.append({"id": row[0], "content": row[1], "role": row[2]})

        if not episodes:
            return {
                "status": "NOOP",
                "message": "No unarchived episodes found for consolidation.",
                "duration_ms": round((time.perf_counter() - start_t) * 1000, 2),
            }

        # Synthesize consolidated insight
        insight_id = f"insight_{uuid.uuid4().hex[:6]}"
        episode_ids = [ep["id"] for ep in episodes]
        summary_text = (
            f"Consolidated knowledge summary from {len(episodes)} interaction turns: "
            + " | ".join(ep["content"][:60] for ep in episodes)
        )

        self.router.query(
            CONSOLIDATION_INSIGHT_CREATE,
            {
                "insight_id": insight_id,
                "summary": summary_text,
                "episode_ids": episode_ids,
                "now": now,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return {
            "status": "SUCCESS",
            "insight_id": insight_id,
            "consolidated_episodes_count": len(episode_ids),
            "summary": summary_text,
            "duration_ms": round((time.perf_counter() - start_t) * 1000, 2),
        }


consolidation_engine = ConsolidationEngine()
