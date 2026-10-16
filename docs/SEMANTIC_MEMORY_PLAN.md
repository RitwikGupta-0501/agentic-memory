# Architectural Report & Master Plan: Hardened Semantic Memory Layer

**Target System:** AegisGraph Cognitive Memory Engine (`backend/app/memory/semantic.py`)  
**Document Type:** Formal Architecture Report & Phased Component Hardening Specification  
**Governing Research:** 
- *HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models* (Gutiérrez et al., Ohio State / Stanford, NeurIPS 2024 — `arXiv:2405.14831`)
- *Zep / Graphiti: A Temporal Knowledge Graph Architecture for Agent Memory* (Rasmussen et al., 2025 — `arXiv:2501.13956`)
- *CoALA: Cognitive Architectures for Language Agents* (Sumers et al., Princeton, 2023 — `arXiv:2309.02427`)
- *Temporal Data & the Relational Model* (Date, Darwen, Lorentzos, Morgan Kaufmann, 2002 / Snodgrass 1999)
- *Mem0 / MemGPT: Entity Extraction and Disambiguation in Multi-Turn Conversational Agents* (2024–2025)

---

## 1. Executive Summary & Problem Diagnosis

In human cognitive science and autonomous agent architectures (CoALA), **Semantic Memory** models declarative, factual world knowledge—entities, concepts, relationships, constraints, and dependencies. 

While **Episodic Memory** (Layer 1) maintains the immutable autobiographical log of raw chronological experiences (*"Alice deployed PostgreSQL to Prod_DB at 10:14 PM; Alice migrated Prod_DB to FalkorDB at 11:30 PM"*), **Semantic Memory** (Layer 2) distills these raw experiences into a queryable, bi-temporal Knowledge Graph (*"Prod_DB USES_TECH FalkorDB with valid_from: t2, superseding PostgreSQL with valid_to: t2"*).

```mermaid
flowchart TD
    subgraph EpisodicTier ["Episodic Memory (Immutable Event Ledger)"]
        EP1["(:Episode {id: 'ep_1', content: 'Alice deployed PostgreSQL'})"]
        EP2["(:Episode {id: 'ep_2', content: 'Alice migrated Prod_DB to FalkorDB'})"]
    end

    subgraph SemanticTier ["Semantic Memory (Bi-Temporal Knowledge Graph)"]
        PDB["(:Entity {name: 'Prod_DB', type: 'Infrastructure'})"]
        PG["(:Entity {name: 'PostgreSQL', type: 'Database'})"]
        FDB["(:Entity {name: 'FalkorDB', type: 'GraphDatabase'})"]

        PDB -.->|"[:RELATES_TO {predicate: 'USES_TECH', valid_from: t1, valid_to: t2, invalidated_by_episode: 'ep_2'}]"| PG
        PDB ==>|"[:RELATES_TO {predicate: 'USES_TECH', valid_from: t2, valid_to: NULL, confidence: 1.0}]"| FDB
    end

    subgraph ProvenanceBridge ["Phase 5 Cross-Layer Grounding Bridge"]
        PG -->|"[:DERIVED_FROM]"| EP1
        FDB -->|"[:DERIVED_FROM]"| EP2
        EP2 -->|"[:EXTRACTED_FACT]"| FDB
        EP2 -->|"[:INVALIDATED_RELATION]"| PDB
        PDB -->|"[:MENTIONED_IN]"| EP1
        PDB -->|"[:MENTIONED_IN]"| EP2
    end

    subgraph RetrievalEngine ["HippoRAG Associative Recall"]
        Query["User Query: 'What database does Prod_DB run on?'"] --> Seed["Seed Entity Linking (Prod_DB)"]
        Seed --> PPR["Personalized PageRank (PPR) Walk over Active Graph"]
        PPR --> Subgraph["Ranked Entity Subgraph + Grounded Episodes (EP2)"]
    end
```

### Clarifying the Phase 5 Dependency: Episodic vs. Semantic Memory

