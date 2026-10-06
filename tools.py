"""
Analyst Agent tools.

Each function is a tool that the Analyst can call. They query the SQLite
database and return structured JSON. The Analyst is responsible for choosing
which tools to call, in what order, and how to interpret the results into
prioritised findings.

Design principles:
  - Tools return data, not opinions. Severity, prioritisation, and synthesis
    are the agent's job.
  - Each tool has a tight, well-described schema. Tool description quality
    affects routing more than prompt tuning.
  - Tools are composable: the agent can chain them (list_stores -> get_store_revenue)
    when it needs to resolve a name to an ID.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

DB_PATH = "data/pos.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_iso_date(value: str, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date YYYY-MM-DD") from exc


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, parsed))


# ============================================================================
# Tool implementations
# ============================================================================


def list_stores() -> dict[str, Any]:
    """Return all 31 stores with metadata. Used when the agent needs to look up
    a store_id from a store name."""
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id, name, region, tier, opened, weekly_target
            FROM stores ORDER BY tier, name
        """).fetchall()
    return {
        "stores": [dict(r) for r in rows],
        "count": len(rows),
    }


def network_summary(start_date: str, end_date: str) -> dict[str, Any]:
    """High-level network performance for a date range.

    Returns total revenue, target, variance, breakdown by tier and region,
    and channel mix. This is typically the agent's first call - it gives a
    macro picture that informs which other tools to invoke.
    """
    _parse_iso_date(start_date, "start_date")
    _parse_iso_date(end_date, "end_date")
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT
              SUM(t.line_total) as actual,
              COUNT(DISTINCT t.store_id) as active_stores,
              COUNT(*) as transaction_count
            FROM transactions t
            WHERE t.date BETWEEN ? AND ?
        """,
            (start_date, end_date),
        ).fetchone()

        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        days = (ed - sd).days + 1

        target_row = conn.execute("SELECT SUM(weekly_target) as t FROM stores").fetchone()
        network_target = (target_row["t"] or 0) * days / 7

        tier_rows = conn.execute(
            """
            SELECT s.tier,
                   SUM(t.line_total) as revenue,
                   COUNT(DISTINCT s.id) as store_count
            FROM stores s LEFT JOIN transactions t
              ON t.store_id = s.id AND t.date BETWEEN ? AND ?
            GROUP BY s.tier
        """,
            (start_date, end_date),
        ).fetchall()

        region_rows = conn.execute(
            """
            SELECT s.region,
                   SUM(t.line_total) as revenue,
                   COUNT(DISTINCT s.id) as store_count
            FROM stores s LEFT JOIN transactions t
              ON t.store_id = s.id AND t.date BETWEEN ? AND ?
            GROUP BY s.region ORDER BY revenue DESC
        """,
            (start_date, end_date),
        ).fetchall()

        channel_rows = conn.execute(
            """
            SELECT channel, SUM(line_total) as revenue, COUNT(*) as txs
            FROM transactions WHERE date BETWEEN ? AND ?
            GROUP BY channel ORDER BY revenue DESC
        """,
            (start_date, end_date),
        ).fetchall()

    actual = row["actual"] or 0
    return {
        "period": {"start": start_date, "end": end_date, "days": days},
        "total_revenue": round(actual, 2),
        "network_target": round(network_target, 2),
        "variance_pct": round((actual - network_target) / network_target * 100, 1) if network_target else None,
        "transaction_count": row["transaction_count"],
        "active_stores": row["active_stores"],
        "by_tier": [dict(r) for r in tier_rows],
        "by_region": [dict(r) for r in region_rows],
        "by_channel": [dict(r) for r in channel_rows],
    }


def store_performance(
    start_date: str,
    end_date: str,
    below_target_only: bool = False,
) -> dict[str, Any]:
    """Per-store actual vs target for a period. Sorted worst-first by variance %.

    Use below_target_only=True to filter to underperformers, useful when the
    network summary already shows the macro picture and the agent is drilling in.
    """
    _parse_iso_date(start_date, "start_date")
    _parse_iso_date(end_date, "end_date")
    with _conn() as conn:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        days = (ed - sd).days + 1

        rows = conn.execute(
            """
            SELECT s.id, s.name, s.region, s.tier, s.weekly_target,
                   COALESCE(SUM(t.line_total), 0) as actual
            FROM stores s LEFT JOIN transactions t
              ON t.store_id = s.id AND t.date BETWEEN ? AND ?
            WHERE s.opened <= ?
            GROUP BY s.id
            ORDER BY actual ASC
        """,
            (start_date, end_date, end_date),
        ).fetchall()

    results: list[dict[str, Any]] = []
    for r in rows:
        target = r["weekly_target"] * days / 7
        actual = r["actual"] or 0
        variance_pct = round((actual - target) / target * 100, 1) if target else 0
        if below_target_only and variance_pct >= 0:
            continue
        results.append(
            {
                "store_id": r["id"],
                "name": r["name"],
                "region": r["region"],
                "tier": r["tier"],
                "target": round(target, 2),
                "actual": round(actual, 2),
                "variance_pct": variance_pct,
                "hit_target": actual >= target,
            }
        )
    results.sort(key=lambda x: x["variance_pct"])
    return {
        "period": {"start": start_date, "end": end_date},
        "stores": results,
        "below_target_count": sum(1 for s in results if not s["hit_target"]),
    }


def store_trend(store_id: str, days: int = 14) -> dict[str, Any]:
    """Daily revenue and target for one store over the last N days, plus
    7-day vs prior 7-day comparison. Use to investigate whether a store's
    underperformance is a one-off or a sustained trend."""
    if not isinstance(store_id, str) or not store_id.strip():
        return {"error": "store_id is required"}
    days = _clamp_int(days, default=14, lo=1, hi=90)
    with _conn() as conn:
        store_row = conn.execute(
            "SELECT id, name, region, tier, weekly_target FROM stores WHERE id = ?",
            (store_id,),
        ).fetchone()
        if not store_row:
            return {"error": f"Store {store_id} not found"}
        store = dict(store_row)
        daily_target = store["weekly_target"] / 7

        max_date = conn.execute("SELECT MAX(date) as d FROM transactions").fetchone()["d"]
        if not max_date:
            return {"error": "No transactions in the database"}
        end = datetime.strptime(max_date, "%Y-%m-%d")
        start = end - timedelta(days=days - 1)

        daily_rows = conn.execute(
            """
            SELECT date, COALESCE(SUM(line_total), 0) as revenue, COUNT(*) as txs
            FROM transactions WHERE store_id = ? AND date BETWEEN ? AND ?
            GROUP BY date ORDER BY date
        """,
            (store_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()

        daily = {r["date"]: dict(r) for r in daily_rows}
        series: list[dict[str, Any]] = []
        for i in range(days):
            d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
            row = daily.get(d, {"date": d, "revenue": 0, "txs": 0})
            row["target"] = round(daily_target, 2)
            row["variance_pct"] = round((row["revenue"] - daily_target) / daily_target * 100, 1) if daily_target else 0
            series.append(row)

        last_7 = sum(d["revenue"] for d in series[-7:])
        prior_7 = sum(d["revenue"] for d in series[-14:-7]) if len(series) >= 14 else None

    return {
        "store": store,
        "daily_target": round(daily_target, 2),
        "series": series,
        "last_7_days_revenue": round(last_7, 2),
        "prior_7_days_revenue": round(prior_7, 2) if prior_7 is not None else None,
        "wow_change_pct": round((last_7 - prior_7) / prior_7 * 100, 1) if prior_7 else None,
        "days_under_target_in_last_7": sum(1 for d in series[-7:] if d["variance_pct"] < 0),
    }


def category_performance(
    start_date: str,
    end_date: str,
    compare_to_prior: bool = True,
) -> dict[str, Any]:
    """Revenue and units sold by product category for a period, optionally with
    week-over-week comparison. Useful for trend findings: which categories are
    growing, which are flat, which are declining network-wide."""
    _parse_iso_date(start_date, "start_date")
    _parse_iso_date(end_date, "end_date")
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT category, SUM(line_total) as revenue, SUM(quantity) as units
            FROM transactions WHERE date BETWEEN ? AND ?
            GROUP BY category ORDER BY revenue DESC
        """,
            (start_date, end_date),
        ).fetchall()
        current = {r["category"]: dict(r) for r in rows}

        prior: dict[str, float] = {}
        if compare_to_prior:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            span = (ed - sd).days + 1
            prior_end = sd - timedelta(days=1)
            prior_start = prior_end - timedelta(days=span - 1)
            prior_rows = conn.execute(
                """
                SELECT category, SUM(line_total) as revenue
                FROM transactions WHERE date BETWEEN ? AND ?
                GROUP BY category
            """,
                (prior_start.strftime("%Y-%m-%d"), prior_end.strftime("%Y-%m-%d")),
            ).fetchall()
            prior = {r["category"]: r["revenue"] for r in prior_rows}

    results: list[dict[str, Any]] = []
    for cat, c in current.items():
        prior_rev = prior.get(cat)
        change_pct = round((c["revenue"] - prior_rev) / prior_rev * 100, 1) if prior_rev else None
        results.append(
            {
                "category": cat,
                "revenue": round(c["revenue"], 2),
                "units": c["units"],
                "wow_change_pct": change_pct,
            }
        )
    results.sort(key=lambda x: -x["revenue"])
    return {"period": {"start": start_date, "end": end_date}, "categories": results}


