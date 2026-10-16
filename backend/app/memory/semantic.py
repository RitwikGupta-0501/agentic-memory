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