> [!IMPORTANT]
> **Why Semantic Memory Must Be Built to Complete the Phase 5 Bridge:**
> In [`docs/EPISODIC_MEMORY_PLAN.md`](file:///home/ritwikg/Repository/agent-memory/docs/EPISODIC_MEMORY_PLAN.md), Phase 5 was designated as *"Cross-Layer Provenance & Bi-Directional Graph Grounding"*.
> 
> Episodic Memory is strictly an **immutable ledger of experiences**. An episode cannot independently manufacture entity nodes, resolve synonym ambiguity, or manage relationship validity intervals.
> 
> It is **Semantic Memory's domain** to:
> 1. Extract entities and facts from episodic text.
> 2. Disambiguate and link entities to the canonical Knowledge Graph.
> 3. Materialize the bidirectional provenance edges (`[:DERIVED_FROM]`, `[:EXTRACTED_FACT]`, and `[:MENTIONED_IN]`).
> 4. Record bi-temporal invalidation metadata (`valid_to = $now, invalidated_by_episode = $ep_id`).
>
> Therefore, **Phase 5 of Episodic Memory is natively Phase 1 of the Semantic Memory overhaul**. Attempting to implement Phase 5 within `episodic.py` in isolation would have required mocking placeholder entities without vector indexes or schema validation.

---

### Diagnosis of Current Implementation Flaws in `app/memory/semantic.py`

A comprehensive code audit of [`backend/app/memory/semantic.py`](file:///home/ritwikg/Repository/agent-memory/backend/app/memory/semantic.py) and [`backend/app/core/cypher_catalog.py`](file:///home/ritwikg/Repository/agent-memory/backend/app/core/cypher_catalog.py) reveals that the current semantic layer is a preliminary demo stub rather than an enterprise-grade cognitive engine:

| Component | Current State in Codebase | Critical Failure Mode in Production |
| :--- | :--- | :--- |
| **Fact Extraction** | Hardcoded substring heuristics (`if "migrated" in lower and "to" in lower:`). | **Zero Generalizability:** Fails on any phrasing deviation, punctuation, multi-clause prompt, or tool output. The system cannot extract arbitrary facts. |
| **Entity Disambiguation** | Blind `MERGE (s:Entity {name: $subject})` without fuzzy normalization or vector matching. | **Entity Fragmentation:** Synonyms like `"Prod_DB"`, `"prod-db"`, `"Production Database"`, and `"primary db"` become disconnected duplicate nodes, destroying graph traversals. |
| **Vector Indexing** | No vector embeddings generated or indexed on `(:Entity)`. | Seed entity discovery for HippoRAG requires exact string matches; cannot resolve conceptual queries or natural language entity mentions. |
| **Bi-Temporal Invalidation** | Invalidation query assumes all relationships are mutually exclusive singletons (`WHERE old_o.name <> $new_object`). | **Data Loss:** Multi-valued predicates (e.g., `CONNECTED_TO`, `DEPENDS_ON`, `MONITORED_BY`) get erroneously deleted when adding a second connection! |
| **Provenance Integrity** | Only creates `(new_o)-[:DERIVED_FROM]->(ep)`. The subject node `s` and the relationship itself are ungrounded. | **Asymmetrical Provenance:** Querying an episode cannot retrieve what facts were extracted from it (`[:EXTRACTED_FACT]` missing); subject entities lack source links. |
| **Time-Travel Queries** | Querying active facts hardcodes `WHERE r.valid_to IS NULL`. | **Historical Blindness:** Cannot answer *"What was the architecture on Oct 14th?"* or reconstruct past graph belief states. |
| **HippoRAG Retrieval** | Simple 2-hop unranked path expansion (`MATCH path = (seed)-[r:RELATES_TO*1..2]-(neighbor)`). | **Combinatorial Explosion:** Returns unranked collections of paths; lacks Personalized PageRank (PPR) scoring, damping factors, or episode activation weighting. |

---

## 2. Research Paper Specifications & Mathematical Models

### 2.1 Bi-Temporal Knowledge Graph Model (Zep / Graphiti & Snodgrass)

Real-world enterprise systems evolve over time. To avoid hallucinating stale configurations while preserving complete historical auditability, every semantic edge in AegisGraph operates under two independent time dimensions:

1. **Valid Time ($T_v = [t_{v\_start}, t_{v\_end}])$:** The time interval during which the relationship was true in the physical world.
2. **Transaction Time ($T_t = [t_{t\_start}, t_{t\_end}])$:** The time interval during which the relationship was recorded in AegisGraph.

```mermaid
gantt
    title Bi-Temporal Lifespan of Prod_DB Technology Stack
    dateFormat X
    axisFormat %s
    section PostgreSQL Belief
    Active Belief (Valid) :0, 100
    Superseded (Invalidated) :done, 100, 150
    section FalkorDB Belief
    Active Belief (Valid) :active, 100, 150
```

#### Invalidation Mechanics
For any relationship $R = (S, P, O)$:
- Active fact at current time $t_{\text{now}}$:
  $$t_{v\_start} \le t_{\text{now}} \quad \land \quad t_{v\_end} \text{ IS NULL}$$
- When superseded by new fact $R' = (S, P, O')$ from episode $E_{\text{new}}$:
  $$R.t_{v\_end} \leftarrow t_{\text{now}}, \quad R.\text{invalidated\_by\_episode} \leftarrow E_{\text{new}}.\text{id}$$
  $$R'.t_{v\_start} \leftarrow t_{\text{now}}, \quad R'.t_{v\_end} \leftarrow \text{NULL}, \quad R'.\text{source\_episode} \leftarrow E_{\text{new}}.\text{id}$$

#### Point-in-Time ("Time-Travel") Query Predicate
To query the exact knowledge graph belief state as of timestamp $T$:
$$\text{Active}(R, T) \iff (R.t_{v\_start} \le T) \land (R.t_{v\_end} \text{ IS NULL} \lor R.t_{v\_end} > T)$$

#### Predicate Cardinality Rules
Relationships fall into two distinct cardinality classes:
1. **Functional / Single-Valued (`SINGLE`):** An entity can have at most one active target for a given predicate (e.g., `USES_TECH`, `HOSTED_ON`, `PRIMARY_DATABASE`). Ingestion of $(S, P, O_{\text{new}})$ invalidates all active $(S, P, O_{\text{old}})$ where $O_{\text{old}} \ne O_{\text{new}}$.
2. **Multi-Valued (`MULTI`):** An entity can have multiple concurrent active targets (e.g., `CONNECTED_TO`, `DEPENDS_ON`, `MONITORED_BY`, `HAS_REPLICA`). Ingestion of $(S, P, O_{\text{new}})$ coexists with existing edges without invalidation unless explicitly revoked.

---

### 2.2 HippoRAG: Neurobiologically Inspired Associative Recall (NeurIPS 2024)

Standard vector search retrieves isolated fragments of text based purely on keyword similarity. HippoRAG mimics the human hippocampal formation (CA1/CA3 associative indexing and neocortical pattern separation) to perform multi-hop associative recall across connected entities in the Knowledge Graph.

```mermaid
flowchart LR
    Q["Query: 'Which database broke during cutover?'"] --> Extraction["Entity Extraction / Linking"]
    Extraction --> Seeds["Seed Entities: ['Prod_DB', 'Migration']"]
    Seeds --> ResetVec["Personalized Reset Vector s_0"]
    ResetVec --> PPR["Personalized PageRank on FalkorDB Active Graph"]
    PPR --> EntityScores["Entity Stationary Probabilities p*"]
    EntityScores --> EpisodeAgg["Episode Activation Aggregation"]
    EpisodeAgg --> Context["Top-K Grounded Context Subgraph"]
```

#### Step 1: Seed Entity Linking & Reset Vector
Given an incoming query $q$, extract noun phrase candidate mentions and map them to graph entities via exact alias matching or dense vector similarity ($\text{sim} \ge \tau_{\text{entity}}$). Form a normalized reset vector $\mathbf{s} \in \mathbb{R}^{|V|}$:
$$s_i = \begin{cases} \frac{\text{sim}(q, v_i)}{\sum_{v_k \in \mathcal{S}} \text{sim}(q, v_k)} & \text{if } v_i \in \mathcal{S} \\ 0 & \text{otherwise} \end{cases}$$

#### Step 2: Personalized PageRank (PPR) Stationary Distribution
Define the transition probability matrix $\mathbf{M}$ over active semantic edges ($t_{v\_end} \text{ IS NULL}$):
$$M_{ij} = \frac{w_{ij}}{\sum_{k \in \mathcal{N}_{\text{out}}(j)} w_{jk}}$$
Where edge weight $w_{ij} = \text{confidence}(e_{ij})$.

The stationary distribution $\mathbf{p} \in \mathbb{R}^{|V|}$ satisfies:
$$\mathbf{p} = (1 - d) \cdot \mathbf{s} + d \cdot \mathbf{M} \mathbf{p}$$
Where $d = 0.85$ is the damping factor.

In FalkorDB OpenCypher, power iteration propagation computes the stationary activation across $K$-hop neighborhoods:
$$\mathbf{p}^{(t+1)} = (1 - d) \mathbf{s} + d \mathbf{M} \mathbf{p}^{(t)}, \quad t \in \{1, \dots, K\}$$

#### Step 3: Episodic Activation Aggregation
Entities transmit their activation mass back to the episodes that derived or mentioned them:
$$\text{Score}(E_k) = \sum_{v \in \mathcal{V}(E_k)} \mathbf{p}(v) \cdot \text{Confidence}(E_k \to v)$$

This ranks past episodic experiences by their topological connectivity to the active concepts in the query, enabling true multi-hop associative recall without combinatorial path explosion.

---

### 2.3 Entity Disambiguation, Alias Graphs & Vector Linking

To prevent graph fragmentation where synonymous or abbreviated names create disjoint nodes:

```mermaid
flowchart TD
    Raw["Raw Extracted Mention: 'prod-db'"] --> Normalization["1. Canonical Slugification ('prod_db')"]
    Normalization --> ExactMatch{"Exact Alias Match in KG?"}
    ExactMatch -->|"Yes"| Canonical["Resolve to Canonical: 'Prod_DB'"]
    ExactMatch -->|"No"| VectorKNN["2. Vector Search (db.idx.vector.queryNodes)"]
    VectorKNN --> SimCheck{"Cosine Similarity >= 0.88?"}
    SimCheck -->|"Yes"| MergeAlias["Link Alias 'prod-db' to Existing 'Prod_DB'"]
    SimCheck -->|"No"| CreateNode["3. Create New Canonical Entity Node"]
```

1. **Canonical Key Normalization:** `canonical_name = re.sub(r'[^a-z0-9]', '_', name.lower().strip())`.
2. **Alias Graph Array:** Entities maintain an array property `aliases: ['prod_db', 'prod-db', 'production-database']`.
3. **Dense Vector Disambiguation:** When an extracted entity name does not match any existing alias, issue a vector similarity search on `Entity.embedding`:
   $$\text{Match}(v_{\text{cand}}) \iff \cos(\mathbf{e}_{\text{new}}, \mathbf{e}_{\text{cand}}) \ge 0.88$$
   If matched, append the raw name to `v_cand.aliases`; if not matched, create a new canonical `:Entity` node.

---

### 2.4 Bidirectional Grounding & Cross-Layer Provenance Contract

To achieve full bidirectional provenance between Episodic Memory and Semantic Memory:
1. **Derivation Grounding:** `(:Entity)-[:DERIVED_FROM {timestamp: $now}]->(:Episode)`
2. **Contextual Mention Grounding:** `(:Entity)-[:MENTIONED_IN {timestamp: $now}]->(:Episode)`
3. **Outbound Fact Ingestion Grounding:** `(:Episode)-[:EXTRACTED_FACT {timestamp: $now}]->(:Entity)`
4. **Invalidation Auditing:** `(:Episode)-[:INVALIDATED_RELATION {timestamp: $now, predicate: $predicate}]->(:Entity)`

This guarantees that an operator or agent can query in either direction:
- From an Entity: *"Show me the exact episode where this entity was first learned."*
- From an Episode: *"Show me all entities and relations that were modified as a result of this interaction."*

---

## 3. Component Breakdown: 5 Hardening Phases

Development is structured into **5 sequential, component-specific phases** executed on isolated feature branches:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Bi-Temporal Schema, Provenance Bridge & Vector Indexing       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 2: LLM Structured Extraction & Entity Disambiguation Engine      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 3: Cardinality-Aware Invalidation & Time-Travel Query Engine     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 4: HippoRAG Personalized PageRank (PPR) Associative Recall       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Phase 5: Multi-Agent Orchestrator Wiring, REST API & Stress Tests      │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Phase 1: Bi-Temporal Schema, Provenance Bridge & Vector Indexing `[COMPLETED]`

> **Status:** ✅ **COMPLETED** (Delivered via `feat/semantic-phase1-schema-and-provenance` — 53/53 Unit & Integration Tests Passing, Native FalkorDB Vector Index on `(:Entity)`, Pydantic v2 `EntityRecord` Domain Schemas, Auto-Vectorization Pipeline, and Full Bidirectional Grounding `[:DERIVED_FROM]`, `[:EXTRACTED_FACT]`, `[:MENTIONED_IN]`)

#### Objective
Establish the hardened data model on FalkorDB for `:Entity` nodes, `:RELATES_TO` bi-temporal edges, and the bidirectional provenance bridge connecting to Episodic Memory (`:Episode`).

#### Component Architecture & Data Model
Every entity node in FalkorDB will conform to the following schema:

```
(:Entity {
    id: STRING,                     // Unique ID: 'ent_' + ULID / UUIDv7
    name: STRING,                   // Human-readable primary display name (e.g. 'Prod_DB')
    canonical_name: STRING,         // Normalized slug for exact indexing (e.g. 'prod_db')
    type: STRING,                   // Entity category: 'Infrastructure' | 'Database' | 'Service' | 'Concept'
    aliases: LIST<STRING>,          // Array of verified aliases and synonyms
    description: STRING,            // Short distilled summary of entity role
    embedding: VECF32[768],         // Dense vector embedding for hybrid similarity search
    created_at: FLOAT,              // System creation timestamp
    updated_at: FLOAT               // Last modification timestamp
})
```

Every semantic relationship edge conforms to:
```
(:Entity)-[:RELATES_TO {
    predicate: STRING,              // Predicate name: 'USES_TECH', 'CONNECTED_TO', 'DEPENDS_ON'
    cardinality: STRING,            // 'SINGLE' (functional) | 'MULTI' (accumulative)
    confidence: FLOAT,              // Extraction confidence in [0.0, 1.0]
    valid_from: FLOAT,              // Start of valid time in physical world
    valid_to: FLOAT | NULL,         // End of valid time (NULL if active)
    transaction_from: FLOAT,        // System recording timestamp
    transaction_to: FLOAT | NULL,   // System retraction timestamp
    source_episode: STRING,         // Episode ID that asserted this fact
    invalidated_by_episode: STRING  // Episode ID that superseded this fact (NULL if active)
}]->(:Entity)
```

#### OpenCypher DDL & Index Bootstrapping
In [`backend/app/core/falkor_client.py`](file:///home/ritwikg/Repository/agent-memory/backend/app/core/falkor_client.py), update `ensure_indices()` to idempotently bootstrap:

```cypher
// 1. Property range indexes for O(1) exact entity lookups
CREATE INDEX FOR (e:Entity) ON (e.name);
CREATE INDEX FOR (e:Entity) ON (e.canonical_name);
CREATE INDEX FOR (e:Entity) ON (e.id);

// 2. Native FalkorDB Vector Index for entity similarity search
CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding) OPTIONS {dimension: 768, similarityFunction: 'cosine'};
```

#### Pydantic v2 Domain Models
```python
class PredicateCardinality(str, Enum):
    SINGLE = "SINGLE"   # Functional: e.g. USES_TECH, PRIMARY_DB (invalidates previous)
    MULTI = "MULTI"     # Multi-valued: e.g. CONNECTS_TO, MONITORED_BY (accumulates)

class EntityNode(BaseModel):
    id: str = Field(default_factory=lambda: f"ent_{uuid.uuid4().hex[:8]}")
    name: str
    canonical_name: str
    type: str = "Concept"
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: float
    updated_at: float

class SemanticTriple(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    cardinality: PredicateCardinality = PredicateCardinality.SINGLE
    subject_type: Optional[str] = "Entity"
    object_type: Optional[str] = "Entity"
```

#### Cypher Queries (`cypher_catalog.py`)
```cypher
// SEMANTIC_PROVENANCE_LINK_EPISODE
MATCH (ep:Episode {id: $episode_id})
MATCH (s:Entity {name: $subject})
MATCH (o:Entity {name: $object})
MERGE (s)-[:MENTIONED_IN {timestamp: $now}]->(ep)
MERGE (o)-[:MENTIONED_IN {timestamp: $now}]->(ep)
MERGE (o)-[:DERIVED_FROM {timestamp: $now}]->(ep)
MERGE (ep)-[:EXTRACTED_FACT {timestamp: $now}]->(o)
RETURN ep.id AS episode_id, s.name AS subject, o.name AS object
```

#### Falsifiable Requirements

1. **R1.1 - Schema Validation**:
   - *Current:* Flat 4-field tuple missing entity attributes, timestamps, and embeddings.
   - *Target:* Pydantic v2 `EntityNode` and `SemanticTriple` enforcing string bounds, cardinality validation, and vector dimensionality.
   - *Acceptance:* Unit tests in `test_semantic_schema_and_vector_index.py` pass with 100% boundary assertion coverage.

2. **R1.2 - Native Entity Vector Index**:
   - *Current:* Property indexes only; no vector index on `Entity`.
   - *Target:* `falkor_client.ensure_indices()` creates dynamic vector index on `(e:Entity) ON (e.embedding)`.
   - *Acceptance:* `db.idx.vector.queryNodes('Entity', ...)` succeeds on freshly booted tenant graphs.

3. **R1.3 - Bidirectional Provenance Integrity**:
   - *Current:* Partial `:DERIVED_FROM` link on object entity only; subject and episode lack links.
   - *Target:* Ingesting a fact creates `(s)-[:MENTIONED_IN]->(ep)`, `(o)-[:DERIVED_FROM]->(ep)`, and `(ep)-[:EXTRACTED_FACT]->(o)`.
   - *Acceptance:* Cypher query traversing from `:Episode` out to `:Entity` via `[:EXTRACTED_FACT]` returns all asserted entities.

---


### Phase 2: LLM Structured Extraction & Entity Disambiguation Engine `[COMPLETED]`

> **Status:** ✅ **COMPLETED** (Delivered via `feat/semantic-phase2-llm-extraction` — 60/60 Unit & Integration Tests Passing, Decoupled `app/memory/prompts.py` Architecture with Gold-Standard OpenIE System Prompt, Strict Directionality Invariant, Canonical Closed Ontology, Predicate Cardinality Classification, Negative Control Conversational Filtering, 3-Step Hybrid Entity Disambiguation with Abbreviation Expansion & Deduplicated Alias Append, and Full REST Endpoints `POST /semantic/extract` & `POST /semantic/resolve`)

#### Objective
Replace hardcoded substring heuristics with a production-grade OpenIE structured extraction pipeline that extracts arbitrary entities and relationships using LLM structured outputs, paired with an entity disambiguation engine that resolves synonyms and aliases via vector similarity.

#### Architecture of the Extraction & Disambiguation Engine

```mermaid
flowchart TD
    In["Raw Agent / User Text Input"] --> ExtractionFork{"LLM Provider"}

    subgraph ExtractionEngine ["Structured OpenIE Engine (app/memory/prompts.py)"]
        ExtractionFork -->|"llm_provider != 'mock'"| LLMExtract["LangChain .with_structured_output()\n(FactExtractionResult via OPENIE_SYSTEM_PROMPT)"]
        ExtractionFork -->|"llm_provider == 'mock'"| MockExtract["Multi-Domain Rule Heuristic\n(DevOps, Infrastructure, DB, Network)"]
        LLMExtract --> Triples["List of SemanticTriple Objects"]
        MockExtract --> Triples
    end

    subgraph DisambiguationEngine ["Entity Resolution Pipeline (app/memory/semantic.py)"]
        Triples --> ForEach["For Each Mentioned Entity (S, O)"]
        ForEach --> Slug["1. Canonical Slug Normalization"]
        Slug --> AliasCheck{"Exact Match on Name or Aliases?\n(SEMANTIC_ENTITY_FIND_BY_ALIAS)"}
        AliasCheck -->|"Found"| ExistingCanonical["Reuse Canonical Entity ID"]
        AliasCheck -->|"Not Found"| VectorCheck["2. Dense Vector Search + Jaccard Hybrid\n(CALL db.idx.vector.queryNodes)"]
        VectorCheck --> SimCheck{"Match Found?\n(sim >= threshold)"}
        SimCheck -->|"Match"| AppendAlias["Append Alias Deduplicated\n(SEMANTIC_ENTITY_APPEND_ALIAS)"]
        SimCheck -->|"No Match"| CreateNew["3. Create New Canonical Entity"]
    end

    AppendAlias --> ReadyTriples["Resolved Canonical Triples"]
    ExistingCanonical --> ReadyTriples
    CreateNew --> ReadyTriples
```

#### 1. Dedicated Prompt Architecture (`backend/app/memory/prompts.py`)

To adhere to industry-standard prompt engineering, prompt templates are decoupled into a dedicated `prompts.py` module. The OpenIE prompt contract incorporates:
- **System Persona & Role:** Senior Knowledge Graph Ontologist extracting declarative assertions into FalkorDB.
- **Directionality Invariant:** Strictly enforced `(Dependent/Consumer) -[PREDICATE]-> (Target/Dependency)`. Inverted triples like `(FalkorDB) -[:USES_TECH]-> (Prod_DB)` are explicitly banned.
- **Closed Canonical Ontology:** Extracted relations are mapped to standardized uppercase predicates:
  - `USES_TECH`, `HOSTED_ON`, `RUNS_ON`, `CONNECTS_TO`, `DEPENDS_ON`, `MONITORED_BY`, `HAS_REPLICA`, `CONFIGURED_WITH`.
- **Cardinality Tagging:** Each triple is classified as `SINGLE` (functional/exclusive; supersedes previous edges) or `MULTI` (accumulative; coexists).
- **In-Context Few-Shot Demonstrations & Negative Controls:** Includes multi-clause architecture migration examples and negative controls (conversational greetings or questions produce empty triple arrays rather than hallucinated entities).

#### 2. Structured OpenIE Output Contract
```python
class FactExtractionResult(BaseModel):
    triples: List[SemanticTriple] = Field(description="Extracted knowledge graph facts")
    entities: List[EntityNode] = Field(description="Extracted entities with categories and descriptions")
    summary: str = Field(description="One-line summary of factual assertions")
    reasoning: Optional[str] = Field(default=None, description="Step-by-step extraction justification")
```

#### 3. Disambiguation Resolution Algorithm
```python
def resolve_entity(
    tenant_id: str,
    raw_name: str,
    entity_type: str = "Concept",
    embedding_provider = embedding_service,
) -> str:
    slug = re.sub(r"[^a-z0-9]", "_", raw_name.lower().strip())
    
    # 1. Exact canonical or alias match
    exact_match = falkor_router.query(
        SEMANTIC_ENTITY_FIND_BY_ALIAS,
        {"slug": slug, "raw_name": raw_name.strip()},
        tenant_id=tenant_id
    )
    if exact_match and exact_match.result_set:
        return exact_match.result_set[0][0]
    
    # 2. Dense vector similarity search with adaptive threshold
    threshold = 0.50 if settings.embedding_provider == "mock" else 0.88
    vec = embedding_provider.embed_query(raw_name)
    vector_match = falkor_router.query(
        SEMANTIC_ENTITY_VECTOR_SIMILARITY,
        {"vec": vec, "threshold": threshold},
        tenant_id=tenant_id
    )
    if vector_match and vector_match.result_set:
        canonical_name = vector_match.result_set[0][0]
        # Append alias deduplicated to existing node
        falkor_router.query(
            SEMANTIC_ENTITY_APPEND_ALIAS,
            {"canonical_name": canonical_name, "raw_name": raw_name.strip()},
            tenant_id=tenant_id
        )
        return canonical_name
    
    return raw_name.strip()
```

#### Falsifiable Requirements

1. **R2.1 - Structured OpenIE Extraction**:
   - *Current:* Fails on any text not matching `"migrated"` or `"primary service is"`.
   - *Target:* OpenIE pipeline parses arbitrary technical narratives (e.g., *"Kubernetes cluster upgraded to v1.30 with Calico CNI"*) into valid `(Kubernetes, USES_VERSION, v1.30)` and `(Kubernetes, USES_CNI, Calico)` triples.
   - *Acceptance:* Unit test in `test_entity_extraction_and_resolution.py` verifying structured triple extraction across varied real-world prompts.

2. **R2.2 - Multi-Alias Entity Disambiguation**:
   - *Current:* Creating `"prod-db"`, `"Prod_DB"`, and `"production database"` spawns 3 disjoint nodes.
   - *Target:* Resolution pipeline maps all three mentions to a single canonical entity with updated `aliases`.
   - *Acceptance:* Unit test asserting that consecutive writes with alias variations produce exactly 1 `:Entity` node with `length(e.aliases) >= 2`.

3. **R2.3 - Negative Control & Conversational Filtering**:
   - *Current:* Conversational utterances either crash or produce garbage entities.
   - *Target:* Non-declarative inputs (greetings, inquiries) return empty lists with zero hallucinated graph mutations.
   - *Acceptance:* Unit test confirming `"Good morning, what is the status of the cluster?"` yields 0 triples and 0 new nodes.

#### Phase 2 Execution Roadmap (7 Atomic Commits)
- **Commit 1:** `feat(cypher): add entity alias lookup and deduplicated alias append queries`
- **Commit 2:** `feat(prompts): add production OpenIE system prompt and in-context demonstrations in prompts.py`
- **Commit 3:** `feat(semantic): implement 3-step entity disambiguation and resolution engine`
- **Commit 4:** `feat(semantic): implement LLM structured OpenIE extraction with multi-domain fallback`
- **Commit 5:** `feat(api): add REST endpoints for semantic extraction and entity resolution`
- **Commit 6:** `test(semantic): add comprehensive tests for OpenIE extraction and entity disambiguation`
- **Commit 7:** `docs: record Semantic Memory Phase 2 completion in tracking documentation`


---

### Phase 3: Cardinality-Aware Invalidation & Time-Travel Query Engine `[COMPLETED]`

> **Status:** ✅ **COMPLETED** (Delivered via `feat/semantic-phase3-bitemporal-timetravel` — 68/68 Unit & Integration Tests Passing, Cardinality-aware invalidation with subject-tracked `[:INVALIDATED_RELATION]`, idempotent active edge refresh, half-open $[t_s, t_e)$ point-in-time snapshotting, entity evolution timelines, subgraph time-travel, Cytoscape dual-edge visualization with phantom null guards, and complete REST API test coverage)

#### Objective
Implement zero-defect bi-temporal edge management that distinguishes single-valued (functional) predicates from multi-valued predicates, alongside an arbitrary-point-in-time ("Time-Travel") query engine.

#### Cardinality-Aware Invalidation Logic
When an agent asserts fact $(S, P, O_{\text{new}})$ with source episode $E$:
1. If $P$ is marked `SINGLE` (functional):
   - Invalidate previous active edge: `OPTIONAL MATCH (s_prev:Entity {name: $s})-[old_r:RELATES_TO {predicate: $p}]->(old_o:Entity) WHERE old_r.valid_to IS NULL AND $cardinality = 'SINGLE' AND old_o.name <> $o_new SET old_r.valid_to = $now, old_r.invalidated_by_episode = $episode_id`.
   - Materialize invalidation link: `MERGE (E)-[:INVALIDATED_RELATION {subject: $s, predicate: $p}]->(old_o)`.
   - Refresh active edge idempotently to avoid duplicate parallel active edges.
2. If $P$ is marked `MULTI`:
   - Existing active edges are preserved untouched.
   - A new active edge $(S, P, O_{\text{new}})$ is added to the graph without invalidation.

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Autonomous Agent
    participant Manager as SemanticMemoryManager
    participant Falkor as FalkorDB Engine

    Note over Agent, Falkor: T1: Ingestion
    Agent->>Manager: upsert_fact("Prod_DB", "USES_TECH", "PostgreSQL", ep="ep_1", card=SINGLE, timestamp=T1)
    Manager->>Falkor: SEMANTIC_PROVENANCE_UPSERT_AND_LINK (valid_from=T1, valid_to=NULL)
    Falkor-->>Manager: Edge active (PostgreSQL)

    Note over Agent, Falkor: T2: Technology Migration
    Agent->>Manager: upsert_fact("Prod_DB", "USES_TECH", "FalkorDB", ep="ep_2", card=SINGLE, timestamp=T2)
    Manager->>Falkor: SEMANTIC_PROVENANCE_UPSERT_AND_LINK (now=T2)
    Note over Falkor: 1. Invalidate PostgreSQL (valid_to=T2, invalidated_by_episode='ep_2')<br/>2. CREATE (ep_2)-[:INVALIDATED_RELATION {subject: 'Prod_DB'}]->(PostgreSQL)<br/>3. Close/refresh existing active edge<br/>4. CREATE active edge to FalkorDB (valid_from=T2, valid_to=NULL)<br/>5. Materialize [:DERIVED_FROM] & [:EXTRACTED_FACT]
    Falkor-->>Manager: {invalidated_count: 1, new_edge: FalkorDB}

    Note over Agent, Falkor: T3: Historical Time-Travel Query
    Agent->>Manager: get_snapshot(tenant_id, as_of=T1)
    Manager->>Falkor: SEMANTIC_TIME_TRAVEL_SNAPSHOT (as_of=T1)
    Falkor-->>Manager: Returns Prod_DB USES_TECH PostgreSQL
    
    Agent->>Manager: get_snapshot(tenant_id, as_of=T2)
    Manager->>Falkor: SEMANTIC_TIME_TRAVEL_SNAPSHOT (as_of=T2)
    Falkor-->>Manager: Returns Prod_DB USES_TECH FalkorDB
```

#### Production Cypher Queries (`cypher_catalog.py`)

```cypher
// SEMANTIC_PROVENANCE_UPSERT_AND_LINK
// 1. Invalidate conflicting functional single-valued active relations if requested
OPTIONAL MATCH (s_prev:Entity {name: $subject})-[old_r:RELATES_TO {predicate: $predicate}]->(old_o:Entity)
WHERE old_r.valid_to IS NULL 
  AND $cardinality = 'SINGLE' 
  AND old_o.name <> $object
SET old_r.valid_to = $now,
    old_r.invalidated_by_episode = $episode_id
WITH count(old_r) AS invalidated_count, collect(DISTINCT old_o) AS invalidated_objects

// 2. Ensure Subject Entity exists
MERGE (s:Entity {name: $subject})
ON CREATE SET
    s.id = $subject_id,
    s.canonical_name = $subject_canonical,
    s.type = $subject_type,
    s.aliases = [$subject],
    s.created_at = $now,
    s.updated_at = $now,
    s.embedding = CASE WHEN $subject_vec IS NOT NULL THEN vecf32($subject_vec) ELSE NULL END
ON MATCH SET
    s.updated_at = $now

// 3. Ensure Object Entity exists
MERGE (o:Entity {name: $object})
ON CREATE SET
    o.id = $object_id,
    o.canonical_name = $object_canonical,
    o.type = $object_type,
    o.aliases = [$object],
    o.created_at = $now,
    o.updated_at = $now,
    o.embedding = CASE WHEN $object_vec IS NOT NULL THEN vecf32($object_vec) ELSE NULL END
ON MATCH SET
    o.updated_at = $now

// 4. Upsert active bi-temporal edge (prevent parallel active duplicate edges)
WITH s, o, invalidated_count, invalidated_objects
OPTIONAL MATCH (s)-[existing_r:RELATES_TO {predicate: $predicate}]->(o)
WHERE existing_r.valid_to IS NULL
DELETE existing_r
CREATE (s)-[new_r:RELATES_TO {
    predicate: $predicate,
    cardinality: $cardinality,
    confidence: $confidence,
    valid_from: coalesce(existing_r.valid_from, $now),
    valid_to: NULL,
    transaction_from: $now,
    source_episode: $episode_id
}]->(o)

// 5. Establish full bidirectional cross-layer provenance to Episode
WITH invalidated_count, invalidated_objects, new_r, s, o
MERGE (ep:Episode {id: $episode_id})
ON CREATE SET ep.timestamp = $now, ep.role = 'system', ep.archived = false
MERGE (s)-[m_s:MENTIONED_IN]->(ep)
ON CREATE SET m_s.timestamp = $now
MERGE (o)-[m_o:MENTIONED_IN]->(ep)
ON CREATE SET m_o.timestamp = $now
MERGE (o)-[d:DERIVED_FROM]->(ep)
ON CREATE SET d.timestamp = $now
MERGE (ep)-[ef:EXTRACTED_FACT {predicate: $predicate}]->(o)
ON CREATE SET ef.timestamp = $now

// 6. Materialize explicit invalidation edges from episode to superseded entities with subject tracking
FOREACH (inv_obj IN invalidated_objects |
    MERGE (ep)-[inv_r:INVALIDATED_RELATION {subject: $subject, predicate: $predicate}]->(inv_obj)
    ON CREATE SET inv_r.timestamp = $now
)

RETURN invalidated_count,
       s.name AS subject,
       new_r.predicate AS predicate,
       o.name AS object,
       new_r.valid_from AS valid_from,
       ep.id AS source_episode
```

```cypher
// SEMANTIC_TIME_TRAVEL_SNAPSHOT
MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
WHERE r.valid_from <= $as_of 
  AND (r.valid_to IS NULL OR r.valid_to > $as_of)
RETURN s.name AS subject,
       s.type AS subject_type,
       r.predicate AS predicate,
       r.cardinality AS cardinality,
       r.confidence AS confidence,
       r.valid_from AS valid_from,
       r.valid_to AS valid_to,
       r.source_episode AS source_episode,
       o.name AS object,
       o.type AS object_type
ORDER BY s.name ASC, r.predicate ASC
```

```cypher
// SEMANTIC_CYTOSCAPE_TIME_TRAVEL (Guarded Against Phantom Null Edges)
MATCH (n:Entity)
WHERE n.created_at <= $as_of
OPTIONAL MATCH (n)-[r:RELATES_TO]->(m:Entity)
WHERE r.valid_from <= $as_of 
  AND (
      (r.valid_to IS NULL OR r.valid_to > $as_of)
      OR ($include_invalidated = true AND r.valid_to <= $as_of)
  )
RETURN collect(DISTINCT {
    id: n.id,
    name: n.name,
    canonical_name: n.canonical_name,
    type: n.type,
    created_at: n.created_at
}) AS nodes,
collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
    id: id(r),
    source: n.name,
    target: m.name,
    predicate: r.predicate,
    cardinality: r.cardinality,
    valid_from: r.valid_from,
    valid_to: r.valid_to,
    status: CASE 
        WHEN r.valid_to IS NULL OR r.valid_to > $as_of THEN 'ACTIVE'
        ELSE 'INVALIDATED'
    END
} ELSE NULL END) AS edges
```

#### Falsifiable Requirements

1. **R3.1 - Atomic Functional Invalidation & Idempotent Refresh**:
   - *Target:* Updating a `SINGLE` predicate sets `valid_to` and `invalidated_by_episode` on the previous active edge in one atomic query. Re-asserting identical facts refreshes without duplicate parallel active edges.
   - *Acceptance:* Unit test `test_functional_invalidation_and_idempotency` asserting `(ep_2)-[:INVALIDATED_RELATION {subject: 'Prod_DB'}]->(PostgreSQL)` and exactly 1 active FalkorDB edge.

2. **R3.2 - Multi-Valued Edge Preservation**:
   - *Target:* Ingesting multiple `CONNECTS_TO` edges allows all edges to remain active concurrently (`valid_to IS NULL`).
   - *Acceptance:* Unit test `test_multi_valued_coexistence` verifying that 3 connections coexist concurrently without invalidation.

3. **R3.3 - Historical Time-Travel Accuracy & Half-Open Intervals**:
   - *Target:* `get_snapshot(tenant_id, as_of=t1)` accurately returns `PostgreSQL` as active, while `as_of=t2` returns `FalkorDB` as active. Strictly adheres to $[t_s, t_e)$ half-open interval semantics at boundaries.
   - *Acceptance:* Integration tests `test_point_in_time_reconstruction` and `test_subsecond_precision_and_boundary_collisions`.

#### Phase 3 Execution Roadmap (8 Atomic Commits)
- **Commit 1:** `feat(cypher): add hardened time-travel snapshot, entity evolution, and cytoscape queries`
- **Commit 2:** `feat(semantic): materialize [:INVALIDATED_RELATION] with subject tracking and idempotent active edge refresh`
- **Commit 3:** `feat(semantic): implement point-in-time get_snapshot engine with half-open interval semantics`
- **Commit 4:** `feat(semantic): implement get_entity_history and get_time_travel_subgraph engines`
- **Commit 5:** `feat(semantic): implement Cytoscape dual-edge time-travel serializer with phantom null guards`
- **Commit 6:** `feat(api): expose REST endpoints for snapshot, history, time-travel, and cytoscape`
- **Commit 7:** `test(semantic): add comprehensive falsifiable test suite in test_semantic_bitemporal_timetravel.py`
- **Commit 8:** `docs: record Semantic Memory Phase 3 completion in master tracking plan`

---

### Phase 4: HippoRAG Personalized PageRank (PPR) Associative Recall `[COMPLETED]`

> **Status:** ✅ **COMPLETED** (Delivered via `feat/semantic-phase4-hipporag-associative-recall` — 76/76 Unit & Integration Tests Passing, sparse Personalized PageRank spreading activation with sublinear hub damping and seed prior preservation, dynamic $K$-hop active subgraph expansion, invalidation-gated cross-layer episodic grounding, time-travel associative recall, and REST endpoints)

#### Objective
Implement the formal NeurIPS 2024 HippoRAG associative retrieval algorithm natively over FalkorDB's active knowledge graph, computing stationary probability distributions via Personalized PageRank to rank connected entities and source episodes.

#### Algorithmic Formulation

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Autonomous Agent / User
    participant Hippo as HippoRAG Engine (semantic.py)
    participant Falkor as FalkorDB Engine

    Agent->>Hippo: retrieve(query="Check database latency on primary DB", top_k=5)
    Hippo->>Falkor: 1. Hybrid Seed Discovery (alias match & HIPPORAG_SEED_VECTOR_SEARCH)
    Falkor-->>Hippo: Seed Entities S = ['Prod_DB'] with initial priors p0
    Hippo->>Falkor: 2. HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION (seed_names, as_of, max_hops=2)
    Falkor-->>Hippo: Active bi-temporal subgraph edges (valid_from <= as_of < valid_to)
    Hippo->>Hippo: 3. Sparse Power Iteration: pi = alpha P^T pi + (1-alpha) p0 + sink teleportation
    Hippo->>Hippo: 4. Sublinear Hub Damping: pi_norm = pi / (1 + ln(1 + D)) + 0.15 * p0
    Hippo->>Falkor: 5. HIPPORAG_EPISODE_GROUNDING_EXPANSION (active_entities, as_of)
    Note over Falkor: Bipartite traversal over [:DERIVED_FROM] & [:MENTIONED_IN]<br/>Filters ep.timestamp <= as_of<br/>Excludes episodes whose facts were superseded (invalidated_count = 0)
    Falkor-->>Hippo: Active grounded episodes & importance scores
    Hippo->>Hippo: 6. Score(Ep) = sum(pi_norm(e) * w_link * Importance(Ep))
    Hippo-->>Agent: Structured HippoRAGResult (Ranked Entities, Ranked Episodes, Subgraph)
```

