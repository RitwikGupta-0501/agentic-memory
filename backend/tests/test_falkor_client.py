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


def test_falkordb_cloud_url_connection_routing():
    """TEST-CLOUD-01: Verifies TenantGraphRouter correctly parses and connects via FalkorDB Cloud URL."""
    # Test connection via URL scheme (falkor://)
    cloud_router = TenantGraphRouter(url="falkor://localhost:6379")
    assert cloud_router.url == "falkor://localhost:6379"
    assert cloud_router.ping() is True


def test_falkordb_cloud_tls_parameters_configuration():
    """TEST-CLOUD-02: Verifies TenantGraphRouter properly preserves Cloud SSL, username, and auth configuration."""
    router = TenantGraphRouter(
        host="test-cluster.cloud.falkordb.com",
        port=16379,
        username="default",
        password="secret_token",
        ssl=True,
        ssl_cert_reqs="none",
    )
    assert router.host == "test-cluster.cloud.falkordb.com"
    assert router.port == 16379
    assert router.username == "default"
    assert router.password == "secret_token"
    assert router.ssl is True
    assert router.ssl_cert_reqs == "none"