def top_products(
    start_date: str,
    end_date: str,
    category: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Top-selling products (by revenue) for a period. Filterable by category.

    Use to investigate category-level findings (e.g. 'Wraps up 15%' -
    drill in to see which specific items drove it)."""
    _parse_iso_date(start_date, "start_date")
    _parse_iso_date(end_date, "end_date")
    limit = _clamp_int(limit, default=10, lo=1, hi=50)
    with _conn() as conn:
        if category:
            rows = conn.execute(
                """
                SELECT plu, product_name, category,
                       SUM(line_total) as revenue, SUM(quantity) as units
                FROM transactions
                WHERE date BETWEEN ? AND ? AND category = ?
                GROUP BY plu ORDER BY revenue DESC LIMIT ?
            """,
                (start_date, end_date, category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT plu, product_name, category,
                       SUM(line_total) as revenue, SUM(quantity) as units
                FROM transactions WHERE date BETWEEN ? AND ?
                GROUP BY plu ORDER BY revenue DESC LIMIT ?
            """,
                (start_date, end_date, limit),
            ).fetchall()
    return {
        "period": {"start": start_date, "end": end_date},
        "category_filter": category,
        "products": [dict(r) | {"revenue": round(r["revenue"], 2)} for r in rows],
    }


def channel_comparison(start_date: str, end_date: str) -> dict[str, Any]:
    """Sales channel breakdown vs the prior equivalent period. Reveals shifts
    between in-store, kiosk, web, app, delivery."""
    _parse_iso_date(start_date, "start_date")
    _parse_iso_date(end_date, "end_date")
    with _conn() as conn:
        sd = datetime.strptime(start_date, "%Y-%m-%d")
        ed = datetime.strptime(end_date, "%Y-%m-%d")
        span = (ed - sd).days + 1
        prior_end = sd - timedelta(days=1)
        prior_start = prior_end - timedelta(days=span - 1)

        current = {
            r["channel"]: dict(r)
            for r in conn.execute(
                """
            SELECT channel, SUM(line_total) as revenue, COUNT(*) as txs
            FROM transactions WHERE date BETWEEN ? AND ?
            GROUP BY channel
        """,
                (start_date, end_date),
            ).fetchall()
        }

        prior = {
            r["channel"]: r["revenue"]
            for r in conn.execute(
                """
            SELECT channel, SUM(line_total) as revenue
            FROM transactions WHERE date BETWEEN ? AND ?
            GROUP BY channel
        """,
                (prior_start.strftime("%Y-%m-%d"), prior_end.strftime("%Y-%m-%d")),
            ).fetchall()
        }

    results: list[dict[str, Any]] = []
    for ch, c in current.items():
        prior_rev = prior.get(ch)
        change_pct = round((c["revenue"] - prior_rev) / prior_rev * 100, 1) if prior_rev else None
        results.append(
            {
                "channel": ch,
                "revenue": round(c["revenue"], 2),
                "transactions": c["txs"],
                "wow_change_pct": change_pct,
            }
        )
    results.sort(key=lambda x: -x["revenue"])
    return {"period": {"start": start_date, "end": end_date}, "channels": results}