#### Production Cypher Queries (`cypher_catalog.py`)

```cypher
// HIPPORAG_SEED_VECTOR_SEARCH
CALL db.idx.vector.queryNodes('Entity', 'embedding', $candidate_limit, vecf32($query_vec))
YIELD node AS e, score
WITH e, (1.0 - score) AS similarity
WHERE similarity >= $min_similarity
RETURN e.name AS name,
       e.canonical_name AS canonical_name,
       e.type AS type,
       coalesce(e.aliases, []) AS aliases,
       similarity
ORDER BY similarity DESC
```

```cypher
// HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION
MATCH (seed:Entity)
WHERE (seed.name IN $seed_names OR seed.canonical_name IN $seed_names)
  AND coalesce(seed.created_at, 0.0) <= $as_of
MATCH path = (seed)-[r:RELATES_TO*1..3]-(target:Entity)
WHERE length(path) <= $max_hops
  AND all(node IN nodes(path) WHERE coalesce(node.created_at, 0.0) <= $as_of)
  AND all(edge IN relationships(path) WHERE 
      edge.valid_from <= $as_of 
      AND (edge.valid_to IS NULL OR edge.valid_to > $as_of)
  )
UNWIND relationships(path) AS edge
RETURN DISTINCT startNode(edge).name AS source,
       edge.predicate AS predicate,
       endNode(edge).name AS target,
       coalesce(edge.confidence, 1.0) AS weight,
       edge.valid_from AS valid_from,
       edge.valid_to AS valid_to
```

