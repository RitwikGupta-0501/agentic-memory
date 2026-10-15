"""Centralized OpenCypher query catalog for AegisGraph.

All memory operations and multi-agent coordination steps execute explicit,
parameterized OpenCypher queries documented in this catalog for compliance
with Hackathon Rule #10 and Rule #3.
"""

from typing import Dict, Any

# ==========================================
# 1. EPISODIC MEMORY & SESSION TOPOLOGY QUERIES (Phase 1 & 2)
# ==========================================

SESSION_ENSURE_AND_LINK = """
MERGE (s:Session {id: $session_id})
ON CREATE SET
    s.tenant_id = $tenant_id,
    s.user_id = $user_id,
    s.created_at = $now,
    s.updated_at = $now,
    s.episode_count = 0
ON MATCH SET
    s.updated_at = $now
WITH s
OPTIONAL MATCH (parent:Session {id: $parent_session_id})
WHERE $parent_session_id IS NOT NULL AND parent.id <> s.id
FOREACH (_ IN CASE WHEN parent IS NOT NULL THEN [1] ELSE [] END |
    MERGE (s)-[:PARENT_SESSION {linked_at: $now}]->(parent)
)
RETURN s
"""

ATOMIC_EPISODE_APPEND = """
MERGE (s:Session {id: $session_id})
ON CREATE SET
    s.tenant_id = $tenant_id,
    s.user_id = $user_id,
    s.created_at = $timestamp,
    s.updated_at = $timestamp,
    s.episode_count = 0
WITH s
OPTIONAL MATCH (parent:Session {id: $parent_session_id})
WHERE $parent_session_id IS NOT NULL AND parent.id <> s.id
FOREACH (_ IN CASE WHEN parent IS NOT NULL THEN [1] ELSE [] END |
    MERGE (s)-[:PARENT_SESSION]->(parent)
)
WITH s
OPTIONAL MATCH (s)-[old_tail_rel:SESSION_TAIL]->(prev_ep:Episode)
DELETE old_tail_rel
CREATE (new_ep:Episode {
    id: $episode_id,
    session_id: $session_id,
    tenant_id: $tenant_id,
    role: $role,
    actor_id: $actor_id,
    content: $content,
    structured_payload: $structured_payload,
    status: $status,
    importance_score: $importance_score,
    utility_score: $utility_score,
    vcache_threshold: $vcache_threshold,
    access_count: 0,
    last_accessed: $timestamp,
    timestamp: $timestamp,
    token_count: $token_count,
    embedding_model: $embedding_model,
    embedding_dim: $embedding_dim,
    embedding: vecf32($embedding),
    archived: false
})
CREATE (s)-[:SESSION_TAIL]->(new_ep)
SET s.updated_at = $timestamp,
    s.episode_count = coalesce(s.episode_count, 0) + 1
FOREACH (_ IN CASE WHEN prev_ep IS NULL THEN [1] ELSE [] END |
    MERGE (s)-[:SESSION_HEAD]->(new_ep)
)
FOREACH (_ IN CASE WHEN prev_ep IS NOT NULL THEN [1] ELSE [] END |
    CREATE (prev_ep)-[:NEXT_EPISODE {
        delta_ms: round(($timestamp - prev_ep.timestamp) * 1000.0)
    }]->(new_ep)
)
RETURN new_ep.id AS episode_id, prev_ep.id AS previous_episode_id, s.episode_count AS seq_num
"""

MULTI_SESSION_LINEAGE_QUERY = """
MATCH (curr:Session {id: $session_id})
OPTIONAL MATCH path = (curr)-[:PARENT_SESSION*0..5]->(anc:Session)
WITH anc ORDER BY anc.created_at ASC
OPTIONAL MATCH (anc)-[:SESSION_HEAD]->(head:Episode)
OPTIONAL MATCH (anc)-[:SESSION_TAIL]->(tail:Episode)
RETURN anc.id AS session_id,
       anc.created_at AS created_at,
       anc.episode_count AS episode_count,
       head.id AS head_episode_id,
       tail.id AS tail_episode_id,
       tail.content AS tail_summary
"""

