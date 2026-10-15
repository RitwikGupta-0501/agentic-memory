"""Seeds realistic 4-tier cognitive memory graphs for demo tenants."""

import logging
import time
from app.core.falkor_client import falkor_router

logger = logging.getLogger("aegis.seed")


def seed_tenant_acme_payments():
    """Seeds Tenant A (acme-payments) with rich 4-tier cognitive memory graph."""
    t_id = "acme-payments"
    now = time.time()
    t1 = now - 3600  # 1 hour ago
    t2 = now - 600   # 10 minutes ago

    # Clean existing graph for fresh deterministic seed
    try:
        falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)
    except Exception:
        pass

    logger.info(f"Seeding tenant '{t_id}'...")

    # 1. Episodic Memory Chained Nodes
    episodes_query = """
    CREATE (ep1:Episode {
        id: 'ep_init_1',
        session_id: 'session_sre_01',
        content: 'Alice: Deploying initial payment processing pipeline with PostgreSQL.',
        role: 'user',
        importance_score: 0.7,
        timestamp: $t1
    })
    CREATE (ep2:Episode {
        id: 'ep_init_2',
        session_id: 'session_sre_01',
        content: 'System: Initialized Prod_DB with PostgreSQL 16 cluster in us-east-1.',
        role: 'system',
        importance_score: 0.6,
        timestamp: $t1 + 60
    })
    CREATE (ep3:Episode {
        id: 'ep_init_3',
        session_id: 'session_sre_01',
        content: 'Alice: Migrating Prod_DB from PostgreSQL to FalkorDB for low-latency cognitive graph memory.',
        role: 'user',
        importance_score: 0.9,
        timestamp: $t2
    })
    CREATE (ep1)-[:NEXT_EPISODE {latency_ms: 60000}]->(ep2)
    CREATE (ep2)-[:NEXT_EPISODE {latency_ms: 300000}]->(ep3)
    """
    falkor_router.query(episodes_query, {"t1": t1, "t2": t2}, tenant_id=t_id)

    # 2. Semantic Memory with Bi-Temporal Invalidation
    semantic_query = """
    MERGE (db:Entity {name: 'Prod_DB', type: 'Infrastructure'})
    MERGE (pg:Entity {name: 'PostgreSQL', type: 'Database'})
    MERGE (falkor:Entity {name: 'FalkorDB', type: 'GraphDatabase'})
    WITH db, pg, falkor
    MATCH (ep2:Episode {id: 'ep_init_2'})
    MATCH (ep3:Episode {id: 'ep_init_3'})
    CREATE (db)-[:RELATES_TO {
        predicate: 'USES_TECH',
        valid_from: $t1,
        valid_to: $t2,
        invalidated_by_episode: 'ep_init_3',
        confidence: 1.0,
        source_episode: 'ep_init_2'
    }]->(pg)
    CREATE (db)-[:RELATES_TO {
        predicate: 'USES_TECH',
        valid_from: $t2,
        valid_to: NULL,
        confidence: 1.0,
        source_episode: 'ep_init_3'
    }]->(falkor)
    CREATE (falkor)-[:DERIVED_FROM]->(ep3)
    CREATE (pg)-[:DERIVED_FROM]->(ep2)
    """
    falkor_router.query(semantic_query, {"t1": t1, "t2": t2}, tenant_id=t_id)

    # 3. Working Memory TaskRun and SubTasks
    working_query = """
    CREATE (tr:TaskRun {
        id: 'task_demo_01',
        goal: 'Migrate core payment database to graph engine',
        created_at: $t2,
        status: 'COMPLETED'
    })
    CREATE (st1:SubTask {
        id: 'st_demo_1',
        title: 'Inspect database configuration',
        description: 'Verify current configuration and compatibility.',
        status: 'COMPLETED',
        locked_by: 'Context & Triage Agent',
        created_at: $t2
    })
    CREATE (st2:SubTask {
        id: 'st_demo_2',
        title: 'Execute migration to FalkorDB',
        description: 'Migrate tables and construct knowledge graph.',
        status: 'COMPLETED',
        locked_by: 'Execution & Reflexion Agent',
        created_at: $t2 + 100
    })
    CREATE (tr)-[:HAS_SUBTASK]->(st1)
    CREATE (tr)-[:HAS_SUBTASK]->(st2)
    CREATE (st2)-[:DEPENDS_ON]->(st1)
    WITH st1, st2
    MATCH (db:Entity {name: 'Prod_DB'})
    CREATE (st1)-[:PINNED_CONTEXT {relevance_reason: 'Target database entity', pinned_at: $t2}]->(db)
    """
    falkor_router.query(working_query, {"t2": t2}, tenant_id=t_id)

    # 4. Procedural Memory: Skill DAG and Learned Guardrail
    procedural_query = """
    CREATE (proc:Procedure {
        id: 'proc_migration_01',
        name: 'Database_Migration',
        trigger_description: 'Automated database migration and cutover',
        success_count: 5,
        fail_count: 1
    })
    CREATE (step1:ActionStep {
        id: 'step_schema_val',
        step_order: 1,
        tool_name: 'query_database_config',
        param_schema: '{"db_name": "string"}'
    })
    CREATE (step2:ActionStep {
        id: 'step_migration_exec',
        step_order: 2,
        tool_name: 'run_database_migration',
        param_schema: '{"source_db": "string", "target_db": "string", "require_wal_checkpoint": "boolean"}'
    })
    CREATE (proc)-[:FIRST_STEP]->(step1)
    CREATE (step1)-[:NEXT_STEP]->(step2)
    CREATE (gr:Guardrail {
        id: 'gr_wal_01',
        rule_text: 'Always enforce require_wal_checkpoint=True during database migrations',
        error_signature: 'ERR_NO_WAL_CHECKPOINT',
        fix_instruction: 'Set require_wal_checkpoint=True to avoid replication drift.',
        created_at: $t2
    })
    CREATE (step2)-[:HAS_GUARDRAIL]->(gr)
    """
    falkor_router.query(procedural_query, {"t2": t2}, tenant_id=t_id)
    logger.info(f"Tenant '{t_id}' successfully seeded.")


def seed_tenant_nebula_cloud():
    """Seeds Tenant B (nebula-cloud) for multi-tenant isolation demonstrations."""
    t_id = "nebula-cloud"
    now = time.time()

    try:
        falkor_router.query("MATCH (n) DETACH DELETE n", tenant_id=t_id)
    except Exception:
        pass

    logger.info(f"Seeding tenant '{t_id}'...")

    query = """
    CREATE (ep:Episode {
        id: 'ep_nebula_1',
        session_id: 'session_cloud_01',
        content: 'Bob: Initialized Nebula Cloud Kubernetes cluster v1.30.',
        role: 'user',
        importance_score: 0.8,
        timestamp: $now
    })
    CREATE (cluster:Entity {name: 'Nebula_K8s_Cluster', type: 'Compute'})
    CREATE (k8s:Entity {name: 'Kubernetes_v1.30', type: 'Platform'})
    CREATE (cluster)-[:RELATES_TO {
        predicate: 'RUNS_VERSION',
        valid_from: $now,
        valid_to: NULL,
        confidence: 1.0,
        source_episode: 'ep_nebula_1'
    }]->(k8s)
    CREATE (k8s)-[:DERIVED_FROM]->(ep)
    """
    falkor_router.query(query, {"now": now}, tenant_id=t_id)
    logger.info(f"Tenant '{t_id}' successfully seeded.")


def seed_all_tenants():
    """Runs all tenant seeds."""
    seed_tenant_acme_payments()
    seed_tenant_nebula_cloud()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed_all_tenants()
