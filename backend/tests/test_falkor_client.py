"""Tests for TenantGraphRouter and multi-tenant graph key isolation."""

import pytest
from app.core.falkor_client import TenantGraphRouter


def test_tenant_graph_key_generation():
    router = TenantGraphRouter(host="localhost", port=6379)

    # Shared tenant graph
    shared_key = router.get_graph_key("acme-payments", shared=True)
    assert shared_key == "mem_acme_payments_shared"

    # User-isolated tenant graph
    user_key = router.get_graph_key("acme-payments", user_id="alice_sre", shared=False)
    assert user_key == "mem_acme_payments_alice_sre"

    # Different tenant isolation
    nebula_key = router.get_graph_key("nebula-cloud", shared=True)
    assert nebula_key == "mem_nebula_cloud_shared"
    assert nebula_key != shared_key
