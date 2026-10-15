# Product Requirements Document (PRD): **AegisGraph** (Working Title)

**Multi-Tenant 4-Tier Cognitive Graph Memory & Multi-Agent Coordination Engine**

| Metadata | Details |
| --- | --- |
| **Event** | Graph Hacks: Context for AI Agents (Powered by FalkorDB) |
| **Primary Track** | **Track 02:** Agent Memory and Coordination |
| **Secondary Track** | **Track 01:** Agents That Act on Connected Data (Cross-Submission) |
| **Submission Deadline** | October 18, 2026, 11:59 PM IST |
| **Core Stack** | Python 3.12, FastAPI, LangChain + LangGraph, `falkordb-py` + `langchain-falkordb`, SvelteKit/Next.js |

---

## 1. Executive Summary & Product Vision

Standard LLM agents suffer from context amnesia, race conditions during multi-agent handoffs, and an inability to learn from operational failures across sessions. Vector-only RAG memory fails because it treats memory as flat, timeless text chunks rather than evolving, causal relationships.

**AegisGraph** is a two-part system built exclusively on **FalkorDB**:

1. **The Core Memory Engine:** A 4-tier cognitive graph architecture implementing **Working, Episodic, Semantic, and Procedural memory** with hardware-level multi-tenant graph isolation, bi-temporal conflict resolution, and atomic multi-agent blackboard coordination.
2. **The Showcase Control Plane:** An interactive multi-tenant web platform where judges can switch tenants/users, watch multiple agents coordinate over shared graph state in real time, inspect live Cypher mutations, and verify cross-session procedural learning.

---

## 2. Theoretical Foundation & Research Citations

Every architectural choice in this PRD directly implements mechanisms from peer-reviewed agentic memory research. **Include this exact table in your `README.md` to establish immediate technical credibility with the judges.**

