"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a minimal test database for tool tests."""
    db_path = tmp_path_factory.mktemp("data") / "pos.db"

    conn = sqlite3.connect(str(db_path))
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
            line_total REAL NOT NULL
        );

        CREATE INDEX idx_tx_store_date ON transactions(store_id, date);
        CREATE INDEX idx_tx_date ON transactions(date);
    """)

    # Insert test stores
    stores = [
        ("ST001", "Test Flagship", "East", "flagship", "2020-01-01", 20000),
        ("ST002", "Test Standard", "West", "standard", "2021-01-01", 15000),
        ("ST003", "Test Small", "North", "small", "2022-01-01", 10000),
    ]
    c.executemany("INSERT INTO stores VALUES (?,?,?,?,?,?)", stores)

    # Insert test products
    products = [
        ("41001", "Test Wrap", "Wraps", 9.00, 10.50, 2.50),
        ("41002", "Test Coffee", "Coffee", 4.50, 6.00, 1.00),
        ("41003", "Test Salad", "Salads", 11.00, 12.50, 3.50),
    ]
    c.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", products)

    # Insert test transactions for the last 14 days
    tx_id = 1
    for day_offset in range(14):
        date = f"2026-04-{17 + day_offset:02d}"
        for store_id in ["ST001", "ST002", "ST003"]:
            for _ in range(10):  # 10 transactions per store per day
                c.execute(
                    "INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"TX{tx_id:08d}",
                        store_id,
                        date,
                        "in_store",
                        "41001",
                        "Test Wrap",
                        "Wraps",
                        2,
                        4.90,
                        0.98,
                        9.80,
                    ),
                )
                tx_id += 1

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_db_path(test_db_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch tools.DB_PATH to use test database."""
    import tools

    monkeypatch.setattr(tools, "DB_PATH", str(test_db_path))
    return test_db_path


@pytest.fixture
def mock_today() -> Generator[str, None, None]:
    """Mock agents._today to return a fixed date.

    This prevents agent tests from querying the database (which doesn't exist in CI).
    Returns "2026-04-30" to match the test database date range (2026-04-17 to 2026-04-30).
    """
    with patch("agents._today", return_value="2026-04-30"):
        yield "2026-04-30"


@pytest.fixture
def sample_analyst_findings() -> dict[str, Any]:
    """Sample analyst output for testing."""
    return {
        "headline": "Network performing at 105% of target this week",
        "findings": [
            {
                "title": "Westbridge under target by 18%",
                "severity": "high",
                "category": "store_performance",
                "evidence": {
                    "store_id": "ST008",
                    "actual": 11885,
                    "target": 14500,
                    "variance_pct": -18.0,
                    "days_under_target": 6,
                },
                "interpretation": "Sustained underperformance over the past week. Not a one-off.",
                "recommended_action": "Check in with store manager",
            },
            {
                "title": "Coffee category up 12%",
                "severity": "low",
                "category": "trend",
                "evidence": {
                    "revenue": 45000,
                    "wow_change_pct": 12.0,
                },
                "interpretation": "Coffee sales showing healthy growth network-wide.",
                "recommended_action": None,
            },
        ],
        "stats": {
            "stores_above_target": 28,
            "stores_below_target": 3,
            "network_revenue": 475000,
            "network_target": 452381,
            "variance_pct": 5.0,
        },
    }


@pytest.fixture
def mock_anthropic_client() -> Generator[MagicMock, None, None]:
    """Mock the Anthropic client for offline testing."""
    with patch("agents.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        yield mock_client


def create_mock_response(
    content: list[Any],
    stop_reason: str = "end_turn",
) -> MagicMock:
    """Helper to create a mock Claude response."""
    mock_response = MagicMock()
    mock_response.stop_reason = stop_reason
    mock_response.content = content
    return mock_response


def create_text_block(text: str) -> MagicMock:
    """Helper to create a mock text content block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def create_tool_use_block(tool_id: str, name: str, input_data: dict[str, Any]) -> MagicMock:
    """Helper to create a mock tool_use content block."""
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block
