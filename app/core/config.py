"""Application settings, loaded from environment variables (and .env locally).

Everything that differs between laptop, CI and Cloud Run lives here, so the
rest of the code never calls os.getenv directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_name: str = "retail-adk-agents"
    app_env: str = Field(default="local", description="local | dev | staging | prod")
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    log_json: bool = True
    cors_origins: list[str] = ["*"]

    # Optional shared API key. Empty = no auth (fine for local, set it on Cloud Run).
    app_api_key: str = ""

    # --- LLM (OpenRouter through LiteLLM) ---
    openrouter_api_key: str = ""
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    # LiteLLM model strings. The "openrouter/" prefix tells LiteLLM which provider to use.
    root_model: str = "openrouter/openai/gpt-4o-mini"
    specialist_model: str = "openrouter/openai/gpt-4o-mini"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    llm_timeout_s: int = 60

    # --- storage ---
    # ADK DatabaseSessionService URL. SQLite for local/demo; swap to
    # postgresql+asyncpg://... (Cloud SQL) for multi-instance production.
    session_db_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'sessions.db'}"
    retail_db_path: str = str(BASE_DIR / "data" / "retail.db")
    seed_demo_data: bool = True

    # --- agent runtime ---
    agent_run_timeout_s: int = 120
    adk_app_name: str = "retail_assistant"
    # Refunds above this amount are parked for human review instead of auto-approved.
    refund_auto_approve_limit: float = 500.0
    return_window_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
