"""Episodic Memory Layer: Chronological autobiographical log with temporal chaining."""

import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.cypher_catalog import EPISODE_INSERT_AND_CHAIN, EPISODE_INSERT_ROOT
from app.core.falkor_client import falkor_router


class EpisodeRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:8]}")
    session_id: str
    content: str
    role: str = "user"  # "user", "agent", "tool", "system"
    importance_score: float = 0.5
    timestamp: float = Field(default_factory=time.time)


class EpisodicMemoryManager:
    """Manages ingestion and chronological retrieval of episodic memory nodes."""

    def __init__(self, router=falkor_router):
        self.router = router

    def record_episode(
        self,
        tenant_id: str,
        session_id: str,
        content: str,
        role: str = "user",
        importance_score: float = 0.5,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Records an episode and chains it to the preceding episode in the session."""
        episode_id = f"ep_{uuid.uuid4().hex[:8]}"
        now = time.time()
        start_t = time.perf_counter()

        # Check if there is an existing episode in this session
        check_query = "MATCH (e:Episode {session_id: $session_id}) RETURN count(e) AS count"
        check_res = self.router.query(
            check_query,
            {"session_id": session_id},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        has_existing = False
        if check_res and check_res.result_set:
            has_existing = check_res.result_set[0][0] > 0

        params = {
            "episode_id": episode_id,
            "session_id": session_id,
            "content": content,
            "role": role,
            "importance_score": importance_score,
            "timestamp": now,
            "latency_ms": round((time.perf_counter() - start_t) * 1000, 2),
        }

        if has_existing:
            query = EPISODE_INSERT_AND_CHAIN
        else:
            query = EPISODE_INSERT_ROOT

        self.router.query(query, params, tenant_id=tenant_id, user_id=user_id)

        return {
            "id": episode_id,
            "session_id": session_id,
            "content": content,
            "role": role,
            "importance_score": importance_score,
            "timestamp": now,
        }

    def get_session_history(
        self,
        tenant_id: str,
        session_id: str,
        limit: int = 50,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves episodes in chronological order for a given session."""
        query = """
        MATCH (ep:Episode {session_id: $session_id})
        RETURN ep.id AS id, ep.role AS role, ep.content AS content,
               ep.importance_score AS importance_score, ep.timestamp AS timestamp
        ORDER BY ep.timestamp ASC
        LIMIT $limit
        """
        res = self.router.query(
            query,
            {"session_id": session_id, "limit": limit},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        episodes = []
        if res and res.result_set:
            for row in res.result_set:
                episodes.append({
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "importance_score": row[3],
                    "timestamp": row[4],
                })
        return episodes


episodic_memory = EpisodicMemoryManager()