| Memory Layer / Concept | Cited Research Paper | Core Mechanism Adopted in Our FalkorDB Engine |
| --- | --- | --- |
| **Overall 4-Tier Taxonomy** | **CoALA:** *Cognitive Architectures for Language Agents* (Sumers et al., Princeton, 2023 – `arXiv:2309.02427`) | Separates internal agent state into Working, Episodic, Semantic, and Procedural memory modules with structured `retrieve`, `reason`, and `write` actions. |
| **Graph Memory Loops** | *Graph-based Agent Memory: Taxonomy, Techniques, and Applications* (Yang et al., 2026 – `arXiv:2602.05665`) | Implements the dual-stream evolution loop: **Fast Stream** (real-time ingestion during turns) and **Slow Stream** (background graph consolidation & pruning). |
| **Working Memory** | **MemGPT:** *Towards LLMs as Operating Systems* (Packer et al., UC Berkeley, 2023 – `arXiv:2310.08560`) | Treats active context as OS RAM with explicit graph pointers (`[:ACTIVE_REF]`) and self-directed memory syscalls (`working_memory_pin`, `working_memory_evict`). |
| **Episodic Memory** | **Zep / Graphiti:** *A Temporal Knowledge Graph Architecture for Agent Memory* (Rasmussen et al., 2025 – `arXiv:2501.13956`) | **Bi-Temporal Graph Modeling:** Tracks both transaction time ($t_{\text{created}}$) and validity windows ($t_{\text{valid\_from}}$, $t_{\text{valid\_to}}$) on edges so contradictions invalidate old facts without deleting audit history. |
| **Episodic Scoring & Reflection** | **Generative Agents:** *Interactive Simulacra of Human Behavior* (Park et al., Stanford, 2023 – `arXiv:2304.03442`) | Scores retrieved memories via hybrid graph + vector weighting: $S = \alpha \cdot \text{Recency} + \beta \cdot \text{Importance} + \gamma \cdot \text{Relevance}$, plus periodic synthesis into higher-order abstractions. |
| **Semantic Memory** | **HippoRAG:** *Neurobiologically Inspired Long-Term Memory for LLMs* (Gutiérrez et al., OSU, 2024 – `arXiv:2405.14831`) | Uses vector search strictly to locate **entry seed nodes**, then executes multi-hop Cypher neighborhood traversal to assemble connected relational context. |
| **Semantic Conflict Resolution** | **Mem0:** *Building Production-Ready AI Agents with Scalable Long-Term Memory* (Chhikara et al., 2025 – `arXiv:2504.19413`) | Distillation-first pipeline using deterministic state transitions (`ADD`, `SUPERSEDE`, `NOOP`) when incoming episodic triples conflict with existing semantic edges. |
| **Procedural Memory** | **Voyager** (*Wang et al., 2023 – `arXiv:2305.16291*`) & **Reflexion** (*Shinn et al., 2023 – `arXiv:2303.11366*`) | Stores reusable action workflows as executable DAGs (`:Procedure` $\rightarrow$ `:ActionStep`) and converts episodic execution failures into persistent `:Guardrail` edges. |
| **Dynamic Thresholding** | **vCache:** *Verified Semantic Prompt Caching* (Schroeder et al., UC Berkeley / Stanford / TU Munich, ICLR 2026 – `arXiv:2502.03771`) | Attaches an online-learned decision boundary $(t_i, \gamma_i)$ to each individual stored node, dynamically shifting its acceptance threshold $\hat{\tau}_i$ after creation via runtime verification. |
| **Post-Creation Value Calibration** | **MemRL:** *Self-Evolving Agents via Runtime Reinforcement Learning on Memory* (Jan 2026 – `arXiv:2601.03192`) | Applies non-parametric RL directly to memory nodes, updating runtime utility/Q-values $Q(m_i)$ post-execution based on task success ($r=+1$) or failure ($r=-1$). |
| **Recall Reinforcement** | **MemoryBank:** *Enhancing Large Language Models with Long-Term Memory* (Zhong et al., AAAI 2024 – `arXiv:2305.10250`) | Implements Ebbinghaus forgetting with post-creation recall reinforcement: accessing a node resets its recency and increments its memory strength $S \leftarrow S + 1$. |

---

## 3. System Architecture & Tech Stack

### 3.1 Tech Stack Specification

* **Graph Database (Primary & Sole Storage):** **FalkorDB** (`falkordb/falkordb:latest` via Docker / FalkorDB Cloud). Leverages native **multi-graph isolation** (`db.select_graph(f"tenant_{tenant_id}")`), native **Vector Indexing** (`db.idx.vector`), and **OpenCypher**.
* **Backend API & Concurrency Engine:** **FastAPI** (Python 3.12, `uv` package manager, `asyncio`, Server-Sent Events / WebSockets for real-time graph mutation streaming).
* **Agent Orchestration & LLM Layer:** **LangChain + LangGraph** + **`langchain-falkordb`** + **`falkordb-py`** (async client `falkordb.asyncio`).
* *Critical Rule #3 Design:* We do **not** rely solely on black-box LangGraph memory checkpointers. Every agent decision, handoff, and memory mutation executes explicit, parameterized Cypher queries against FalkorDB that are logged and streamed to the UI.


* **Frontend Showcase Platform:** **SvelteKit** (or Next.js) + **Tailwind CSS** + **Cytoscape.js** (for interactive, color-coded 4-tier graph rendering).

### 3.2 Native Multi-Tenancy Architecture (Track 02 Requirement)

Instead of fragile `WHERE n.tenant_id = $id` filtering in a single monolithic graph, AegisGraph maps each tenant + workspace to a **dedicated, isolated FalkorDB graph key** (`falkordb_client.select_graph(f"mem_{tenant_id}_{user_id}")`), with an optional shared organizational graph (`mem_{tenant_id}_shared`). This guarantees zero cross-tenant leakage and microsecond sparse-matrix switching.

---

## 4. Deep-Dive: The 4 Memory Layers (Definitions, Mechanics & Priority)

