"""FastAPI entrypoint.

    uvicorn app.main:app --reload --port 8080

Startup (lifespan):
  1. configure logging
  2. create + seed the retail SQLite DB
  3. build AgentService (ADK runners + DatabaseSessionService)
Shutdown closes the runners.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.core.security import require_api_key
from app.data.db import init_db
from app.data.seed import seed_if_empty
from app.routers import agents, catalog, chat, health, sessions
from app.services.agent_service import AgentService

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    # LiteLLM also reads the key from the environment; set it for libraries that look there.
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)
    else:
        log.warning("OPENROUTER_API_KEY is not set - chat calls will fail until it is.")

    init_db()
    if settings.seed_demo_data:
        seed_if_empty()
    if settings.session_db_url.startswith("sqlite"):
        Path(settings.session_db_url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)

    if not hasattr(app.state, "agent_service"):  # tests may inject their own
        app.state.agent_service = AgentService(settings)
    log.info("startup complete", extra={"status": settings.app_env})
    yield
    await app.state.agent_service.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Retail Multi-Agent Assistant",
        version=settings.app_version,
        description="FastAPI + Google ADK + OpenRouter (LiteLLM) retail assistant",
        lifespan=lifespan,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_deps = [Depends(require_api_key)]
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api/v1", dependencies=api_deps)
    app.include_router(agents.router, prefix="/api/v1", dependencies=api_deps)
    app.include_router(sessions.router, prefix="/api/v1", dependencies=api_deps)
    app.include_router(catalog.router, prefix="/api/v1", dependencies=api_deps)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def ui():
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
print(app)
