"""Main FastAPI entrypoint for AegisGraph backend."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.falkor_client import falkor_router
from app.api.routes_memory import router as memory_router
from app.api.routes_coordination import router as coordination_router
from app.api.routes_consolidation import router as consolidation_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aegis.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: verifies FalkorDB connection on startup."""
    logger.info("Starting AegisGraph Cognitive Engine...")
    falkor_online = falkor_router.ping()
    if falkor_online:
        logger.info("Connected to FalkorDB successfully.")
    else:
        logger.warning(
            f"FalkorDB is currently offline at {settings.falkordb_host}:{settings.falkordb_port}. "
            "Backend will operate with fallback mock endpoints until FalkorDB is online."
        )
    yield
    logger.info("AegisGraph backend shutdown.")


app = FastAPI(
    title="AegisGraph: Cognitive Memory & Agent Coordination Engine",
    description="4-tier cognitive graph memory engine built exclusively on FalkorDB.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(memory_router)
app.include_router(coordination_router)
app.include_router(consolidation_router)


@app.get("/")
def root() -> Dict[str, Any]:
    return {
        "name": "AegisGraph API",
        "version": "0.1.0",
        "status": "ONLINE",
        "tracks": ["Track 02: Agent Memory and Coordination", "Track 01: Agents That Act on Connected Data"],
        "docs_url": "/docs",
    }


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    falkor_status = falkor_router.ping()
    return {
        "status": "HEALTHY" if falkor_status else "DEGRADED",
        "falkordb_connected": falkor_status,
        "falkordb_host": falkor_router.host,
        "falkordb_port": falkor_router.port,
        "default_tenant": settings.default_tenant_id,
        "llm_provider": settings.llm_provider,
    }


