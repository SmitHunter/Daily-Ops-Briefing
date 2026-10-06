"""
Load JSON data into a SQLite database for fast indexed queries.
Run after generate_transactions.py.
"""

import json
import os
import sqlite3

DB_PATH = "data/pos.db"

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.executescript("""
CREATE TABLE stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    tier TEXT NOT NULL,
    opened TEXT NOT NULL,
    weekly_target INTEGER NOT NULL
);

CREATE TABLE products (
    plu TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    price_delivery REAL,
    unit_cost REAL NOT NULL
);

CREATE TABLE transactions (
    transaction_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    date TEXT NOT NULL,
    channel TEXT NOT NULL,
    plu TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    unit_cost REAL NOT NULL,
    line_total REAL NOT NULL,
    FOREIGN KEY (store_id) REFERENCES stores(id),
    FOREIGN KEY (plu) REFERENCES products(plu)
);

CREATE INDEX idx_tx_store_date ON transactions(store_id, date);
CREATE INDEX idx_tx_date ON transactions(date);
CREATE INDEX idx_tx_category ON transactions(category);
CREATE INDEX idx_tx_plu ON transactions(plu);
""")

with open("data/stores.json") as f:
    stores = json.load(f)
c.executemany(
    "INSERT INTO stores VALUES (?,?,?,?,?,?)",
    [(s["id"], s["name"], s["region"], s["tier"], s["opened"], s["weekly_target"]) for s in stores],
)

with open("data/products.json") as f:
    products = json.load(f)
c.executemany(
    "INSERT INTO products VALUES (?,?,?,?,?,?)",
    [(p["plu"], p["name"], p["category"], p["price"], p.get("price_delivery"), p["unit_cost"]) for p in products],
)

with open("data/transactions.json") as f:
    txs = json.load(f)

print(f"Inserting {len(txs):,} transactions...")
c.executemany(
    "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
    [
        (
            t["transaction_id"],
            t["store_id"],
            t["date"],
            t["channel"],
            t["plu"],
            t["product_name"],
            t["category"],
            t["quantity"],
            t["unit_price"],
            t["unit_cost"],
            t["line_total"],
        )
        for t in txs
    ],
)

conn.commit()
conn.close()

size = os.path.getsize(DB_PATH)
print(f"Database written: {DB_PATH}  ({size / 1024 / 1024:.1f} MB)")
