"""Procedural Memory Layer: Reusable skill DAGs and Reflexion guardrail compilation."""

import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.cypher_catalog import (
    PROCEDURE_CREATE,
    ACTION_STEP_APPEND,
    PROCEDURAL_RETRIEVAL_WITH_GUARDRAILS,
    PROCEDURAL_GUARDRAIL_ATTACH,
)
from app.core.falkor_client import falkor_router


class ActionStepSpec(BaseModel):
    id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:6]}")
    step_order: int
    tool_name: str
    param_schema: str = "{}"


class ProceduralMemoryManager:
    """Manages skill DAGs, guardrails, and cross-session procedural learning."""

    def __init__(self, router=falkor_router):
        self.router = router

    def register_procedure(
        self,
        tenant_id: str,
        name: str,
        trigger_description: str,
        steps: List[ActionStepSpec],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a procedure node and its ordered action steps in FalkorDB."""
        proc_id = f"proc_{uuid.uuid4().hex[:6]}"

        # 1. Create Procedure
        self.router.query(
            PROCEDURE_CREATE,
            {
                "procedure_id": proc_id,
                "name": name,
                "trigger_description": trigger_description,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # 2. Append Steps
        for step in steps:
            self.router.query(
                ACTION_STEP_APPEND,
                {
                    "procedure_id": proc_id,
                    "step_id": step.id,
                    "step_order": step.step_order,
                    "tool_name": step.tool_name,
                    "param_schema": step.param_schema,
                },
                tenant_id=tenant_id,
                user_id=user_id,
            )

        # 3. Chain consecutive steps with NEXT_STEP
        sorted_steps = sorted(steps, key=lambda s: s.step_order)
        for i in range(len(sorted_steps) - 1):
            chain_query = """
            MATCH (s1:ActionStep {id: $id1})
            MATCH (s2:ActionStep {id: $id2})
            MERGE (s1)-[:NEXT_STEP]->(s2)
            """
            self.router.query(
                chain_query,
                {"id1": sorted_steps[i].id, "id2": sorted_steps[i+1].id},
                tenant_id=tenant_id,
                user_id=user_id,
            )

        return {
            "procedure_id": proc_id,
            "name": name,
            "steps_count": len(steps),
        }

    def retrieve_procedure(
        self,
        tenant_id: str,
        procedure_name: str,
        intent: str = "",
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a skill DAG along with any attached Guardrails from past failures."""
        res = self.router.query(
            PROCEDURAL_RETRIEVAL_WITH_GUARDRAILS,
            {"procedure_name": procedure_name, "intent": intent or procedure_name},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not res or not res.result_set or not res.result_set[0]:
            return None

        row = res.result_set[0]
        proc_node = row[0]
        steps_nodes = row[1] if len(row) > 1 and row[1] else []
        guardrails_nodes = row[2] if len(row) > 2 and row[2] else []

        proc_props = getattr(proc_node, "properties", {})
        steps = [getattr(s, "properties", {}) for s in steps_nodes if s]
        guardrails = [getattr(g, "properties", {}) for g in guardrails_nodes if g]

        return {
            "procedure": proc_props,
            "steps": steps,
            "guardrails": guardrails,
        }

    def attach_guardrail(
        self,
        tenant_id: str,
        step_id: str,
        rule_text: str,
        error_signature: str,
        fix_instruction: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reflexion hook: Attaches a Guardrail node to a step that encountered an operational failure."""
        now = time.time()
        guardrail_id = f"gr_{uuid.uuid4().hex[:6]}"

        self.router.query(
            PROCEDURAL_GUARDRAIL_ATTACH,
            {
                "step_id": step_id,
                "guardrail_id": guardrail_id,
                "rule_text": rule_text,
                "error_signature": error_signature,
                "fix_instruction": fix_instruction,
                "now": now,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return {
            "guardrail_id": guardrail_id,
            "step_id": step_id,
            "rule_text": rule_text,
            "fix_instruction": fix_instruction,
        }


procedural_memory = ProceduralMemoryManager()
