"""Product catalog tools used by the catalog agent.

ADK turns each function into a tool: the name, type hints and docstring become the
schema the LLM sees, so docstrings here are written for the model, not just humans.
Tools return plain dicts with a "status" key so the model can tell success from failure.
"""

from __future__ import annotations

from app.data.db import get_conn, rows_to_dicts


def search_products(query: str = "", category: str = "", max_price: float = 0.0, limit: int = 5) -> dict:
    """Search the product catalog.

    Args:
        query: Free-text keywords matched against product name, brand and description. Empty for any.
        category: Optional category filter. One of: electronics, home, apparel, grocery. Empty for all.
        max_price: Optional maximum price in USD. Use 0 for no limit.
        limit: Maximum number of results (1-10).

    Returns:
        dict with status and a list of matching products (sku, name, brand, price, rating, in_stock).
    """
    limit = max(1, min(int(limit or 5), 10))
    sql = "SELECT sku, name, brand, category, price, rating, stock FROM products WHERE 1=1"
    params: list = []
    for word in (query or "").split():
        sql += " AND (name LIKE ? OR brand LIKE ? OR description LIKE ? OR category LIKE ?)"
        like = f"%{word}%"
        params += [like, like, like, like]
    if category:
        sql += " AND category = ?"
        params.append(category.lower().strip())
    if max_price and max_price > 0:
        sql += " AND price <= ?"
        params.append(max_price)
    sql += " ORDER BY rating DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = rows_to_dicts(conn.execute(sql, params).fetchall())
    for r in rows:
        r["in_stock"] = r.pop("stock") > 0
    if not rows:
        return {"status": "not_found", "message": "No products matched. Try fewer or different keywords.", "products": []}
    return {"status": "success", "count": len(rows), "products": rows}


def get_product_details(sku: str) -> dict:
    """Get full details for one product by SKU (for example ELEC-1001).

    Args:
        sku: The product SKU.

    Returns:
        dict with status and the product's full record including description and stock level.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku.strip().upper(),)).fetchone()
    if not row:
        return {"status": "not_found", "message": f"No product with SKU {sku}."}
    return {"status": "success", "product": dict(row)}


def check_inventory(sku: str) -> dict:
    """Check how many units of a product are in stock.

    Args:
        sku: The product SKU.

    Returns:
        dict with status, units_available and an availability label.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT name, stock FROM products WHERE sku = ?", (sku.strip().upper(),)).fetchone()
    if not row:
        return {"status": "not_found", "message": f"No product with SKU {sku}."}
    stock = row["stock"]
    label = "out_of_stock" if stock == 0 else "low_stock" if stock < 10 else "in_stock"
    return {"status": "success", "sku": sku.upper(), "name": row["name"], "units_available": stock, "availability": label}
