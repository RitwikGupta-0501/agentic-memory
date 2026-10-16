"""Semantic Memory Layer: Bi-temporal knowledge graph and HippoRAG hybrid retrieval."""

import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.cypher_catalog import (
    BITEMPORAL_INVALIDATE_AND_UPSERT,
    HIPPORAG_HYBRID_RETRIEVAL,
    SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING,
    SEMANTIC_PROVENANCE_UPSERT_AND_LINK,
    SEMANTIC_ENTITY_VECTOR_SEARCH,
    SEMANTIC_ENTITY_FIND_BY_ALIAS,
    SEMANTIC_ENTITY_APPEND_ALIAS,
    SEMANTIC_ENTITY_VECTOR_SIMILARITY,
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

    @staticmethod
    def _token_jaccard(a: str, b: str) -> float:
        """Calculates token-level Jaccard similarity across punctuation/whitespace splits."""
        set_a = set(re.split(r"[\s_\-]+", a.lower().strip()))
        set_b = set(re.split(r"[\s_\-]+", b.lower().strip()))
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def resolve_entity(
        self,
        tenant_id: str,
        raw_name: str,
        entity_type: str = "Concept",
        user_id: Optional[str] = None,
    ) -> str:
        """Resolves a raw entity mention or alias to its canonical name."""
        details = self.resolve_entity_detailed(
            tenant_id=tenant_id,
            raw_name=raw_name,
            entity_type=entity_type,
            user_id=user_id,
        )
        return details["canonical_name"]

    def resolve_entity_detailed(
        self,
        tenant_id: str,
        raw_name: str,
        entity_type: str = "Concept",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes 3-step entity resolution (canonical slug/alias -> dense vector similarity -> Jaccard fallback)."""
        clean_name = raw_name.strip()
        if not clean_name:
            return {
                "raw_name": raw_name,
                "canonical_name": raw_name,
                "resolved": False,
                "method": "empty_input",
                "similarity": 0.0,
                "aliases": [],
            }

        slug = self.slugify(clean_name)

        # Step 1: Exact canonical slug or alias array match
        exact_match = self.router.query(
            SEMANTIC_ENTITY_FIND_BY_ALIAS,
            {"slug": slug, "raw_name": clean_name},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if exact_match and exact_match.result_set:
            row = exact_match.result_set[0]
            matched_name = row[1]
            aliases = row[4] or []
            return {
                "raw_name": clean_name,
                "canonical_name": matched_name,
                "resolved": matched_name.lower() != clean_name.lower(),
                "method": "exact_match",
                "similarity": 1.0,
                "aliases": aliases,
            }

        # Step 2: Dense vector similarity search with adaptive threshold
        threshold = 0.50 if settings.embedding_provider == "mock" else 0.85
        vec = self.embeddings.embed_query(clean_name)

        vector_match = self.router.query(
            SEMANTIC_ENTITY_VECTOR_SIMILARITY,
            {"candidate_limit": 5, "vec": vec, "threshold": threshold},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if vector_match and vector_match.result_set:
            row = vector_match.result_set[0]
            matched_name = row[1]
            sim = float(row[5]) if len(row) > 5 else 1.0

            # Step 3: Append alias deduplicated to existing node
            now = time.time()
            append_res = self.router.query(
                SEMANTIC_ENTITY_APPEND_ALIAS,
                {"canonical_name": matched_name, "raw_name": clean_name, "now": now},
                tenant_id=tenant_id,
                user_id=user_id,
            )
            updated_aliases = []
            if append_res and append_res.result_set:
                updated_aliases = append_res.result_set[0][1] or []

            return {
                "raw_name": clean_name,
                "canonical_name": matched_name,
                "resolved": True,
                "method": "vector_similarity",
                "similarity": round(sim, 4),
                "aliases": updated_aliases,
            }

        # Lexical Jaccard token overlap fallback (especially useful for mock provider)
        all_entities = self.search_entities(tenant_id=tenant_id, query=clean_name, limit=10, user_id=user_id)
        for ent in all_entities:
            jaccard = self._token_jaccard(clean_name, ent["name"])
            if jaccard >= 0.50:
                now = time.time()
                self.router.query(
                    SEMANTIC_ENTITY_APPEND_ALIAS,
                    {"canonical_name": ent["name"], "raw_name": clean_name, "now": now},
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                return {
                    "raw_name": clean_name,
                    "canonical_name": ent["name"],
                    "resolved": True,
                    "method": "lexical_jaccard",
                    "similarity": round(jaccard, 4),
                    "aliases": ent.get("aliases", []),
                }

        # Novel entity (not found in graph)
        return {
            "raw_name": clean_name,
            "canonical_name": clean_name,
            "resolved": False,
            "method": "new_entity",
            "similarity": 0.0,
            "aliases": [clean_name],
        }


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
        resolve_entities: bool = True,
    ) -> Dict[str, Any]:
        """Executes bi-temporal invalidation and materializes bidirectional cross-layer provenance."""
        now = time.time()
        clean_subj = subject.strip()
        clean_pred = predicate.strip().upper()
        clean_obj = new_object.strip()

        if resolve_entities:
            clean_subj = self.resolve_entity(tenant_id, clean_subj, subject_type, user_id=user_id)
            clean_obj = self.resolve_entity(tenant_id, clean_obj, object_type, user_id=user_id)

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

