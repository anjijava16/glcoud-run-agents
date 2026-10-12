"""Plain REST data APIs (no LLM). The UI uses these for the customer picker, and they
are handy for checking what the agents' tools will see."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.data.db import get_conn, rows_to_dicts
from app.tools.catalog_tools import get_product_details, search_products

router = APIRouter(tags=["retail-data"])


@router.get("/products")
async def products(q: str = "", category: str = "", max_price: float = 0, limit: int = Query(10, le=10)):
    return search_products(q, category, max_price, limit)


@router.get("/products/{sku}")
async def product(sku: str):
    res = get_product_details(sku)
    if res["status"] != "success":
        raise HTTPException(404, res["message"])
    return res["product"]


@router.get("/customers")
async def customers():
    with get_conn() as conn:
        return rows_to_dicts(conn.execute("SELECT customer_id, name, tier FROM customers ORDER BY customer_id"))


@router.get("/customers/{customer_id}/orders")
async def customer_orders(customer_id: str):
    with get_conn() as conn:
        return rows_to_dicts(
            conn.execute(
                "SELECT order_id, status, created_at, total FROM orders WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            )
        )


@router.get("/returns")
async def returns(status: str = ""):
    sql, params = "SELECT * FROM returns", []
    if status:
        sql, params = sql + " WHERE status = ?", [status]
    with get_conn() as conn:
        return rows_to_dicts(conn.execute(sql + " ORDER BY created_at DESC LIMIT 100", params))
