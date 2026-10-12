"""Demo data so the app is usable the moment it boots.

Order dates are relative to "now", which keeps the 30-day return window demo
working no matter when you run it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.data.db import get_conn, init_db

log = logging.getLogger(__name__)

PRODUCTS = [
    # sku, name, category, brand, price, description, rating, stock
    (
        "ELEC-1001",
        "Aurora Noise-Cancelling Headphones",
        "electronics",
        "Aurora",
        249.99,
        "Over-ear wireless headphones, 35h battery, adaptive ANC, USB-C fast charge.",
        4.6,
        42,
    ),
    (
        "ELEC-1002",
        "Pulse Mini Bluetooth Speaker",
        "electronics",
        "Pulse",
        59.99,
        "Waterproof IP67 pocket speaker, 12h battery, pairs two units for stereo.",
        4.3,
        120,
    ),
    (
        "ELEC-1003",
        'Vertex 14" Ultrabook',
        "electronics",
        "Vertex",
        1199.00,
        "14-inch 2.8K OLED laptop, 16GB RAM, 1TB SSD, 1.2kg aluminium chassis.",
        4.7,
        8,
    ),
    (
        "ELEC-1004",
        "Orbit Smartwatch S2",
        "electronics",
        "Orbit",
        329.00,
        "AMOLED smartwatch with GPS, heart-rate, sleep tracking and 7-day battery.",
        4.4,
        0,
    ),
    (
        "HOME-2001",
        "Brewmaster Pour-Over Coffee Kit",
        "home",
        "Brewmaster",
        79.50,
        "Gooseneck kettle, ceramic dripper, 100 filters and a glass carafe.",
        4.8,
        35,
    ),
    (
        "HOME-2002",
        "CloudRest Memory Foam Pillow",
        "home",
        "CloudRest",
        45.00,
        "Cooling gel memory foam pillow, removable bamboo cover, medium-firm.",
        4.2,
        200,
    ),
    (
        "HOME-2003",
        'Ember Cast Iron Skillet 12"',
        "home",
        "Ember",
        39.99,
        "Pre-seasoned 12-inch cast iron skillet, oven safe to 260C.",
        4.9,
        64,
    ),
    (
        "APP-3001",
        "TrailFlex Running Shoes",
        "apparel",
        "TrailFlex",
        129.00,
        "Lightweight trail running shoe, rock plate, sizes 6-13.",
        4.5,
        55,
    ),
    (
        "APP-3002",
        "Nimbus Rain Jacket",
        "apparel",
        "Nimbus",
        159.00,
        "Packable 3-layer waterproof breathable shell with pit zips.",
        4.6,
        22,
    ),
    ("APP-3003", "Merino Everyday Crew Tee", "apparel", "Woolly", 48.00, "Odour-resistant 150gsm merino wool t-shirt.", 4.4, 90),
    (
        "GROC-4001",
        "Single-Origin Ethiopian Coffee Beans 1kg",
        "grocery",
        "Highland",
        32.00,
        "Washed Yirgacheffe, light roast, notes of jasmine and citrus.",
        4.7,
        150,
    ),
    (
        "GROC-4002",
        "Organic Matcha Powder 100g",
        "grocery",
        "Kyoto Leaf",
        24.50,
        "Ceremonial grade stone-ground matcha from Uji.",
        4.5,
        75,
    ),
]

CUSTOMERS = [
    ("CUST-001", "Maya Patel", "maya@example.com", "gold"),
    ("CUST-002", "Daniel Kim", "daniel@example.com", "standard"),
    ("CUST-003", "Sofia Rossi", "sofia@example.com", "platinum"),
]


def _orders(now: datetime):
    d = lambda days: (now - timedelta(days=days)).isoformat(timespec="seconds")  # noqa: E731
    # order_id, customer, status, created, delivered, carrier, tracking, items[(sku, qty, price)]
    return [
        (
            "ORD-10001",
            "CUST-001",
            "delivered",
            d(12),
            d(9),
            "UPS",
            "1Z999AA10123456784",
            [("ELEC-1001", 1, 249.99), ("GROC-4001", 2, 32.00)],
        ),
        ("ORD-10002", "CUST-001", "shipped", d(3), None, "FedEx", "7712 3456 7890", [("APP-3001", 1, 129.00)]),
        ("ORD-10003", "CUST-001", "delivered", d(55), d(50), "USPS", "9400 1000 0000 0000 0000 00", [("HOME-2003", 1, 39.99)]),
        ("ORD-10004", "CUST-002", "processing", d(0), None, None, None, [("HOME-2001", 1, 79.50), ("HOME-2002", 2, 45.00)]),
        ("ORD-10005", "CUST-003", "delivered", d(6), d(2), "UPS", "1Z999AA10987654321", [("ELEC-1003", 1, 1199.00)]),
    ]


def seed_if_empty() -> bool:
    init_db()
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
            return False
        conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?)", PRODUCTS)
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?)", CUSTOMERS)
        for oid, cust, status, created, delivered, carrier, tracking, items in _orders(datetime.now(UTC)):
            total = round(sum(q * p for _, q, p in items), 2)
            conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)",
                (oid, cust, status, created, delivered, carrier, tracking, total),
            )
            conn.executemany("INSERT INTO order_items VALUES (?,?,?,?)", [(oid, s, q, p) for s, q, p in items])
    log.info("Seeded retail demo data")
    return True
