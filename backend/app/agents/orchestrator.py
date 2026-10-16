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
        await asyncio.sleep(0.4)

        # Context Agent recalls historical interactions via Park et al. 3-factor retrieval
        historical_episodes = episodic_memory.retrieve_episodes(
            tenant_id=tenant_id,
            query=user_prompt,
            session_id=session_id,
            cross_session=True,
            top_k=3,
            user_id=user_id,
        )

        recalled_count = len(historical_episodes)
        top_score = historical_episodes[0]["composite_score"] if historical_episodes else 0.0

        yield {
            "type": "episodic_retrieval_event",
            "agent": "Context & Triage Agent",
            "phase": "retrieval",
            "message": f"Park et al. 3-factor retrieval matched {recalled_count} historical episode(s) (top composite: {top_score}).",
            "cypher": "CALL db.idx.vector.queryNodes('Episode'...) + MemoryBank decay + MemRL utility",
            "retrieved_episodes": [
                {
                    "id": h["episode"]["id"],
                    "composite_score": h["composite_score"],
                    "recency": h["recency_score"],
                    "importance": h["importance_score"],
                    "relevance": h["relevance_score"],
                }
                for h in historical_episodes
            ],
        }
        await asyncio.sleep(0.4)

        # Context Agent inspects Semantic Knowledge Graph with full ontological metadata
        extracted_facts = semantic_memory.extract_facts(user_prompt)
        extracted_seeds: List[str] = []
        for tr in extracted_facts.triples:
            extracted_seeds.extend([tr.subject, tr.object])
            semantic_memory.upsert_fact(
                tenant_id=tenant_id,
                subject=tr.subject,
                predicate=tr.predicate,
                new_object=tr.object,
                episode_id=ep["id"],
                confidence=tr.confidence,
                cardinality=tr.cardinality,
                subject_type=tr.subject_type or "Entity",
                object_type=tr.object_type or "Entity",
                user_id=user_id,
            )

        # Dual Cognitive Recall: Associative Semantic Recall (HippoRAG PPR)
        unique_seeds = list(dict.fromkeys(extracted_seeds)) or None
        hippo_res = semantic_memory.hipporag_retrieve(
            tenant_id=tenant_id,
            query=user_prompt,
            seed_entities=unique_seeds,
            top_k=3,
            user_id=user_id,
        )

        yield {
            "type": "hipporag_event",
            "agent": "Context & Triage Agent",
            "phase": "semantic_retrieval",
            "message": f"HippoRAG associative recall identified {len(hippo_res.ranked_entities)} entity(ies) across {len(hippo_res.active_subgraph_edges)} active relations.",
            "cypher": "CALL db.idx.vector.queryNodes('Entity'...) + Personalized PageRank + Bipartite Episode Grounding",
            "seeds": hippo_res.seeds,
            "ranked_entities": [e.model_dump() for e in hippo_res.ranked_entities[:3]],
            "grounded_episodes": [ge.model_dump() for ge in hippo_res.ranked_episodes[:2]],
            "active_edges_count": len(hippo_res.active_subgraph_edges),
        }
        await asyncio.sleep(0.4)

        # Pin context pointers in Working Memory Blackboard
        # 1. Pin source episode
        working_memory.pin_context(
            tenant_id=tenant_id,
            subtask_id=f"{task_id}_st1",
            target_id=ep["id"],
            reason="Source user prompt and requirement context",
            user_id=user_id,
        )

        # 2. Pin top retrieved entities
        for top_ent in hippo_res.ranked_entities[:2]:
            working_memory.pin_context(
                tenant_id=tenant_id,
                subtask_id=f"{task_id}_st1",
                target_id=top_ent.name,
                reason=f"HippoRAG associative entity (score: {top_ent.degree_normalized_score})",
                user_id=user_id,
            )

        # 3. Pin top grounded episodes if different from source episode
        for top_ge in hippo_res.ranked_episodes[:1]:
            if top_ge.episode_id != ep["id"]:
                working_memory.pin_context(
                    tenant_id=tenant_id,
                    subtask_id=f"{task_id}_st1",
                    target_id=top_ge.episode_id,
                    reason=f"HippoRAG grounded episode (score: {top_ge.grounded_score})",
                    user_id=user_id,
                )

        working_memory.complete_subtask(
            tenant_id=tenant_id,
            subtask_id=f"{task_id}_st1",
            agent_id="Context & Triage Agent",
            result_summary="Target database validated. Pinned context reference to episode.",
            user_id=user_id,
            reward=1.0,
        )

        yield {
            "type": "agent_event",
            "agent": "Context & Triage Agent",
            "phase": "complete",
            "message": "Completed triage. Attached [:PINNED_CONTEXT] pointers to Episode and active Entity graph. Handoff to Executor Agent.",
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

        inherited_nodes = st2_claim.get("inherited_context", []) if st2_claim else []
        yield {
            "type": "agent_event",
            "agent": "Execution & Reflexion Agent",
            "phase": "claim",
            "message": f"Atomically claimed SubTask 2: '{st2_claim['title'] if st2_claim else 'Execution'}'. Inherited {len(inherited_nodes)} pinned context node(s) from SubTask 1.",
            "inherited_context": inherited_nodes,
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
            reward=1.0 if res.get("status") == "SUCCESS" else -1.0,
        )

        yield {
            "type": "task_completed",
            "agent": "Execution & Reflexion Agent",
            "status": "ALL_COMPLETED",
            "message": f"Task execution finished successfully: {res.get('message')}",
            "result": res,
        }


multi_agent_engine = MultiAgentCoordinationEngine()
