"""Direct agent APIs: call one specialist without going through the coordinator.

Useful for other services (e.g. an order-tracking widget only needs the order agent),
for evaluating a single agent in isolation, and for debugging routing problems.

GET  /api/v1/agents                      -> list agents, tools, sub-agents
POST /api/v1/agents/{agent}/chat         -> JSON
POST /api/v1/agents/{agent}/chat/stream  -> SSE
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.routers.chat import sse_response
from app.routers.deps import get_agent_service
from app.schemas import AgentInfo, ChatRequest, ChatResponse
from app.services.agent_service import AgentNotFound, AgentService, UpstreamLLMError

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentInfo])
async def list_agents(svc: AgentService = Depends(get_agent_service)):
    return svc.describe_agents()


@router.post("/{agent}/chat", response_model=ChatResponse)
async def agent_chat(agent: str, req: ChatRequest, svc: AgentService = Depends(get_agent_service)):
    try:
        result = await svc.chat(agent, req.user_id, req.message, req.session_id, req.customer_id)
    except AgentNotFound:
        raise HTTPException(404, f"Unknown agent '{agent}'. Options: {svc.agent_keys()}")
    except TimeoutError as e:
        raise HTTPException(504, "Agent run timed out") from e
    except UpstreamLLMError as e:
        raise HTTPException(502, f"LLM provider error ({e}). Check OPENROUTER_API_KEY and the model name.") from e
    return ChatResponse(**result.__dict__)


@router.post("/{agent}/chat/stream")
async def agent_chat_stream(agent: str, req: ChatRequest, svc: AgentService = Depends(get_agent_service)):
    if agent not in svc.agent_keys():
        raise HTTPException(404, f"Unknown agent '{agent}'. Options: {svc.agent_keys()}")
    return sse_response(svc.stream(agent, req.user_id, req.message, req.session_id, req.customer_id))
