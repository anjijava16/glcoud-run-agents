"""LLM factory: OpenRouter models via ADK's LiteLlm wrapper.

ADK talks to Gemini natively; for anything else it ships `LiteLlm`, which hands the
call to LiteLLM. LiteLLM understands `openrouter/<vendor>/<model>` strings, so one
OpenRouter key gives every agent access to OpenAI, Anthropic, Llama, Mistral, etc.

Pick models that support tool/function calling — the specialists depend on it.
"""

from __future__ import annotations

from collections.abc import Callable

from google.adk.models.base_llm import BaseLlm
from google.adk.models.lite_llm import LiteLlm

from app.core.config import get_settings

# Tests swap this to inject a scripted fake model (see tests/fake_llm.py).
_override: Callable[[str], BaseLlm] | None = None


def set_model_override(factory: Callable[[str], BaseLlm] | None) -> None:
    global _override
    _override = factory


def build_model(role: str = "specialist") -> BaseLlm:
    """role: 'root' or 'specialist' — lets you run a stronger router and cheaper specialists."""
    if _override is not None:
        return _override(role)
    s = get_settings()
    model_name = s.root_model if role == "root" else s.specialist_model
    return LiteLlm(
        model=model_name,
        api_key=s.openrouter_api_key or None,
        api_base=s.openrouter_api_base,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
        timeout=s.llm_timeout_s,
        num_retries=2,
        # OpenRouter uses these for attribution/rankings; harmless otherwise.
        extra_headers={"HTTP-Referer": "https://github.com/retail-adk-agents", "X-Title": s.app_name},
    )
