"""Liveness/readiness.

Use /health and /ready from outside. Cloud Run reserves URL paths ending in "z"
(/healthz, /readyz, ...) on its public *.run.app URLs and answers them itself with a
404, so those only work locally or from inside the container. They're kept as aliases.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.data.db import get_conn
from app.routers.deps import get_agent_service
from app.services.agent_service import AgentService

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/healthz", include_in_schema=False)
async def health():
    s = get_settings()
    return {"status": "ok", "app": s.app_name, "version": s.app_version, "env": s.app_env}


@router.get("/ready")
@router.get("/readyz", include_in_schema=False)
async def ready(svc: AgentService = Depends(get_agent_service)):
    checks = {}
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1 FROM products LIMIT 1")
        checks["retail_db"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["retail_db"] = f"fail: {e.__class__.__name__}"
    try:
        await svc.session_service.list_sessions(app_name="__readyz__", user_id="__readyz__")
        checks["session_db"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["session_db"] = f"fail: {e.__class__.__name__}"
    checks["llm_key_configured"] = bool(get_settings().openrouter_api_key)
    ok = checks["retail_db"] == "ok" and checks["session_db"] == "ok"
    return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)