### Layer 1: Episodic + Semantic Coupled Bi-Temporal Memory

* **Implementation Priority:** **P0 (Build First — Hours 1–18)**
* **What It Means:**
* **Episodic Memory** is the chronological, immutable autobiographical log of *what happened, when, and in which session* (conversations, tool outputs, failures).
* **Semantic Memory** is the structured, evolving world model of *entities, facts, and relationships* distilled from those episodes.


* **How It Works in FalkorDB:**
1. **Episodic Write:** Every user message or agent tool execution creates an `:Episode` node chained via `[:NEXT_EPISODE]` for temporal ordering, storing raw text, `timestamp`, `session_id`, `importance_score`, and a vector embedding.
2. **Semantic Extraction & Provenance:** An async LangChain structured-output extractor parses entities and relationships from the `:Episode`, merging `(:Entity)` nodes and linking them back to the source episode via `[:MENTIONED_IN]` and `[:DERIVED_FROM]`.
3. **Bi-Temporal Conflict Resolution (The Zep/Graphiti Pattern):** Semantic relationships are represented as edges (or reified `:Fact` nodes) with `valid_from` and `valid_to` timestamps:
* When a user says *"Our production database is PostgreSQL"* in Session 1, FalkorDB creates:
`(:Entity {name: "Prod_DB"})-[:USES_TECH {valid_from: T1, valid_to: null, source_ep: Ep1}]->(:Entity {name: "PostgreSQL"})`
* When the user says *"We migrated Prod_DB from Postgres to FalkorDB"* in Session 2, a Cypher mutation locates the active `USES_TECH` edge where `valid_to IS NULL`, sets `r.valid_to = T2`, and creates a new edge to `"FalkorDB"` with `valid_from: T2`.


4. **Hybrid HippoRAG Retrieval:** On query, FalkorDB runs `CALL db.idx.vector.queryNodes('Entity', 'embedding', 5, $vec)` to find entry nodes, then traverses 2 hops across active edges (`WHERE r.valid_to IS NULL`) plus their linked `:Episode` provenance nodes.



```cypher
// Core Bi-Temporal Invalidation + Upsert Query (Priority 1)
MATCH (s:Entity {name: $subject})-[old_r:RELATES_TO {predicate: $predicate}]->(old_o:Entity)
WHERE old_r.valid_to IS NULL AND old_o.name <> $new_object
SET old_r.valid_to = $now, old_r.invalidated_by_episode = $episode_id
WITH count(old_r) AS invalidated_count
MERGE (s:Entity {name: $subject})
MERGE (new_o:Entity {name: $new_object})
MERGE (ep:Episode {id: $episode_id})
CREATE (s)-[new_r:RELATES_TO {
    predicate: $predicate,
    valid_from: $now,
    valid_to: NULL,
    confidence: $confidence,
    source_episode: $episode_id
}]->(new_o)
CREATE (new_o)-[:DERIVED_FROM]->(ep)
RETURN invalidated_count, new_r

```

---

### Layer 2: Working Memory & Multi-Agent Coordination Blackboard

* **Implementation Priority:** **P0 (Build Second — Hours 19–34)**
* **What It Means:**
* **Working Memory** is the active, short-term scratchpad for an ongoing multi-step task. In a multi-agent system, it acts as the **shared coordination state** (blackboard) allowing multiple concurrent agents to claim subtasks, pass context pointers, and hand off execution without duplicating prompts.


