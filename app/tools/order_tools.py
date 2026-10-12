"""Order tools. The signed-in customer comes from ADK session state, never from the
model's arguments, so one customer can't ask the agent to read someone else's orders."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from google.adk.tools import ToolContext

from app.data.db import get_conn, rows_to_dicts


def _customer_id(tool_context: ToolContext) -> str | None:
    return tool_context.state.get("customer_id")


def _load_order(conn, order_id: str, customer_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM orders WHERE order_id = ? AND customer_id = ?", (order_id.strip().upper(), customer_id)
    ).fetchone()
    if not row:
        return None
    order = dict(row)
    order["items"] = rows_to_dicts(
        conn.execute(
            "SELECT oi.sku, p.name, oi.quantity, oi.unit_price FROM order_items oi "
            "JOIN products p ON p.sku = oi.sku WHERE oi.order_id = ?",
            (order["order_id"],),
        ).fetchall()
    )
    return order


def list_my_orders(tool_context: ToolContext) -> dict:
    """List the signed-in customer's orders, newest first.

    Returns:
        dict with status and a list of orders (order_id, status, created_at, total).
    """
    cid = _customer_id(tool_context)
    if not cid:
        return {"status": "error", "message": "No signed-in customer on this session."}
    with get_conn() as conn:
        rows = rows_to_dicts(
            conn.execute(
                "SELECT order_id, status, created_at, total FROM orders WHERE customer_id = ? ORDER BY created_at DESC",
                (cid,),
            ).fetchall()
        )
    return {"status": "success", "orders": rows}


def get_order_status(order_id: str, tool_context: ToolContext) -> dict:
    """Get status, items, carrier and tracking number for one of the customer's orders.

    Args:
        order_id: The order id, for example ORD-10001.

    Returns:
        dict with status and the full order.
    """
    cid = _customer_id(tool_context)
    if not cid:
        return {"status": "error", "message": "No signed-in customer on this session."}
    with get_conn() as conn:
        order = _load_order(conn, order_id, cid)
    if not order:
        return {"status": "not_found", "message": f"Order {order_id} was not found for this customer."}
    return {"status": "success", "order": order}


def place_order(sku: str, quantity: int, tool_context: ToolContext) -> dict:
    """Place a new order for the signed-in customer. Only call this after the customer
    has explicitly confirmed the product, quantity and price.

    Args:
        sku: Product SKU to buy.
        quantity: Number of units (1-10).

    Returns:
        dict with status and the created order id and total.
    """
    cid = _customer_id(tool_context)
    if not cid:
        return {"status": "error", "message": "No signed-in customer on this session."}
    quantity = int(quantity)
    if not 1 <= quantity <= 10:
        return {"status": "error", "message": "Quantity must be between 1 and 10."}
    with get_conn() as conn:
        product = conn.execute("SELECT sku, name, price, stock FROM products WHERE sku = ?", (sku.strip().upper(),)).fetchone()
        if not product:
            return {"status": "not_found", "message": f"No product with SKU {sku}."}
        # Conditional decrement = no overselling even with concurrent requests.
        cur = conn.execute(
            "UPDATE products SET stock = stock - ? WHERE sku = ? AND stock >= ?", (quantity, product["sku"], quantity)
        )
        if cur.rowcount == 0:
            return {"status": "error", "message": f"Only {product['stock']} unit(s) of {product['name']} in stock."}
        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        total = round(product["price"] * quantity, 2)
        conn.execute(
            "INSERT INTO orders (order_id, customer_id, status, created_at, total) VALUES (?,?,?,?,?)",
            (order_id, cid, "processing", datetime.now(UTC).isoformat(timespec="seconds"), total),
        )
        conn.execute("INSERT INTO order_items VALUES (?,?,?,?)", (order_id, product["sku"], quantity, product["price"]))
    tool_context.state["last_order_id"] = order_id
    return {"status": "success", "order_id": order_id, "product": product["name"], "quantity": quantity, "total": total}


def cancel_order(order_id: str, tool_context: ToolContext) -> dict:
    """Cancel one of the customer's orders. Only orders still in 'processing' can be cancelled.

    Args:
        order_id: The order id to cancel.

    Returns:
        dict with status and a message.
    """
    cid = _customer_id(tool_context)
    if not cid:
        return {"status": "error", "message": "No signed-in customer on this session."}
    with get_conn() as conn:
        order = _load_order(conn, order_id, cid)
        if not order:
            return {"status": "not_found", "message": f"Order {order_id} was not found for this customer."}
        if order["status"] != "processing":
            msg = f"Order is '{order['status']}' and can no longer be cancelled. Suggest a return instead."
            return {"status": "error", "message": msg}
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order["order_id"],))
        for item in order["items"]:
            conn.execute("UPDATE products SET stock = stock + ? WHERE sku = ?", (item["quantity"], item["sku"]))
    return {"status": "success", "message": f"Order {order['order_id']} cancelled and stock released."}