```cypher
// HIPPORAG_EPISODE_GROUNDING_EXPANSION
MATCH (e:Entity)
WHERE e.name IN $entity_names
MATCH (e)-[r:DERIVED_FROM|MENTIONED_IN]->(ep:Episode)
WHERE coalesce(ep.archived, false) = false
  AND coalesce(ep.timestamp, r.timestamp, 0.0) <= $as_of
OPTIONAL MATCH (s:Entity)-[old_rel:RELATES_TO {source_episode: ep.id}]->(t:Entity)
WHERE old_rel.valid_to IS NOT NULL AND old_rel.valid_to <= $as_of
WITH e, r, ep, count(old_rel) AS invalidated_count
WHERE invalidated_count = 0
RETURN e.name AS entity,
       type(r) AS link_type,
       ep.id AS episode_id,
       coalesce(ep.content, '') AS content,
       coalesce(ep.role, 'system') AS role,
       coalesce(ep.utility_score, ep.importance_score, 0.5) AS importance_score,
       coalesce(ep.timestamp, 0.0) AS timestamp
```

#### Execution Roadmap & Atomic Commits

- **Commit 1:** `feat(cypher): add HippoRAG seed vector match, dynamic hop active subgraph, and temporally-filtered episode grounding queries`
- **Commit 2:** `feat(semantic): define HippoRAG Pydantic schemas with dict subscript compatibility and sparse Personalized PageRank algorithm`
- **Commit 3:** `feat(semantic): implement hybrid seed entity linking with lexical alias check and mock vector guards`
- **Commit 4:** `feat(semantic): implement cross-layer bipartite episode grounding with invalidation and temporal filtering`
- **Commit 5:** `feat(semantic): implement unified hipporag_retrieve with time-travel and zero-seed fallback`
- **Commit 6:** `feat(api): expose query-driven HippoRAG endpoints in routes_memory.py with backward compatibility`
- **Commit 7:** `test(semantic): add comprehensive HippoRAG test suite in test_hipporag_associative_retrieval.py`
- **Commit 8:** `docs: record Semantic Memory Phase 4 completion in master tracking plan`

