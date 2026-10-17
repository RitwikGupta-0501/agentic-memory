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

EPISODE_UTILITY_FEEDBACK_UPDATE = """
MATCH (ep:Episode {id: $episode_id})
WITH ep, coalesce(ep.utility_score, ep.importance_score, 0.5) AS old_u,
     coalesce(ep.vcache_threshold, 0.78) AS old_tau
WITH ep, old_tau,
     round((old_u + $alpha * ($reward - old_u)) * 1000.0) / 1000.0 AS raw_u
SET ep.access_count = coalesce(ep.access_count, 0) + 1,
    ep.last_accessed = $now,
    ep.utility_score = CASE
        WHEN raw_u < 0.05 THEN 0.05
        WHEN raw_u > 1.00 THEN 1.00
        ELSE raw_u
    END,
    ep.vcache_threshold = CASE
        WHEN $reward > 0 THEN CASE WHEN old_tau - 0.02 < 0.50 THEN 0.50 ELSE round((old_tau - 0.02) * 100.0) / 100.0 END
        ELSE CASE WHEN old_tau + 0.05 > 0.98 THEN 0.98 ELSE round((old_tau + 0.05) * 100.0) / 100.0 END
    END
RETURN ep.id AS episode_id,
       ep.utility_score AS new_utility,
       ep.vcache_threshold AS new_threshold,
       ep.access_count AS access_count
"""

MEMORY_UTILITY_FEEDBACK_UPDATE = """
MATCH (st:SubTask {id: $subtask_id})-[:PINNED_CONTEXT]->(m)
WITH m, coalesce(m.utility_score, m.importance_score, 0.5) AS old_u,
     coalesce(m.vcache_threshold, 0.78) AS old_tau
WITH m, old_tau,
     round((old_u + $alpha * ($reward - old_u)) * 1000.0) / 1000.0 AS raw_u
SET m.access_count = coalesce(m.access_count, 0) + 1,
    m.last_accessed = $now,
    m.utility_score = CASE
        WHEN raw_u < 0.05 THEN 0.05
        WHEN raw_u > 1.00 THEN 1.00
        ELSE raw_u
    END,
    m.vcache_threshold = CASE
        WHEN $reward > 0 THEN CASE WHEN old_tau - 0.02 < 0.50 THEN 0.50 ELSE round((old_tau - 0.02) * 100.0) / 100.0 END
        ELSE CASE WHEN old_tau + 0.05 > 0.98 THEN 0.98 ELSE round((old_tau + 0.05) * 100.0) / 100.0 END
    END
RETURN coalesce(m.id, m.name) AS id,
       m.utility_score AS new_utility,
       m.vcache_threshold AS new_threshold,
       m.access_count AS access_count
"""

# DEPRECATED: Retained for backward compatibility; superseded by ATOMIC_EPISODE_APPEND
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

# DEPRECATED: Retained for backward compatibility; superseded by ATOMIC_EPISODE_APPEND
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

EPISODE_HYBRID_CANDIDATE_FETCH = """
CALL db.idx.vector.queryNodes('Episode', 'embedding', $candidate_limit, vecf32($query_vec))
YIELD node AS ep, score AS distance
WITH ep, CASE 
    WHEN (1.0 - distance) < 0.0 THEN 0.0 
    WHEN (1.0 - distance) > 1.0 THEN 1.0 
    ELSE (1.0 - distance) 
END AS raw_score
WHERE coalesce(ep.archived, false) = false
  AND ($cross_session = true OR ep.session_id = $session_id)
RETURN ep, raw_score
"""

EPISODE_FALLBACK_SCAN_FETCH = """
MATCH (ep:Episode)
WHERE coalesce(ep.archived, false) = false
  AND ($cross_session = true OR ep.session_id = $session_id)
RETURN ep, 0.5 AS raw_score
ORDER BY ep.timestamp DESC
LIMIT $candidate_limit
"""

