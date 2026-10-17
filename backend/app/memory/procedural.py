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
        steps: List[Any],
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a procedure node and its ordered action steps in FalkorDB."""
        proc_id = f"proc_{uuid.uuid4().hex[:6]}"
        step_objs: List[ActionStepSpec] = [
            s if isinstance(s, ActionStepSpec) else ActionStepSpec(**s) for s in steps
        ]

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
        for step in step_objs:
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
        sorted_steps = sorted(step_objs, key=lambda s: s.step_order)
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
            "steps_count": len(step_objs),
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

        if not res or not res.result_set:
            return None

        proc_props = {}
        steps_map = {}
        guardrails_map = {}

        for row in res.result_set:
            if not row:
                continue
            proc_node = row[0]
            if proc_node and not proc_props:
                proc_props = getattr(proc_node, "properties", {})

            steps_nodes = row[1] if len(row) > 1 and row[1] else []
            for s in steps_nodes:
                if s:
                    s_props = getattr(s, "properties", {})
                    s_id = s_props.get("id")
                    if s_id and s_id not in steps_map and s_id != proc_props.get("id"):
                        steps_map[s_id] = s_props

            guardrails_nodes = row[2] if len(row) > 2 and row[2] else []
            for g in guardrails_nodes:
                if g:
                    g_props = getattr(g, "properties", {})
                    g_id = g_props.get("id")
                    if g_id and g_id not in guardrails_map:
                        guardrails_map[g_id] = g_props

        if not proc_props:
            return None

        return {
            "procedure": proc_props,
            "steps": list(steps_map.values()),
            "guardrails": list(guardrails_map.values()),
        }


    def attach_guardrail(
        self,
        tenant_id: str,
        step_id: str,
        rule_text: str,
        error_signature: str,
        fix_instruction: str,
        episode_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reflexion hook: Attaches a Guardrail node to a step that encountered an operational failure, linked to the failure Episode."""
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
                "episode_id": episode_id,
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
            "episode_id": episode_id,
        }

    def compile_guardrail_from_failure(
        self,
        tenant_id: str,
        step_id: str,
        error_signature: str,
        rule_text: str,
        fix_instruction: str,
        episode_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compiles an operational failure trace into an active preventive Guardrail with cross-layer provenance."""
        return self.attach_guardrail(
            tenant_id=tenant_id,
            step_id=step_id,
            rule_text=rule_text,
            error_signature=error_signature,
            fix_instruction=fix_instruction,
            episode_id=episode_id,
            user_id=user_id,
        )

    def record_procedure_outcome(
        self,
        tenant_id: str,
        procedure_name: str,
        success: bool,
        user_id: Optional[str] = None,
    ) -> bool:
        """Increments success_count or fail_count on a Procedure node."""
        field = "success_count" if success else "fail_count"
        q = f"""
        MATCH (p:Procedure)
        WHERE p.name = $name
        SET p.{field} = coalesce(p.{field}, 0) + 1,
            p.updated_at = $now
        RETURN p.{field} AS count
        """
        res = self.router.query(q, {"name": procedure_name, "now": time.time()}, tenant_id=tenant_id, user_id=user_id)
        return bool(res and res.result_set)


procedural_memory = ProceduralMemoryManager()