#### Falsifiable Verification Matrix (`test_hipporag_associative_retrieval.py`)

| Test Identifier | Category | Scenario & Invariants | Result |
| :--- | :--- | :--- | :--- |
| **TEST-HIPPORAG-01** | **Mathematical Proximity Decay** | Star/chain graph: `Prod_DB` (Seed) $\to$ `FalkorDB` (1-hop) $\to$ `Redis_Engine` (2-hop), plus `Prod_DB` $\to$ `Prometheus` (1-hop). Strictly verifies $\tilde{\pi}(\text{Prod\_DB}) > \tilde{\pi}(\text{FalkorDB}) > \tilde{\pi}(\text{Redis\_Engine}) > 0$. Multi-edge seed is never penalized below downstream nodes. | ✅ **PASS** |
| **TEST-HIPPORAG-02** | **Stale Fact Pruning (Temporal Gating)** | `Prod_DB` migrated from `PostgreSQL` to `FalkorDB`. Query at $t=2500.0$: Active node `FalkorDB` receives positive mass; superseded node `PostgreSQL` is strictly excluded from active subgraph. | ✅ **PASS** |
| **TEST-HIPPORAG-03** | **Bipartite Episode Grounding Convergence** | Two episodes: `ep_1` (created `PostgreSQL`, superseded at $t=2000.0$) and `ep_2` (created `FalkorDB`, active at $t=2000.0$). Query at $t=2500.0$: `ep_2` is ranked #1. Obsolete `ep_1` receives 0 grounding score due to invalidation filter. | ✅ **PASS** |
| **TEST-HIPPORAG-04** | **Hybrid Natural Language Seed Discovery** | Query: *"Check database latency on primary DB"*. Graph contains entity `Prod_DB` with alias `"primary db"`. Automatic alias resolution identifies `Prod_DB` as seed; activation spreads through its active neighbors. | ✅ **PASS** |
| **TEST-HIPPORAG-05** | **Time-Travel Associative Recall** | Migration occurred at $t=2000.0$. At $\tau_1 = 1500.0$: `PostgreSQL` and `ep_1` are retrieved; future `ep_2` never leaks. At $\tau_2 = 2500.0$: `FalkorDB` and `ep_2` are retrieved; `ep_1` is pruned. | ✅ **PASS** |
| **TEST-HIPPORAG-06** | **Cold-Start / Zero-Seed Fallback** | Query with completely disjoint technical domain (`"quantum teleportation entanglement"`). Returns `status="NO_SEEDS_FOUND"` cleanly without false positives, unhandled exceptions, or `ZeroDivisionError`. | ✅ **PASS** |
| **TEST-HIPPORAG-07** | **REST API Endpoints & Backward Compatibility** | Validates HTTP 200 responses across primary (`POST /api/v1/memory/semantic/hipporag`) and legacy (`POST /api/v1/memory/hipporag`) endpoints with full dictionary subscript compatibility. | ✅ **PASS** |