* **How It Works in FalkorDB:**
1. **Task Decomposition Graph:** When a complex request arrives, the *Planner Agent* writes a `:TaskRun` node connected to a DAG of `:SubTask` nodes linked by `[:DEPENDS_ON]` edges.
2. **High-Concurrency Atomic Claiming:** Multiple async worker agents (*Researcher Agent*, *Executor/Verifier Agent*) poll FalkorDB concurrently. A single atomic Cypher query finds a `:SubTask` with `status: 'PENDING'` whose upstream `[:DEPENDS_ON]` nodes are all `'COMPLETED'`, and flips it to `'IN_PROGRESS'` with `locked_by: $agent_id`.
3. **Zero-Copy Context Handoffs (MemGPT Pointers):** Instead of stuffing 10,000 tokens of history into a handoff payload, Agent A attaches `[:PINNED_CONTEXT {relevance_reason}]` edges directly from the `:SubTask` node to the exact `:Entity`, `:Episode`, or `:Procedure` nodes Agent B needs. Agent B wakes up, queries its assigned `:SubTask` neighborhood in 1 hop, and has instant, deterministic context.



```cypher
// Atomic Concurrent SubTask Claim + Context Pointer Fetch (Priority 2)
MATCH (t:TaskRun {id: $task_id})-[:HAS_SUBTASK]->(st:SubTask {status: 'PENDING'})
WHERE NOT EXISTS {
    MATCH (st)-[:DEPENDS_ON]->(dep:SubTask)
    WHERE dep.status <> 'COMPLETED'
}
WITH st LIMIT 1
SET st.status = 'IN_PROGRESS',
    st.locked_by = $agent_id,
    st.claimed_at = $now
WITH st
OPTIONAL MATCH (st)-[:DEPENDS_ON]->(parent:SubTask)-[:PINNED_CONTEXT]->(ctx)
RETURN st, collect(ctx) AS inherited_context_nodes

```

---

### Layer 3: Procedural Memory (Executable Skill DAGs & Failure Guardrails)

* **Implementation Priority:** **P1 (Build Third — Hours 35–50 — The Winning Differentiator)**
* **What It Means:**
* **Procedural Memory** stores *how to do things*—learned workflows, tool execution sequences, and operational guardrails distilled from past successes and mistakes.


* **How It Works in FalkorDB:**
1. **Skill Subgraphs:** Stored as `(:Procedure {name, trigger_description, embedding, success_count, fail_count})` connected via `[:FIRST_STEP]` and `[:NEXT_STEP]` to `(:ActionStep {step_order, tool_name, param_schema})` nodes.
2. **The Reflexion Mutation Loop (Learning from Failure):**
* Suppose the *Executor Agent* attempts a task, calls a tool with bad parameters or hits a domain edge case, and fails.
* That failure is logged as an `:Episode {outcome: 'ERROR'}`.
* When the agent recovers and succeeds on retry, the **Procedural Compiler Node** in LangGraph executes a Cypher mutation: it creates a `(:Guardrail {rule_text, error_signature, fix_instruction})` node and links it via `[:HAS_GUARDRAIL]` to the specific `:ActionStep` or `:Procedure`.


3. **Cross-Session Recall:** In any future session, before executing a plan, the agent queries FalkorDB for matching `:Procedure` subgraphs and their attached `:Guardrail` nodes. It sees the guardrail immediately and executes the task cleanly on the first attempt.



```cypher
// Procedural Skill + Guardrail Retrieval Query (Priority 3)
CALL db.idx.vector.queryNodes('Procedure', 'embedding', 1, $intent_embedding)
YIELD node AS proc, score
WHERE score > 0.78
MATCH path = (proc)-[:FIRST_STEP|NEXT_STEP*1..10]->(step:ActionStep)
OPTIONAL MATCH (step)-[:HAS_GUARDRAIL]->(g:Guardrail)
RETURN proc, nodes(path) AS ordered_steps, collect(g) AS active_guardrails

```

---

### Layer 4: Slow-Stream Memory Consolidation & Decay Engine

* **Implementation Priority:** **P2 (Build Fourth — Hours 51–60)**
* **What It Means:**
* Cognitive memory cannot grow unboundedly without noise. The **Consolidation Layer** acts like human sleep: compressing old episodic chains into high-level semantic summaries, merging duplicate entities, and decaying low-utility nodes.


