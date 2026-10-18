"""API endpoints for multi-agent coordination blackboard and real-time streaming."""

import json
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.agents.orchestrator import multi_agent_engine

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


class AgentRunRequest(BaseModel):
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = Field(default=None, description="Session ID. If not provided, a new session is generated.")
    prompt: str = Field(..., min_length=1)


@router.post("/stream")
async def run_multi_agent_stream(req: AgentRunRequest):
    """Server-Sent Events (SSE) endpoint streaming real-time agent handoffs and memory executions."""
    tenant_id = req.tenant_id or settings.default_tenant_id
    user_id = req.user_id or settings.default_user_id
    session_id = req.session_id or f"session_{uuid.uuid4().hex[:8]}"

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
async def run_multi_agent_sync(req: AgentRunRequest) -> Dict[str, Any]:
    """Synchronous execution endpoint returning all coordination events and final answer in one response."""
    tenant_id = req.tenant_id or settings.default_tenant_id
    user_id = req.user_id or settings.default_user_id
    session_id = req.session_id or f"session_{uuid.uuid4().hex[:8]}"

    events = []
    error_event = None
    final_answer = None

    async for event in multi_agent_engine.execute_task_stream(
        tenant_id=tenant_id,
        session_id=session_id,
        user_prompt=req.prompt,
        user_id=user_id,
    ):
        events.append(event)
        if event.get("type") == "error":
            error_event = event
        if event.get("answer"):
            final_answer = event.get("answer")

    if error_event:
        return {
            "status": "ERROR",
            "message": error_event.get("message", "Agent execution error"),
            "events": events,
            "session_id": session_id,
        }

    return {
        "status": "SUCCESS",
        "answer": final_answer,
        "events": events,
        "session_id": session_id,
    }
