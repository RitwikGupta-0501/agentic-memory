# AegisGraph: Complete Phase-by-Phase Execution Roadmap
**Target Event:** Graph Hacks: Context for AI Agents (Powered by FalkorDB)  
**Tracks:** Track 02 (Agent Memory and Coordination — Primary) & Track 01 (Agents That Act on Connected Data — Secondary)  
**Hard Deadline:** October 18, 2026, 11:59 PM IST  

---

## Current Repository Status Snapshot (As of Oct 15, 11:30 PM IST)

| Component | Status | Files Implemented | Remaining Work |
| :--- | :--- | :--- | :--- |
| **FalkorDB Multi-Tenant Router** | 🟢 90% Done | `app/core/falkor_client.py`, `app/core/config.py` | Add vector index bootstrap (`db.idx.vector`) alongside property indexes. |
| **OpenCypher Query Catalog** | 🟢 95% Done | `app/core/cypher_catalog.py` | Add dynamic provenance path query & vector similarity hybrid query. |
| **4-Tier Memory Managers** | 🟡 80% Done | `episodic.py`, `semantic.py`, `working.py`, `procedural.py`, `consolidation.py` | Wire real LLM structured extraction (`EntityTriple`) & LLM consolidation summary alongside mock fallback. |
| **Multi-Agent Orchestrator** | 🟡 60% Done | `app/agents/orchestrator.py`, `app/agents/tools.py` | Convert linear generator into real LangGraph `StateGraph` + concurrent `asyncio.gather` workers. |
| **FastAPI Routes & Seeding** | 🟢 90% Done | `app/main.py`, `routes_memory.py`, `routes_coordination.py`, `routes_consolidation.py`, `seed_data.py` | Add `GET /api/v1/tenants` and `DELETE /api/v1/memory/reset` for easy judge testing. |
| **Showcase Frontend UI** | 🔴 0% Done | *Not started* | Build split-screen Dashboard (Tenant Switcher, Agent Stream, Cytoscape 4-Tier Graph, Cypher Inspector). |
| **Docker & Submission Assets** | 🔴 20% Done | `backend/Dockerfile` | Create root `docker-compose.yml`, root `README.md` with Mermaid diagrams, and 3-min Demo Video. |

---

## Phase 1: Live FalkorDB Container & Backend LLM Upgrade
**Window:** Tonight (Oct 15, 11:30 PM) – Oct 16, 10:00 AM IST  
**Goal:** Eliminate mock-only limitations so any custom judge prompt dynamically extracts entities, resolves bi-temporal conflicts, and passes all live FalkorDB integration tests.

### Step 1.1: Root `docker-compose.yml` & Live Test Verification
- [ ] Create root `docker-compose.yml` orchestrating:
  - `falkordb`: `falkordb/falkordb:latest` exposing `6379:6379` (Redis/Bolt protocol) and `3000:3000` (FalkorDB Browser UI).
  - `backend`: `./backend` exposing `8000:8000` with `FALKORDB_HOST=falkordb`.
- [ ] Run `uv run pytest -v` against the running FalkorDB container and verify `tests/test_live_falkordb_integration.py` executes and passes (0 skipped tests).
- [ ] Fix `Dockerfile` in `backend/` if `python:3.14-slim` has wheel build issues on cloud hosts (keep `python:3.12-slim` or `3.13-slim` ready for fast cloud deployment).

### Step 1.2: Real LLM Structured Extraction + Hybrid Vector Indexing
- [ ] Add LLM provider package (`langchain-google-genai` or `langchain-openai`) to `pyproject.toml`.
- [ ] In `app/memory/semantic.py`, update `extract_triples_from_text(text: str)`:
  - When `settings.llm_provider != "mock"`, invoke LangChain `.with_structured_output(EntityTripleList)` to extract arbitrary `(subject, predicate, object, confidence)` triples from any user prompt.
  - Keep the existing `if "migrated" in lower:` heuristics as a deterministic fallback if API keys are missing or rate-limited.
- [ ] In `app/memory/consolidation.py`, upgrade `trigger_consolidation_cycle()` to synthesize a crisp executive insight using the LLM when online (with the string-join summary as fallback).
- [ ] In `app/core/falkor_client.py`, add vector index creation for `Entity`, `Episode`, and `Procedure` nodes (`CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding) OPTIONS {dimension: 768, similarityFunction: 'cosine'}`).

