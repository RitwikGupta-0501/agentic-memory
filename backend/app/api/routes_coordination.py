"""API endpoints for multi-agent coordination blackboard and real-time streaming."""

import json
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.agents.orchestrator import multi_agent_engine

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class AgentRunRequest(BaseModel):
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = "session_demo_1"
    prompt: str


@router.post("/stream")
async def run_multi_agent_stream(req: AgentRunRequest):
    """Server-Sent Events (SSE) endpoint streaming real-time agent handoffs and Cypher executions."""
    tenant_id = req.tenant_id or settings.default_tenant_id
    user_id = req.user_id or settings.default_user_id
    session_id = req.session_id or "session_demo_1"

    async def event_generator():
        async for event in multi_agent_engine.execute_task_stream(
            tenant_id=tenant_id,
            session_id=session_id,
            user_prompt=req.prompt,
            user_id=user_id,
        ):
            yield {"event": "agent_step", "data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@router.post("/run")
async def run_multi_agent_sync(req: AgentRunRequest):
    """Synchronous execution endpoint returning all coordination events in one response."""
    tenant_id = req.tenant_id or settings.default_tenant_id
    user_id = req.user_id or settings.default_user_id
    session_id = req.session_id or "session_demo_1"

    events = []
    async for event in multi_agent_engine.execute_task_stream(
        tenant_id=tenant_id,
        session_id=session_id,
        user_prompt=req.prompt,
        user_id=user_id,
    ):
        events.append(event)

    return {"status": "SUCCESS", "events": events}
