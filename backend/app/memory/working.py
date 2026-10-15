"""Working Memory Layer: Atomic blackboard coordination, task DAGs, and context pinning."""

import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.cypher_catalog import (
    TASK_DAG_CREATE,
    SUBTASK_CREATE,
    SUBTASK_ADD_DEPENDENCY,
    WORKING_MEMORY_ATOMIC_CLAIM,
    WORKING_MEMORY_COMPLETE_SUBTASK,
    WORKING_MEMORY_PIN_CONTEXT,
    MEMORY_UTILITY_FEEDBACK_UPDATE,
)
from app.core.falkor_client import falkor_router


class SubTaskSpec(BaseModel):
    id: str = Field(default_factory=lambda: f"st_{uuid.uuid4().hex[:6]}")
    title: str
    description: str
    depends_on: List[str] = Field(default_factory=list)


class WorkingMemoryManager:
    """Manages multi-agent coordination blackboard in FalkorDB."""

    def __init__(self, router=falkor_router):
        self.router = router

    def initialize_task_dag(
        self,
        tenant_id: str,
        goal: str,
        subtasks: List[SubTaskSpec],
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a TaskRun and subtask DAG in FalkorDB."""
        t_id = task_id or f"task_{uuid.uuid4().hex[:6]}"
        now = time.time()

        # 1. Create TaskRun
        self.router.query(
            TASK_DAG_CREATE,
            {"task_id": t_id, "goal": goal, "now": now},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # 2. Create SubTasks
        for st in subtasks:
            self.router.query(
                SUBTASK_CREATE,
                {
                    "task_id": t_id,
                    "subtask_id": st.id,
                    "title": st.title,
                    "description": st.description,
                    "now": now,
                },
                tenant_id=tenant_id,
                user_id=user_id,
            )

        # 3. Create Dependencies
        for st in subtasks:
            for dep_id in st.depends_on:
                self.router.query(
                    SUBTASK_ADD_DEPENDENCY,
                    {"subtask_id": st.id, "dep_id": dep_id},
                    tenant_id=tenant_id,
                    user_id=user_id,
                )

        return {
            "task_id": t_id,
            "goal": goal,
            "subtask_count": len(subtasks),
            "status": "ACTIVE",
        }

    def claim_next_subtask(
        self,
        tenant_id: str,
        task_id: str,
        agent_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically claims the next ready PENDING subtask for an agent."""
        now = time.time()
        res = self.router.query(
            WORKING_MEMORY_ATOMIC_CLAIM,
            {"task_id": task_id, "agent_id": agent_id, "now": now},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not res or not res.result_set or not res.result_set[0]:
            return None

        st_node = res.result_set[0][0]
        inherited_ctx = res.result_set[0][1] if len(res.result_set[0]) > 1 else []

        props = getattr(st_node, "properties", {})
        return {
            "subtask_id": props.get("id"),
            "title": props.get("title"),
            "status": "IN_PROGRESS",
            "locked_by": agent_id,
            "inherited_context": [
                getattr(c, "properties", str(c)) for c in inherited_ctx if c
            ],
        }

    def complete_subtask(
        self,
        tenant_id: str,
        subtask_id: str,
        agent_id: str,
        result_summary: str,
        user_id: Optional[str] = None,
        reward: Optional[float] = None,
        alpha: float = 0.2,
    ) -> bool:
        """Marks a subtask as COMPLETED and optionally updates utility of pinned context."""
        now = time.time()
        res = self.router.query(
            WORKING_MEMORY_COMPLETE_SUBTASK,
            {
                "subtask_id": subtask_id,
                "agent_id": agent_id,
                "result_summary": result_summary,
                "now": now,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if reward is not None:
            self.router.query(
                MEMORY_UTILITY_FEEDBACK_UPDATE,
                {
                    "subtask_id": subtask_id,
                    "reward": float(reward),
                    "alpha": float(alpha),
                    "now": now,
                },
                tenant_id=tenant_id,
                user_id=user_id,
            )
        return bool(res and res.result_set)

    def pin_context(
        self,
        tenant_id: str,
        subtask_id: str,
        target_id: str,
        reason: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """Attaches a zero-copy PINNED_CONTEXT pointer to an entity or episode."""
        now = time.time()
        res = self.router.query(
            WORKING_MEMORY_PIN_CONTEXT,
            {
                "subtask_id": subtask_id,
                "target_id": target_id,
                "reason": reason,
                "now": now,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return bool(res and res.result_set)


working_memory = WorkingMemoryManager()