---

### Phase 5: Multi-Agent Orchestrator Wiring, REST API & Stress Tests

#### Objective
Wire the hardened Semantic Memory layer directly into the multi-agent coordinator (`orchestrator.py`), expose REST inspection endpoints for the frontend visualizer, and subject the layer to high-concurrency chaos stress tests.

#### Integration Architecture

```mermaid
flowchart TD
    subgraph MultiAgentStream ["Multi-Agent Execution Pipeline (orchestrator.py)"]
        User["User Prompt"] --> Orch["1. Orchestrator Agent (Decomposes DAG)"]
        Orch --> Context["2. Context & Triage Agent"]
        Context --> DualRecall{"Dual Cognitive Recall"}
        DualRecall -->|"Temporal Autobiography"| ParkRec["Park et al. 3-Factor Episodic Recall"]
        DualRecall -->|"Knowledge Graph Association"| HippoRec["HippoRAG Associative Semantic Recall"]
        ParkRec --> Blackboard["Working Memory Blackboard"]
        HippoRec --> Blackboard
        Blackboard --> Handoff["3. Execution & Reflexion Agent"]
    end

    subgraph RESTEndpoints ["REST Management API (routes_memory.py)"]
        POST1["POST /api/v1/memory/semantic/fact"]
        POST2["POST /api/v1/memory/semantic/extract"]
        POST3["POST /api/v1/memory/semantic/timetravel"]
        POST4["POST /api/v1/memory/semantic/hipporag"]
    end
```

