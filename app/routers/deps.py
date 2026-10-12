from __future__ import annotations

from fastapi import Request

from app.services.agent_service import AgentService


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service