EPISODE_BATCH_RECALL_TOUCH_AND_EXPAND = """
UNWIND $episode_ids AS ep_id
MATCH (ep:Episode {id: ep_id})
SET ep.access_count = coalesce(ep.access_count, 0) + CASE WHEN $touch = true THEN 1 ELSE 0 END,
    ep.last_accessed = CASE WHEN $touch = true THEN $now ELSE coalesce(ep.last_accessed, ep.timestamp) END
WITH ep
OPTIONAL MATCH (ctx)-[r:DERIVED_FROM|PINNED_CONTEXT|TRIGGERED_BY|CONSOLIDATES]->(ep)
RETURN ep.id AS episode_id,
       ep.access_count AS access_count,
       ep.last_accessed AS last_accessed,
       collect(DISTINCT {
           label: labels(ctx)[0],
           id: coalesce(ctx.id, ctx.name),
           rel_type: type(r)
       }) AS provenance_links
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

# DEPRECATED: Retained for backward compatibility; superseded by SEMANTIC_PROVENANCE_UPSERT_AND_LINK
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
CREATE (s)-[:MENTIONED_IN {timestamp: $now}]->(ep)
CREATE (new_o)-[:MENTIONED_IN {timestamp: $now}]->(ep)
CREATE (ep)-[:EXTRACTED_FACT {timestamp: $now, predicate: $predicate}]->(new_o)
RETURN invalidated_count, new_r
"""

SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING = """
MERGE (e:Entity {name: $name})
ON CREATE SET
    e.id = $id,
    e.canonical_name = $canonical_name,
    e.type = $type,
    e.aliases = [$name],
    e.description = $description,
    e.created_at = $now,
    e.updated_at = $now,
    e.embedding = CASE WHEN $embedding IS NOT NULL THEN vecf32($embedding) ELSE NULL END
ON MATCH SET
    e.updated_at = $now,
    e.type = coalesce($type, e.type),
    e.embedding = CASE WHEN $embedding IS NOT NULL THEN vecf32($embedding) ELSE e.embedding END
RETURN e.id AS id, e.name AS name, e.canonical_name AS canonical_name, e.type AS type
"""

