"""Episodic Memory Layer: Chronological autobiographical log with temporal chaining and vector index."""

import json
import math
import time
import uuid
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.cypher_catalog import (
    ATOMIC_EPISODE_APPEND,
    EPISODE_BATCH_RECALL_TOUCH_AND_EXPAND,
    EPISODE_FALLBACK_SCAN_FETCH,
    EPISODE_HYBRID_CANDIDATE_FETCH,
    EPISODE_UTILITY_FEEDBACK_UPDATE,
    EPISODE_VECTOR_SEARCH_CANDIDATES,
    MULTI_SESSION_LINEAGE_QUERY,
    SESSION_ENSURE_AND_LINK,
)
from app.core.embeddings.factory import embedding_service
from app.core.falkor_client import falkor_router
from app.memory.importance import ImportanceScorer, importance_scorer


class ScoredEpisode(BaseModel):
    """Pydantic model representing a candidate episode ranked via Park et al. 3-factor scoring."""

    episode: Dict[str, Any]
    recency_score: float
    importance_score: float
    utility_score: float
    relevance_score: float
    vcache_threshold: float
    vcache_passed: bool
    composite_score: float
    provenance_links: List[Dict[str, Any]] = Field(default_factory=list)


class EpisodeRecord(BaseModel):
    """Pydantic v2 data model representing an immutable episodic experience node."""

    id: str = Field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:10]}")
    session_id: str
    parent_session_id: Optional[str] = None
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

    def __init__(
        self,
        router=falkor_router,
        embeddings=embedding_service,
        scorer: Optional[ImportanceScorer] = None,
    ):
        self.router = router
        self.embeddings = embeddings
        self.scorer = scorer or importance_scorer

    def record_episode(
        self,
        tenant_id: str,
        session_id: str,
        content: str,
        role: str = "user",
        actor_id: str = "user",
        status: str = "SUCCESS",
        structured_payload: Optional[Dict[str, Any]] = None,
        importance_score: Optional[float] = None,
        utility_score: Optional[float] = None,
        vcache_threshold: float = 0.78,
        token_count: Optional[int] = None,
        embedding: Optional[List[float]] = None,
        user_id: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        episode_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Atomically appends an episode to the session tail pointer and maintains linear timeline."""
        now = float(timestamp) if timestamp is not None else time.time()
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

        # 3. Dynamic importance scoring if not explicitly supplied
        if importance_score is None:
            computed_importance = self.scorer.score(
                content=content,
                role=role,
                status=status,
                structured_payload=structured_payload,
            )
        else:
            computed_importance = importance_score

        final_utility = utility_score if utility_score is not None else computed_importance

        # 4. Validate against EpisodeRecord schema
        record = EpisodeRecord(
            id=ep_id,
            session_id=session_id,
            parent_session_id=parent_session_id,
            tenant_id=t_id,
            role=role,
            actor_id=actor_id,
            content=content,
            structured_payload=structured_payload,
            status=status,
            importance_score=computed_importance,
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

        # 4. Serialize structured payload
        payload_json = json.dumps(structured_payload) if structured_payload is not None else None

        # 5. Execute single atomic session tail pointer append
        params = {
            "session_id": record.session_id,
            "parent_session_id": parent_session_id,
            "tenant_id": record.tenant_id,
            "user_id": user_id,
            "timestamp": record.timestamp,
            "episode_id": record.id,
            "role": record.role,
            "actor_id": record.actor_id,
            "content": record.content,
            "structured_payload": payload_json,
            "status": record.status,
            "importance_score": record.importance_score,
            "utility_score": record.utility_score,
            "vcache_threshold": record.vcache_threshold,
            "token_count": record.token_count,
            "embedding_model": record.embedding_model,
            "embedding_dim": record.embedding_dim,
            "embedding": record.embedding,
        }

        res = self.router.query(
            ATOMIC_EPISODE_APPEND,
            params,
            tenant_id=t_id,
            user_id=user_id,
        )

        prev_ep_id = None
        seq_num = 1
        if res and res.result_set and res.result_set[0]:
            row = res.result_set[0]
            prev_ep_id = row[1]
            seq_num = row[2]

        result_dict = record.model_dump()
        result_dict["previous_episode_id"] = prev_ep_id
        result_dict["seq_num"] = seq_num
        result_dict["latency_ms"] = round((time.perf_counter() - start_t) * 1000, 2)
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

    def retrieve_episodes(
        self,
        tenant_id: str,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        candidate_limit: int = 25,
        cross_session: bool = False,
        alpha: float = 1.0,
        beta: float = 1.0,
        gamma: float = 1.0,
        decay_lambda: float = 0.0001925,
        strict_vcache: bool = False,
        touch_recall: bool = True,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves and ranks episodic memories using Park et al. 3-factor composite ranking.

        Balances:
        - Factor 1 (Recency): MemoryBank Ebbinghaus exponential decay reinforced by recall frequency.
        - Factor 2 (Importance/Utility): MemRL clamped Q-value falling back to initial importance score.
        - Factor 3 (Relevance): Vector cosine similarity with per-node vCache decision boundary gating.

        Performs atomic batch recall-touch and inbound provenance expansion on top-k winners in 1 round trip.
        """
        vec = self.embeddings.embed_text(query)
        t_id = tenant_id or settings.default_tenant_id
        now = time.time()

        params = {
            "query_vec": vec,
            "candidate_limit": candidate_limit,
            "session_id": session_id or "",
            "cross_session": cross_session or (session_id is None),
        }

        candidate_rows = []
        try:
            res = self.router.query(
                EPISODE_HYBRID_CANDIDATE_FETCH,
                params,
                tenant_id=t_id,
                user_id=user_id,
            )
            if res and res.result_set:
                candidate_rows = res.result_set
        except Exception:
            candidate_rows = []

        # Fallback scan if vector ANN returns 0 candidates or index error (e.g. intra-session sparsity)
        if not candidate_rows:
            fallback_res = self.router.query(
                EPISODE_FALLBACK_SCAN_FETCH,
                {
                    "candidate_limit": candidate_limit,
                    "session_id": session_id or "",
                    "cross_session": cross_session or (session_id is None),
                },
                tenant_id=t_id,
                user_id=user_id,
            )
            if fallback_res and fallback_res.result_set:
                candidate_rows = fallback_res.result_set

        if not candidate_rows:
            return []

        weight_sum = (alpha + beta + gamma) if (alpha + beta + gamma) > 0 else 1.0
        scored_candidates: List[ScoredEpisode] = []

        for row in candidate_rows:
            ep_node = row[0]
            raw_score = float(row[1]) if len(row) > 1 and row[1] is not None else 0.5
            props = getattr(ep_node, "properties", {}) if ep_node else {}
            if not props:
                continue

            # 1. Relevance: raw_score is already standardized cosine similarity [0.0, 1.0]
            relevance = max(0.0, min(1.0, raw_score))

            # vCache decision boundary
            vcache_tau = float(props.get("vcache_threshold", 0.75))
            vcache_passed = relevance >= vcache_tau
            if strict_vcache and not vcache_passed:
                continue

            effective_relevance = relevance if vcache_passed else (relevance * 0.5)

            # 2. Recency: MemoryBank decay with access_count reinforcement
            access_count = int(props.get("access_count", 0))
            last_t = float(props.get("last_accessed") or props.get("timestamp", now))
            delta_t = max(0.0, now - last_t)
            recency = math.exp(-(decay_lambda * delta_t) / (access_count + 1))
            recency = max(0.0, min(1.0, recency))

            # 3. Importance / MemRL Utility
            importance = float(props.get("importance_score", 0.5))
            utility = float(props.get("utility_score", importance))
            utility = max(0.05, min(1.0, utility))

            # 4. Composite Score
            composite = (alpha * recency + beta * utility + gamma * effective_relevance) / weight_sum
            composite = max(0.0, min(1.0, composite))

            payload = props.get("structured_payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    pass

            ep_dict = {
                "id": props.get("id"),
                "session_id": props.get("session_id"),
                "role": props.get("role"),
                "actor_id": props.get("actor_id", "user"),
                "status": props.get("status", "SUCCESS"),
                "content": props.get("content"),
                "structured_payload": payload,
                "timestamp": props.get("timestamp"),
                "last_accessed": props.get("last_accessed"),
                "access_count": access_count,
                "token_count": props.get("token_count", 0),
            }

            scored = ScoredEpisode(
                episode=ep_dict,
                recency_score=round(recency, 4),
                importance_score=round(importance, 4),
                utility_score=round(utility, 4),
                relevance_score=round(relevance, 4),
                vcache_threshold=round(vcache_tau, 4),
                vcache_passed=vcache_passed,
                composite_score=round(composite, 4),
            )
            scored_candidates.append(scored)

        # Sort descending by composite_score and slice top_k
        scored_candidates.sort(key=lambda s: s.composite_score, reverse=True)
        top_candidates = scored_candidates[:top_k]

        if not top_candidates:
            return []

        # 5. Atomic Batch Recall Touch & Provenance Expansion
        top_ids = [s.episode["id"] for s in top_candidates if s.episode.get("id")]
        if top_ids:
            touch_params = {
                "episode_ids": top_ids,
                "touch": touch_recall,
                "now": now,
            }
            touch_res = self.router.query(
                EPISODE_BATCH_RECALL_TOUCH_AND_EXPAND,
                touch_params,
                tenant_id=t_id,
                user_id=user_id,
            )
            provenance_by_id = {}
            if touch_res and touch_res.result_set:
                for trow in touch_res.result_set:
                    t_ep_id = trow[0]
                    new_access = trow[1]
                    new_last = trow[2]
                    plinks = trow[3] or []
                    provenance_by_id[t_ep_id] = {
                        "access_count": new_access,
                        "last_accessed": new_last,
                        "provenance_links": [
                            link for link in plinks if link and link.get("id")
                        ],
                    }

            # Attach provenance links & updated access counters to top candidates
            for cand in top_candidates:
                cid = cand.episode.get("id")
                if cid in provenance_by_id:
                    p_info = provenance_by_id[cid]
                    cand.provenance_links = p_info["provenance_links"]
                    if touch_recall:
                        cand.episode["access_count"] = p_info["access_count"]
                        cand.episode["last_accessed"] = p_info["last_accessed"]

        return [c.model_dump() for c in top_candidates]

    def get_session_lineage(
        self,
        tenant_id: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves session hierarchy tree and ancestor head/tail summaries in O(1) pointer hops."""
        t_id = tenant_id or settings.default_tenant_id
        res = self.router.query(
            MULTI_SESSION_LINEAGE_QUERY,
            {"session_id": session_id},
            tenant_id=t_id,
            user_id=user_id,
        )
        lineage = []
        if res and res.result_set:
            for row in res.result_set:
                lineage.append({
                    "session_id": row[0],
                    "created_at": row[1],
                    "episode_count": row[2] or 0,
                    "head_episode_id": row[3],
                    "tail_episode_id": row[4],
                    "tail_summary": row[5],
                })
        return lineage

    def update_episode_feedback(
        self,
        tenant_id: str,
        episode_id: str,
        reward: float,
        alpha: float = 0.2,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates an episode's utility score (MemRL) and decision threshold (vCache) post-execution."""
        t_id = tenant_id or settings.default_tenant_id
        now = time.time()
        params = {
            "episode_id": episode_id,
            "reward": float(reward),
            "alpha": float(alpha),
            "now": now,
        }
        res = self.router.query(
            EPISODE_UTILITY_FEEDBACK_UPDATE,
            params,
            tenant_id=t_id,
            user_id=user_id,
        )
        if res and res.result_set and res.result_set[0]:
            row = res.result_set[0]
            return {
                "status": "SUCCESS",
                "episode_id": row[0],
                "new_utility": row[1],
                "new_threshold": row[2],
                "access_count": row[3],
            }
        return {"status": "NOT_FOUND", "episode_id": episode_id}


episodic_memory = EpisodicMemoryManager()
