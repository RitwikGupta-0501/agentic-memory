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
    PROCEDURAL_OUTCOME_RECORD,
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
        now = time.time()
        proc_id = f"proc_{uuid.uuid4().hex[:6]}"
        step_objs: List[ActionStepSpec] = [
            s if isinstance(s, ActionStepSpec) else ActionStepSpec(**s) for s in steps
        ]

        # 1. Create Procedure
        proc_res = self.router.query(
            PROCEDURE_CREATE,
            {
                "procedure_id": proc_id,
                "name": name,
                "trigger_description": trigger_description,
                "now": now,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )

        actual_proc_id = proc_id
        if proc_res and proc_res.result_set and proc_res.result_set[0]:
            p_node = proc_res.result_set[0][0]
            if hasattr(p_node, "properties"):
                actual_proc_id = p_node.properties.get("id", proc_id)

        # 2. Append Steps
        for step in step_objs:
            self.router.query(
                ACTION_STEP_APPEND,
                {
                    "procedure_id": actual_proc_id,
                    "step_id": step.id,
                    "step_order": step.step_order,
                    "tool_name": step.tool_name,
                    "param_schema": step.param_schema,
                    "now": now,
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
            "procedure_id": actual_proc_id,
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
            {"procedure_name": procedure_name, "intent": intent or ""},
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not res or not res.result_set or not res.result_set[0]:
            return None

        row = res.result_set[0]
        proc_node = row[0]
        if not proc_node:
            return None

        proc_props = getattr(proc_node, "properties", {})
        if not proc_props:
            return None

        steps_map = {}
        guardrails_map = {}

        steps_nodes = row[1] if len(row) > 1 and row[1] else []
        for s in steps_nodes:
            if s:
                s_props = getattr(s, "properties", {})
                s_id = s_props.get("id")
                if s_id and s_id not in steps_map:
                    steps_map[s_id] = s_props

        guardrails_nodes = row[2] if len(row) > 2 and row[2] else []
        for g in guardrails_nodes:
            if g:
                g_props = getattr(g, "properties", {})
                g_sig = g_props.get("error_signature") or g_props.get("id")
                if g_sig and g_sig not in guardrails_map:
                    guardrails_map[g_sig] = g_props

        ordered_steps = sorted(steps_map.values(), key=lambda s: s.get("step_order", 0))

        return {
            "procedure": proc_props,
            "steps": ordered_steps,
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

        res = self.router.query(
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

        actual_gr_id = guardrail_id
        if res and res.result_set and res.result_set[0] and res.result_set[0][0]:
            g_props = getattr(res.result_set[0][0], "properties", {})
            actual_gr_id = g_props.get("id", guardrail_id)

        return {
            "guardrail_id": actual_gr_id,
            "step_id": step_id,
            "rule_text": rule_text,
            "error_signature": error_signature,
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
    ) -> Dict[str, Any]:
        """Records reinforcement success or failure outcome counts, updating Bayesian success rate and MemRL utility score."""
        now = time.time()
        res = self.router.query(
            PROCEDURAL_OUTCOME_RECORD,
            {
                "procedure_name": procedure_name,
                "success": success,
                "now": now,
            },
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if res and res.result_set and res.result_set[0]:
            row = res.result_set[0]
            return {
                "success": True,
                "procedure_name": procedure_name,
                "success_count": row[0],
                "fail_count": row[1],
                "bayesian_success_rate": row[2],
                "utility_score": row[3],
            }
        return {"success": False, "procedure_name": procedure_name}

    def reset_guardrails(
        self,
        tenant_id: str,
        procedure_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """Detaches and deletes learned Guardrails for a tenant or specific procedure."""
        if procedure_name:
            q = """
            MATCH (p:Procedure)-[:FIRST_STEP|NEXT_STEP*1..15]->(s:ActionStep)-[:HAS_GUARDRAIL]->(g:Guardrail)
            WHERE p.name = $procedure_name OR toLower(p.name) = toLower($procedure_name)
            DETACH DELETE g
            RETURN count(g) AS deleted_count
            """
            res = self.router.query(q, {"procedure_name": procedure_name}, tenant_id=tenant_id, user_id=user_id)
        else:
            q = "MATCH (g:Guardrail) DETACH DELETE g RETURN count(g) AS deleted_count"
            res = self.router.query(q, tenant_id=tenant_id, user_id=user_id)
        return res.result_set[0][0] if res and res.result_set and res.result_set[0] else 0


procedural_memory = ProceduralMemoryManager()
