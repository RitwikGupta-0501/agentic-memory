"""Episodic Memory Layer: Chronological autobiographical log with temporal chaining and vector index."""

import json
import time
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.cypher_catalog import (
    EPISODE_INSERT_AND_CHAIN,
    EPISODE_INSERT_ROOT,
    EPISODE_VECTOR_SEARCH_CANDIDATES,
)
from app.core.embeddings.factory import embedding_service
from app.core.falkor_client import falkor_router


class EpisodeRecord(BaseModel):
    """Pydantic v2 data model representing an immutable episodic experience node."""

    id: str = Field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:10]}")
    session_id: str
    tenant_id: str = "acme-payments"
    role: Literal["user", "agent", "tool", "system"] = "user"
    actor_id: str = "user"
    content: str
    structured_payload: Optional[Dict[str, Any]] = None
    status: Literal["SUCCESS", "ERROR", "WARNING", "INFO"] = "SUCCESS"
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    utility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    vcache_threshold: float = Field(default=0.78, ge=0.0, le=1.0)
    access_count: int = Field(default=0, ge=0)
    last_accessed: float = Field(default_factory=time.time)
    timestamp: float = Field(default_factory=time.time)
    token_count: int = Field(default=0, ge=0)
    embedding_model: Optional[str] = None
    embedding_dim: Optional[int] = None
    embedding: Optional[List[float]] = None
    archived: bool = False


