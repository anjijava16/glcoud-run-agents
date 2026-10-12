"""Optional API-key guard for the /api routes.

If APP_API_KEY is empty the check is skipped. On Cloud Run you'd normally put the
key in Secret Manager (Terraform does this) or front the service with IAP.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().app_api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing X-API-Key")
