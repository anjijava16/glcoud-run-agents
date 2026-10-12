"""Session APIs backed by ADK's DatabaseSessionService (SQLite by default).

A session = one conversation thread: its state (customer_id, last replies...) and the
full event history. The UI uses these to show the sidebar and reload old chats.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.routers.deps import get_agent_service
from app.schemas import Message, SessionCreate, SessionDetail, SessionSummary
from app.services.agent_service import COORDINATOR, AgentNotFound, AgentService, SessionNotFound

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _public_state(state: dict) -> dict:
    # Hide ADK-internal/temp keys from API consumers.
    return {k: v for k, v in state.items() if not k.startswith(("temp:", "_adk"))}


def _messages(session) -> list[Message]:
    out: list[Message] = []
    for ev in session.events:
        if not ev.content or not ev.content.parts:
            continue
        text = "".join(p.text for p in ev.content.parts if p.text and not getattr(p, "thought", False))
        if text and not ev.partial:
            role = "user" if ev.author == "user" else "assistant"
            out.append(Message(role=role, author=ev.author, text=text, timestamp=ev.timestamp))
    return out


def _title(session) -> str | None:
    for m in _messages(session):
        if m.role == "user":
            return m.text[:60]
    return None


@router.post("", response_model=SessionSummary, status_code=201)
async def create_session(body: SessionCreate, svc: AgentService = Depends(get_agent_service)):
    try:
        s = await svc.create_session(body.agent, body.user_id, body.customer_id)
    except AgentNotFound:
        raise HTTPException(404, f"Unknown agent '{body.agent}'")
    return SessionSummary(
        session_id=s.id, app_name=s.app_name, user_id=s.user_id, last_update_time=s.last_update_time, state=_public_state(s.state)
    )


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    user_id: str = Query(...), agent: str = Query(COORDINATOR), svc: AgentService = Depends(get_agent_service)
):
    try:
        sessions = await svc.list_sessions(agent, user_id)
    except AgentNotFound:
        raise HTTPException(404, f"Unknown agent '{agent}'")
    out = []
    for s in sessions:
        # list_sessions doesn't load events; fetch each for a title (fine at demo scale).
        full = await svc.get_session(agent, user_id, s.id)
        out.append(
            SessionSummary(
                session_id=s.id,
                app_name=s.app_name,
                user_id=s.user_id,
                last_update_time=s.last_update_time,
                title=_title(full),
                state=_public_state(full.state),
            )
        )
    return out


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str, user_id: str = Query(...), agent: str = Query(COORDINATOR), svc: AgentService = Depends(get_agent_service)
):
    try:
        s = await svc.get_session(agent, user_id, session_id)
    except (AgentNotFound, SessionNotFound):
        raise HTTPException(404, "Session not found")
    return SessionDetail(
        session_id=s.id,
        app_name=s.app_name,
        user_id=s.user_id,
        last_update_time=s.last_update_time,
        title=_title(s),
        state=_public_state(s.state),
        messages=_messages(s),
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str, user_id: str = Query(...), agent: str = Query(COORDINATOR), svc: AgentService = Depends(get_agent_service)
):
    try:
        await svc.delete_session(agent, user_id, session_id)
    except (AgentNotFound, SessionNotFound):
        raise HTTPException(404, "Session not found")
    return Response(status_code=204)
