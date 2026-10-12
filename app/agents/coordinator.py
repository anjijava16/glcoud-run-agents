"""Root agent: the coordinator that routes to specialists.

ADK "LLM-driven delegation": the coordinator has `sub_agents`, and ADK gives it an
automatic `transfer_to_agent` tool. The model picks a specialist based on each
sub-agent's `description`; control moves to that specialist, which can transfer
again (e.g. catalog -> orders when the customer decides to buy).
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from app.agents import prompts
from app.agents.callbacks import input_guardrail
from app.agents.model import build_model
from app.agents.specialists import (
    build_catalog_agent,
    build_order_agent,
    build_returns_agent,
    build_support_agent,
)


def build_root_agent() -> LlmAgent:
    return LlmAgent(
        name="retail_coordinator",
        description="Front-desk coordinator that routes customers to the right retail specialist.",
        model=build_model("root"),
        instruction=prompts.ROOT,
        sub_agents=[
            build_catalog_agent(),
            build_order_agent(),
            build_returns_agent(),
            build_support_agent(),
        ],
        before_model_callback=input_guardrail,
    )
