"""Centralized OpenCypher query catalog for AegisGraph.

All memory operations and multi-agent coordination steps execute explicit,
parameterized OpenCypher queries documented in this catalog for compliance
with Hackathon Rule #10 and Rule #3.
"""

from typing import Dict, Any

# ==========================================
# 1. EPISODIC MEMORY QUERIES (Priority 1A)
# ==========================================

EPISODE_INSERT_AND_CHAIN = """
MATCH (last_ep:Episode {session_id: $session_id})
WHERE NOT (last_ep)-[:NEXT_EPISODE]->()
MERGE (new_ep:Episode {
    id: $episode_id,
    session_id: $session_id,
    content: $content,
    role: $role,
    importance_score: $importance_score,
    timestamp: $timestamp
})
CREATE (last_ep)-[:NEXT_EPISODE {latency_ms: $latency_ms}]->(new_ep)
RETURN new_ep
"""

EPISODE_INSERT_ROOT = """
MERGE (new_ep:Episode {
    id: $episode_id,
    session_id: $session_id,
    content: $content,
    role: $role,
    importance_score: $importance_score,
    timestamp: $timestamp
})
RETURN new_ep
"""

# ==========================================
# 2. SEMANTIC MEMORY & BI-TEMPORAL QUERIES (Priority 1B)
# ==========================================

BITEMPORAL_INVALIDATE_AND_UPSERT = """
MATCH (s:Entity {name: $subject})-[old_r:RELATES_TO {predicate: $predicate}]->(old_o:Entity)
WHERE old_r.valid_to IS NULL AND old_o.name <> $new_object
SET old_r.valid_to = $now, old_r.invalidated_by_episode = $episode_id
WITH count(old_r) AS invalidated_count
MERGE (s:Entity {name: $subject})
MERGE (new_o:Entity {name: $new_object})
MERGE (ep:Episode {id: $episode_id})
CREATE (s)-[new_r:RELATES_TO {
    predicate: $predicate,
    valid_from: $now,
    valid_to: NULL,
    confidence: $confidence,
    source_episode: $episode_id
}]->(new_o)
CREATE (new_o)-[:DERIVED_FROM]->(ep)
RETURN invalidated_count, new_r
"""

HIPPORAG_HYBRID_RETRIEVAL = """
MATCH (seed:Entity)
WHERE seed.name IN $seed_entities
OPTIONAL MATCH path = (seed)-[r:RELATES_TO*1..2]-(neighbor:Entity)
WHERE all(edge IN relationships(path) WHERE edge.valid_to IS NULL)
OPTIONAL MATCH (neighbor)-[:DERIVED_FROM]->(ep:Episode)
RETURN seed, collect(path) AS paths, collect(ep) AS episodes
"""

# ==========================================
# 3. WORKING MEMORY & BLACKBOARD COORDINATION (Priority 2)
# ==========================================

TASK_DAG_CREATE = """
MERGE (tr:TaskRun {
    id: $task_id,
    goal: $goal,
    created_at: $now,
    status: 'ACTIVE'
})
RETURN tr
"""

SUBTASK_CREATE = """
MATCH (tr:TaskRun {id: $task_id})
MERGE (st:SubTask {
    id: $subtask_id,
    title: $title,
    description: $description,
    status: 'PENDING',
    created_at: $now
})
MERGE (tr)-[:HAS_SUBTASK]->(st)
RETURN st
"""

SUBTASK_ADD_DEPENDENCY = """
MATCH (st:SubTask {id: $subtask_id})
MATCH (dep:SubTask {id: $dep_id})
MERGE (st)-[:DEPENDS_ON]->(dep)
RETURN st, dep
"""

WORKING_MEMORY_ATOMIC_CLAIM = """
MATCH (t:TaskRun {id: $task_id})-[:HAS_SUBTASK]->(st:SubTask {status: 'PENDING'})
WHERE NOT EXISTS {
    MATCH (st)-[:DEPENDS_ON]->(dep:SubTask)
    WHERE dep.status <> 'COMPLETED'
}
WITH st LIMIT 1
SET st.status = 'IN_PROGRESS',
    st.locked_by = $agent_id,
    st.claimed_at = $now
WITH st
OPTIONAL MATCH (st)-[:DEPENDS_ON]->(parent:SubTask)-[:PINNED_CONTEXT]->(ctx)
RETURN st, collect(ctx) AS inherited_context_nodes
"""

WORKING_MEMORY_COMPLETE_SUBTASK = """
MATCH (st:SubTask {id: $subtask_id, locked_by: $agent_id})
SET st.status = 'COMPLETED',
    st.completed_at = $now,
    st.result_summary = $result_summary
RETURN st
"""

WORKING_MEMORY_PIN_CONTEXT = """
MATCH (st:SubTask {id: $subtask_id})
MATCH (target) WHERE target.id = $target_id OR target.name = $target_id
MERGE (st)-[r:PINNED_CONTEXT {relevance_reason: $reason, pinned_at: $now}]->(target)
RETURN r
"""

# ==========================================
# 4. PROCEDURAL MEMORY & REFLEXION (Priority 3)
# ==========================================