SEMANTIC_PROVENANCE_UPSERT_AND_LINK = """
// 1. Invalidate conflicting functional single-valued active relations if requested
OPTIONAL MATCH (s_prev:Entity {name: $subject})-[old_r:RELATES_TO {predicate: $predicate}]->(old_o:Entity)
WHERE old_r.valid_to IS NULL 
  AND $cardinality = 'SINGLE' 
  AND old_o.name <> $object
SET old_r.valid_to = $now,
    old_r.invalidated_by_episode = $episode_id
WITH count(old_r) AS invalidated_count, collect(DISTINCT old_o) AS invalidated_objects

// 2. Ensure Subject Entity exists
MERGE (s:Entity {name: $subject})
ON CREATE SET
    s.id = $subject_id,
    s.canonical_name = $subject_canonical,
    s.type = $subject_type,
    s.aliases = [$subject],
    s.created_at = $now,
    s.updated_at = $now,
    s.embedding = CASE WHEN $subject_vec IS NOT NULL THEN vecf32($subject_vec) ELSE NULL END
ON MATCH SET
    s.id = coalesce(s.id, $subject_id),
    s.canonical_name = coalesce(s.canonical_name, $subject_canonical),
    s.type = coalesce(s.type, $subject_type),
    s.embedding = CASE WHEN s.embedding IS NULL AND $subject_vec IS NOT NULL THEN vecf32($subject_vec) ELSE s.embedding END,
    s.aliases = CASE WHEN $subject IN coalesce(s.aliases, []) THEN coalesce(s.aliases, []) ELSE coalesce(s.aliases, []) + $subject END,
    s.updated_at = $now

// 3. Ensure Object Entity exists
MERGE (o:Entity {name: $object})
ON CREATE SET
    o.id = $object_id,
    o.canonical_name = $object_canonical,
    o.type = $object_type,
    o.aliases = [$object],
    o.created_at = $now,
    o.updated_at = $now,
    o.embedding = CASE WHEN $object_vec IS NOT NULL THEN vecf32($object_vec) ELSE NULL END
ON MATCH SET
    o.id = coalesce(o.id, $object_id),
    o.canonical_name = coalesce(o.canonical_name, $object_canonical),
    o.type = coalesce(o.type, $object_type),
    o.embedding = CASE WHEN o.embedding IS NULL AND $object_vec IS NOT NULL THEN vecf32($object_vec) ELSE o.embedding END,
    o.aliases = CASE WHEN $object IN coalesce(o.aliases, []) THEN coalesce(o.aliases, []) ELSE coalesce(o.aliases, []) + $object END,
    o.updated_at = $now

// 4. Upsert active bi-temporal edge (prevent parallel active duplicate edges)
WITH s, o, invalidated_count, invalidated_objects
OPTIONAL MATCH (s)-[existing_r:RELATES_TO {predicate: $predicate}]->(o)
WHERE existing_r.valid_to IS NULL
DELETE existing_r
CREATE (s)-[new_r:RELATES_TO {
    predicate: $predicate,
    cardinality: $cardinality,
    confidence: $confidence,
    valid_from: coalesce(existing_r.valid_from, $now),
    valid_to: NULL,
    transaction_from: $now,
    source_episode: $episode_id
}]->(o)

// 5. Establish full bidirectional cross-layer provenance to Episode
WITH invalidated_count, invalidated_objects, new_r, s, o
MERGE (ep:Episode {id: $episode_id})
ON CREATE SET ep.timestamp = $now, ep.role = 'system', ep.archived = false
MERGE (s)-[m_s:MENTIONED_IN]->(ep)
ON CREATE SET m_s.timestamp = $now
MERGE (o)-[m_o:MENTIONED_IN]->(ep)
ON CREATE SET m_o.timestamp = $now
MERGE (o)-[d:DERIVED_FROM]->(ep)
ON CREATE SET d.timestamp = $now
MERGE (ep)-[ef:EXTRACTED_FACT {predicate: $predicate}]->(o)
ON CREATE SET ef.timestamp = $now

// 6. Materialize explicit invalidation edges from episode to superseded entities with subject tracking
FOREACH (inv_obj IN invalidated_objects |
    MERGE (ep)-[inv_r:INVALIDATED_RELATION {subject: $subject, predicate: $predicate}]->(inv_obj)
    ON CREATE SET inv_r.timestamp = $now
)

RETURN invalidated_count,
       s.name AS subject,
       new_r.predicate AS predicate,
       o.name AS object,
       new_r.valid_from AS valid_from,
       ep.id AS source_episode
"""

SEMANTIC_ENTITY_VECTOR_SEARCH = """
CALL db.idx.vector.queryNodes('Entity', 'embedding', $limit, vecf32($query_vec))
YIELD node AS e, score
RETURN e.id AS id,
       e.name AS name,
       e.canonical_name AS canonical_name,
       e.type AS type,
       e.aliases AS aliases,
       (1.0 - score) AS similarity
ORDER BY similarity DESC
"""

SEMANTIC_ENTITY_FIND_BY_ALIAS = """
MATCH (e:Entity)
WHERE e.canonical_name = $slug
   OR e.name = $raw_name
   OR $raw_name IN coalesce(e.aliases, [])
   OR any(a IN coalesce(e.aliases, []) WHERE toLower(a) = toLower($raw_name))
   OR toLower(e.name) = toLower($raw_name)
RETURN e.id AS id,
       e.name AS name,
       e.canonical_name AS canonical_name,
       e.type AS type,
       coalesce(e.aliases, []) AS aliases
LIMIT 1
"""

