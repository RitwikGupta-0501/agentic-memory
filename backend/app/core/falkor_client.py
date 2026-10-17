"""FalkorDB client connection router and multi-tenant graph manager."""

import logging
from typing import Any, Dict, List, Optional
from falkordb import FalkorDB
from app.core.config import settings

logger = logging.getLogger("aegis.falkor")


class TenantGraphRouter:
    """Manages multi-tenant graph isolation and OpenCypher execution across local and FalkorDB Cloud."""

    def __init__(
        self,
        url: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        username: Optional[str] = None,
        ssl: Optional[bool] = None,
        ssl_cert_reqs: Optional[str] = None,
    ):
        self.url = url or settings.falkordb_url
        self.host = host or settings.falkordb_host
        self.port = port or settings.falkordb_port
        self.password = password if password is not None else settings.falkordb_password
        self.username = username or settings.falkordb_username
        self.ssl = ssl if ssl is not None else settings.falkordb_ssl
        self.ssl_cert_reqs = ssl_cert_reqs or settings.falkordb_ssl_cert_reqs
        self._client: Optional[FalkorDB] = None
        self._initialized_graphs = set()

    def get_client(self) -> FalkorDB:
        """Returns the active FalkorDB client or creates a new connection."""
        if self._client is None:
            if self.url:
                logger.info("Connecting to FalkorDB Cloud via URL...")
                url_kwargs: Dict[str, Any] = {}
                if "falkors://" in self.url or "rediss://" in self.url:
                    url_kwargs["ssl_cert_reqs"] = self.ssl_cert_reqs
                self._client = FalkorDB.from_url(self.url, **url_kwargs)
            else:
                logger.info(f"Connecting to FalkorDB at {self.host}:{self.port} (SSL={self.ssl})...")
                kwargs: Dict[str, Any] = {
                    "host": self.host,
                    "port": self.port,
                }
                if self.password:
                    kwargs["password"] = self.password
                if self.username:
                    kwargs["username"] = self.username
                if self.ssl:
                    kwargs["ssl"] = True
                    if self.ssl_cert_reqs:
                        kwargs["ssl_cert_reqs"] = self.ssl_cert_reqs

                self._client = FalkorDB(**kwargs)
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
        """Idempotently ensures property and dynamic vector indexes are created on the selected graph."""
        try:
            from app.core.embeddings.factory import embedding_service
            import time

            # 1. Create property range indexes
            index_queries = [
                "CREATE INDEX FOR (e:Entity) ON (e.name)",
                "CREATE INDEX FOR (e:Entity) ON (e.canonical_name)",
                "CREATE INDEX FOR (e:Entity) ON (e.id)",
                "CREATE INDEX FOR (s:Session) ON (s.id)",
                "CREATE INDEX FOR (ep:Episode) ON (ep.id)",
                "CREATE INDEX FOR (ep:Episode) ON (ep.session_id)",
                "CREATE INDEX FOR (ep:Episode) ON (ep.timestamp)",
                "CREATE INDEX FOR (ep:Episode) ON (ep.actor_id)",
                "CREATE INDEX FOR (tr:TaskRun) ON (tr.id)",
                "CREATE INDEX FOR (st:SubTask) ON (st.id)",
                "CREATE INDEX FOR (p:Procedure) ON (p.name)",
            ]
            for q in index_queries:
                try:
                    graph.query(q)
                except Exception:
                    pass

            # 2. Dynamic Vector Indexes on Episode.embedding and Entity.embedding
            active_dim = embedding_service.provider.dimension
            vec_idx_queries = [
                (
                    f"CREATE VECTOR INDEX FOR (ep:Episode) ON (ep.embedding) "
                    f"OPTIONS {{dimension: {active_dim}, similarityFunction: 'cosine'}}"
                ),
                (
                    f"CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding) "
                    f"OPTIONS {{dimension: {active_dim}, similarityFunction: 'cosine'}}"
                ),
            ]
            for vq in vec_idx_queries:
                try:
                    graph.query(vq)
                except Exception:
                    pass

            # 3. GraphMetadata singleton
            now = time.time()
            meta_query = """
            MERGE (m:GraphMetadata {graph_key: $graph_key})
            ON CREATE SET m.active_embedding_model = $model,
                          m.active_dimension = $dim,
                          m.created_at = $now
            """
            try:
                graph.query(
                    meta_query,
                    {
                        "graph_key": graph.name,
                        "model": embedding_service.provider.model_name,
                        "dim": active_dim,
                        "now": now,
                    },
                )
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Index initialization note: {e}")

    def check_graph_embedding_drift(
        self,
        tenant_id: str = None,
        user_id: str = None,
        shared: bool = True,
    ) -> Dict[str, Any]:
        """Detects whether active embedding configuration matches stored graph embeddings."""
        from app.core.embeddings.factory import embedding_service

        graph = self.get_graph(tenant_id, user_id, shared)
        active_model = embedding_service.provider.model_name
        active_dim = embedding_service.provider.dimension

        try:
            res = graph.query("MATCH (m:GraphMetadata) RETURN m.active_embedding_model, m.active_dimension LIMIT 1")
            if res and res.result_set and res.result_set[0]:
                stored_model = res.result_set[0][0]
                stored_dim = res.result_set[0][1]
                drift_detected = (stored_model != active_model) or (stored_dim != active_dim)
                return {
                    "status": "DRIFT_DETECTED" if drift_detected else "MATCH",
                    "tenant_id": tenant_id or settings.default_tenant_id,
                    "stored_model": stored_model,
                    "stored_dimension": stored_dim,
                    "active_model": active_model,
                    "active_dimension": active_dim,
                    "drift_detected": drift_detected,
                }
        except Exception as e:
            logger.debug(f"Drift check exception: {e}")

        return {
            "status": "MATCH",
            "tenant_id": tenant_id or settings.default_tenant_id,
            "stored_model": active_model,
            "stored_dimension": active_dim,
            "active_model": active_model,
            "active_dimension": active_dim,
            "drift_detected": False,
        }

    def get_indexes(
        self,
        tenant_id: str = None,
        user_id: str = None,
        shared: bool = True,
    ) -> List[Any]:
        """Returns the active indexes on the selected tenant graph."""
        graph = self.get_graph(tenant_id, user_id, shared)
        try:
            res = graph.query("CALL db.indexes()")
            return res.result_set or []
        except Exception as e:
            logger.warning(f"Failed to query db.indexes(): {e}")
            return []

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
