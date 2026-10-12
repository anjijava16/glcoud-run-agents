"""AgentService: the one place that owns ADK Runners and the session store.

Routers never touch ADK directly. They call `chat()` / `stream()` / session helpers
here. That keeps HTTP concerns (validation, status codes, SSE framing) apart from
agent concerns (runners, events, state).

Runners
    "coordinator" -> retail_coordinator with 4 sub-agents (the main chat)
    "catalog" | "orders" | "returns" | "support" -> one specialist each (direct APIs)

Each runner gets its own ADK app_name, so sessions don't collide between them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, DatabaseSessionService, Session
from google.genai import types

from app.agents.coordinator import build_root_agent
from app.agents.specialists import SPECIALISTS
from app.core.config import Settings

log = logging.getLogger(__name__)

COORDINATOR = "coordinator"


class AgentNotFound(KeyError):
    pass


class SessionNotFound(KeyError):
    pass


class UpstreamLLMError(RuntimeError):
    """The model provider (OpenRouter via LiteLLM) failed: bad key, rate limit, outage, network."""


def _is_llm_error(exc: BaseException) -> bool:
    return type(exc).__module__.startswith("litellm") or "litellm" in str(exc)[:200].lower()


@dataclass
class ChatResult:
    session_id: str
    reply: str
    agents: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0


def _text_of(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(p.text for p in event.content.parts if p.text and not getattr(p, "thought", False))


class AgentService:
    def __init__(self, settings: Settings, session_service: BaseSessionService | None = None):
        self.settings = settings
        self.session_service = session_service or DatabaseSessionService(db_url=settings.session_db_url)
        self.runners: dict[str, Runner] = {}
        self._build_runners()

    # ---------- setup ----------
    def _app_name(self, agent_key: str) -> str:
        base = self.settings.adk_app_name
        return base if agent_key == COORDINATOR else f"{base}_{agent_key}"

    def _build_runners(self) -> None:
        self.runners[COORDINATOR] = Runner(
            app_name=self._app_name(COORDINATOR), agent=build_root_agent(), session_service=self.session_service
        )
        for key, factory in SPECIALISTS.items():
            self.runners[key] = Runner(app_name=self._app_name(key), agent=factory(), session_service=self.session_service)

    def agent_keys(self) -> list[str]:
        return list(self.runners)

    def describe_agents(self) -> list[dict[str, Any]]:
        out = []
        for key, runner in self.runners.items():
            agent = runner.agent
            out.append(
                {
                    "key": key,
                    "name": agent.name,
                    "description": agent.description,
                    "sub_agents": [a.name for a in getattr(agent, "sub_agents", [])],
                    "tools": [getattr(t, "__name__", getattr(t, "name", str(t))) for t in getattr(agent, "tools", [])],
                }
            )
        return out

    def _runner(self, agent_key: str) -> Runner:
        try:
            return self.runners[agent_key]
        except KeyError as e:
            raise AgentNotFound(agent_key) from e

    # ---------- sessions ----------
    async def create_session(self, agent_key: str, user_id: str, customer_id: str, session_id: str | None = None) -> Session:
        self._runner(agent_key)
        return await self.session_service.create_session(
            app_name=self._app_name(agent_key),
            user_id=user_id,
            session_id=session_id,
            state={"customer_id": customer_id, "user:customer_id": customer_id},
        )

    async def get_session(self, agent_key: str, user_id: str, session_id: str) -> Session:
        self._runner(agent_key)
        session = await self.session_service.get_session(
            app_name=self._app_name(agent_key), user_id=user_id, session_id=session_id
        )
        if session is None:
            raise SessionNotFound(session_id)
        return session

    async def list_sessions(self, agent_key: str, user_id: str) -> list[Session]:
        self._runner(agent_key)
        resp = await self.session_service.list_sessions(app_name=self._app_name(agent_key), user_id=user_id)
        return sorted(resp.sessions, key=lambda s: s.last_update_time, reverse=True)

    async def delete_session(self, agent_key: str, user_id: str, session_id: str) -> None:
        await self.get_session(agent_key, user_id, session_id)
        await self.session_service.delete_session(app_name=self._app_name(agent_key), user_id=user_id, session_id=session_id)

    async def _ensure_session(self, agent_key: str, user_id: str, session_id: str | None, customer_id: str) -> str:
        if session_id:
            try:
                await self.get_session(agent_key, user_id, session_id)
                return session_id
            except SessionNotFound:
                pass  # client sent an id we don't know (e.g. new instance) -> create it under that id
        session = await self.create_session(agent_key, user_id, customer_id, session_id=session_id)
        return session.id

    # ---------- running ----------
    async def chat(self, agent_key: str, user_id: str, message: str, session_id: str | None, customer_id: str) -> ChatResult:
        runner = self._runner(agent_key)
        sid = await self._ensure_session(agent_key, user_id, session_id, customer_id)
        started = time.perf_counter()
        result = ChatResult(session_id=sid, reply="")
        content = types.Content(role="user", parts=[types.Part(text=message)])

        try:
            async with asyncio.timeout(self.settings.agent_run_timeout_s):
                async for event in runner.run_async(user_id=user_id, session_id=sid, new_message=content):
                    self._collect(event, result)
                    if event.is_final_response() and _text_of(event):
                        result.reply = _text_of(event)
        except TimeoutError:
            raise
        except Exception as exc:
            if _is_llm_error(exc):
                log.error("LLM provider error: %s", exc, extra={"agent": agent_key, "session_id": sid})
                raise UpstreamLLMError(type(exc).__name__) from exc
            raise

        result.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if not result.reply:
            result.reply = "Sorry, I couldn't produce an answer. Please try rephrasing."
        log.info("chat done", extra={"agent": agent_key, "session_id": sid, "latency_ms": result.latency_ms})
        return result

    async def stream(
        self, agent_key: str, user_id: str, message: str, session_id: str | None, customer_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Yields UI-friendly events: session, agent, tool_call, tool_result, delta, final, done, error."""
        runner = self._runner(agent_key)
        sid = await self._ensure_session(agent_key, user_id, session_id, customer_id)
        yield {"type": "session", "session_id": sid}
        content = types.Content(role="user", parts=[types.Part(text=message)])
        run_config = RunConfig(streaming_mode=StreamingMode.SSE)
        current_agent = None
        final_text = ""
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self.settings.agent_run_timeout_s):
                async for event in runner.run_async(user_id=user_id, session_id=sid, new_message=content, run_config=run_config):
                    if event.author and event.author != "user" and event.author != current_agent:
                        current_agent = event.author
                        yield {"type": "agent", "agent": current_agent}
                    for call in event.get_function_calls():
                        yield {"type": "tool_call", "agent": event.author, "name": call.name, "args": call.args or {}}
                    for resp in event.get_function_responses():
                        status = resp.response.get("status") if isinstance(resp.response, dict) else None
                        yield {"type": "tool_result", "agent": event.author, "name": resp.name, "status": status}
                    text = _text_of(event)
                    if not text:
                        continue
                    if event.partial:
                        yield {"type": "delta", "agent": event.author, "text": text}
                    elif event.is_final_response():
                        final_text = text
                        yield {"type": "final", "agent": event.author, "text": text}
        except TimeoutError:
            yield {"type": "error", "message": "The assistant took too long to respond. Please try again."}
        except Exception as exc:  # surface to the UI instead of a dead stream
            log.exception("stream failed")
            msg = (
                "The language model provider returned an error. Check OPENROUTER_API_KEY and the model name."
                if _is_llm_error(exc)
                else f"Agent error: {exc.__class__.__name__}"
            )
            yield {"type": "error", "message": msg}
        if not final_text:
            log.warning("stream ended without final text", extra={"session_id": sid})
        yield {"type": "done", "latency_ms": round((time.perf_counter() - started) * 1000, 1)}

    @staticmethod
    def _collect(event: Event, result: ChatResult) -> None:
        if event.author and event.author != "user" and event.author not in result.agents:
            result.agents.append(event.author)
        for call in event.get_function_calls():
            result.tool_calls.append({"agent": event.author, "name": call.name, "args": call.args or {}})

    async def close(self) -> None:
        for runner in self.runners.values():
            try:
                await runner.close()
            except Exception:  # pragma: no cover - best effort on shutdown
                log.debug("runner close failed", exc_info=True)
