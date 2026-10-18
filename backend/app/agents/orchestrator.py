"""Cognitive Agent Engine deeply integrated with FalkorDB 4-tier memory."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings
from app.memory.episodic import episodic_memory
from app.memory.semantic import semantic_memory
from app.memory.working import working_memory, SubTaskSpec
from app.memory.procedural import procedural_memory
from app.agents.tools import (
    run_database_migration,
    query_database_config,
    query_knowledge_graph,
    search_memory_episodes,
)

logger = logging.getLogger("aegis.agents.cognitive")


class CognitiveAgentEngine:
    """Production cognitive agent executing against FalkorDB Episodic, Semantic, Working, and Procedural memory."""

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        """Constructs and caches the configured LLM client. Returns None if unavailable."""
        provider = settings.llm_provider.lower().strip()
        try:
            if provider == "gemini" and settings.gemini_api_key:
                from langchain_google_genai import ChatGoogleGenerativeAI
                # Use gemma-4-26b-a4b-it or gemini-3.8-flash for active Gemini API keys
                model = "gemini-flash-lite-latest"
                return ChatGoogleGenerativeAI(
                    model=model,
                    google_api_key=settings.gemini_api_key,
                    timeout=15.0,
                )
            elif provider == "openai" and settings.openai_api_key:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model="gpt-4o-mini",
                    api_key=settings.openai_api_key,
                    timeout=20.0,
                )
            elif provider == "anthropic" and settings.anthropic_api_key:
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(
                    model="claude-3-5-sonnet-20241022",
                    api_key=settings.anthropic_api_key,
                    timeout=20.0,
                )
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider '{provider}': {e}")
        return None

    def _extract_text_content(self, raw_content: Any) -> str:
        """Extracts text content from various LLM response formats."""
        if isinstance(raw_content, str):
            return raw_content.strip()
        elif isinstance(raw_content, list):
            texts = []
            for item in raw_content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text" and "text" in item:
                        texts.append(item["text"])
                    elif "content" in item:
                        texts.append(str(item["content"]))
            return "\n".join(texts).strip() or str(raw_content)
        return str(raw_content).strip()

    async def execute_task_stream(
        self,
        tenant_id: str,
        session_id: str,
        user_prompt: str,
        user_id: Optional[str] = None,
        parent_session_id: Optional[str] = None,
        isolation_mode: str = "tenant_shared",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the cognitive agent, streaming thoughts, memory retrievals, blackboard updates, and answer."""
        task_id = f"task_{uuid.uuid4().hex[:6]}"
        now = time.time()
        tenant = tenant_id or settings.default_tenant_id
        user = user_id or settings.default_user_id

        # -------------------------------------------------------------
        # Step 1: Record initial user turn in Episodic Memory
        # -------------------------------------------------------------
        ep = episodic_memory.record_episode(
            tenant_id=tenant,
            session_id=session_id,
            content=user_prompt,
            role="user",
            user_id=user,
            parent_session_id=parent_session_id,
            scope="private",
        )

        yield {
            "type": "agent_event",
            "agent": "Orchestrator Agent",
            "phase": "plan",
            "message": f"Received goal: '{user_prompt}' [Policy: {isolation_mode}]. Logged turn to Episodic Memory ({ep['id']}). Decomposing into Working Memory DAG...",
            "cypher": "MERGE (new_ep:Episode {...})",
            "isolation_mode": isolation_mode,
        }

        # -------------------------------------------------------------
        # Step 2: Initialize Working Memory TaskRun and SubTasks DAG
        # -------------------------------------------------------------
        st1_id = f"{task_id}_st1"
        st2_id = f"{task_id}_st2"
        st3_id = f"{task_id}_st3"

        subtasks = [
            SubTaskSpec(
                id=st1_id,
                title="Triage environment and query bi-temporal database state",
                description="Query active entities, recall episodic history, and retrieve associative semantic graph.",
                depends_on=[],
            ),
            SubTaskSpec(
                id=st2_id,
                title="Execute actions and enforce procedural guardrails",
                description="Check procedural memory for learned guardrails, execute actions, and perform Reflexion on failure.",
                depends_on=[st1_id],
            ),
            SubTaskSpec(
                id=st3_id,
                title="Synthesize grounded cognitive answer",
                description="Synthesize final response with LLM grounded in 4-tier FalkorDB memory.",
                depends_on=[st2_id],
            ),
        ]

        working_memory.initialize_task_dag(
            tenant_id=tenant,
            goal=user_prompt,
            subtasks=subtasks,
            task_id=task_id,
            user_id=user,
        )

        yield {
            "type": "blackboard_event",
            "agent": "Orchestrator Agent",
            "task_id": task_id,
            "status": "DAG_CREATED",
            "subtasks": [{"id": st.id, "title": st.title, "status": "PENDING"} for st in subtasks],
            "cypher": "MERGE (tr:TaskRun {id: $task_id})-[:HAS_SUBTASK]->(st:SubTask...)",
        }

        # -------------------------------------------------------------
        # Step 3: SubTask 1 - Triage, Episodic Recall, OpenIE, and HippoRAG
        # -------------------------------------------------------------
        st1_claim = working_memory.claim_next_subtask(
            tenant_id=tenant,
            task_id=task_id,
            agent_id="Context & Triage Agent",
            user_id=user,
        )

        yield {
            "type": "agent_event",
            "agent": "Context & Triage Agent",
            "phase": "claim",
            "message": f"Atomically locked SubTask 1: '{st1_claim['title'] if st1_claim else 'Triage'}'",
            "cypher": "MATCH (t:TaskRun)-[:HAS_SUBTASK]->(st:SubTask {status: 'PENDING'}) SET st.status = 'IN_PROGRESS'...",
        }

        # 3a. Park et al. 3-factor episodic retrieval
        historical_episodes = episodic_memory.retrieve_episodes(
            tenant_id=tenant,
            query=user_prompt,
            session_id=session_id,
            cross_session=True,
            top_k=3,
            user_id=user,
            isolation_mode=isolation_mode,
        )

        recalled_count = len(historical_episodes)
        top_score = historical_episodes[0]["composite_score"] if historical_episodes else 0.0

        yield {
            "type": "episodic_retrieval_event",
            "agent": "Context & Triage Agent",
            "phase": "retrieval",
            "message": f"Park et al. 3-factor retrieval matched {recalled_count} historical episode(s) (top composite: {top_score}) under policy '{isolation_mode}'.",
            "cypher": "CALL db.idx.vector.queryNodes('Episode'...) + MemoryBank decay + MemRL utility",
            "isolation_mode": isolation_mode,
            "retrieved_episodes": [
                {
                    "id": h["episode"]["id"],
                    "content": h["episode"].get("content", ""),
                    "composite_score": h["composite_score"],
                    "recency": h["recency_score"],
                    "importance": h["importance_score"],
                    "relevance": h["relevance_score"],
                }
                for h in historical_episodes
            ],
        }

        # 3b. OpenIE Fact Extraction & Semantic Upsert
        extracted_facts = semantic_memory.extract_facts(user_prompt)
        extracted_seeds: List[str] = []
        for tr in extracted_facts.triples:
            extracted_seeds.extend([tr.subject, tr.object])
            semantic_memory.upsert_fact(
                tenant_id=tenant,
                subject=tr.subject,
                predicate=tr.predicate,
                new_object=tr.object,
                episode_id=ep["id"],
                confidence=tr.confidence,
                cardinality=tr.cardinality,
                subject_type=tr.subject_type or "Entity",
                object_type=tr.object_type or "Entity",
                user_id=user,
            )

        # 3c. HippoRAG Associative Retrieval
        unique_seeds = list(dict.fromkeys(extracted_seeds)) or None
        hippo_res = semantic_memory.hipporag_retrieve(
            tenant_id=tenant,
            query=user_prompt,
            seed_entities=unique_seeds,
            top_k=3,
            user_id=user,
            isolation_mode=isolation_mode,
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

        # 3d. Pin context pointers to SubTask 1 in Working Memory
        # Pin source episode
        working_memory.pin_context(
            tenant_id=tenant,
            subtask_id=st1_id,
            target_id=ep["id"],
            reason="Source user prompt and requirement context",
            user_id=user,
        )

        # Pin top retrieved entities
        for top_ent in hippo_res.ranked_entities[:2]:
            working_memory.pin_context(
                tenant_id=tenant,
                subtask_id=st1_id,
                target_id=top_ent.name,
                reason=f"HippoRAG associative entity (score: {top_ent.degree_normalized_score})",
                user_id=user,
            )

        # Pin top grounded episodes
        for top_ge in hippo_res.ranked_episodes[:1]:
            if top_ge.episode_id != ep["id"]:
                working_memory.pin_context(
                    tenant_id=tenant,
                    subtask_id=st1_id,
                    target_id=top_ge.episode_id,
                    reason=f"HippoRAG grounded episode (score: {top_ge.grounded_score})",
                    user_id=user,
                )

        working_memory.complete_subtask(
            tenant_id=tenant,
            subtask_id=st1_id,
            agent_id="Context & Triage Agent",
            result_summary="Context triage and dual cognitive recall completed.",
            user_id=user,
            reward=1.0,
        )

        yield {
            "type": "agent_event",
            "agent": "Context & Triage Agent",
            "phase": "complete",
            "message": "Completed triage. Attached [:PINNED_CONTEXT] pointers to Episode and active Entity graph. Handoff to Executor Agent.",
            "cypher": "MERGE (st)-[:PINNED_CONTEXT]->(target); SET st.status = 'COMPLETED'",
        }

        # -------------------------------------------------------------
        # Step 4: SubTask 2 - Execution, Procedural Memory, and Reflexion
        # -------------------------------------------------------------
        st2_claim = working_memory.claim_next_subtask(
            tenant_id=tenant,
            task_id=task_id,
            agent_id="Execution & Reflexion Agent",
            user_id=user,
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

        # Check if the prompt triggers procedural execution or contains an operational action
        prompt_lower = user_prompt.lower()
        is_migration_task = any(k in prompt_lower for k in ("migrat", "database_migration", "postgres", "wal checkpoint"))

        action_result: Optional[Dict[str, Any]] = None

        if is_migration_task:
            # Procedural Memory Lookup: Check if a Guardrail exists for database migration
            proc_check = procedural_memory.retrieve_procedure(
                tenant_id=tenant,
                procedure_name="Database_Migration",
                intent="migration cutover",
                user_id=user,
            )

            if not proc_check:
                # Register base procedure and steps if not present
                procedural_memory.register_procedure(
                    tenant_id=tenant,
                    name="Database_Migration",
                    trigger_description="Automated database migration and cutover",
                    steps=[
                        {
                            "id": "step_schema_val",
                            "step_order": 1,
                            "tool_name": "query_database_config",
                            "param_schema": '{"db_name": "string"}',
                        },
                        {
                            "id": "step_migration_exec",
                            "step_order": 2,
                            "tool_name": "run_database_migration",
                            "param_schema": '{"source_db": "string", "target_db": "string", "require_wal_checkpoint": "boolean"}',
                        },
                    ],
                    user_id=user,
                )
                proc_check = procedural_memory.retrieve_procedure(
                    tenant_id=tenant,
                    procedure_name="Database_Migration",
                    intent="migration cutover",
                    user_id=user,
                )

            has_guardrail = bool(proc_check and proc_check.get("guardrails"))

            if has_guardrail:
                yield {
                    "type": "procedural_event",
                    "agent": "Execution & Reflexion Agent",
                    "phase": "guardrail_hit",
                    "message": "Procedural memory hit: Found existing (:Guardrail) for Database_Migration. Enforcing WAL checkpoint flag on first attempt!",
                    "cypher": "CALL db.idx.vector.queryNodes('Procedure'...) MATCH (step)-[:HAS_GUARDRAIL]->(g)",
                }
                action_result = run_database_migration("PostgreSQL", "FalkorDB", require_wal_checkpoint=True)
                procedural_memory.record_procedure_outcome(
                    tenant_id=tenant,
                    procedure_name="Database_Migration",
                    success=True,
                    user_id=user,
                )
            else:
                yield {
                    "type": "agent_event",
                    "agent": "Execution & Reflexion Agent",
                    "phase": "tool_execution",
                    "message": "Attempting migration tool execution without pre-existing guardrail...",
                    "cypher": "EXECUTE run_database_migration(source='PostgreSQL', target='FalkorDB', require_wal_checkpoint=False)",
                }
                res = run_database_migration("PostgreSQL", "FalkorDB", require_wal_checkpoint=False)

                if res.get("status") == "ERROR":
                    yield {
                        "type": "reflexion_event",
                        "agent": "Execution & Reflexion Agent",
                        "phase": "reflexion_learn",
                        "message": f"Encountered domain trap ({res['error_signature']}). Compiling new (:Guardrail) into Procedural Memory!",
                        "cypher": "MERGE (step)-[:HAS_GUARDRAIL]->(:Guardrail {error_signature: 'ERR_NO_WAL_CHECKPOINT', ...})",
                    }
                    # 1. Log failure episode to Episodic Memory
                    err_msg = res.get("error_message") or res.get("message") or "Unknown error"
                    fail_ep = episodic_memory.record_episode(
                        tenant_id=tenant,
                        session_id=session_id,
                        content=f"Tool failure in migration: {err_msg} (Error: {res.get('error_signature')})",
                        role="tool",
                        importance_score=0.90,
                        user_id=user,
                    )
                    # 2. Record failure in procedural memory
                    procedural_memory.record_procedure_outcome(
                        tenant_id=tenant,
                        procedure_name="Database_Migration",
                        success=False,
                        user_id=user,
                    )
                    # 3. Compile guardrail grounded in failure episode
                    procedural_memory.compile_guardrail_from_failure(
                        tenant_id=tenant,
                        step_id="step_migration_exec",
                        error_signature=res["error_signature"],
                        rule_text="Always enforce require_wal_checkpoint=True during database migrations",
                        fix_instruction="Set require_wal_checkpoint=True to avoid replication drift.",
                        episode_id=fail_ep["id"],
                        user_id=user,
                    )
                    # 4. Retry with the compiled fix
                    action_result = run_database_migration("PostgreSQL", "FalkorDB", require_wal_checkpoint=True)
                    if action_result.get("status") == "SUCCESS":
                        procedural_memory.record_procedure_outcome(
                            tenant_id=tenant,
                            procedure_name="Database_Migration",
                            success=True,
                            user_id=user,
                        )
                else:
                    action_result = res
        else:
            action_result = {"status": "SUCCESS", "message": "Procedural context evaluated."}

        working_memory.complete_subtask(
            tenant_id=tenant,
            subtask_id=st2_id,
            agent_id="Execution & Reflexion Agent",
            result_summary=action_result.get("message", "Execution complete."),
            user_id=user,
            reward=1.0 if action_result.get("status") == "SUCCESS" else -1.0,
        )

        yield {
            "type": "agent_event",
            "agent": "Execution & Reflexion Agent",
            "phase": "complete",
            "message": "SubTask 2 complete. Pinned execution outcomes and handoff to Response Agent.",
            "cypher": "SET st.status = 'COMPLETED'",
        }

        # -------------------------------------------------------------
        # Step 5: SubTask 3 - Grounded Response Generation with LLM
        # -------------------------------------------------------------
        st3_claim = working_memory.claim_next_subtask(
            tenant_id=tenant,
            task_id=task_id,
            agent_id="Response Agent",
            user_id=user,
        )

        # Build context prompt
        ep_context_text = "\n".join([
            f"- [{h['episode'].get('role', 'user')}]: {h['episode'].get('content', '')}"
            for h in historical_episodes
        ]) or "No previous episodes."

        hippo_entities_text = ", ".join([
            f"{e.name} (type: {getattr(e, 'type', 'Entity')})" for e in hippo_res.ranked_entities
        ]) or "None"

        active_edges_text = "\n".join([
            f"- {edge.get('source', '')} -[{edge.get('predicate', '')}]-> {edge.get('target', '')}"
            if isinstance(edge, dict)
            else f"- {getattr(edge, 'source', '')} -[{getattr(edge, 'predicate', '')}]-> {getattr(edge, 'target', '')}"
            for edge in hippo_res.active_subgraph_edges
        ]) or "None"

        action_summary_text = action_result.get("message", "") if action_result else ""

        system_prompt = (
            "You are AegisGraph Cognitive Assistant, an AI agent with persistent multi-tenant memory "
            "backed by FalkorDB (Episodic, Semantic, Working, and Procedural Memory).\n"
            "Answer the user query accurately and concisely using the retrieved memory context.\n\n"
            f"ACTIVE MEMORY ISOLATION POLICY: {isolation_mode}\n"
            f"CURRENT USER CONTEXT: {user}\n\n"
            f"RECALLED EPISODIC INTERACTIONS:\n{ep_context_text}\n\n"
            f"RECALLED SEMANTIC ENTITIES:\n{hippo_entities_text}\n\n"
            f"ACTIVE KNOWLEDGE GRAPH RELATIONS:\n{active_edges_text}\n\n"
            f"OPERATIONAL ACTION RESULTS:\n{action_summary_text}\n"
        )

        llm = self._get_llm()

        # User Instruction: If model is not available, return an error. No fake answers.
        if llm is None:
            err_msg = (
                f"LLM model is not available or configured (provider: '{settings.llm_provider}'). "
                "Cannot generate response without an available model. Please set a valid LLM_PROVIDER and API key."
            )
            working_memory.fail_subtask(
                tenant_id=tenant,
                subtask_id=st3_id,
                agent_id="Response Agent",
                error_message=err_msg,
                user_id=user,
            )
            yield {
                "type": "error",
                "status": "ERROR",
                "message": err_msg,
                "agent": "Response Agent",
                "isolation_mode": isolation_mode,
            }
            return

        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
            llm_response = await asyncio.to_thread(llm.invoke, messages)
            answer_text = self._extract_text_content(llm_response.content)
        except Exception as e:
            err_msg = f"LLM model generation failed: {e}"
            logger.error(err_msg)
            working_memory.fail_subtask(
                tenant_id=tenant,
                subtask_id=st3_id,
                agent_id="Response Agent",
                error_message=err_msg,
                user_id=user,
            )
            yield {
                "type": "error",
                "status": "ERROR",
                "message": err_msg,
                "agent": "Response Agent",
                "isolation_mode": isolation_mode,
            }
            return

        # Record agent turn in Episodic Memory
        agent_ep = episodic_memory.record_episode(
            tenant_id=tenant,
            session_id=session_id,
            content=answer_text,
            role="agent",
            user_id=user,
            scope="private",
        )

        working_memory.complete_subtask(
            tenant_id=tenant,
            subtask_id=st3_id,
            agent_id="Response Agent",
            result_summary="Grounded cognitive response generated and recorded.",
            user_id=user,
            reward=1.0,
        )

        yield {
            "type": "agent_answer",
            "agent": "Cognitive Agent",
            "answer": answer_text,
            "episode_id": agent_ep["id"],
            "isolation_mode": isolation_mode,
        }

        yield {
            "type": "task_completed",
            "agent": "Execution & Reflexion Agent",
            "status": "ALL_COMPLETED",
            "message": f"Task execution finished successfully: {action_summary_text or 'Answer generated.'}",
            "result": action_result,
            "answer": answer_text,
            "task_id": task_id,
            "isolation_mode": isolation_mode,
        }


multi_agent_engine = CognitiveAgentEngine()
