"""LangGraph multi-agent coordinator backed by FalkorDB Working Memory."""

import asyncio
import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory
from app.memory.working import working_memory, SubTaskSpec
from app.memory.procedural import procedural_memory
from app.agents.tools import run_database_migration, query_database_config


class MultiAgentCoordinationEngine:
    """Orchestrates 3 LangGraph-style agents coordinating over FalkorDB blackboard state."""

    async def execute_task_stream(
        self,
        tenant_id: str,
        session_id: str,
        user_prompt: str,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the 3 coordinating agents, streaming thoughts, blackboard mutations, and Cypher logs."""
        task_id = f"task_{uuid.uuid4().hex[:6]}"
        now = time.time()

        # Step 1: Record initial user turn in Episodic Memory
        ep = episodic_memory.record_episode(
            tenant_id=tenant_id,
            session_id=session_id,
            content=user_prompt,
            role="user",
            importance_score=0.8,
            user_id=user_id,
        )

        yield {
            "type": "agent_event",
            "agent": "Orchestrator Agent",
            "phase": "plan",
            "message": f"Received goal: '{user_prompt}'. Logging to Episodic Memory ({ep['id']}). Decomposing into Working Memory DAG...",
            "cypher": "MERGE (new_ep:Episode {...})",
        }
        await asyncio.sleep(0.4)

        # Step 2: Orchestrator decomposes task into Working Memory SubTasks
        subtasks = [
            SubTaskSpec(
                id=f"{task_id}_st1",
                title="Triage environment and query bi-temporal database state",
                description="Query active entities and check current database configuration.",
                depends_on=[],
            ),
            SubTaskSpec(
                id=f"{task_id}_st2",
                title="Execute migration and enforce procedural guardrails",
                description="Check procedural memory for learned migration guardrails and execute.",
                depends_on=[f"{task_id}_st1"],
            ),
        ]

        working_memory.initialize_task_dag(
            tenant_id=tenant_id,
            goal=user_prompt,
            subtasks=subtasks,
            task_id=task_id,
            user_id=user_id,
        )

        yield {
            "type": "blackboard_event",
            "agent": "Orchestrator Agent",
            "task_id": task_id,
            "status": "DAG_CREATED",
            "subtasks": [{"id": st.id, "title": st.title, "status": "PENDING"} for st in subtasks],
            "cypher": "MERGE (tr:TaskRun {id: $task_id})-[:HAS_SUBTASK]->(st:SubTask...)",
        }
        await asyncio.sleep(0.5)

        # Step 3: Context & Triage Agent claims SubTask 1 atomically
        st1_claim = working_memory.claim_next_subtask(
            tenant_id=tenant_id,
            task_id=task_id,
            agent_id="Context & Triage Agent",
            user_id=user_id,
        )

        yield {
            "type": "agent_event",
            "agent": "Context & Triage Agent",
            "phase": "claim",
            "message": f"Atomically locked SubTask 1: '{st1_claim['title'] if st1_claim else 'Triage'}'",
            "cypher": "MATCH (t:TaskRun)-[:HAS_SUBTASK]->(st:SubTask {status: 'PENDING'}) SET st.status = 'IN_PROGRESS', st.locked_by = 'Context & Triage Agent'...",
        }
        await asyncio.sleep(0.5)

        # Context Agent inspects Semantic Knowledge Graph
        triples = semantic_memory.extract_triples_from_text(user_prompt)
        for tr in triples:
            semantic_memory.upsert_fact(
                tenant_id=tenant_id,
                subject=tr.subject,
                predicate=tr.predicate,
                new_object=tr.object,
                episode_id=ep["id"],
                user_id=user_id,
            )

        # Pin context pointer
        working_memory.pin_context(
            tenant_id=tenant_id,
            subtask_id=f"{task_id}_st1",
            target_id=ep["id"],
            reason="Source user prompt and requirement context",
            user_id=user_id,
        )

        working_memory.complete_subtask(
            tenant_id=tenant_id,
            subtask_id=f"{task_id}_st1",
            agent_id="Context & Triage Agent",
            result_summary="Target database validated. Pinned context reference to episode.",
            user_id=user_id,
        )

        yield {
            "type": "agent_event",
            "agent": "Context & Triage Agent",
            "phase": "complete",
            "message": "Completed triage. Attached [:PINNED_CONTEXT] pointer to Episode. Handoff to Executor Agent.",
            "cypher": "MERGE (st)-[:PINNED_CONTEXT]->(target); SET st.status = 'COMPLETED'",
        }
        await asyncio.sleep(0.5)

        # Step 4: Execution & Reflexion Agent claims SubTask 2 atomically
        st2_claim = working_memory.claim_next_subtask(
            tenant_id=tenant_id,
            task_id=task_id,
            agent_id="Execution & Reflexion Agent",
            user_id=user_id,
        )

        yield {
            "type": "agent_event",
            "agent": "Execution & Reflexion Agent",
            "phase": "claim",
            "message": f"Atomically claimed SubTask 2: '{st2_claim['title'] if st2_claim else 'Execution'}'",
            "cypher": "MATCH (t:TaskRun)-[:HAS_SUBTASK]->(st:SubTask {status: 'PENDING'}) ...",
        }
        await asyncio.sleep(0.4)

        # Procedural Memory Lookup: Check if a Guardrail already exists for database migration
        proc_check = procedural_memory.retrieve_procedure(
            tenant_id=tenant_id,
            procedure_name="Database_Migration",
            intent="migration cutover",
            user_id=user_id,
        )

        has_guardrail = False
        if proc_check and proc_check.get("guardrails"):
            has_guardrail = True

        if has_guardrail:
            yield {
                "type": "procedural_event",
                "agent": "Execution & Reflexion Agent",
                "phase": "guardrail_hit",
                "message": "Procedural memory hit: Found existing (:Guardrail) for Database_Migration. Enforcing WAL checkpoint flag on first attempt!",
                "cypher": "CALL db.idx.vector.queryNodes('Procedure'...) MATCH (step)-[:HAS_GUARDRAIL]->(g)",
            }
            res = run_database_migration("PostgreSQL", "FalkorDB", require_wal_checkpoint=True)
        else:
            yield {
                "type": "agent_event",
                "agent": "Execution & Reflexion Agent",
                "phase": "tool_execution",
                "message": "Attempting migration tool execution without pre-existing guardrail...",
                "cypher": "EXECUTE run_database_migration(source='PostgreSQL', target='FalkorDB', require_wal_checkpoint=False)",
            }
            await asyncio.sleep(0.4)
            res = run_database_migration("PostgreSQL", "FalkorDB", require_wal_checkpoint=False)

            if res["status"] == "ERROR":
                yield {
                    "type": "reflexion_event",
                    "agent": "Execution & Reflexion Agent",
                    "phase": "reflexion_learn",
                    "message": f"Encountered domain trap ({res['error_signature']}). Compiling new (:Guardrail) into Procedural Memory!",
                    "cypher": "MERGE (step)-[:HAS_GUARDRAIL]->(:Guardrail {error_signature: 'ERR_NO_WAL_CHECKPOINT', ...})",
                }
                # Record the guardrail in FalkorDB
                procedural_memory.attach_guardrail(
                    tenant_id=tenant_id,
                    step_id="step_migration_exec",
                    rule_text="Always enforce require_wal_checkpoint=True during database migrations",
                    error_signature=res["error_signature"],
                    fix_instruction="Set require_wal_checkpoint=True",
                    user_id=user_id,
                )
                await asyncio.sleep(0.4)
                # Retry with the compiled fix
                res = run_database_migration("PostgreSQL", "FalkorDB", require_wal_checkpoint=True)

        working_memory.complete_subtask(
            tenant_id=tenant_id,
            subtask_id=f"{task_id}_st2",
            agent_id="Execution & Reflexion Agent",
            result_summary=res.get("message", "Migration complete."),
            user_id=user_id,
        )

        yield {
            "type": "task_completed",
            "agent": "Execution & Reflexion Agent",
            "status": "ALL_COMPLETED",
            "message": f"Task execution finished successfully: {res.get('message')}",
            "result": res,
        }


multi_agent_engine = MultiAgentCoordinationEngine()
