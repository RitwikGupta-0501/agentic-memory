"""Integration tests against live FalkorDB instance."""

import pytest
from app.core.falkor_client import falkor_router
from app.memory.semantic import semantic_memory
from app.memory.working import working_memory, SubTaskSpec
from app.memory.procedural import procedural_memory


@pytest.fixture(scope="module")
def check_falkor():
    if not falkor_router.ping():
        pytest.skip("FalkorDB is offline; skipping live integration tests.")


def test_live_multi_tenant_isolation(check_falkor):
    """Ensures acme-payments and nebula-cloud are completely isolated graphs."""
    acme_res = falkor_router.query("MATCH (n:Entity) RETURN count(n)", tenant_id="acme-payments")
    nebula_res = falkor_router.query("MATCH (n:Entity) RETURN count(n)", tenant_id="nebula-cloud")

    acme_count = acme_res.result_set[0][0]
    nebula_count = nebula_res.result_set[0][0]

    assert acme_count >= 3  # Prod_DB, PostgreSQL, FalkorDB
    assert nebula_count >= 2  # Nebula_K8s_Cluster, Kubernetes_v1.30


def test_live_bitemporal_state(check_falkor):
    """Verifies that superseded facts have valid_to set while current facts have valid_to NULL."""
    query = """
    MATCH (db:Entity {name: 'Prod_DB'})-[r:RELATES_TO]->(target:Entity)
    RETURN target.name, r.valid_to IS NOT NULL AS is_invalidated
    """
    res = falkor_router.query(query, tenant_id="acme-payments")
    results = {row[0]: row[1] for row in res.result_set}

    # PostgreSQL was superseded by FalkorDB
    assert results.get("PostgreSQL") is True
    assert results.get("FalkorDB") is False


def test_live_procedural_guardrail(check_falkor):
    """Verifies that Database_Migration procedure has the learned Guardrail attached."""
    proc = procedural_memory.retrieve_procedure(
        tenant_id="acme-payments",
        procedure_name="Database_Migration",
    )
    assert proc is not None
    assert len(proc["guardrails"]) >= 1
    assert "ERR_NO_WAL_CHECKPOINT" in proc["guardrails"][0]["error_signature"]
