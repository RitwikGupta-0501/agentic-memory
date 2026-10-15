"""Semantic Memory Layer: Bi-temporal knowledge graph and HippoRAG hybrid retrieval."""

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.cypher_catalog import (
    BITEMPORAL_INVALIDATE_AND_UPSERT,
    HIPPORAG_HYBRID_RETRIEVAL,
)
from app.core.falkor_client import falkor_router


class EntityTriple(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0


class SemanticMemoryManager:
    """Manages bi-temporal entity relationships and HippoRAG retrieval."""

    def __init__(self, router=falkor_router):
        self.router = router

    def upsert_fact(
        self,
        tenant_id: str,
        subject: str,
        predicate: str,
        new_object: str,
        episode_id: str,
        confidence: float = 1.0,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes bi-temporal invalidation of superseded facts and inserts the new fact."""
        now = time.time()
        params = {
            "subject": subject.strip(),
            "predicate": predicate.strip().upper(),
            "new_object": new_object.strip(),
            "episode_id": episode_id,
            "confidence": confidence,
            "now": now,
        }

        res = self.router.query(
            BITEMPORAL_INVALIDATE_AND_UPSERT,
            params,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        invalidated_count = 0
        if res and res.result_set:
            invalidated_count = res.result_set[0][0]

        return {
            "subject": subject,
            "predicate": predicate,
            "object": new_object,
            "valid_from": now,
            "valid_to": None,
            "invalidated_count": invalidated_count,
            "source_episode": episode_id,
        }

    def hipporag_retrieve(
        self,
        tenant_id: str,
        seed_entities: List[str],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Hybrid HippoRAG retrieval: Seed entities -> 2-hop active neighborhood expansion."""
        if not seed_entities:
            return {"seeds": [], "subgraph": []}

        res = self.router.query(
            HIPPORAG_HYBRID_RETRIEVAL,
            {"seed_entities": seed_entities},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        results = []
        if res and res.result_set:
            for row in res.result_set:
                seed_node = row[0]
                results.append({
                    "seed": getattr(seed_node, "properties", {}).get("name", str(seed_node)),
                    "path_count": len(row[1]) if row[1] else 0,
                    "episodes_count": len(row[2]) if row[2] else 0,
                })

        return {"seeds": seed_entities, "matches": results}

    def extract_triples_from_text(self, text: str) -> List[EntityTriple]:
        """Extracts entity triples from text. Uses rule-based heuristics for mock mode."""
        lower = text.lower()
        triples = []

        # Common DevOps pattern heuristics for immediate out-of-the-box demo
        if "migrated" in lower and "to" in lower:
            # e.g., "We migrated Prod_DB from Postgres to FalkorDB"
            if "falkordb" in lower:
                triples.append(EntityTriple(subject="Prod_DB", predicate="USES_TECH", object="FalkorDB"))
            elif "postgres" in lower:
                triples.append(EntityTriple(subject="Prod_DB", predicate="USES_TECH", object="PostgreSQL"))
        elif "database is" in lower or "db is" in lower:
            if "postgres" in lower:
                triples.append(EntityTriple(subject="Prod_DB", predicate="USES_TECH", object="PostgreSQL"))
            elif "falkordb" in lower:
                triples.append(EntityTriple(subject="Prod_DB", predicate="USES_TECH", object="FalkorDB"))
        elif "primary service is" in lower:
            parts = text.split("is")
            if len(parts) > 1:
                triples.append(EntityTriple(subject="PrimaryService", predicate="IDENTIFIED_AS", object=parts[1].strip()))

        return triples


semantic_memory = SemanticMemoryManager()
