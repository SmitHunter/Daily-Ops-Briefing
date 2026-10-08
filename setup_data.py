"""
Data pipeline orchestrator. Runs on startup to ensure the SQLite DB exists
and contains fresh data. Idempotent - safe to run repeatedly.

If data/pos.db exists, exits immediately. Otherwise runs:
  1. generate_transactions.py -> data/transactions.json (deterministic via seed)
  2. build_db.py -> data/pos.db (SQLite from JSON)

Reason for this design: keeps the repo small (source JSON only; the SQLite
DB is built at deploy time). DB is built deterministically from a fixed
random seed so every deploy produces identical data - useful for testing
and demos.
"""

import os
import subprocess
import sys

DB_PATH = "data/pos.db"

if os.path.exists(DB_PATH):
    print(f"{DB_PATH} already exists, skipping setup.", flush=True)
    sys.exit(0)

print("Building POS dataset...", flush=True)

# stores.json and products.json are committed to the repo.
# transactions.json is generated, then DB is built, then JSON is removed.
steps = [
    [sys.executable, "generate_transactions.py"],
    [sys.executable, "build_db.py"],
]

for cmd in steps:
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"Step failed: {' '.join(cmd)}", flush=True)
        sys.exit(1)

# Clean up the intermediate JSON
if os.path.exists("data/transactions.json"):
    os.remove("data/transactions.json")
    print("\nRemoved intermediate data/transactions.json", flush=True)

size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
print(f"\nSetup complete. {DB_PATH} ready ({size_mb:.1f} MB).", flush=True)