# ============================================================================
# Tool schema for Claude
# ============================================================================

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_stores",
        "description": (
            "Return all stores with id, name, region, tier, opened date, and weekly target. "
            "Useful when you need to look up a store_id from a name."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "network_summary",
        "description": (
            "High-level network performance for a date range. Returns total revenue vs target, "
            "breakdowns by tier and region, and channel mix. Usually the first call to make - "
            "it gives the macro picture that informs which other tools to invoke."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "store_performance",
        "description": (
            "Per-store actual vs target for a period, sorted worst-first. "
            "Set below_target_only=true to filter to underperformers when drilling into a finding."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "below_target_only": {"type": "boolean", "default": False},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "store_trend",
        "description": (
            "Daily revenue and target for one store over the last N days, plus 7-day vs prior 7-day comparison. "
            "Use to investigate whether a store's underperformance is a one-off or a sustained trend."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "e.g. ST008"},
                "days": {
                    "type": "integer",
                    "default": 14,
                    "description": "How many days of history to return. Default 14.",
                },
            },
            "required": ["store_id"],
        },
    },
    {
        "name": "category_performance",
        "description": (
            "Revenue and units by product category for a period, with optional week-over-week comparison. "
            "Reveals which categories are growing or declining network-wide."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "compare_to_prior": {"type": "boolean", "default": True},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "top_products",
        "description": (
            "Top-selling products by revenue for a period, optionally filtered to a category. "
            "Use to drill into category-level findings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "category": {
                    "type": "string",
                    "description": "Optional category filter, e.g. 'Wraps', 'Coffee', 'Combos'",
                },
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "channel_comparison",
        "description": (
            "Sales by channel (in_store, kiosk, web, app, delivery) for a period, with week-over-week change. "
            "Reveals shifts in customer behaviour."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["start_date", "end_date"],
        },
    },
]

TOOL_FUNCTIONS: dict[str, Any] = {
    "list_stores": list_stores,
    "network_summary": network_summary,
    "store_performance": store_performance,
    "store_trend": store_trend,
    "category_performance": category_performance,
    "top_products": top_products,
    "channel_comparison": channel_comparison,
}
