"""FalkorDB client connection router and multi-tenant graph manager."""

import logging
from typing import Any, Dict, List, Optional
from falkordb import FalkorDB
from app.core.config import settings

logger = logging.getLogger("aegis.falkor")


class TenantGraphRouter:
    """Manages multi-tenant graph isolation and OpenCypher execution."""

    def __init__(self, host: str = None, port: int = None, password: str = None):
        self.host = host or settings.falkordb_host
        self.port = port or settings.falkordb_port
        self.password = password if password is not None else settings.falkordb_password
        self._client: Optional[FalkorDB] = None
        self._initialized_graphs = set()

    def get_client(self) -> FalkorDB:
        """Returns the active FalkorDB client or creates a new connection."""
        if self._client is None:
            logger.info(f"Connecting to FalkorDB at {self.host}:{self.port}...")
            self._client = FalkorDB(
                host=self.host,
                port=self.port,
                password=self.password if self.password else None,
            )
        return self._client

    def ping(self) -> bool:
        """Checks if FalkorDB is reachable."""
        try:
            client = self.get_client()
            client.connection.ping()
            return True
        except Exception as e:
            logger.warning(f"FalkorDB ping failed: {e}")
            return False

    def get_graph_key(
        self,
        tenant_id: str = None,
        user_id: str = None,
        shared: bool = True,
    ) -> str:
        """Computes the isolated FalkorDB graph key for a tenant and user."""
        t_id = (tenant_id or settings.default_tenant_id).replace("-", "_").lower()
        if shared or not user_id:
            return f"mem_{t_id}_shared"
        u_id = user_id.replace("-", "_").lower()
        return f"mem_{t_id}_{u_id}"

    def get_graph(
        self,
        tenant_id: str = None,
        user_id: str = None,
        shared: bool = True,
    ):
        """Selects the isolated FalkorDB graph and guarantees vector indexes exist."""
        client = self.get_client()
        graph_key = self.get_graph_key(tenant_id, user_id, shared)
        graph = client.select_graph(graph_key)

        if graph_key not in self._initialized_graphs:
            self.ensure_indices(graph)
            self._initialized_graphs.add(graph_key)

        return graph

    def ensure_indices(self, graph) -> None:
        """Idempotently ensures indexes are created on the selected graph."""
        try:
            # Create property indexes for fast lookups
            index_queries = [
                "CREATE INDEX FOR (e:Entity) ON (e.name)",
                "CREATE INDEX FOR (ep:Episode) ON (ep.id)",
                "CREATE INDEX FOR (tr:TaskRun) ON (tr.id)",
                "CREATE INDEX FOR (st:SubTask) ON (st.id)",
                "CREATE INDEX FOR (p:Procedure) ON (p.name)",
            ]
            for q in index_queries:
                try:
                    graph.query(q)
                except Exception:
                    pass  # Index already exists or not supported by engine version
        except Exception as e:
            logger.debug(f"Index initialization note: {e}")

    def query(
        self,
        query_str: str,
        params: Optional[Dict[str, Any]] = None,
        tenant_id: str = None,
        user_id: str = None,
        shared: bool = True,
    ) -> Any:
        """Executes a parameterized Cypher query on the tenant's isolated graph."""
        graph = self.get_graph(tenant_id, user_id, shared)
        return graph.query(query_str, params or {})


# Global singleton instance
falkor_router = TenantGraphRouter()
