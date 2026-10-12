"""Retail data store (SQLite).

This is the "system of record" the agents' tools talk to: products, customers,
orders, returns. It is deliberately separate from the ADK session database so you
can swap either one independently (e.g. real catalog API + Cloud SQL sessions).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.core.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku          TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    brand        TEXT NOT NULL,
    price        REAL NOT NULL,
    description  TEXT NOT NULL,
    rating       REAL NOT NULL DEFAULT 0,
    stock        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS customers (
    customer_id  TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL,
    tier         TEXT NOT NULL DEFAULT 'standard'
);
CREATE TABLE IF NOT EXISTS orders (
    order_id     TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    status       TEXT NOT NULL,          -- processing | shipped | delivered | cancelled
    created_at   TEXT NOT NULL,
    delivered_at TEXT,
    carrier      TEXT,
    tracking_no  TEXT,
    total        REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id     TEXT NOT NULL REFERENCES orders(order_id),
    sku          TEXT NOT NULL REFERENCES products(sku),
    quantity     INTEGER NOT NULL,
    unit_price   REAL NOT NULL,
    PRIMARY KEY (order_id, sku)
);
CREATE TABLE IF NOT EXISTS returns (
    return_id    TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL REFERENCES orders(order_id),
    sku          TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    refund_amount REAL NOT NULL,
    status       TEXT NOT NULL,          -- approved | pending_review | rejected
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
"""


def _db_path() -> str:
    path = get_settings().retail_db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Short-lived connection per call. SQLite connections are cheap and this keeps
    the tools thread-safe when ADK runs sync tools off the event loop."""
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]