class EpisodicMemoryManager:
    """Manages ingestion and chronological retrieval of vector-indexed episodic memory nodes."""

    def __init__(self, router=falkor_router, embeddings=embedding_service):
        self.router = router
        self.embeddings = embeddings

    def record_episode(
        self,
        tenant_id: str,
        session_id: str,
        content: str,
        role: str = "user",
        actor_id: str = "user",
        status: str = "SUCCESS",
        structured_payload: Optional[Dict[str, Any]] = None,
        importance_score: float = 0.5,
        utility_score: Optional[float] = None,
        vcache_threshold: float = 0.78,
        token_count: Optional[int] = None,
        embedding: Optional[List[float]] = None,
        user_id: Optional[str] = None,
        episode_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Records an episode, vectorizes its content, and chains it to the preceding episode in the session."""
        now = time.time()
        start_t = time.perf_counter()

        ep_id = episode_id or f"ep_{uuid.uuid4().hex[:10]}"
        t_id = tenant_id or settings.default_tenant_id

        # 1. Compute token count heuristic if not supplied
        computed_tokens = token_count if token_count is not None else max(1, len(content) // 4)

        # 2. Generate vector embedding if not provided
        if embedding is None:
            vec = self.embeddings.embed_text(content)
        else:
            vec = embedding

        active_model = self.embeddings.provider.model_name
        active_dim = self.embeddings.provider.dimension
        final_utility = utility_score if utility_score is not None else importance_score

        # 3. Validate against EpisodeRecord schema
        record = EpisodeRecord(
            id=ep_id,
            session_id=session_id,
            tenant_id=t_id,
            role=role,
            actor_id=actor_id,
            content=content,
            structured_payload=structured_payload,
            status=status,
            importance_score=importance_score,
            utility_score=final_utility,
            vcache_threshold=vcache_threshold,
            access_count=0,
            last_accessed=now,
            timestamp=now,
            token_count=computed_tokens,
            embedding_model=active_model,
            embedding_dim=active_dim,
            embedding=vec,
            archived=False,
        )

        # 4. Check if there is an existing episode in this session for chaining
        check_query = "MATCH (e:Episode {session_id: $session_id}) RETURN count(e) AS count"
        check_res = self.router.query(
            check_query,
            {"session_id": session_id},
            tenant_id=t_id,
            user_id=user_id,
        )

        has_existing = False
        if check_res and check_res.result_set:
            has_existing = check_res.result_set[0][0] > 0

        # 5. Serialize structured payload
        payload_json = json.dumps(structured_payload) if structured_payload is not None else None

        params = {
            "episode_id": record.id,
            "session_id": record.session_id,
            "tenant_id": record.tenant_id,
            "content": record.content,
            "role": record.role,
            "actor_id": record.actor_id,
            "status": record.status,
            "structured_payload": payload_json,
            "importance_score": record.importance_score,
            "utility_score": record.utility_score,
            "vcache_threshold": record.vcache_threshold,
            "access_count": record.access_count,
            "last_accessed": record.last_accessed,
            "timestamp": record.timestamp,
            "token_count": record.token_count,
            "embedding_model": record.embedding_model,
            "embedding_dim": record.embedding_dim,
            "embedding": record.embedding,
            "latency_ms": round((time.perf_counter() - start_t) * 1000, 2),
        }

        query = EPISODE_INSERT_AND_CHAIN if has_existing else EPISODE_INSERT_ROOT
        self.router.query(query, params, tenant_id=t_id, user_id=user_id)

        result_dict = record.model_dump()
        result_dict["latency_ms"] = params["latency_ms"]
        return result_dict

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
        RETURN ep.id AS id, ep.role AS role, ep.actor_id AS actor_id,
               ep.status AS status, ep.content AS content,
               ep.structured_payload AS structured_payload,
               ep.importance_score AS importance_score,
               ep.utility_score AS utility_score,
               ep.access_count AS access_count,
               ep.timestamp AS timestamp, ep.token_count AS token_count
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
                payload = None
                if row[5]:
                    try:
                        payload = json.loads(row[5])
                    except Exception:
                        payload = row[5]

                episodes.append({
                    "id": row[0],
                    "role": row[1],
                    "actor_id": row[2] or "user",
                    "status": row[3] or "SUCCESS",
                    "content": row[4],
                    "structured_payload": payload,
                    "importance_score": row[6],
                    "utility_score": row[7] if row[7] is not None else row[6],
                    "access_count": row[8] or 0,
                    "timestamp": row[9],
                    "token_count": row[10] or 0,
                })
        return episodes

    def search_episodes(
        self,
        tenant_id: str,
        query: str,
        session_id: Optional[str] = None,
        candidate_limit: int = 10,
        cross_session: bool = False,
        min_similarity: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Searches vector index for top candidate episodes filtered by vCache threshold and active model."""
        vec = self.embeddings.embed_text(query)
        active_model = self.embeddings.provider.model_name
        t_id = tenant_id or settings.default_tenant_id

        params = {
            "query_vec": vec,
            "candidate_limit": candidate_limit,
            "session_id": session_id or "",
            "cross_session": cross_session or (session_id is None),
            "current_model": active_model,
        }

        res = self.router.query(
            EPISODE_VECTOR_SEARCH_CANDIDATES,
            params,
            tenant_id=t_id,
            user_id=user_id,
        )

        results = []
        if res and res.result_set:
            for row in res.result_set:
                node = row[0]
                similarity = float(row[1]) if len(row) > 1 else 0.0
                props = getattr(node, "properties", {}) if node else {}
                payload = props.get("structured_payload")
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        pass

                results.append({
                    "id": props.get("id"),
                    "session_id": props.get("session_id"),
                    "role": props.get("role"),
                    "actor_id": props.get("actor_id", "user"),
                    "status": props.get("status", "SUCCESS"),
                    "content": props.get("content"),
                    "structured_payload": payload,
                    "importance_score": props.get("importance_score", 0.5),
                    "utility_score": props.get("utility_score", 0.5),
                    "vcache_threshold": props.get("vcache_threshold", 0.78),
                    "access_count": props.get("access_count", 0),
                    "timestamp": props.get("timestamp"),
                    "similarity_score": round(similarity, 4),
                })

        if min_similarity is not None:
            results = [r for r in results if r["similarity_score"] >= min_similarity]

        return results


episodic_memory = EpisodicMemoryManager()
