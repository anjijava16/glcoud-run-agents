"""Specialist agent factories.

Each function returns a *new* agent instance. That matters: an ADK agent can have
only one parent, so the coordinator tree and the direct-to-specialist APIs each need
their own copies.
"""

from __future__ import annotations

from collections.abc import Callable

from google.adk.agents import LlmAgent

from app.agents import prompts
from app.agents.callbacks import after_tool, before_tool, input_guardrail
from app.agents.model import build_model
from app.tools.catalog_tools import check_inventory, get_product_details, search_products
from app.tools.order_tools import cancel_order, get_order_status, list_my_orders, place_order
from app.tools.policy_tools import get_store_policy
from app.tools.returns_tools import check_return_eligibility, initiate_return


def _agent(name: str, description: str, instruction: str, tools: list, output_key: str) -> LlmAgent:
    return LlmAgent(
        name=name,
        description=description,  # the coordinator reads this when deciding where to route
        model=build_model("specialist"),
        instruction=instruction,
        tools=tools,
        output_key=output_key,  # last reply saved to session state for other agents/APIs
        before_model_callback=input_guardrail,
        before_tool_callback=before_tool,
        after_tool_callback=after_tool,
    )


def build_catalog_agent() -> LlmAgent:
    return _agent(
        "catalog_agent",
        "Finds products, gives product details and checks stock.",
        prompts.CATALOG,
        [search_products, get_product_details, check_inventory],
        "last_catalog_reply",
    )


def build_order_agent() -> LlmAgent:
    return _agent(
        "order_agent",
        "Handles the signed-in customer's orders: status, tracking, placing and cancelling.",
        prompts.ORDERS,
        [list_my_orders, get_order_status, place_order, cancel_order],
        "last_order_reply",
    )


def build_returns_agent() -> LlmAgent:
    return _agent(
        "returns_agent",
        "Checks return eligibility and creates returns and refunds.",
        prompts.RETURNS,
        [check_return_eligibility, initiate_return],
        "last_returns_reply",
    )


def build_support_agent() -> LlmAgent:
    return _agent(
        "support_agent",
        "Answers store policy questions: shipping, warranty, price match, loyalty, payment, contact.",
        prompts.SUPPORT,
        [get_store_policy],
        "last_support_reply",
    )


SPECIALISTS: dict[str, Callable[[], LlmAgent]] = {
    "catalog": build_catalog_agent,
    "orders": build_order_agent,
    "returns": build_returns_agent,
    "support": build_support_agent,
}