SEMANTIC_ENTITY_APPEND_ALIAS = """
MATCH (e:Entity)
WHERE e.name = $canonical_name OR e.canonical_name = $canonical_name
SET e.aliases = CASE 
    WHEN $raw_name IN coalesce(e.aliases, []) THEN coalesce(e.aliases, [])
    ELSE coalesce(e.aliases, []) + $raw_name
END,
e.updated_at = $now
RETURN e.name AS name, e.aliases AS aliases
LIMIT 1
"""

SEMANTIC_ENTITY_VECTOR_SIMILARITY = """
CALL db.idx.vector.queryNodes('Entity', 'embedding', $candidate_limit, vecf32($vec))
YIELD node AS e, score
WITH e, (1.0 - score) AS similarity
WHERE similarity >= $threshold
RETURN e.id AS id,
       e.name AS name,
       e.canonical_name AS canonical_name,
       e.type AS type,
       coalesce(e.aliases, []) AS aliases,
       similarity
ORDER BY similarity DESC
LIMIT 1
"""

SEMANTIC_TIME_TRAVEL_SNAPSHOT = """
MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
WHERE r.valid_from <= $as_of 
  AND (r.valid_to IS NULL OR r.valid_to > $as_of)
RETURN s.name AS subject,
       s.type AS subject_type,
       r.predicate AS predicate,
       r.cardinality AS cardinality,
       r.confidence AS confidence,
       r.valid_from AS valid_from,
       r.valid_to AS valid_to,
       r.source_episode AS source_episode,
       o.name AS object,
       o.type AS object_type
ORDER BY s.name ASC, r.predicate ASC
"""

SEMANTIC_ENTITY_EVOLUTION_TIMELINE = """
MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
WHERE s.name = $entity_name OR s.canonical_name = $slug OR $entity_name IN coalesce(s.aliases, [])
RETURN s.name AS subject,
       r.predicate AS predicate,
       o.name AS object,
       r.cardinality AS cardinality,
       r.confidence AS confidence,
       r.valid_from AS valid_from,
       r.valid_to AS valid_to,
       r.source_episode AS source_episode,
       r.invalidated_by_episode AS invalidated_by_episode,
       CASE WHEN r.valid_to IS NULL THEN 'ACTIVE' ELSE 'SUPERSEDED' END AS status
ORDER BY r.valid_from ASC
"""

SEMANTIC_TIME_TRAVEL_SUBGRAPH = """
MATCH (seed:Entity)
WHERE seed.name = $seed_name OR seed.canonical_name = $slug OR $seed_name IN coalesce(seed.aliases, [])
OPTIONAL MATCH (seed)-[r:RELATES_TO]-(neighbor:Entity)
WHERE r.valid_from <= $as_of 
  AND (r.valid_to IS NULL OR r.valid_to > $as_of)
RETURN seed.name AS seed,
       seed.type AS seed_type,
       collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
           source: startNode(r).name,
           predicate: r.predicate,
           target: endNode(r).name,
           cardinality: r.cardinality,
           valid_from: r.valid_from,
           valid_to: r.valid_to,
           status: CASE WHEN r.valid_to IS NULL THEN 'ACTIVE' ELSE 'SUPERSEDED' END
       } ELSE NULL END) AS relationships,
       collect(DISTINCT CASE WHEN neighbor IS NOT NULL THEN neighbor.name ELSE NULL END) AS neighbors
"""