* **How It Works in FalkorDB:**
1. **Interactive "Trigger Consolidation Cycle" Button:** Exposed via `POST /api/v1/memory/consolidate` so judges can trigger it on demand during the demo.
2. **Post-Execution Utility & Threshold Feedback (`vCache` + `MemRL`):** When subtasks complete, memory nodes pinned via `[:PINNED_CONTEXT]` receive reinforcement updates based on whether the action succeeded ($r = +1$) or encountered an error ($r = -1$):
   ```cypher
   MATCH (st:SubTask {id: $subtask_id})-[:PINNED_CONTEXT]->(m)
   SET m.access_count = coalesce(m.access_count, 0) + 1,
       m.last_accessed = $now,
       m.utility_score = coalesce(m.utility_score, m.importance_score, 0.5) + $alpha * ($reward - coalesce(m.utility_score, m.importance_score, 0.5)),
       m.vcache_threshold = CASE
           WHEN $reward > 0 THEN coalesce(m.vcache_threshold, 0.78) - 0.02
           ELSE coalesce(m.vcache_threshold, 0.78) + 0.05
       END
   RETURN m.id AS id, m.name AS name, m.utility_score AS new_utility, m.vcache_threshold AS new_threshold
   ```
3. **Graph Retention Scoring (`MemoryBank` Strength + `MemRL` Utility + Degree):**
   Combines Ebbinghaus recall reinforcement ($S \leftarrow S + 1$), runtime reinforcement learning utility, and graph degree:

$$\text{RetentionScore}(n) = (\text{Degree}(n) + 1) \times \text{Utility}(n) \times e^{-\frac{\lambda \cdot (t_{\text{now}} - t_{\text{last\_accessed}})}{\text{AccessCount}(n) + 1}}$$

4. **Episode Compression:** Identifies clusters of older `:Episode` nodes (> $N$ turns old) sharing the same `:Entity` neighborhood, uses an LLM call to synthesize a `:ConsolidatedInsight` node, rewires provenance edges, and marks raw episodes as `archived: true`.

---

## 5. The Showcase Platform (Multi-Tenant Demo Application)

To make the invisible backend mechanics visually undeniable to judges, the Showcase Platform will feature a **"DevOps / Incident & Codebase Triage Copilot"** scenario (which seamlessly satisfies both **Track 02** and **Track 01**).

### 5.1 Core UI Views (Single-Screen Split Layout)

1. **Top Bar — Multi-Tenant & Session Switcher:**
* Dropdown to switch between **Tenant A (`acme-payments`)** and **Tenant B (`nebula-cloud`)**, and Users (`alice_sre`, `bob_backend`).
* Displays active FalkorDB Graph Key (`mem_acme-payments_shared`) and sub-millisecond query latency metrics.


2. **Left Panel — Multi-Agent Chat & Handoff Stream:**
* Shows the user prompt and live status badges of 3 coordinating LangGraph agents:
* `🧭 Orchestrator Agent` (Decomposes tasks into Working Memory `:SubTask` nodes)
* `🔍 Context & Triage Agent` (Queries Semantic + Episodic bi-temporal graph)
* `⚙️ Execution & Reflexion Agent` (Executes tools & mutates `:Procedure` / `:Guardrail` nodes)




3. **Center Panel — Live 4-Tier FalkorDB Graph Visualizer (Cytoscape.js):**
* Color-coded nodes:
* 🟡 **Yellow:** `:TaskRun` / `:SubTask` (Working Memory — pulses when locked by an agent)
* 🔵 **Blue:** `:Episode` (Episodic Memory)
* 🟢 **Green:** `:Entity` (Semantic Memory — solid edges for current facts, dashed red edges for superseded historical facts where `valid_to IS NOT NULL`)
* 🟣 **Purple:** `:Procedure` / `:ActionStep` / `:Guardrail` (Procedural Memory)




