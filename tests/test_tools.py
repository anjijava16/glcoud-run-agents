"""Unit tests for the tool functions (no LLM involved)."""

from __future__ import annotations

import pytest


class FakeToolContext:
    """Just enough of ADK's ToolContext for the tools: a state dict and an agent name."""

    def __init__(self, customer_id: str | None = "CUST-001"):
        self.state = {"customer_id": customer_id} if customer_id else {}
        self.agent_name = "test"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("RETAIL_DB_PATH", str(tmp_path / "retail.db"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.data.seed import seed_if_empty

    seed_if_empty()
    yield
    get_settings.cache_clear()


def test_search_and_filters():
    from app.tools.catalog_tools import search_products

    res = search_products("headphones")
    assert res["status"] == "success" and res["products"][0]["sku"] == "ELEC-1001"
    cheap = search_products(category="electronics", max_price=100)
    assert [p["sku"] for p in cheap["products"]] == ["ELEC-1002"]
    assert search_products("unicorn")["status"] == "not_found"


def test_inventory_labels():
    from app.tools.catalog_tools import check_inventory

    assert check_inventory("ELEC-1004")["availability"] == "out_of_stock"
    assert check_inventory("ELEC-1003")["availability"] == "low_stock"


def test_orders_are_scoped_to_customer():
    from app.tools.order_tools import get_order_status, list_my_orders

    assert {o["order_id"] for o in list_my_orders(FakeToolContext())["orders"]} == {"ORD-10001", "ORD-10002", "ORD-10003"}
    # CUST-002 must not see CUST-001's order
    assert get_order_status("ORD-10001", FakeToolContext("CUST-002"))["status"] == "not_found"
    assert list_my_orders(FakeToolContext(None))["status"] == "error"


def test_place_and_cancel_order_updates_stock():
    from app.tools.catalog_tools import check_inventory
    from app.tools.order_tools import cancel_order, place_order

    ctx = FakeToolContext()
    before = check_inventory("HOME-2001")["units_available"]
    placed = place_order("HOME-2001", 2, ctx)
    assert placed["status"] == "success" and placed["total"] == 159.0
    assert check_inventory("HOME-2001")["units_available"] == before - 2
    assert ctx.state["last_order_id"] == placed["order_id"]
    assert cancel_order(placed["order_id"], ctx)["status"] == "success"
    assert check_inventory("HOME-2001")["units_available"] == before


def test_cannot_oversell_or_cancel_shipped():
    from app.tools.order_tools import cancel_order, place_order

    assert place_order("ELEC-1004", 1, FakeToolContext())["status"] == "error"  # out of stock
    assert cancel_order("ORD-10002", FakeToolContext())["status"] == "error"  # already shipped


def test_returns_window_and_human_review():
    from app.tools.returns_tools import check_return_eligibility, initiate_return

    ctx = FakeToolContext()
    assert check_return_eligibility("ORD-10001", ctx)["eligible"] is True
    assert check_return_eligibility("ORD-10003", ctx)["eligible"] is False  # 50 days ago
    ok = initiate_return("ORD-10001", "ELEC-1001", 1, "too tight", ctx)
    assert ok["return_status"] == "approved" and ok["refund_amount"] == 249.99
    # can't return the same unit twice
    assert initiate_return("ORD-10001", "ELEC-1001", 1, "again", ctx)["status"] == "error"

    big = initiate_return("ORD-10005", "ELEC-1003", 1, "defective", FakeToolContext("CUST-003"))
    assert big["return_status"] == "pending_review"  # $1199 > $500 limit


def test_policy_lookup():
    from app.tools.policy_tools import get_store_policy

    assert get_store_policy("Price Match")["status"] == "success"
    assert "available_topics" in get_store_policy("nonsense")
