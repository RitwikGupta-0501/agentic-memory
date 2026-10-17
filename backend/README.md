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

FastAPI, LangChain, LangGraph, and FalkorDB-powered 4-Tier Cognitive Graph Memory Engine.

## Running Tests
```bash
uv run pytest -v
```

## Running Dev Server
```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