SEMANTIC_CYTOSCAPE_TIME_TRAVEL = """
MATCH (n:Entity)
WHERE n.created_at <= $as_of
OPTIONAL MATCH (n)-[r:RELATES_TO]->(m:Entity)
WHERE r.valid_from <= $as_of 
  AND (
      (r.valid_to IS NULL OR r.valid_to > $as_of)
      OR ($include_invalidated = true AND r.valid_to <= $as_of)
  )
RETURN collect(DISTINCT {
    id: n.id,
    name: n.name,
    canonical_name: n.canonical_name,
    type: n.type,
    created_at: n.created_at
}) AS nodes,
collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
    id: id(r),
    source: n.name,
    target: m.name,
    predicate: r.predicate,
    cardinality: r.cardinality,
    valid_from: r.valid_from,
    valid_to: r.valid_to,
    status: CASE 
        WHEN r.valid_to IS NULL OR r.valid_to > $as_of THEN 'ACTIVE'
        ELSE 'INVALIDATED'
    END
} ELSE NULL END) AS edges
"""



# DEPRECATED: Retained for backward compatibility; superseded by HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION
HIPPORAG_HYBRID_RETRIEVAL = """
MATCH (seed:Entity)
WHERE seed.name IN $seed_entities
OPTIONAL MATCH path = (seed)-[r:RELATES_TO*1..2]-(neighbor:Entity)
WHERE all(edge IN relationships(path) WHERE edge.valid_to IS NULL)
OPTIONAL MATCH (neighbor)-[:DERIVED_FROM]->(ep:Episode)
RETURN seed, collect(path) AS paths, collect(ep) AS episodes
"""

HIPPORAG_SEED_VECTOR_SEARCH = """
CALL db.idx.vector.queryNodes('Entity', 'embedding', $candidate_limit, vecf32($query_vec))
YIELD node AS e, score
WITH e, (1.0 - score) AS similarity
WHERE similarity >= $min_similarity
RETURN e.name AS name,
       e.canonical_name AS canonical_name,
       e.type AS type,
       coalesce(e.aliases, []) AS aliases,
       similarity
ORDER BY similarity DESC
"""

HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION = """
MATCH (seed:Entity)
WHERE (seed.name IN $seed_names OR seed.canonical_name IN $seed_names)
  AND coalesce(seed.created_at, 0.0) <= $as_of
MATCH path = (seed)-[r:RELATES_TO*1..3]-(target:Entity)
WHERE length(path) <= $max_hops
  AND none(n IN nodes(path)[1..] WHERE n = seed)
  AND none(idx IN range(0, length(path) - 2) WHERE nodes(path)[idx] = nodes(path)[idx + 2])
  AND all(node IN nodes(path) WHERE coalesce(node.created_at, 0.0) <= $as_of)
  AND all(edge IN relationships(path) WHERE 
      edge.valid_from <= $as_of 
      AND (edge.valid_to IS NULL OR edge.valid_to > $as_of)
  )
UNWIND relationships(path) AS edge
RETURN DISTINCT startNode(edge).name AS source,
       edge.predicate AS predicate,
       endNode(edge).name AS target,
       coalesce(edge.confidence, 1.0) AS weight,
       edge.valid_from AS valid_from,
       edge.valid_to AS valid_to
"""

HIPPORAG_EPISODE_GROUNDING_EXPANSION = """
MATCH (e:Entity)
WHERE e.name IN $entity_names
MATCH (e)-[r:DERIVED_FROM|MENTIONED_IN]->(ep:Episode)
WHERE coalesce(ep.archived, false) = false
  AND coalesce(ep.timestamp, r.timestamp, 0.0) <= $as_of
OPTIONAL MATCH (s:Entity)-[old_rel:RELATES_TO {source_episode: ep.id}]->(t:Entity)
WHERE old_rel.valid_to IS NOT NULL AND old_rel.valid_to <= $as_of
WITH e, r, ep, count(old_rel) AS invalidated_count
WHERE invalidated_count = 0
RETURN e.name AS entity,
       type(r) AS link_type,
       ep.id AS episode_id,
       coalesce(ep.content, '') AS content,
       coalesce(ep.role, 'system') AS role,
       coalesce(ep.utility_score, ep.importance_score, 0.5) AS importance_score,
       coalesce(ep.timestamp, 0.0) AS timestamp
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
MATCH (target)
WHERE (target:Entity OR target:Episode OR target:Procedure)
  AND (target.id = $target_id OR target.name = $target_id)
MERGE (st)-[r:PINNED_CONTEXT]->(target)
ON CREATE SET r.relevance_reason = $reason, r.pinned_at = $now
ON MATCH SET r.relevance_reason = $reason, r.pinned_at = $now
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
WHERE NOT n:GraphMetadata
OPTIONAL MATCH (n)-[r]->(m)
RETURN collect(DISTINCT n) AS nodes,
collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
    id: id(r),
    source: id(n),
    target: id(m),
    type: type(r),
    valid_from: r.valid_from,
    valid_to: r.valid_to,
    predicate: r.predicate,
    status: r.status
} ELSE NULL END) AS edges
"""

