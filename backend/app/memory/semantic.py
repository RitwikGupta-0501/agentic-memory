import math
import re
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.cypher_catalog import (
    BITEMPORAL_INVALIDATE_AND_UPSERT,
    HIPPORAG_HYBRID_RETRIEVAL,
    HIPPORAG_SEED_VECTOR_SEARCH,
    HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION,
    HIPPORAG_EPISODE_GROUNDING_EXPANSION,
    SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING,
    SEMANTIC_PROVENANCE_UPSERT_AND_LINK,
    SEMANTIC_ENTITY_VECTOR_SEARCH,
    SEMANTIC_ENTITY_FIND_BY_ALIAS,
    SEMANTIC_ENTITY_APPEND_ALIAS,
    SEMANTIC_ENTITY_VECTOR_SIMILARITY,
    SEMANTIC_TIME_TRAVEL_SNAPSHOT,
    SEMANTIC_ENTITY_EVOLUTION_TIMELINE,
    SEMANTIC_TIME_TRAVEL_SUBGRAPH,
    SEMANTIC_CYTOSCAPE_TIME_TRAVEL,
)
from app.core.falkor_client import falkor_router
from app.core.embeddings.factory import embedding_service
from app.memory.prompts import (
    OPENIE_SYSTEM_PROMPT,
    format_openie_prompt,
    infer_predicate_cardinality,
    CANONICAL_PREDICATES,
)


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


class SemanticTriple(BaseModel):
    subject: str = Field(description="The dependent, consumer, or caller entity")
    predicate: str = Field(description="Canonical uppercase relationship predicate (e.g. USES_TECH, CONNECTS_TO, RUNS_ON)")
    object: str = Field(description="The target dependency, technology, host, or callee entity")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    cardinality: str = Field(default="SINGLE", description="Cardinality: SINGLE or MULTI")
    subject_type: str = Field(default="Concept", description="Entity category for subject")
    object_type: str = Field(default="Concept", description="Entity category for object")


class ExtractedEntity(BaseModel):
    name: str = Field(description="Proper entity name (e.g. Prod_DB, PostgreSQL_16)")
    canonical_name: Optional[str] = Field(default=None, description="Normalized slug")
    type: str = Field(default="Concept", description="Category: Database, Service, Infrastructure, etc.")
    description: Optional[str] = Field(default=None, description="Concise technical summary")


class FactExtractionResult(BaseModel):
    triples: List[SemanticTriple] = Field(default_factory=list, description="Extracted knowledge graph facts")
    entities: List[ExtractedEntity] = Field(default_factory=list, description="Extracted entities with categories and descriptions")
    summary: str = Field(default="", description="One-line summary of factual assertions")
    reasoning: Optional[str] = Field(default=None, description="Extraction reasoning and invariants")


