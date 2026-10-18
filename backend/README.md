---
title: AegisGraph Cognitive Engine
emoji: 🧠
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 8000
pinned: false
---

# AegisGraph Backend

Production backend service for **AegisGraph**, powered by **FastAPI**, **FalkorDB**, **LangChain**, and **Pydantic**. Implements hardware-isolated multi-tenant graph memory across **Working**, **Episodic**, **Semantic**, and **Procedural** memory tiers.

---

## 1. Directory Structure

```text
backend/
├── app/
│   ├── main.py                  # FastAPI application entrypoint & lifespan
│   ├── core/                    # Infrastructure & database connectivity
│   │   ├── config.py            # Pydantic v2 application settings
│   │   ├── falkor_client.py     # Multi-tenant FalkorDB graph router
│   │   ├── cypher_catalog.py    # Centralized OpenCypher query repository
│   │   └── embeddings/          # Vector embedding provider factory & reindexer
│   ├── memory/                  # The 4 Cognitive Memory Tiers
│   │   ├── episodic.py          # Session tracking & Park et al. 3-factor composite recall
│   │   ├── semantic.py          # Bi-temporal knowledge graph & HippoRAG PageRank
│   │   ├── working.py           # Multi-agent Task DAG & context pinning blackboard
│   │   ├── procedural.py        # Workflows, tool schemas, & Reflexion guardrails
│   │   ├── consolidation.py     # Background slow-stream memory pruning & decay
│   │   └── importance.py        # LLM importance scoring
│   ├── agents/                  # Cognitive Orchestration Engine
│   │   ├── orchestrator.py      # Production CognitiveAgentEngine & SSE generator
│   │   └── tools.py             # Domain actions & graph memory inspection tools
│   └── api/                     # REST & SSE API Endpoints
│       ├── routes_coordination.py # /api/v1/agents (run, stream)
│       ├── routes_memory.py       # /api/v1/memory (episodic, semantic, working, procedural)
│       └── routes_consolidation.py# /api/v1/memory (consolidate, retention)
└── tests/                       # 100+ Pytest suites verifying graph schemas & algorithms
```

---

## 2. Environment Configuration

Copy `.env.example` to `.env` in the root or set environment variables:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `FALKORDB_HOST` | Hostname of the FalkorDB instance (local or Cloud) | `localhost` |
| `FALKORDB_PORT` | Port of the FalkorDB instance | `6379` |
| `FALKORDB_PASSWORD` | Password for FalkorDB authentication | `""` |
| `LLM_PROVIDER` | Active LLM provider (`gemini`, `openai`, `anthropic`) | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API Key | `""` |
| `OPENAI_API_KEY` | OpenAI API Key (if using OpenAI) | `""` |
| `ANTHROPIC_API_KEY` | Anthropic API Key (if using Anthropic) | `""` |
| `DEFAULT_TENANT_ID`| Default tenant graph namespace | `tenant-default` |
| `DEFAULT_USER_ID`  | Default user graph namespace | `user-default` |
| `EMBEDDING_PROVIDER`| Embedding engine (`fastembed`, `gemini`, `openai`, `mock`) | `gemini` |

---

## 3. Running Locally with `uv`

### Install Dependencies
```bash
cd backend
uv sync
```

### Start Development Server
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The interactive OpenAPI docs are accessible at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## 4. Running the Test Suite

AegisGraph has comprehensive unit and live-integration test suites validating Cypher queries, vector indices, bi-temporal edge transitions, and agent Reflexion loops:

```bash
# Run all tests
uv run pytest -v

# Run cognitive agent & memory integration tests
uv run pytest tests/test_cognitive_agent.py \
              tests/test_orchestrator_e2e_reflexion.py \
              tests/test_bitemporal_memory.py \
              tests/test_procedural_memory.py \
              tests/test_episodic_schema.py -v
```

---

## 5. Docker Deployment

Build and run the standalone backend container:

```bash
docker build -t aegisgraph-backend .
docker run -p 8000:8000 --env-file ../.env aegisgraph-backend
```