#### High-Concurrency Chaos Test Matrix

| Test Identifier | Category | Test Scenario | Success Criteria (Pass/Fail) |
| :--- | :--- | :--- | :--- |
| **TEST-SEM-CONC-01** | **Concurrency** | 20 concurrent coroutines executing bi-temporal invalidation on the same entity simultaneously. | **PASS:** Zero deadlocks; exactly 1 active edge remains (`valid_to IS NULL`); 19 historical edges cleanly invalidated. |
| **TEST-SEM-ISOL-02** | **Multi-Tenancy** | Ingest 50 facts into `acme-payments` and 50 into `nebula-cloud` concurrently. | **PASS:** Zero cross-tenant leakage. Querying `acme-payments` returns 0 entities from `nebula-cloud`. |
| **TEST-SEM-TIME-03** | **Time-Travel** | Query graph across 5 historical timestamps after multiple sequential migrations. | **PASS:** Graph reconstruction matches exact historical truth at each discrete epoch. |
| **TEST-SEM-HIPPO-04** | **PPR Convergence** | Execute HippoRAG on a 100-node synthetic knowledge graph. | **PASS:** Algorithm converges in $< 35\text{ms}$; returns strictly ordered activation scores. |
| **TEST-SEM-FALL-05** | **Degraded Fallback** | Ingest facts with LLM API keys disabled. | **PASS:** Pipeline automatically routes through local vectorizer and deterministic rule heuristic with 0 unhandled exceptions. |