### Step 1.3: Post-Creation Dynamic Score Adaptation & Feedback Loop (vCache + MemRL + MemoryBank)
- [ ] Add `MEMORY_UTILITY_FEEDBACK_UPDATE` query to `app/core/cypher_catalog.py`:
  - Implements **`vCache`** (ICLR 2026) per-node decision boundary shifts ($\hat{\tau}_i$) based on verified runtime outcomes.
  - Implements **`MemRL`** (Jan 2026) non-parametric Q-value update rule: $Q_{t+1}(m_i) \leftarrow Q_t(m_i) + \alpha (r_t - Q_t(m_i))$.
  - Implements **`MemoryBank`** (AAAI 2024) recall reinforcement: updates `m.access_count = coalesce(m.access_count, 0) + 1` and `m.last_accessed = $now`.
- [ ] Hook `MEMORY_UTILITY_FEEDBACK_UPDATE` into `working_memory.complete_subtask()` and `orchestrator.py` so memory nodes pinned via `[:PINNED_CONTEXT]` receive $r = +1$ upon success and $r = -1$ upon tool error.
- [ ] In `app/memory/consolidation.py`, update `calculate_retention_scores()` from flat degree decay to the combined `MemoryBank` Strength $\times$ `MemRL` Utility $\times$ Graph Degree retention formula:
  $$\text{RetentionScore}(n) = (\text{Degree}(n) + 1) \times \text{Utility}(n) \times e^{-\frac{\lambda \cdot (t_{\text{now}} - t_{\text{last\_accessed}})}{\text{AccessCount}(n) + 1}}$$

---

## Phase 2: True LangGraph Multi-Agent Concurrency & Reflexion Engine
**Window:** Oct 16, 10:00 AM – Oct 16, 8:00 PM IST  
**Goal:** Make `app/agents/orchestrator.py` a genuine `langgraph.graph.StateGraph` where multiple agents coordinate strictly through FalkorDB Working Memory locks and learn dynamically from tool failures.

### Step 2.1: Refactor `orchestrator.py` into a LangGraph `StateGraph`
- [ ] Define `AgentCoordinationState(TypedDict)` holding `tenant_id`, `session_id`, `task_id`, `user_prompt`, `events_queue`, and `status`.
- [ ] Implement 3 distinct LangGraph nodes:
  1. **`planner_node` (Orchestrator Agent):** Logs the prompt into `:Episode`, extracts semantic triples into `:Entity`, and writes a dynamic DAG of `:SubTask` nodes into FalkorDB (`initialize_task_dag`).
  2. **`concurrent_workers_node` (Context Agent + Executor Agent):** Spawns 2 concurrent async workers (`asyncio.gather`) that poll FalkorDB via `working_memory.claim_next_subtask()`.
     - Worker A (*Context & Triage Agent*) claims ready triage subtasks, runs `hipporag_retrieve()`, and attaches `[:PINNED_CONTEXT]` edges to relevant `:Entity` and `:Episode` nodes.
     - Worker B (*Execution & Reflexion Agent*) claims downstream execution subtasks once upstream dependencies flip to `COMPLETED`, reads inherited `[:PINNED_CONTEXT]` nodes in 1 hop, and queries `procedural_memory.retrieve_procedure()`.
  3. **`reflexion_compiler_node` (Reflexion Loop):** Triggered conditionally via LangGraph `add_conditional_edges` whenever a tool execution returns `status == "ERROR"`.
     - Logs the failure `:Episode`.
     - Calls `procedural_memory.attach_guardrail()` to mutate the `:ActionStep` subgraph in FalkorDB.
     - Loops back to `concurrent_workers_node` to retry the step with the newly compiled guardrail parameter.

### Step 2.2: Add Judge-Friendly Reset & Tenant Inspection Endpoints
- [ ] In `app/api/routes_memory.py`, add:
  - `GET /api/v1/memory/tenants`: Returns metadata and node/edge counts for `acme-payments` and `nebula-cloud`.
  - `POST /api/v1/memory/reset-guardrails`: Deletes only `:Guardrail` nodes on `acme-payments` so judges can test the **"Run 1 Fails & Learns $\rightarrow$ Run 2 One-Shots"** flow repeatedly with one click.

