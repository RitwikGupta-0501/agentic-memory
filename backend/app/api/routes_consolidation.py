"""API endpoints for memory consolidation and retention decay scoring."""

from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.memory.consolidation import consolidation_engine

router = APIRouter(prefix="/api/v1/memory", tags=["consolidation"])


class ConsolidateRequest(BaseModel):
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/consolidate")
def trigger_memory_consolidation(req: ConsolidateRequest) -> Dict[str, Any]:
    """Manually triggers a Slow-Stream memory consolidation cycle."""
    tenant_id = req.tenant_id or settings.default_tenant_id
    res = consolidation_engine.trigger_consolidation_cycle(
        tenant_id=tenant_id,
        session_id=req.session_id,
        user_id=req.user_id,
    )
    return res


@router.get("/retention")
def get_retention_scores(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns calculated node retention scores using exponential recency decay."""
    t_id = tenant_id or settings.default_tenant_id
    scores = consolidation_engine.calculate_retention_scores(tenant_id=t_id)
    return {"tenant_id": t_id, "scores": scores}
