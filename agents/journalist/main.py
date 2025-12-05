"""
Journalist Agent - entrypoint

Lightweight agent wrapper that exposes a simple interface to the JournalistEngine.
This mirrors other agents' structure so it can be registered with MCP or run standalone
for local testing.
"""
from __future__ import annotations

import logging
from common.observability import bootstrap_observability

# Initialize observability for the Journalist agent
bootstrap_observability("journalist", level=logging.INFO)
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .journalist_engine import JournalistEngine
from .tools import health_check

# Compatibility: expose create_database_service for tests that patch agent modules
try:
    from database.utils.migrated_database_utils import (
        create_database_service,  # type: ignore
    )
except Exception:
    create_database_service = None

logger = logging.getLogger(__name__)

engine: JournalistEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    logger.info("Starting Journalist agent...")
    engine = JournalistEngine()
    try:
        yield
    finally:
        logger.info("Shutting down Journalist agent...")
        if engine:
            await engine.shutdown()


app = FastAPI(title="Journalist Agent", version="0.1", lifespan=lifespan)


@app.get("/health")
async def _health():
    return health_check()


@app.post("/crawl_url")
async def crawl_url(payload: dict):
    """Trigger a crawl for a single URL via the journalist engine.

    Expects JSON like: { "url": "https://...", "mode": "standard" }
    """
    if engine is None:
        return {"success": False, "error": "Engine not initialized"}
    result = await engine.crawl_and_analyze(payload.get("url"), mode=payload.get("mode"))
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8016)