4. **Right Panel — Cypher & Provenance Inspector ("Show the Path Behind an Answer"):**
* Clicking any agent response highlights the exact subgraph traversal path in the Center Panel and displays:
* The exact **OpenCypher query** executed.
* **Time-Travel Slider / Toggle:** Toggle between *"Current Belief State"* and *"Historical Belief State (Include Invalidated Edges)"*.
* **"Run Memory Consolidation" Button:** Compresses old episodes live on screen.





---

## 6. Recommended Repository Structure

```text
aegis-graph/
├── docker-compose.yml              # FalkorDB (ports 6379, 3000) + FastAPI Backend + Frontend
├── README.md                       # Architecture diagrams, Paper citations, Data Model, Cypher Catalog
├── backend/
│   ├── pyproject.toml              # uv: fastapi, falkordb, langchain, langchain-falkordb, langgraph
│   ├── app/
│   │   ├── main.py                 # FastAPI entrypoint + SSE stream endpoints
│   │   ├── core/
│   │   │   ├── falkor_client.py    # Multi-tenant graph router & vector index bootstrapper
│   │   │   └── cypher_catalog.py   # All parameterized Cypher queries (documented for Rule #10)
│   │   ├── memory/
│   │   │   ├── working.py          # Priority 2: Atomic task DAGs, locking & context pointers
│   │   │   ├── episodic.py         # Priority 1A: Episode logging & temporal chains
│   │   │   ├── semantic.py         # Priority 1B: Entity extraction, bi-temporal upsert & HippoRAG
│   │   │   ├── procedural.py       # Priority 3: Skill DAG retrieval & Reflexion guardrail writer
│   │   │   └── consolidation.py    # Priority 4: Slow-stream decay & episode summarization
│   │   └── agents/
│   │       ├── orchestrator.py     # LangGraph multi-agent coordinator backed by FalkorDB Working Memory
│   │       └── tools.py            # Mock incident/codebase tools that trigger realistic failure/recovery
└── frontend/                       # SvelteKit or Next.js Showcase Dashboard
    ├── src/
    │   ├── components/
    │   │   ├── TenantSwitcher.svelte
    │   │   ├── GraphCanvas.svelte  # Cytoscape.js 4-tier visualizer
    │   │   ├── AgentStream.svelte  # Real-time multi-agent handoff feed
    │   │   └── CypherInspector.svelte

```

---

## 7. Master Execution & Submission Checklist

Use this sequential checklist to track execution through **October 18, 11:59 PM IST**.

### Phase 0: Environment & FalkorDB Bootstrap (Hours 0–4)

* [ ] Spin up FalkorDB via Docker (`docker run -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest`).
* [ ] Initialize Python backend with `uv` (`fastapi`, `uvicorn`, `falkordb`, `langchain`, `langchain-falkordb`, `langgraph`, `pydantic`).
* [ ] Implement `TenantGraphRouter`: helper that takes `(tenant_id, user_id)` and selects isolated FalkorDB graph `mem_{tenant_id}` while auto-creating vector indexes on `:Entity(embedding)`, `:Episode(embedding)`, and `:Procedure(embedding)`.
* [ ] Centralize all raw Cypher queries inside `cypher_catalog.py` so they can be streamed to the UI and easily pasted into `README.md` for Rule #10.

### Phase 1: Priority 1 — Coupled Episodic & Semantic Bi-Temporal Memory (Hours 5–20)

* [ ] Implement `:Episode` node ingestion with `[:NEXT_EPISODE]` chaining and vector embeddings.
* [ ] Build LLM structured output extractor (`EntityTriple`: subject, predicate, object, confidence).
* [ ] Write and test the **Bi-Temporal Conflict Resolution Cypher Query** (invalidating contradicted edges via `SET r.valid_to = $now` and inserting the new edge with `valid_from = $now` and `[:DERIVED_FROM]->(:Episode)`).
* [ ] Implement **HippoRAG Hybrid Retrieval** (Vector search seed nodes $\rightarrow$ 2-hop active Cypher neighborhood traversal $\rightarrow$ provenance episode lookup).