EPISODE_INSERT_AND_CHAIN = """
MATCH (last_ep:Episode {session_id: $session_id})
WHERE NOT (last_ep)-[:NEXT_EPISODE]->()
MERGE (new_ep:Episode {id: $episode_id})
ON CREATE SET
    new_ep.session_id = $session_id,
    new_ep.tenant_id = $tenant_id,
    new_ep.content = $content,
    new_ep.role = $role,
    new_ep.actor_id = $actor_id,
    new_ep.status = $status,
    new_ep.structured_payload = $structured_payload,
    new_ep.importance_score = $importance_score,
    new_ep.utility_score = $utility_score,
    new_ep.vcache_threshold = $vcache_threshold,
    new_ep.access_count = $access_count,
    new_ep.last_accessed = $last_accessed,
    new_ep.timestamp = $timestamp,
    new_ep.token_count = $token_count,
    new_ep.embedding_model = $embedding_model,
    new_ep.embedding_dim = $embedding_dim,
    new_ep.embedding = vecf32($embedding),
    new_ep.archived = false
CREATE (last_ep)-[:NEXT_EPISODE {latency_ms: $latency_ms}]->(new_ep)
RETURN new_ep
"""

EPISODE_INSERT_ROOT = """
MERGE (new_ep:Episode {id: $episode_id})
ON CREATE SET
    new_ep.session_id = $session_id,
    new_ep.tenant_id = $tenant_id,
    new_ep.content = $content,
    new_ep.role = $role,
    new_ep.actor_id = $actor_id,
    new_ep.status = $status,
    new_ep.structured_payload = $structured_payload,
    new_ep.importance_score = $importance_score,
    new_ep.utility_score = $utility_score,
    new_ep.vcache_threshold = $vcache_threshold,
    new_ep.access_count = $access_count,
    new_ep.last_accessed = $last_accessed,
    new_ep.timestamp = $timestamp,
    new_ep.token_count = $token_count,
    new_ep.embedding_model = $embedding_model,
    new_ep.embedding_dim = $embedding_dim,
    new_ep.embedding = vecf32($embedding),
    new_ep.archived = false
RETURN new_ep
"""

EPISODE_VECTOR_SEARCH_CANDIDATES = """
CALL db.idx.vector.queryNodes('Episode', 'embedding', $candidate_limit, vecf32($query_vec))
YIELD node AS ep, score AS distance
WITH ep, (1.0 - distance) AS similarity_score
WHERE (ep.session_id = $session_id OR $cross_session = true)
  AND (ep.embedding_model = $current_model OR $current_model IS NULL)
  AND similarity_score >= coalesce(ep.vcache_threshold, 0.50)
RETURN ep, similarity_score
ORDER BY similarity_score DESC
"""

GRAPH_METADATA_GET = """
MATCH (m:GraphMetadata)
RETURN m.active_embedding_model AS active_model,
       m.active_dimension AS active_dimension,
       m.last_reindexed_at AS last_reindexed_at
LIMIT 1
"""

GRAPH_METADATA_UPSERT = """
MERGE (m:GraphMetadata {tenant_id: $tenant_id})
SET m.active_embedding_model = $model,
    m.active_dimension = $dim,
    m.updated_at = $now
RETURN m
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
WHERE NOT (st)-[:DEPENDS_ON]->(:SubTask {status: 'PENDING'})
  AND NOT (st)-[:DEPENDS_ON]->(:SubTask {status: 'IN_PROGRESS'})
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
    "EPISODE_VECTOR_SEARCH_CANDIDATES": EPISODE_VECTOR_SEARCH_CANDIDATES,
    "GRAPH_METADATA_GET": GRAPH_METADATA_GET,
    "GRAPH_METADATA_UPSERT": GRAPH_METADATA_UPSERT,
    "SESSION_ENSURE_AND_LINK": SESSION_ENSURE_AND_LINK,
    "ATOMIC_EPISODE_APPEND": ATOMIC_EPISODE_APPEND,
    "MULTI_SESSION_LINEAGE_QUERY": MULTI_SESSION_LINEAGE_QUERY,
}
