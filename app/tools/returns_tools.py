"""Returns and refunds tools, with a simple human-in-the-loop rule: big refunds
go to 'pending_review' instead of being auto-approved."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from google.adk.tools import ToolContext

from app.core.config import get_settings
from app.data.db import get_conn


def _days_since(iso_ts: str) -> int:
    ts = datetime.fromisoformat(iso_ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).days


def check_return_eligibility(order_id: str, tool_context: ToolContext) -> dict:
    """Check whether an order can be returned. Orders must be delivered and within the return window.

    Args:
        order_id: The order id, for example ORD-10001.

    Returns:
        dict with status, eligible (bool), days_since_delivery, window_days and the returnable items.
    """
    cid = tool_context.state.get("customer_id")
    if not cid:
        return {"status": "error", "message": "No signed-in customer on this session."}
    window = get_settings().return_window_days
    with get_conn() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND customer_id = ?", (order_id.strip().upper(), cid)
        ).fetchone()
        if not order:
            return {"status": "not_found", "message": f"Order {order_id} was not found for this customer."}
        items = [
            dict(r)
            for r in conn.execute(
                "SELECT oi.sku, p.name, oi.quantity, oi.unit_price FROM order_items oi "
                "JOIN products p ON p.sku = oi.sku WHERE oi.order_id = ?",
                (order["order_id"],),
            ).fetchall()
        ]
    if order["status"] != "delivered" or not order["delivered_at"]:
        return {"status": "success", "eligible": False, "reason": f"Order is '{order['status']}', not delivered yet."}
    days = _days_since(order["delivered_at"])
    eligible = days <= window
    return {
        "status": "success",
        "eligible": eligible,
        "days_since_delivery": days,
        "window_days": window,
        "reason": "Within return window." if eligible else f"Delivered {days} days ago, outside the {window}-day window.",
        "items": items,
    }


def initiate_return(order_id: str, sku: str, quantity: int, reason: str, tool_context: ToolContext) -> dict:
    """Create a return and refund request for an item from a delivered order.
    Call check_return_eligibility first and confirm the item and reason with the customer.

    Args:
        order_id: The order id.
        sku: SKU of the item being returned.
        quantity: Number of units to return.
        reason: Short reason given by the customer (e.g. 'defective', 'wrong size').

    Returns:
        dict with status, return_id, refund_amount and return status (approved or pending_review).
    """
    eligibility = check_return_eligibility(order_id, tool_context)
    if eligibility.get("status") != "success":
        return eligibility
    if not eligibility["eligible"]:
        return {"status": "error", "message": eligibility["reason"]}
    item = next((i for i in eligibility["items"] if i["sku"] == sku.strip().upper()), None)
    if not item:
        return {"status": "error", "message": f"SKU {sku} is not part of order {order_id}."}
    quantity = int(quantity)
    with get_conn() as conn:
        already = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM returns WHERE order_id = ? AND sku = ? AND status != 'rejected'",
            (order_id.upper(), item["sku"]),
        ).fetchone()[0]
        if quantity < 1 or quantity + already > item["quantity"]:
            return {"status": "error", "message": f"Can return at most {item['quantity'] - already} unit(s) of this item."}
        refund = round(item["unit_price"] * quantity, 2)
        limit = get_settings().refund_auto_approve_limit
        return_status = "approved" if refund <= limit else "pending_review"
        return_id = f"RET-{uuid.uuid4().hex[:8].upper()}"
        conn.execute(
            "INSERT INTO returns VALUES (?,?,?,?,?,?,?,?)",
            (
                return_id,
                order_id.upper(),
                item["sku"],
                quantity,
                reason[:200],
                refund,
                return_status,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
    note = (
        "Refund approved. A prepaid return label has been emailed; refund lands 3-5 business days after we receive it."
        if return_status == "approved"
        else f"Refunds over ${limit:.0f} need a quick human review (usually under 24h). The customer will get an email."
    )
    return {"status": "success", "return_id": return_id, "refund_amount": refund, "return_status": return_status, "note": note}
