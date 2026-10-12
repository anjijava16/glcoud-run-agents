"""Request-ID + access log middleware."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import request_id_ctx

log = logging.getLogger("access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Cloud Run sets X-Cloud-Trace-Context; reuse a caller-provided id if present.
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        latency = round((time.perf_counter() - start) * 1000, 1)
        response.headers["x-request-id"] = rid
        if not request.url.path.startswith("/static"):
            log.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={"path": request.url.path, "status": response.status_code, "latency_ms": latency},
            )
        return response