#### Falsifiable Requirements

1. **R5.1 - Multi-Agent Blackboard Integration**:
   - *Current:* Context Agent only extracts facts without running HippoRAG retrieval.
   - *Target:* Context Agent executes `hipporag_retrieve()`, attaching `[:PINNED_CONTEXT]` pointers to both top entities and top episodes.
   - *Acceptance:* Running `execute_task_stream()` emits `hipporag_event` and pins semantic context to Subtask 1.

2. **R5.2 - Multi-Tenant Isolation Under Concurrency**:
   - *Current:* Basic sequential test.
   - *Target:* High-concurrency async coroutines accessing isolated tenant graphs maintain 100% graph boundary integrity.
   - *Acceptance:* Passing `test_semantic_concurrency.py` with 20 parallel workers.

---

## 4. Implementation File Manifest & Mapping

When executing these 5 phases, changes will touch the following specific files in the repository:

```
backend/
├── app/
│   ├── core/
│   │   ├── falkor_client.py       # Add :Entity vector index in ensure_indices()
│   │   └── cypher_catalog.py      # Hardened BITEMPORAL upsert, time-travel, and HippoRAG queries
│   ├── memory/
│   │   ├── prompts.py             # Production OpenIE extraction prompts and in-context demonstrations
│   │   └── semantic.py            # Complete overhaul: Pydantic v2 schemas, LLM extraction, HippoRAG
│   ├── agents/
│   │   └── orchestrator.py        # Context Agent calls HippoRAG & pins entity context
│   └── api/
│       └── routes_memory.py       # Endpoints for semantic fact upsert, time-travel, HippoRAG
└── tests/
    ├── test_semantic_schema_and_vector_index.py  # [NEW] Phase 1: Schema, vector index, provenance
    ├── test_entity_extraction_and_resolution.py  # [NEW] Phase 2: OpenIE extraction & disambiguation
    ├── test_semantic_bitemporal_timetravel.py    # [NEW] Phase 3: Cardinality & point-in-time queries
    ├── test_hipporag_associative_retrieval.py   # [NEW] Phase 4: HippoRAG PPR mathematical tests
    └── test_semantic_concurrency.py              # [NEW] Phase 5: High-concurrency chaos stress tests
```

---

## 5. Summary & Handoff to Procedural Memory (Layer 3)

Upon completion of these 5 phases:
1. **Semantic Memory** will be an enterprise-grade, bi-temporal knowledge graph with continuous fact extraction, entity disambiguation, and HippoRAG associative retrieval.
2. The **Phase 5 Cross-Layer Provenance Bridge** will be 100% complete: every entity and relationship will be anchored to the ground-truth episodic experiences that created or invalidated it.
3. This sets the stage for **Procedural Memory (Layer 3)** (`procedural.py`), where skill workflows (`:Procedure` $\to$ `:ActionStep`) will link directly to Semantic Entities (`[:TARGETS_ENTITY]`) and compile Reflexion guardrails directly from Episodic failures (`[:TRIGGERED_BY]`).

---

## 6. Execution Discipline & Quality Guarantees

All phases will be executed in accordance with strict engineering standards:
1. **Dedicated Feature Branches:** Each phase implemented on an isolated branch (`feat/semantic-phase1-schema-and-provenance`, `feat/semantic-phase2-llm-extraction`, etc.).
2. **Atomic Single-Line Commits:** Frequent, meaningful commits following conventional commit syntax.
3. **Pull Request Lifecycle:** Managed end-to-end via `gh pr create` and `gh pr merge --merge --delete-branch`.
4. **Zero Regression Policy:** All 46 existing tests on `main` must remain green across every phase.
