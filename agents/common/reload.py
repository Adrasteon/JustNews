"""Common runtime reload endpoint for JustNews agents.

Provides a small registry where agents can register named reload callbacks
and exposes a `/admin/reload` POST endpoint that invokes them. This allows
operators to trigger runtime reloads (for example swapping embedding models
after updating ModelStore) without restarting the process.

Usage:
    from agents.common.reload import register_reload_endpoint, register_reload_handler
    register_reload_handler('embedding_model', lambda: ...)
    register_reload_endpoint(app)

The endpoint accepts JSON: {"handlers": ["embedding_model"]} or {"all": true}
and returns per-handler success/failure details.
"""
from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from common.observability import get_logger

logger = get_logger(__name__)

# Simple in-process registry of reload handlers
_RELOAD_HANDLERS: dict[str, Callable[[], Any]] = {}


def register_reload_handler(name: str, fn: Callable[[], Any]) -> None:
    """Register a reload handler under `name`.

    Handlers should be zero-argument callables that perform the reload work.
    They may return arbitrary info (which will be included in the endpoint
    response) or raise an Exception on failure.
    """
    _RELOAD_HANDLERS[name] = fn


def register_reload_endpoint(app: FastAPI, path: str = "/admin/reload") -> None:
    """Register the POST reload endpoint on the provided FastAPI app.

    Request JSON schema:
      {"handlers": ["embedding_model"]}
      {"all": true}
    """

    async def _reload(request: Request):
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        if not body:
            raise HTTPException(status_code=400, detail="Missing request body")

        targets: list[str] = []
        if body.get("all"):
            targets = list(_RELOAD_HANDLERS.keys())
        else:
            targets = body.get("handlers") or []

        if not targets:
            raise HTTPException(status_code=400, detail="No handlers specified")

        results = {}
        for t in targets:
            if t not in _RELOAD_HANDLERS:
                results[t] = {"ok": False, "error": "handler_not_registered"}
                continue
            try:
                info = _RELOAD_HANDLERS[t]()
                results[t] = {"ok": True, "info": info}
            except Exception as e:
                logger.exception("reload_handler_failed", handler=t)
                results[t] = {"ok": False, "error": str(e), "trace": traceback.format_exc()}

        return {"results": results}

    app.post(path)(_reload)