PROCEDURE_CREATE = """
MERGE (p:Procedure {
    id: $procedure_id,
    name: $name,
    trigger_description: $trigger_description,
    success_count: 0,
    fail_count: 0
})
RETURN p
"""

ACTION_STEP_APPEND = """
MATCH (p:Procedure {id: $procedure_id})
MERGE (step:ActionStep {
    id: $step_id,
    step_order: $step_order,
    tool_name: $tool_name,
    param_schema: $param_schema
})
WITH p, step
OPTIONAL MATCH (p)-[:FIRST_STEP]->(first:ActionStep)
FOREACH (_ IN CASE WHEN first IS NULL AND $step_order = 1 THEN [1] ELSE [] END |
    CREATE (p)-[:FIRST_STEP]->(step)
)
RETURN step
"""

PROCEDURAL_RETRIEVAL_WITH_GUARDRAILS = """
MATCH (proc:Procedure)
WHERE proc.name = $procedure_name OR proc.trigger_description CONTAINS $intent
OPTIONAL MATCH path = (proc)-[:FIRST_STEP|NEXT_STEP*1..10]->(step:ActionStep)
OPTIONAL MATCH (step)-[:HAS_GUARDRAIL]->(g:Guardrail)
RETURN proc, nodes(path) AS ordered_steps, collect(g) AS active_guardrails
"""

PROCEDURAL_GUARDRAIL_ATTACH = """
MATCH (step:ActionStep {id: $step_id})
MERGE (g:Guardrail {
    id: $guardrail_id,
    rule_text: $rule_text,
    error_signature: $error_signature,
    fix_instruction: $fix_instruction,
    created_at: $now
})
MERGE (step)-[:HAS_GUARDRAIL]->(g)
RETURN g
"""

# ==========================================
# 5. CONSOLIDATION & SLOW-STREAM DECAY (Priority 4)
# ==========================================

CONSOLIDATION_RETENTION_QUERY = """
MATCH (n)
WHERE n:Entity OR n:Episode
OPTIONAL MATCH (n)-[r]-()
WITH n, count(r) AS degree
RETURN n, degree
"""

CONSOLIDATION_INSIGHT_CREATE = """
MERGE (ci:ConsolidatedInsight {
    id: $insight_id,
    summary: $summary,
    created_at: $now
})
WITH ci
UNWIND $episode_ids AS ep_id
MATCH (ep:Episode {id: ep_id})
SET ep.archived = true
CREATE (ci)-[:CONSOLIDATES]->(ep)
RETURN ci
"""

# ==========================================
# 6. VISUALIZATION & AUDIT QUERIES
# ==========================================

VISUALIZE_ALL_GRAPH = """
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT {
    id: id(r),
    source: id(n),
    target: id(m),
    type: type(r),
    valid_from: r.valid_from,
    valid_to: r.valid_to,
    predicate: r.predicate,
    status: r.status
}) AS edges
"""

VISUALIZE_ACTIVE_GRAPH = """
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
WHERE r.valid_to IS NULL
RETURN collect(DISTINCT n) AS nodes, collect(DISTINCT {
    id: id(r),
    source: id(n),
    target: id(m),
    type: type(r),
    valid_from: r.valid_from,
    valid_to: r.valid_to,
    predicate: r.predicate,
    status: r.status
}) AS edges
"""

CYPHER_CATALOG: Dict[str, str] = {
    "EPISODE_INSERT_AND_CHAIN": EPISODE_INSERT_AND_CHAIN,
    "EPISODE_INSERT_ROOT": EPISODE_INSERT_ROOT,
    "BITEMPORAL_INVALIDATE_AND_UPSERT": BITEMPORAL_INVALIDATE_AND_UPSERT,
    "HIPPORAG_HYBRID_RETRIEVAL": HIPPORAG_HYBRID_RETRIEVAL,
    "TASK_DAG_CREATE": TASK_DAG_CREATE,
    "SUBTASK_CREATE": SUBTASK_CREATE,
    "SUBTASK_ADD_DEPENDENCY": SUBTASK_ADD_DEPENDENCY,
    "WORKING_MEMORY_ATOMIC_CLAIM": WORKING_MEMORY_ATOMIC_CLAIM,
    "WORKING_MEMORY_COMPLETE_SUBTASK": WORKING_MEMORY_COMPLETE_SUBTASK,
    "WORKING_MEMORY_PIN_CONTEXT": WORKING_MEMORY_PIN_CONTEXT,
    "PROCEDURE_CREATE": PROCEDURE_CREATE,
    "ACTION_STEP_APPEND": ACTION_STEP_APPEND,
    "PROCEDURAL_RETRIEVAL_WITH_GUARDRAILS": PROCEDURAL_RETRIEVAL_WITH_GUARDRAILS,
    "PROCEDURAL_GUARDRAIL_ATTACH": PROCEDURAL_GUARDRAIL_ATTACH,
    "CONSOLIDATION_RETENTION_QUERY": CONSOLIDATION_RETENTION_QUERY,
    "CONSOLIDATION_INSIGHT_CREATE": CONSOLIDATION_INSIGHT_CREATE,
    "VISUALIZE_ALL_GRAPH": VISUALIZE_ALL_GRAPH,
    "VISUALIZE_ACTIVE_GRAPH": VISUALIZE_ACTIVE_GRAPH,
}