### Step 2.3: Concurrency & Reflexion Integration Tests
- [ ] Add `tests/test_concurrent_subtask_claiming.py`: Spawns 5 concurrent async coroutines calling `claim_next_subtask` on the same `task_id` and asserts that each subtask is claimed by **at most one** agent (proving Track 02's *"High-concurrency reads and writes"* requirement).

---

## Phase 3: The Showcase Control Plane Frontend (`frontend/`)
**Window:** Oct 16, 8:00 PM – Oct 17, 6:00 PM IST  
**Goal:** Build a visually striking, dark-mode "Cinematic Slate" dashboard that makes the 4 memory layers, bi-temporal invalidation, and multi-agent locking immediately obvious in a 3-minute demo.

### Step 3.1: Frontend Scaffold & Layout (SvelteKit or Next.js + Tailwind)
- [ ] Initialize `frontend/` with Tailwind CSS and `cytoscape` (`npm i cytoscape lucide-svelte` or `lucide-react`).
- [ ] Build the **4-Panel Single-Screen Command Center**:
  1. **Top Header Bar (`TenantSwitcher`):**
     - Dropdown switching between `Tenant A: acme-payments (Alice - SRE)` and `Tenant B: nebula-cloud (Bob - CloudOps)`.
     - Live badge displaying the isolated FalkorDB Graph Key (`mem_acme_payments_shared`).
     - Quick-action buttons: `[Re-Seed Demo Data]`, `[Clear Learned Guardrails]`, `[Run Sleep Consolidation]`.
  2. **Left Panel (`AgentStream` — 30% width):**
     - Prompt input box + 3 one-click **Preset Demo Scenario Pills**:
       - *Scenario 1 (Bi-Temporal Update):* `"We migrated Prod_DB from PostgreSQL to FalkorDB for real-time graph memory."`
       - *Scenario 2 (Reflexion Failure -> Guardrail Compile):* `"Run production cutover migration for Prod_DB."` (First run hits `ERR_NO_WAL_CHECKPOINT`, compiles `:Guardrail`, retries, and succeeds).
       - *Scenario 3 (Cross-Session Recall):* `"Execute database migration for replica cluster."` (Hits Procedural Memory, sees `:Guardrail`, succeeds on attempt #1).
     - Live SSE event feed showing color-coded cards for `Orchestrator Agent`, `Context & Triage Agent`, and `Execution & Reflexion Agent`.
  3. **Center Panel (`GraphCanvas` — 45% width):**
     - Embedded **Cytoscape.js** canvas polling/refreshing on every SSE `agent_step` event from `GET /api/v1/memory/graph`.
     - **4-Tier Node Styling:**
       - 🟡 `tier == "working"` (`:TaskRun`, `:SubTask`): Amber/Yellow hexagons (pulsing border when `status == "IN_PROGRESS"`).
       - 🔵 `tier == "episodic"` (`:Episode`): Blue circles chained sequentially.
       - 🟢 `tier == "semantic"` (`:Entity`): Emerald rounded rectangles.
       - 🟣 `tier == "procedural"` (`:Procedure`, `:ActionStep`, `:Guardrail`): Purple diamonds.
     - **Bi-Temporal Edge Styling:**
       - Active facts (`is_superseded == false`): Solid emerald arrows with predicate labels.
       - Superseded historical facts (`is_superseded == true`): Dashed crimson arrows with strikethrough labels (`USES_TECH [expired]`).
     - **Top-Right Canvas Toggle:** `[x] Show Historical Superseded Beliefs (Time-Travel Mode)` (toggles `include_invalidated=true/false` on `/api/v1/memory/graph`).
  4. **Right Panel (`CypherInspector` — 25% width):**
     - Displays the live OpenCypher queries streamed in the SSE `cypher` field as the agents execute.
     - **Node/Edge Provenance Inspector:** Clicking any node or edge in the Cytoscape canvas displays its raw properties (`valid_from`, `valid_to`, `source_episode`, `locked_by`, `error_signature`) and highlights its 1-hop neighborhood.

---

## Phase 4: End-to-End Integration, Documentation & Rule #10 Compliance
**Window:** Oct 17, 6:00 PM – Oct 18, 12:00 PM IST  
**Goal:** Satisfy every mandatory item in Hackathon Rules #2, #3, #5, #10, and #11 so judges have zero reasons to dock points.

### Step 4.1: Root `README.md` Overhaul (Rule #10 & #11)
- [ ] Replace the minimal 15-line `README.md` with a comprehensive technical specification containing:
  1. **Track Declarations (Rule #5):** Explicitly state entry into **Track 02: Agent Memory and Coordination** and **Track 01: Agents That Act on Connected Data**.
  2. **System Architecture & 4-Tier Graph Data Model (Rule #10):** Mermaid ER diagram detailing all 7 node labels (`:Episode`, `:Entity`, `:TaskRun`, `:SubTask`, `:Procedure`, `:ActionStep`, `:Guardrail`, `:ConsolidatedInsight`) and edge properties.
  3. **Why FalkorDB is Irreplaceable (Rule #3 Defense):** Explain how removing FalkorDB breaks multi-tenant graph key isolation, bi-temporal edge invalidation, atomic Cypher subtask locking, and procedural DAG traversal.
  4. **OpenCypher Query Catalog (Rule #10):** Embed the core Cypher queries from `app/core/cypher_catalog.py` with explanations of how each operates.
  5. **Peer-Reviewed Research Citations Table:** CoALA, Zep/Graphiti, MemGPT, HippoRAG, Mem0, Voyager, Reflexion, vCache (ICLR 2026), MemRL (2026), and MemoryBank (AAAI 2024).
  6. **1-Command Local Setup Instructions (Rule #10):** `docker compose up --build` + `uv run pytest -v`.
  7. **AI Coding Assistant Disclosure (Rule #11):** Explicit disclosure statement regarding AI assistant usage during development.

---

## Phase 5: Deployment, 3-Minute Demo Video & Final Submission
**Window:** Oct 18, 12:00 PM – Oct 18, 9:00 PM IST (3-hour buffer before 11:59 PM deadline)  
**Goal:** Deploy a live accessible URL, record a crisp 180-second demo video, and submit early.

### Step 5.1: Cloud Deployment (Rule #10)
- [ ] Provision a FalkorDB Cloud instance (or a single Docker VM on AWS/Render/Railway/DigitalOcean running `docker compose up -d`).
- [ ] Verify public URL loads the Frontend Dashboard with `acme-payments` and `nebula-cloud` pre-seeded.

### Step 5.2: Record the 3-Minute Demo Video (Rule #10)
Follow this strict 4-beat script:
- [ ] **0:00 – 0:40 | Hook & Multi-Tenant Graph Isolation:** Show the live dashboard. Switch between `acme-payments` (`mem_acme_payments_shared`) and `nebula-cloud` (`mem_nebula_cloud_shared`). Show that tenant graphs are 100% isolated in FalkorDB.
- [ ] **0:40 – 1:25 | Bi-Temporal Episodic $\rightarrow$ Semantic Conflict Resolution:** Click Preset 1 (*"Migrate Prod_DB from PostgreSQL to FalkorDB"*). Show the green `:Entity` nodes updating in Cytoscape. Toggle the **Time-Travel Switch** to reveal the dashed red `USES_TECH` edge to `PostgreSQL` (`valid_to` stamped) alongside the active solid edge to `FalkorDB`, tracing both back to their `:Episode` nodes.
- [ ] **1:25 – 2:15 | Working Memory Blackboard & Concurrent Agent Handoffs:** Trigger a multi-agent run. Point to the yellow `:SubTask` nodes turning `IN_PROGRESS` as `Context & Triage Agent` locks Subtask 1 via atomic Cypher, attaches a `[:PINNED_CONTEXT]` edge, and hands off to `Execution & Reflexion Agent`.
- [ ] **2:15 – 3:00 | Procedural Memory & Reflexion Guardrail Loop:** Clear guardrails and run the migration tool. Watch Run 1 hit `ERR_NO_WAL_CHECKPOINT`, trigger the Reflexion hook, and spawn a purple `:Guardrail` node on the graph. Run a second session immediately—watch the agent query the Procedural DAG first, spot the `:Guardrail`, enforce `require_wal_checkpoint=True` on attempt #1, and finish with the **Sleep Consolidation** button compressing episodes into an `:Insight` node.

### Step 5.3: Final Submission Verification
- [ ] Confirm GitHub repository visibility is **Public**.
- [ ] Submit before **Oct 18, 2026, 9:00 PM IST** (do not wait until the final hour).
