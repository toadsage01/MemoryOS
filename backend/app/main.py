"""FastAPI app entry — mounts routers, runs startup hooks."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from . import graph
from .auth import require_token
from .config import get_settings
from .routers import context, dedup as dedup_router, ingest, projects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("sbs.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot checks: write the auth token if missing, sanity-check Neo4j."""
    s = get_settings()
    token = s.ensure_auth_token()
    log.info("auth token ready (first 8 chars: %s...)", token[:8])
    log.info(
        "config: embedding=%s/%s curator=%s/%s dedup_threshold=%.2f brief_max_words=%d",
        s.embedding_provider,
        s.embedding_model,
        s.curator_model_provider,
        s.curator_model_name,
        s.dedup_fused_score_threshold,
        s.brief_max_words,
    )
    # Neo4j — best-effort; the user might not have it running yet.
    try:
        graph.get_driver()
        log.info("neo4j: connected + schema applied")
    except Exception as e:
        log.warning(
            "neo4j: not reachable yet (%s). Start it with `docker compose up -d neo4j`. "
            "Endpoints that need the graph will return 503 until it's up.",
            e,
        )
    yield
    # Shutdown
    log.info("closing neo4j driver")
    graph.close()


app = FastAPI(
    title="Second Brain Sync",
    version="0.1.0",
    description="Personal memory layer for LLM web chats.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    """No-auth liveness probe. Returns config snapshot for sanity."""
    s = get_settings()
    return {
        "status": "ok",
        "embedding_provider": s.embedding_provider,
        "curator_model_provider": s.curator_model_provider,
        "neo4j_uri": s.neo4j_uri,  # not a secret
        "chroma_persist_dir": str(s.chroma_path),
    }


@app.get("/whoami")
def whoami(_=Depends(require_token)) -> dict:
    """Token-check endpoint for the extension's setup flow."""
    return {"ok": True, "msg": "token is valid"}


app.include_router(projects.router)
app.include_router(ingest.router)
app.include_router(context.router)
app.include_router(dedup_router.router)

