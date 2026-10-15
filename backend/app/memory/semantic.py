"""Semantic Memory Layer: Bi-temporal knowledge graph and HippoRAG hybrid retrieval."""

import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.cypher_catalog import (
    BITEMPORAL_INVALIDATE_AND_UPSERT,
    HIPPORAG_HYBRID_RETRIEVAL,
    SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING,
    SEMANTIC_PROVENANCE_UPSERT_AND_LINK,
    SEMANTIC_ENTITY_VECTOR_SEARCH,
)
from app.core.falkor_client import falkor_router
from app.core.embeddings.factory import embedding_service


class PredicateCardinality(str, Enum):
    SINGLE = "SINGLE"   # Functional: e.g. USES_TECH, PRIMARY_DB (invalidates previous)
    MULTI = "MULTI"     # Multi-valued: e.g. CONNECTS_TO, MONITORED_BY (accumulates)


class EntityRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"ent_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., min_length=1, max_length=128)
    canonical_name: str
    type: str = "Concept"
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class EntityTriple(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0


class SemanticFactInput(BaseModel):
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    episode_id: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    cardinality: PredicateCardinality = PredicateCardinality.SINGLE
    subject_type: str = "Entity"
    object_type: str = "Entity"


class SemanticMemoryManager:
    """Manages bi-temporal entity relationships, vector indexing, and bidirectional provenance."""

    def __init__(self, router=falkor_router, embeddings=embedding_service):
        self.router = router
        self.embeddings = embeddings

    @staticmethod
    def slugify(name: str) -> str:
        """Normalizes an entity name to a canonical lowercase slug."""
        clean = re.sub(r"[^a-z0-9]", "_", name.lower().strip())
        return re.sub(r"_+", "_", clean).strip("_")

    def ensure_entity(
        self,
        tenant_id: str,
        name: str,
        type: str = "Concept",
        description: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Idempotently merges an Entity node with canonical slug and dense embedding."""
        now = time.time()
        canonical = self.slugify(name)
        ent_id = f"ent_{uuid.uuid4().hex[:8]}"

        if embedding is None:
            embed_text = f"{name} ({type}): {description or name}"
            embedding = self.embeddings.embed_query(embed_text)

        params = {
            "id": ent_id,
            "name": name.strip(),
            "canonical_name": canonical,
            "type": type.strip(),
            "description": description or "",
            "embedding": embedding,
            "now": now,
        }

        res = self.router.query(
            SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING,
            params,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if res and res.result_set:
            row = res.result_set[0]
            return {
                "id": row[0],
                "name": row[1],
                "canonical_name": row[2],
                "type": row[3],
                "aliases": [name.strip()],
                "embedding": embedding,
            }

        return {
            "id": ent_id,
            "name": name.strip(),
            "canonical_name": canonical,
            "type": type.strip(),
            "aliases": [name.strip()],
            "embedding": embedding,
        }

    def upsert_fact(
        self,
        tenant_id: str,
        subject: str,
        predicate: str,
        new_object: str,
        episode_id: str,
        confidence: float = 1.0,
        cardinality: Any = "SINGLE",
        subject_type: str = "Entity",
        object_type: str = "Entity",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes bi-temporal invalidation and materializes bidirectional cross-layer provenance."""
        now = time.time()
        clean_subj = subject.strip()
        clean_pred = predicate.strip().upper()
        clean_obj = new_object.strip()

        card_str = cardinality.value if isinstance(cardinality, PredicateCardinality) else str(cardinality).upper()

        # Generate dense embeddings for entities
        s_vec = self.embeddings.embed_query(f"{clean_subj} ({subject_type})")
        o_vec = self.embeddings.embed_query(f"{clean_obj} ({object_type})")

        params = {
            "subject": clean_subj,
            "subject_id": f"ent_{uuid.uuid4().hex[:8]}",
            "subject_canonical": self.slugify(clean_subj),
            "subject_type": subject_type,
            "subject_vec": s_vec,
            "predicate": clean_pred,
            "object": clean_obj,
            "object_id": f"ent_{uuid.uuid4().hex[:8]}",
            "object_canonical": self.slugify(clean_obj),
            "object_type": object_type,
            "object_vec": o_vec,
            "episode_id": episode_id,
            "confidence": float(confidence),
            "cardinality": card_str,
            "now": now,
        }

        res = self.router.query(
            SEMANTIC_PROVENANCE_UPSERT_AND_LINK,
            params,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        invalidated_count = 0
        if res and res.result_set:
            invalidated_count = res.result_set[0][0]

        return {
            "subject": clean_subj,
            "predicate": clean_pred,
            "object": clean_obj,
            "valid_from": now,
            "valid_to": None,
            "invalidated_count": invalidated_count,
            "source_episode": episode_id,
            "cardinality": card_str,
        }

    def search_entities(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Vector similarity search over Entity nodes in FalkorDB."""
        query_vec = self.embeddings.embed_query(query)
        res = self.router.query(
            SEMANTIC_ENTITY_VECTOR_SEARCH,
            {"query_vec": query_vec, "limit": limit},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        entities = []
        if res and res.result_set:
            for row in res.result_set:
                raw_sim = float(row[5]) if len(row) > 5 else 0.0
                norm_sim = max(0.0, min(1.0, raw_sim))
                entities.append({
                    "id": row[0],
                    "name": row[1],
                    "canonical_name": row[2],
                    "type": row[3],
                    "aliases": row[4] or [],
                    "similarity": round(norm_sim, 4),
                })
        return entities

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

