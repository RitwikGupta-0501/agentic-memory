# AegisGraph REST & Streaming API Reference

The AegisGraph backend exposes a FastAPI REST API and Server-Sent Events (SSE) streaming interface for cognitive memory management and agent execution.

Interactive Swagger documentation is available locally at `http://localhost:8000/docs`.

---

## 1. Agent Coordination & Execution Endpoints

### 1.1 Execute Agent Task (Synchronous)
Runs the full 3-subtask cognitive loop (Triage -> Execution/Reflexion -> Synthesis) and returns the answer with execution event logs.

- **Method**: `POST`
- **Path**: `/api/v1/agents/run`
- **Request Body**:
  ```json
  {
    "prompt": "What is our primary production database?",
    "tenant_id": "tenant-acme",
    "user_id": "alice",
    "session_id": "session-prod-01"
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "task_id": "task_4f8b1a",
    "status": "SUCCESS",
    "answer": "Our primary production database is FalkorDB running in cloud region Asia-South1.",
    "duration_ms": 1385.2,
    "events": [
      {
        "type": "agent_event",
        "agent": "Orchestrator Agent",
        "phase": "plan",
        "message": "Received goal... Decomposing into Working Memory DAG..."
      },
      {
        "type": "episodic_retrieval_event",
        "agent": "Context & Triage Agent",
        "phase": "retrieval",
        "message": "Park et al. 3-factor retrieval matched 2 historical episode(s)..."
      },
      {
        "type": "hipporag_event",
        "agent": "Context & Triage Agent",
        "phase": "semantic_retrieval",
        "message": "HippoRAG associative recall identified 2 entity(ies)..."
      }
    ]
  }
  ```

---

### 1.2 Stream Agent Execution (SSE)
Streams agent events, memory recall operations, blackboard status updates, and the final answer in real time using Server-Sent Events.

- **Method**: `POST`
- **Path**: `/api/v1/agents/stream`
- **Content-Type**: `text/event-stream`
- **Request Body**:
  ```json
  {
    "prompt": "Run database migration and check guardrails.",
    "tenant_id": "tenant-acme",
    "session_id": "session-live-01"
  }
  ```
- **SSE Stream Output**:
  ```text
  data: {"type": "agent_event", "agent": "Orchestrator Agent", "phase": "plan", "message": "..."}

  data: {"type": "blackboard_event", "task_id": "task_a1b2", "status": "DAG_CREATED", "subtasks": [...]}

  data: {"type": "episodic_retrieval_event", "phase": "retrieval", "retrieved_episodes": [...]}

  data: {"type": "hipporag_event", "seeds": ["PostgreSQL", "FalkorDB"], "ranked_entities": [...]}

  data: {"type": "procedural_event", "phase": "guardrail_hit", "message": "Enforcing WAL checkpoint flag on first attempt!"}

  data: {"type": "final_answer", "answer": "Migration executed successfully with WAL checkpoint verified."}
  ```

---

## 2. Episodic Memory Endpoints

### 2.1 Record Episode
- **Method**: `POST`
- **Path**: `/api/v1/memory/episode`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "session_id": "session-101",
    "role": "user",
    "content": "We are migrating to FalkorDB on Monday.",
    "importance_score": 0.85
  }
  ```

### 2.2 Retrieve Episodes (Park et al. 3-Factor Model)
- **Method**: `POST`
- **Path**: `/api/v1/memory/episodes/retrieve`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "query": "What database was migrated?",
    "top_k": 3,
    "cross_session": true,
    "alpha": 1.0,
    "beta": 1.0,
    "gamma": 1.0
  }
  ```

### 2.3 Record Memory Feedback (MemRL Q-Learning)
Updates the runtime utility score of an episode after task completion:
- **Method**: `POST`
- **Path**: `/api/v1/memory/episode/feedback`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "episode_id": "ep_abc123",
    "reward": 1.0
  }
  ```

---

## 3. Semantic Memory & HippoRAG Endpoints

### 3.1 Upsert Fact (Bi-Temporal)
- **Method**: `POST`
- **Path**: `/api/v1/memory/semantic/fact`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "subject": "Prod_DB",
    "predicate": "USES_TECH",
    "object": "FalkorDB",
    "cardinality": "SINGLE",
    "confidence": 1.0
  }
  ```

### 3.2 HippoRAG Associative Graph Retrieval
Executes Personalized PageRank spreading activation over the active knowledge graph:
- **Method**: `POST`
- **Path**: `/api/v1/memory/semantic/hipporag`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "query": "What technologies power our database?",
    "top_k": 5,
    "damping": 0.85,
    "max_hops": 2
  }
  ```

### 3.3 Historical Entity Snapshot (Time-Travel)
Retrieves the state of an entity as it existed at a past Unix timestamp:
- **Method**: `GET`
- **Path**: `/api/v1/memory/semantic/history/{entity_name}?tenant_id=tenant-acme`

---

## 4. Working Memory (Blackboard) Endpoints

### 4.1 Initialize Task DAG
- **Method**: `POST`
- **Path**: `/api/v1/memory/working/dag`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "goal": "Migrate schema and verify replication",
    "task_id": "task_mig_01",
    "subtasks": [
      {
        "id": "st1",
        "title": "Triage schema",
        "description": "Inspect Postgres tables",
        "depends_on": []
      },
      {
        "id": "st2",
        "title": "Execute migration",
        "description": "Stream data to FalkorDB",
        "depends_on": ["st1"]
      }
    ]
  }
  ```

### 4.2 Atomically Claim Next SubTask
- **Method**: `POST`
- **Path**: `/api/v1/memory/working/claim`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "task_id": "task_mig_01",
    "agent_id": "Executor-Agent-01"
  }
  ```

### 4.3 Pin Context Node
- **Method**: `POST`
- **Path**: `/api/v1/memory/working/pin`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "subtask_id": "st1",
    "target_id": "ent_postgres",
    "reason": "Source schema reference"
  }
  ```

---

## 5. Procedural Memory Endpoints

### 5.1 Retrieve Procedure & Guardrails
- **Method**: `POST`
- **Path**: `/api/v1/memory/procedural/retrieve`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "procedure_name": "Database_Migration",
    "intent": "migration cutover"
  }
  ```

### 5.2 Compile Reflexion Guardrail
- **Method**: `POST`
- **Path**: `/api/v1/memory/procedural/compile-reflexion`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-acme",
    "step_id": "step_migration_exec",
    "error_signature": "ERR_NO_WAL_CHECKPOINT",
    "rule_text": "Always set require_wal_checkpoint=True during cutover",
    "fix_instruction": "Pass require_wal_checkpoint=True in tool parameters",
    "episode_id": "ep_fail_turn_01"
  }
  ```

---

## 6. System & Health Endpoints

### 6.1 Service Health
- **Method**: `GET`
- **Path**: `/api/health`
- **Response**:
  ```json
  {
    "status": "HEALTHY",
    "falkordb_connected": true,
    "falkordb_host": "xxxx.falkordb.cloud",
    "falkordb_port": 50891,
    "default_tenant": "tenant-default",
    "llm_provider": "gemini"
  }
  ```