VISUALIZE_ACTIVE_GRAPH = """
MATCH (n)
WHERE NOT n:GraphMetadata
OPTIONAL MATCH (n)-[r]->(m)
WHERE r.valid_to IS NULL
RETURN collect(DISTINCT n) AS nodes,
collect(DISTINCT CASE WHEN r IS NOT NULL THEN {
    id: id(r),
    source: id(n),
    target: id(m),
    type: type(r),
    valid_from: r.valid_from,
    valid_to: r.valid_to,
    predicate: r.predicate,
    status: r.status
} ELSE NULL END) AS edges
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
    "EPISODE_UTILITY_FEEDBACK_UPDATE": EPISODE_UTILITY_FEEDBACK_UPDATE,
    "MEMORY_UTILITY_FEEDBACK_UPDATE": MEMORY_UTILITY_FEEDBACK_UPDATE,
    "EPISODE_HYBRID_CANDIDATE_FETCH": EPISODE_HYBRID_CANDIDATE_FETCH,
    "EPISODE_FALLBACK_SCAN_FETCH": EPISODE_FALLBACK_SCAN_FETCH,
    "EPISODE_BATCH_RECALL_TOUCH_AND_EXPAND": EPISODE_BATCH_RECALL_TOUCH_AND_EXPAND,
    "SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING": SEMANTIC_ENTITY_MERGE_WITH_EMBEDDING,
    "SEMANTIC_PROVENANCE_UPSERT_AND_LINK": SEMANTIC_PROVENANCE_UPSERT_AND_LINK,
    "SEMANTIC_ENTITY_VECTOR_SEARCH": SEMANTIC_ENTITY_VECTOR_SEARCH,
    "SEMANTIC_ENTITY_FIND_BY_ALIAS": SEMANTIC_ENTITY_FIND_BY_ALIAS,
    "SEMANTIC_ENTITY_APPEND_ALIAS": SEMANTIC_ENTITY_APPEND_ALIAS,
    "SEMANTIC_ENTITY_VECTOR_SIMILARITY": SEMANTIC_ENTITY_VECTOR_SIMILARITY,
    "SEMANTIC_TIME_TRAVEL_SNAPSHOT": SEMANTIC_TIME_TRAVEL_SNAPSHOT,
    "SEMANTIC_ENTITY_EVOLUTION_TIMELINE": SEMANTIC_ENTITY_EVOLUTION_TIMELINE,
    "SEMANTIC_TIME_TRAVEL_SUBGRAPH": SEMANTIC_TIME_TRAVEL_SUBGRAPH,
    "SEMANTIC_CYTOSCAPE_TIME_TRAVEL": SEMANTIC_CYTOSCAPE_TIME_TRAVEL,
    "HIPPORAG_SEED_VECTOR_SEARCH": HIPPORAG_SEED_VECTOR_SEARCH,
    "HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION": HIPPORAG_ACTIVE_SUBGRAPH_EXPANSION,
    "HIPPORAG_EPISODE_GROUNDING_EXPANSION": HIPPORAG_EPISODE_GROUNDING_EXPANSION,
}

