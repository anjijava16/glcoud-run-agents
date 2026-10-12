"""Main chat API: talks to the coordinator, which routes to specialists.

POST /api/v1/chat          -> one JSON response when the turn is finished
POST /api/v1/chat/stream   -> Server-Sent Events (what the web UI uses)
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.routers.deps import get_agent_service
from app.schemas import ChatRequest, ChatResponse
from app.services.agent_service import COORDINATOR, AgentService, UpstreamLLMError

router = APIRouter(prefix="/chat", tags=["chat"])


def sse_response(gen) -> StreamingResponse:
    async def frames():
        async for evt in gen:
            yield f"event: {evt['type']}\ndata: {json.dumps(evt, default=str)}\n\n"

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        # X-Accel-Buffering stops proxies buffering the stream; Cloud Run streams fine.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, svc: AgentService = Depends(get_agent_service)):
    try:
        result = await svc.chat(COORDINATOR, req.user_id, req.message, req.session_id, req.customer_id)
    except TimeoutError as e:
        raise HTTPException(504, "Agent run timed out") from e
    except UpstreamLLMError as e:
        raise HTTPException(502, f"LLM provider error ({e}). Check OPENROUTER_API_KEY and the model name.") from e
    return ChatResponse(**result.__dict__)


@router.post("/stream")
async def chat_stream(req: ChatRequest, svc: AgentService = Depends(get_agent_service)):
    return sse_response(svc.stream(COORDINATOR, req.user_id, req.message, req.session_id, req.customer_id))