### Phase 2: Priority 2 — Working Memory & Multi-Agent Coordination (Hours 21–36)

* [ ] Implement `:TaskRun` and `:SubTask` DAG creation in FalkorDB (`[:HAS_SUBTASK]`, `[:DEPENDS_ON]`).
* [ ] Implement the **Atomic SubTask Claiming Query** (`status: 'PENDING'` $\rightarrow$ `'IN_PROGRESS'` with `locked_by: $agent_id`).
* [ ] Implement **Context Pointers** (`(:SubTask)-[:PINNED_CONTEXT]->(:Entity | :Episode | :Procedure)`) for zero-copy state handoffs between agents.
* [ ] Wire up 3 async LangGraph worker nodes (*Planner*, *Researcher*, *Executor*) coordinating via the FalkorDB blackboard and streaming events over FastAPI SSE.

### Phase 3: Priority 3 — Procedural Memory & Reflexion Loop (Hours 37–50)

* [ ] Implement `:Procedure` $\rightarrow$ `[:FIRST_STEP | :NEXT_STEP]` $\rightarrow$ `:ActionStep` schema in FalkorDB.
* [ ] Build the **Reflexion Post-Failure Hook**: when an agent tool call fails and subsequently recovers, automatically create a `(:Guardrail)` node attached to the `:ActionStep` via `[:HAS_GUARDRAIL]` and link it to the failed `:Episode`.
* [ ] Verify the **"2-Session Learning Demo"**: Session 1 hits a simulated tool trap, recovers, and writes a `:Guardrail` node. Session 2 queries the `:Procedure` graph first, reads the `:Guardrail`, and bypasses the trap on attempt #1.

### Phase 4: Priority 4 — Memory Consolidation & Showcase UI (Hours 51–64)

* [ ] Implement `POST /api/v1/memory/consolidate`: merges duplicate entities, summarizes old `:Episode` clusters into `:ConsolidatedInsight` nodes, and archives stale nodes.
* [ ] Build the Frontend Dashboard:
* [ ] Tenant & User Switcher (proving multi-tenant isolation).
* [ ] Live Cytoscape.js graph view with 4-tier color coding and Historical vs. Active edge toggle.
* [ ] Live Cypher Query & Provenance path inspector panel.


* [ ] Pre-seed 2 tenants (`acme-payments` and `nebula-cloud`) with realistic initial incidents/facts so the graph looks rich immediately upon launch.

### Phase 5: Hackathon Rule #10 Compliance & Submission Polish (Hours 65–72)

* [ ] **Rule #3 Check:** Verify that removing FalkorDB breaks 100% of agent state, memory recall, and task coordination.
* [ ] **Rule #10 Check — Public Git Repo & README:**
* [ ] Document the complete 4-tier Graph Data Model (Mermaid schema diagram).
* [ ] Include the dedicated **Cypher Query & Algorithm Catalog** section in `README.md`.
* [ ] Include the **Research Paper Citations Table** in `README.md`.
* [ ] Add deterministic `docker-compose up --build` setup instructions.


* [ ] **Rule #11 Check:** Add an explicit *"AI Coding Assistant Disclosure"* section at the bottom of `README.md`.
* [ ] **Rule #10 Check — Live Deployment + Demo Video:**
* [ ] Deploy backend + FalkorDB + frontend (or provide 1-command Docker setup + hosted tunnel).
* [ ] Record a tight 3-minute Demo Video demonstrating: (1) Bi-temporal conflict resolution, (2) Concurrent multi-agent handoffs via Working Memory, (3) Cross-session Procedural learning via Guardrails, and (4) Multi-tenant isolation switch.


* [ ] **Rule #5 Check:** Explicitly list **Track 02 (Agent Memory and Coordination)** and **Track 01 (Agents That Act on Connected Data)** on the submission form before Oct 18, 11:59 PM IST.