class SemanticFactInput(BaseModel):
    subject: str = Field(..., min_length=1)
    predicate: str = Field(..., min_length=1)
    object: str = Field(..., min_length=1)
    episode_id: str = Field(..., min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    cardinality: PredicateCardinality = PredicateCardinality.SINGLE
    subject_type: str = "Entity"
    object_type: str = "Entity"


class HippoRAGRankedEntity(BaseModel):
    name: str
    type: str = "Concept"
    raw_ppr: float
    degree_normalized_score: float
    is_seed: bool = False


class HippoRAGGroundedEpisode(BaseModel):
    episode_id: str
    content: str
    role: str = "system"
    importance_score: float
    grounded_score: float
    contributing_entities: List[str] = Field(default_factory=list)


class HippoRAGResult(BaseModel):
    status: str = "SUCCESS"
    seeds: List[str] = Field(default_factory=list)
    seed_scores: Dict[str, float] = Field(default_factory=dict)
    as_of: float
    ranked_entities: List[HippoRAGRankedEntity] = Field(default_factory=list)
    ranked_episodes: List[HippoRAGGroundedEpisode] = Field(default_factory=list)
    active_subgraph_edges: List[Dict[str, Any]] = Field(default_factory=list)

    def __getitem__(self, item: str) -> Any:
        if item == "matches":
            return [e.model_dump() for e in self.ranked_entities]
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        if item == "matches":
            return [e.model_dump() for e in self.ranked_entities]
        return getattr(self, item, default)


def _compute_personalized_pagerank(
    adj: Dict[str, List[Tuple[str, float]]],
    p0: Dict[str, float],
    all_nodes: List[str],
    alpha: float = 0.85,
    max_iter: int = 25,
    tol: float = 1e-5,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Executes sparse power-iteration Personalized PageRank with sublinear hub damping."""
    if not all_nodes:
        return {}, {}

    total_p0 = sum(p0.get(u, 0.0) for u in all_nodes)
    if total_p0 > 0:
        norm_p0 = {u: p0.get(u, 0.0) / total_p0 for u in all_nodes}
    else:
        uniform_val = 1.0 / len(all_nodes)
        norm_p0 = {u: uniform_val for u in all_nodes}

    # 1. Build transition probability matrix P and degree dictionary
    P: Dict[str, Dict[str, float]] = {}
    deg: Dict[str, float] = {}
    for u in all_nodes:
        nbrs = adj.get(u, [])
        total_w = sum(w for _, w in nbrs)
        deg[u] = total_w
        if total_w > 0:
            P[u] = {v: w / total_w for v, w in nbrs}
        else:
            P[u] = {}

    pi = dict(norm_p0)
    for _ in range(max_iter):
        next_pi = {u: (1.0 - alpha) * norm_p0.get(u, 0.0) for u in all_nodes}
        # Sink mass redistribution
        sink_mass = sum(pi[u] for u in all_nodes if not P[u])
        for u in all_nodes:
            next_pi[u] += alpha * sink_mass * norm_p0.get(u, 0.0)
        # Random walk transfer
        for u, trans in P.items():
            mass = pi.get(u, 0.0)
            if mass > 0:
                for v, prob in trans.items():
                    next_pi[v] += alpha * mass * prob
        diff = sum(abs(next_pi[u] - pi[u]) for u in all_nodes)
        pi = next_pi
        if diff < tol:
            break

    # Sublinear hub damping + seed prior preservation
    norm_pi = {
        u: (pi[u] / (1.0 + math.log1p(deg.get(u, 0.0)))) + (0.15 * norm_p0.get(u, 0.0))
        for u in all_nodes
    }
    return pi, norm_pi



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
        """Calculates token-level Jaccard similarity with DevOps abbreviation expansion."""
        abbr = {
            "prod": "production",
            "dev": "development",
            "stg": "staging",
            "stage": "staging",
            "db": "database",
            "k8s": "kubernetes",
            "cfg": "config",
            "conf": "config",
            "auth": "authentication",
            "gw": "gateway",
            "msg": "message",
            "srv": "service",
            "svc": "service",
            "pg": "postgresql",
            "postgres": "postgresql",
            "psql": "postgresql",
        }
        tokens_a = {abbr.get(w, w) for w in re.split(r"[\s_\-]+", a.lower().strip()) if w}
        tokens_b = {abbr.get(w, w) for w in re.split(r"[\s_\-]+", b.lower().strip()) if w}
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
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
            if clean_name not in aliases:
                now = time.time()
                append_res = self.router.query(
                    SEMANTIC_ENTITY_APPEND_ALIAS,
                    {"canonical_name": matched_name, "raw_name": clean_name, "now": now},
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                if append_res and append_res.result_set:
                    aliases = append_res.result_set[0][1] or aliases
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

        # Lexical Jaccard token overlap fallback across existing active entities
        all_res = self.router.query(
            "MATCH (e:Entity) RETURN e.name AS name, coalesce(e.aliases, []) AS aliases LIMIT 50",
            {},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if all_res and all_res.result_set:
            for row in all_res.result_set:
                ent_name = row[0]
                ent_aliases = row[1] or []
                jaccard = self._token_jaccard(clean_name, ent_name)
                if jaccard >= 0.50:
                    now = time.time()
                    append_res = self.router.query(
                        SEMANTIC_ENTITY_APPEND_ALIAS,
                        {"canonical_name": ent_name, "raw_name": clean_name, "now": now},
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    updated_aliases = append_res.result_set[0][1] if append_res and append_res.result_set else ent_aliases
                    return {
                        "raw_name": clean_name,
                        "canonical_name": ent_name,
                        "resolved": True,
                        "method": "lexical_jaccard",
                        "similarity": round(jaccard, 4),
                        "aliases": updated_aliases,
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

    def append_entity_alias(
        self,
        tenant_id: str,
        canonical_name: str,
        raw_alias: str,
        user_id: Optional[str] = None,
    ) -> List[str]:
        """Appends a new alias to an existing entity."""
        res = self.router.query(
            SEMANTIC_ENTITY_APPEND_ALIAS,
            {"canonical_name": canonical_name, "raw_name": raw_alias.strip(), "now": time.time()},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if res and res.result_set:
            return res.result_set[0][1] or []
        return []

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
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Executes bi-temporal invalidation and materializes bidirectional cross-layer provenance."""
        now = float(timestamp) if timestamp is not None else time.time()
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
        valid_from = now
        if res and res.result_set:
            invalidated_count = res.result_set[0][0]
            valid_from = float(res.result_set[0][4]) if res.result_set[0][4] is not None else now

        return {
            "subject": clean_subj,
            "predicate": clean_pred,
            "object": clean_obj,
            "valid_from": valid_from,
            "valid_to": None,
            "invalidated_count": invalidated_count,
            "source_episode": episode_id,
            "cardinality": card_str,
        }

    def get_snapshot(
        self,
        tenant_id: str,
        as_of: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns the full knowledge graph state active at timestamp as_of."""
        target_t = float(as_of) if as_of is not None else time.time()
        res = self.router.query(
            SEMANTIC_TIME_TRAVEL_SNAPSHOT,
            {"as_of": target_t},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        facts = []
        if res and res.result_set:
            for row in res.result_set:
                facts.append({
                    "subject": row[0],
                    "subject_type": row[1],
                    "predicate": row[2],
                    "cardinality": row[3],
                    "confidence": float(row[4]),
                    "valid_from": float(row[5]),
                    "valid_to": float(row[6]) if row[6] is not None else None,
                    "source_episode": row[7],
                    "object": row[8],
                    "object_type": row[9],
                })
        return facts

    def get_entity_history(
        self,
        tenant_id: str,
        entity_name: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns the full chronological evolution of all relationships an entity participated in."""
        clean_name = self.resolve_entity(tenant_id, entity_name, user_id=user_id)
        slug = self.slugify(clean_name)
        res = self.router.query(
            SEMANTIC_ENTITY_EVOLUTION_TIMELINE,
            {"entity_name": clean_name, "slug": slug},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        timeline = []
        active_count = 0
        superseded_count = 0
        if res and res.result_set:
            for row in res.result_set:
                status = row[9]
                if status == "ACTIVE":
                    active_count += 1
                else:
                    superseded_count += 1
                timeline.append({
                    "subject": row[0],
                    "predicate": row[1],
                    "object": row[2],
                    "cardinality": row[3],
                    "confidence": float(row[4]),
                    "valid_from": float(row[5]),
                    "valid_to": float(row[6]) if row[6] is not None else None,
                    "source_episode": row[7],
                    "invalidated_by_episode": row[8],
                    "status": status,
                })
        return {
            "entity_name": clean_name,
            "total_transitions": len(timeline),
            "active_facts_count": active_count,
            "superseded_facts_count": superseded_count,
            "timeline": timeline,
        }

    def get_time_travel_subgraph(
        self,
        tenant_id: str,
        seed_entity: str,
        as_of: Optional[float] = None,
        depth: int = 1,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns point-in-time neighborhood view around a seed entity."""
        target_t = float(as_of) if as_of is not None else time.time()
        clean_name = self.resolve_entity(tenant_id, seed_entity, user_id=user_id)
        slug = self.slugify(clean_name)
        res = self.router.query(
            SEMANTIC_TIME_TRAVEL_SUBGRAPH,
            {"seed_name": clean_name, "slug": slug, "as_of": target_t},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if res and res.result_set:
            row = res.result_set[0]
            raw_rels = row[2] or []
            clean_rels = [r for r in raw_rels if r and r.get("target") is not None]
            raw_neighbors = row[3] or []
            clean_neighbors = [n for n in raw_neighbors if n is not None]
            return {
                "seed": row[0],
                "seed_type": row[1],
                "as_of": target_t,
                "relationships": clean_rels,
                "neighbors": clean_neighbors,
            }
        return {
            "seed": clean_name,
            "seed_type": "Concept",
            "as_of": target_t,
            "relationships": [],
            "neighbors": [],
        }

    def get_cytoscape_elements_as_of(
        self,
        tenant_id: str,
        as_of: Optional[float] = None,
        include_invalidated: bool = True,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Converts FalkorDB query results into Cytoscape.js format with visual dual-edge styling."""
        target_t = float(as_of) if as_of is not None else time.time()
        res = self.router.query(
            SEMANTIC_CYTOSCAPE_TIME_TRAVEL,
            {"as_of": target_t, "include_invalidated": include_invalidated},
            tenant_id=tenant_id,
            user_id=user_id,
        )
        elements: Dict[str, List[Dict[str, Any]]] = {"nodes": [], "edges": []}
        if res and res.result_set:
            raw_nodes, raw_edges = res.result_set[0]
            for n in raw_nodes or []:
                if n and n.get("name"):
                    elements["nodes"].append({
                        "data": {
                            "id": n["name"],
                            "label": n["name"],
                            "canonical_name": n.get("canonical_name", ""),
                            "type": n.get("type", "Concept"),
                            "created_at": n.get("created_at"),
                        }
                    })
            for e in raw_edges or []:
                if e and e.get("target") is not None:
                    is_active = e.get("status") == "ACTIVE"
                    elements["edges"].append({
                        "data": {
                            "id": f"e_{e['source']}_{e['predicate']}_{e['target']}_{int(e.get('valid_from', 0))}",
                            "source": e["source"],
                            "target": e["target"],
                            "label": e["predicate"],
                            "cardinality": e.get("cardinality", "SINGLE"),
                            "valid_from": e.get("valid_from"),
                            "valid_to": e.get("valid_to"),
                            "status": e.get("status"),
                            "line_style": "solid" if is_active else "dashed",
                            "color": "#10b981" if is_active else "#ef4444",
                        }
                    })
        return elements




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

    def _has_lexical_overlap(self, query: str, entity_name: str, aliases: List[str]) -> bool:
        """Determines if there is meaningful lexical or abbreviation overlap between query and entity."""
        q_clean = query.lower()
        q_tokens = set(re.findall(r"\w+", q_clean))
        cand_strings = [entity_name] + (aliases or [])
        for s in cand_strings:
            s_clean = s.lower().replace("_", " ")
            s_tokens = set(re.findall(r"\w+", s_clean))
            if q_tokens & s_tokens:
                return True
            if s_clean in q_clean or (len(s_clean) >= 3 and s_clean in q_clean):
                return True
            if self._token_jaccard(query, s) > 0.15:
                return True
        return False

    def hipporag_find_seeds(
        self,
        tenant_id: str,
        query: Optional[str] = None,
        seed_entities: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        candidate_limit: int = 10,
        min_similarity: float = 0.45,
    ) -> Dict[str, float]:
        """Hybrid seed entity discovery via explicit entities, alias matching, and vector search."""
        seed_scores: Dict[str, float] = {}

        # 1. Explicit seed entities
        if seed_entities:
            for s in seed_entities:
                if not s or not s.strip():
                    continue
                try:
                    resolved = self.resolve_entity(tenant_id=tenant_id, raw_name=s.strip(), user_id=user_id)
                    seed_scores[resolved] = 1.0
                except Exception:
                    seed_scores[s.strip()] = 1.0

        # 2. Query-based seed discovery
        if query and query.strip():
            clean_query = query.strip()
            # 2a. N-gram alias matching (from length 4 down to 1)
            words = [w for w in re.split(r"[\s,;:.!?]+", clean_query) if w]
            for n in range(min(4, len(words)), 0, -1):
                for i in range(len(words) - n + 1):
                    phrase = " ".join(words[i : i + n])
                    if len(phrase) < 2:
                        continue
                    res = self.router.query(
                        SEMANTIC_ENTITY_FIND_BY_ALIAS,
                        {"slug": self.slugify(phrase), "raw_name": phrase},
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    if res and res.result_set:
                        row = res.result_set[0]
                        ent_name = row[1]
                        seed_scores[ent_name] = max(seed_scores.get(ent_name, 0.0), 1.0)

            # 2b. Dense vector similarity search
            try:
                q_vec = self.embeddings.embed_query(clean_query)
                res = self.router.query(
                    HIPPORAG_SEED_VECTOR_SEARCH,
                    {
                        "candidate_limit": candidate_limit,
                        "query_vec": q_vec,
                        "min_similarity": min_similarity,
                    },
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                is_mock = getattr(self.embeddings, "is_mock", False) or settings.embedding_provider.lower() == "mock"
                if res and res.result_set:
                    for row in res.result_set:
                        ent_name = row[0]
                        ent_aliases = row[3] or []
                        sim = float(row[4]) if len(row) > 4 else 0.0
                        norm_sim = max(0.0, min(1.0, sim))

                        # Bug 3 mitigation: In mock mode, reject candidates without lexical/alias overlap
                        if is_mock and not self._has_lexical_overlap(clean_query, ent_name, ent_aliases):
                            continue

                        seed_scores[ent_name] = max(seed_scores.get(ent_name, 0.0), round(norm_sim, 4))
            except Exception:
                pass

        return seed_scores

    def hipporag_ground_episodes(
        self,
        tenant_id: str,
        norm_pi: Dict[str, float],
        as_of: float,
        user_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[HippoRAGGroundedEpisode]:
        """Projects entity activation mass onto episodic memory with temporal and invalidation gating."""
        if not norm_pi:
            return []

        active_entities = [name for name, score in norm_pi.items() if score > 0.0]
        if not active_entities:
            return []

        res = self.router.query(
            HIPPORAG_EPISODE_GROUNDING_EXPANSION,
            {
                "entity_names": active_entities,
                "as_of": as_of,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not res or not res.result_set:
            return []

        episodes_map: Dict[str, Dict[str, Any]] = {}
        for row in res.result_set:
            ent_name = row[0]
            link_type = str(row[1]) if row[1] else "DERIVED_FROM"
            ep_id = row[2]
            content = row[3] or ""
            role = row[4] or "system"
            importance = float(row[5]) if row[5] is not None else 0.5
            timestamp = float(row[6]) if row[6] is not None else 0.0

            w_link = 1.0 if link_type == "DERIVED_FROM" else 0.6
            ent_score = norm_pi.get(ent_name, 0.0)
            contrib = ent_score * w_link * importance

            if ep_id not in episodes_map:
                episodes_map[ep_id] = {
                    "episode_id": ep_id,
                    "content": content,
                    "role": role,
                    "importance_score": importance,
                    "timestamp": timestamp,
                    "grounded_score": 0.0,
                    "contributing_entities": set(),
                }

            episodes_map[ep_id]["grounded_score"] += contrib
            episodes_map[ep_id]["contributing_entities"].add(ent_name)

        ranked = [
            HippoRAGGroundedEpisode(
                episode_id=data["episode_id"],
                content=data["content"],
                role=data["role"],
                importance_score=round(data["importance_score"], 4),
                grounded_score=round(data["grounded_score"], 6),
                contributing_entities=sorted(list(data["contributing_entities"])),
            )
            for data in episodes_map.values()
        ]
        ranked.sort(key=lambda x: x.grounded_score, reverse=True)
        return ranked[:top_k]

    def hipporag_retrieve(
        self,
        tenant_id: str,
        query: Optional[str] = None,
        seed_entities: Optional[List[str]] = None,
        top_k: int = 5,
        damping: float = 0.85,
        max_hops: int = 2,
        as_of: Optional[float] = None,
        user_id: Optional[str] = None,
    ) -> HippoRAGResult:
        """Executes NeurIPS 2024 HippoRAG associative retrieval over active knowledge graph."""
        target_t = float(as_of) if as_of is not None else time.time()

        # Step 1: Hybrid Seed Discovery (lexical exact + alias + vector with mock guards)
        seed_scores = self.hipporag_find_seeds(
            tenant_id=tenant_id,
            query=query,
            seed_entities=seed_entities,
            user_id=user_id,
        )

        if not seed_scores:
            return HippoRAGResult(
                status="NO_SEEDS_FOUND",
                seeds=[],
                seed_scores={},
                as_of=target_t,
                ranked_entities=[],
                ranked_episodes=[],
                active_subgraph_edges=[],
            )

        seeds = list(seed_scores.keys())

        # Step 2: Fetch Active Subgraph within max_hops (bi-temporal filtering)
        subgraph_res = self.router.query(
            HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION,
            {
                "seed_names": seeds,
                "as_of": target_t,
                "max_hops": max(1, min(3, max_hops)),
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )

        adj: Dict[str, List[Tuple[str, float]]] = {}
        edges: List[Dict[str, Any]] = []
        all_nodes_set = set(seeds)

        if subgraph_res and subgraph_res.result_set:
            for row in subgraph_res.result_set:
                src = row[0]
                pred = row[1]
                tgt = row[2]
                w = float(row[3]) if row[3] is not None else 1.0
                v_from = float(row[4]) if row[4] is not None else 0.0
                v_to = float(row[5]) if row[5] is not None else None

                edges.append({
                    "source": src,
                    "predicate": pred,
                    "target": tgt,
                    "weight": w,
                    "valid_from": v_from,
                    "valid_to": v_to,
                })
                # Undirected graph for spreading activation (Collins & Loftus 1975)
                adj.setdefault(src, []).append((tgt, w))
                adj.setdefault(tgt, []).append((src, w))
                all_nodes_set.add(src)
                all_nodes_set.add(tgt)

        # Step 3: Compute Personalized PageRank spreading activation
        all_nodes = sorted(list(all_nodes_set))
        p0 = {u: seed_scores.get(u, 0.0) for u in all_nodes}
        raw_pi, norm_pi = _compute_personalized_pagerank(
            adj=adj,
            p0=p0,
            all_nodes=all_nodes,
            alpha=damping,
        )

        # Step 4: Rank entities
        sorted_nodes = sorted(
            all_nodes,
            key=lambda u: (norm_pi.get(u, 0.0), raw_pi.get(u, 0.0)),
            reverse=True,
        )
        ranked_entities = [
            HippoRAGRankedEntity(
                name=u,
                raw_ppr=round(raw_pi.get(u, 0.0), 6),
                degree_normalized_score=round(norm_pi.get(u, 0.0), 6),
                is_seed=(u in seed_scores),
            )
            for u in sorted_nodes
        ]

        # Step 5: Bipartite Projection onto Grounded Episodes
        ranked_episodes = self.hipporag_ground_episodes(
            tenant_id=tenant_id,
            norm_pi=norm_pi,
            as_of=target_t,
            user_id=user_id,
            top_k=top_k,
        )

        # Step 6: Return structured result
        return HippoRAGResult(
            status="SUCCESS",
            seeds=seeds,
            seed_scores=seed_scores,
            as_of=target_t,
            ranked_entities=ranked_entities[:top_k * 2],
            ranked_episodes=ranked_episodes,
            active_subgraph_edges=edges,
        )

    def _get_structured_llm(self):
        """Constructs a LangChain chat model with structured FactExtractionResult output."""
        provider = settings.llm_provider.lower().strip()
        if provider == "openai" and settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.0,
                api_key=settings.openai_api_key,
            )
            return llm.with_structured_output(FactExtractionResult)
        elif provider == "gemini" and settings.gemini_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=0.0,
                google_api_key=settings.gemini_api_key,
            )
            return llm.with_structured_output(FactExtractionResult)
        elif provider == "anthropic" and settings.anthropic_api_key:
            try:
                from langchain_anthropic import ChatAnthropic
                llm = ChatAnthropic(
                    model="claude-3-5-sonnet-20241022",
                    temperature=0.0,
                    api_key=settings.anthropic_api_key,
                )
                return llm.with_structured_output(FactExtractionResult)
            except ImportError:
                pass
        return None

    def extract_facts(self, text: str) -> FactExtractionResult:
        """Extracts structured OpenIE facts using real LLM if configured, or multi-domain fallback heuristic."""
        clean_text = text.strip()
        if not clean_text:
            return FactExtractionResult(triples=[], entities=[], summary="Empty text provided.")

        # Try real LLM structured extraction if configured
        if settings.llm_provider != "mock":
            try:
                structured_llm = self._get_structured_llm()
                if structured_llm is not None:
                    prompt = format_openie_prompt(clean_text)
                    result = structured_llm.invoke(prompt)
                    if isinstance(result, FactExtractionResult):
                        for t in result.triples:
                            if not t.cardinality:
                                t.cardinality = infer_predicate_cardinality(t.predicate)
                        for e in result.entities:
                            if not e.canonical_name:
                                e.canonical_name = self.slugify(e.name)
                        return result
                    elif isinstance(result, dict):
                        return FactExtractionResult(**result)
            except Exception as e:
                import logging
                logging.getLogger("aegis.semantic").warning(f"LLM extraction failed, using heuristic: {e}")

        # Deterministic multi-domain rule heuristic
        return self._rule_based_extract_facts(clean_text)

    def _rule_based_extract_facts(self, text: str) -> FactExtractionResult:
        """Deterministic multi-domain OpenIE extraction heuristic."""
        lower = text.lower().strip()

        # 1. Negative control: Greetings
        greetings = ("hello", "hi", "hey", "good morning", "good afternoon", "good evening", "howdy")
        words = re.findall(r"\w+", lower)
        if any(lower.startswith(g) for g in greetings) and len(words) <= 6:
            return FactExtractionResult(
                triples=[],
                entities=[],
                summary="User greeting; no declarative facts asserted.",
                reasoning="Conversational greeting without architectural assertions.",
            )

        # 2. Negative control: Troubleshooting questions without state mutation
        is_question = lower.endswith("?") or lower.startswith(
            ("can you ", "could you ", "why ", "what ", "how ", "where ", "is there ", "who ")
        )
        has_declarative = any(
            k in lower for k in [
                "migrated", "upgraded", "runs on", "hosted on", "connects to",
                "depends on", "monitored by", "replica", "database is", "db is"
            ]
        )
        if is_question and not has_declarative:
            return FactExtractionResult(
                triples=[],
                entities=[],
                summary="Operational troubleshooting inquiry; no new declarative facts asserted.",
                reasoning="Inquiry contains no architectural mutations.",
            )

        triples: List[SemanticTriple] = []
        entities_map: Dict[str, ExtractedEntity] = {}

        def add_triple(
            s: str,
            p: str,
            o: str,
            s_type: str = "Concept",
            o_type: str = "Concept",
            conf: float = 1.0,
            card: Optional[str] = None,
        ):
            p_norm = p.strip().upper()
            c_norm = card or infer_predicate_cardinality(p_norm)
            triples.append(
                SemanticTriple(
                    subject=s.strip(),
                    predicate=p_norm,
                    object=o.strip(),
                    confidence=conf,
                    cardinality=c_norm,
                    subject_type=s_type,
                    object_type=o_type,
                )
            )
            s_clean = s.strip()
            if s_clean not in entities_map:
                entities_map[s_clean] = ExtractedEntity(
                    name=s_clean,
                    canonical_name=self.slugify(s_clean),
                    type=s_type,
                    description=f"{s_clean} ({s_type})",
                )
            o_clean = o.strip()
            if o_clean not in entities_map:
                entities_map[o_clean] = ExtractedEntity(
                    name=o_clean,
                    canonical_name=self.slugify(o_clean),
                    type=o_type,
                    description=f"{o_clean} ({o_type})",
                )

        # Pattern 1: Database/Technology Migration
        if "migrat" in lower and "to" in lower:
            subj = "Prod_DB"
            m_subj = re.search(r"(?:cutover for|migrated|migrating)\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
            if m_subj and m_subj.group(1).lower() not in ("from", "to", "we", "the", "our"):
                subj = m_subj.group(1).strip()

            target_tech = "FalkorDB" if "falkordb" in lower else "PostgreSQL" if "postgres" in lower else None
            if not target_tech:
                m_to = re.search(r"\bto\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
                if m_to:
                    target_tech = m_to.group(1).strip()

            if target_tech:
                add_triple(subj, "USES_TECH", target_tech, s_type="Infrastructure", o_type="Database", conf=1.0, card="SINGLE")

        elif "database is" in lower or "db is" in lower:
            target_tech = "PostgreSQL" if "postgres" in lower else "FalkorDB" if "falkordb" in lower else "PostgreSQL"
            add_triple("Prod_DB", "USES_TECH", target_tech, s_type="Infrastructure", o_type="Database", conf=1.0, card="SINGLE")

        elif "upgraded to" in lower or "upgraded" in lower:
            m_up = re.search(r"([A-Za-z0-9_\-]+)\s+(?:cluster\s+)?upgraded(?:\s+to)?\s+([A-Za-z0-9_.\-]+)", text, re.IGNORECASE)
            if m_up:
                subj = m_up.group(1).strip()
                ver = m_up.group(2).strip()
                add_triple(subj, "USES_TECH", ver, s_type="Infrastructure", o_type="Tool", conf=0.95, card="SINGLE")
            if "calico" in lower:
                add_triple("Kubernetes", "CONFIGURED_WITH", "Calico", s_type="Infrastructure", o_type="Tool", conf=0.90, card="SINGLE")

        # Pattern 2: Service Runtime & Hosting
        m_runs = re.search(r"([A-Za-z0-9_\-]+)\s+(?:microservice\s+|service\s+)?runs on\s+(?:our\s+)?([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m_runs:
            subj = m_runs.group(1).strip()
            host = m_runs.group(2).strip()
            add_triple(subj, "RUNS_ON", host, s_type="Service", o_type="Infrastructure", conf=0.98, card="SINGLE")

        m_hosted = re.search(r"([A-Za-z0-9_\-]+)\s+(?:is\s+)?hosted on\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m_hosted:
            subj = m_hosted.group(1).strip()
            host = m_hosted.group(2).strip()
            add_triple(subj, "HOSTED_ON", host, s_type="Service", o_type="Infrastructure", conf=0.98, card="SINGLE")

        # Pattern 3: Networking & Service Connections
        m_conn = re.search(r"([A-Za-z0-9_\-]+)\s+connects to\s+([^.]+)", text, re.IGNORECASE)
        if m_conn:
            subj = m_conn.group(1).strip()
            targets_blob = m_conn.group(2).strip()
            parts = re.split(r",|\sand\s", targets_blob)
            for p in parts:
                cleaned = re.sub(r"[^\w\-]", "", p.strip())
                if cleaned and cleaned.lower() not in ("and", "the", "our", "a"):
                    t_type = "Database" if "db" in cleaned.lower() else "ExternalAPI" if any(k in cleaned.lower() for k in ["gateway", "api", "stripe"]) else "Service"
                    add_triple(subj, "CONNECTS_TO", cleaned, s_type="Service", o_type=t_type, conf=0.95, card="MULTI")

        # Pattern 4: Dependencies
        m_dep = re.search(r"([A-Za-z0-9_\-]+)\s+depends on\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m_dep:
            subj = m_dep.group(1).strip()
            dep = m_dep.group(2).strip()
            add_triple(subj, "DEPENDS_ON", dep, s_type="Service", o_type="Service", conf=0.95, card="MULTI")

        # Pattern 5: Monitoring & Observability
        m_mon = re.search(r"([A-Za-z0-9_\-]+)\s+(?:is\s+)?monitored by\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m_mon:
            subj = m_mon.group(1).strip()
            tool = m_mon.group(2).strip()
            add_triple(subj, "MONITORED_BY", tool, s_type="Service", o_type="Tool", conf=0.95, card="MULTI")

        # Pattern 6: High Availability Replicas
        m_rep = re.search(r"([A-Za-z0-9_\-]+)\s+has replica\s+([A-Za-z0-9_\-]+)", text, re.IGNORECASE)
        if m_rep:
            subj = m_rep.group(1).strip()
            rep = m_rep.group(2).strip()
            add_triple(subj, "HAS_REPLICA", rep, s_type="Database", o_type="Database", conf=0.95, card="MULTI")

        # Pattern 7: Primary service identifier
        if "primary service is" in lower:
            parts = text.split("is")
            if len(parts) > 1:
                target = parts[1].strip().split()[0].strip()
                add_triple("PrimaryService", "IDENTIFIED_AS", target, s_type="Service", o_type="Service", conf=1.0, card="SINGLE")

        summary = f"Extracted {len(triples)} facts for {', '.join(entities_map.keys())}." if triples else "No declarative knowledge graph facts asserted in input."
        return FactExtractionResult(
            triples=triples,
            entities=list(entities_map.values()),
            summary=summary,
            reasoning="Extracted via deterministic multi-domain OpenIE heuristic.",
        )

    def extract_triples_from_text(self, text: str) -> List[EntityTriple]:
        """Extracts entity triples from text with backward-compatible EntityTriple return type."""
        facts = self.extract_facts(text)
        return [
            EntityTriple(
                subject=t.subject,
                predicate=t.predicate,
                object=t.object,
                confidence=t.confidence,
            )
            for t in facts.triples
        ]



semantic_memory = SemanticMemoryManager()

