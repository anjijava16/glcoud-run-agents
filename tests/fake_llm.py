"""A scripted stand-in for the real LLM so tests run offline, free and deterministically,
while still exercising the real ADK machinery: Runner, transfers, tool execution,
DatabaseSessionService persistence and SSE streaming.

Behaviour, decided from which tools ADK put on the request:
  coordinator (has transfer_to_agent, no domain tools) -> transfer to a specialist
                                                          picked by keyword
  specialist, no tool result yet                       -> call its first domain tool
  specialist, after a tool result                      -> answer in text
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

ROUTES = {
    "return": "returns_agent",
    "refund": "returns_agent",
    "order": "order_agent",
    "policy": "support_agent",
    "shipping": "support_agent",
}

TOOL_PLAN = {
    "search_products": {"query": "headphones"},
    "list_my_orders": {},
    "check_return_eligibility": {"order_id": "ORD-10001"},
    "get_store_policy": {"topic": "shipping"},
}


def _last_user_text(req: LlmRequest) -> str:
    for c in reversed(req.contents or []):
        if c.role == "user" and c.parts and any(p.text for p in c.parts):
            return " ".join(p.text or "" for p in c.parts).lower()
    return ""


def _last_function_response(req: LlmRequest):
    if not req.contents:
        return None
    last = req.contents[-1]
    for p in last.parts or []:
        if p.function_response:
            return p.function_response
    return None


class FakeLlm(BaseLlm):
    model: str = "fake-llm"

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        tools = set((llm_request.tools_dict or {}).keys())
        domain_tools = [t for t in TOOL_PLAN if t in tools]
        fr = _last_function_response(llm_request)

        if fr is not None and fr.name != "transfer_to_agent":
            text = f"Here is what I found via {fr.name}: status={fr.response.get('status')}."
            if stream:
                half = len(text) // 2
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text[:half])]), partial=True)
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text[half:])]), partial=True)
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]), turn_complete=True)
            return

        if domain_tools:
            name = domain_tools[0]
            call = types.FunctionCall(name=name, args=TOOL_PLAN[name])
        elif "transfer_to_agent" in tools:
            msg = _last_user_text(llm_request)
            target = next((agent for kw, agent in ROUTES.items() if kw in msg), "catalog_agent")
            call = types.FunctionCall(name="transfer_to_agent", args={"agent_name": target})
        else:
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="Hello!")]))
            return
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]))
