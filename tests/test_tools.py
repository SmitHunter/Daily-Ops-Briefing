"""Tests for the analyst tools."""

from __future__ import annotations

from pathlib import Path

import tools


class TestListStores:
    """Tests for list_stores tool."""

    def test_returns_all_stores(self, mock_db_path: Path) -> None:
        result = tools.list_stores()
        assert "stores" in result
        assert "count" in result
        assert result["count"] == 3
        assert len(result["stores"]) == 3

    def test_store_has_required_fields(self, mock_db_path: Path) -> None:
        result = tools.list_stores()
        store = result["stores"][0]
        assert "id" in store
        assert "name" in store
        assert "region" in store
        assert "tier" in store
        assert "weekly_target" in store


class TestNetworkSummary:
    """Tests for network_summary tool."""

    def test_returns_summary_for_date_range(self, mock_db_path: Path) -> None:
        result = tools.network_summary("2026-04-24", "2026-04-30")
        assert "period" in result
        assert "total_revenue" in result
        assert "network_target" in result
        assert "variance_pct" in result
        assert "by_tier" in result
        assert "by_region" in result
        assert "by_channel" in result

    def test_calculates_correct_days(self, mock_db_path: Path) -> None:
        result = tools.network_summary("2026-04-24", "2026-04-30")
        assert result["period"]["days"] == 7

    def test_handles_single_day(self, mock_db_path: Path) -> None:
        result = tools.network_summary("2026-04-30", "2026-04-30")
        assert result["period"]["days"] == 1

    def test_rejects_invalid_date(self, mock_db_path: Path) -> None:
        import pytest

        with pytest.raises(ValueError, match="start_date"):
            tools.network_summary("30-04-2026", "2026-04-30")


class TestStorePerformance:
    """Tests for store_performance tool."""

    def test_returns_all_stores_by_default(self, mock_db_path: Path) -> None:
        result = tools.store_performance("2026-04-24", "2026-04-30")
        assert "stores" in result
        assert "below_target_count" in result
        assert len(result["stores"]) == 3

    def test_filters_below_target_only(self, mock_db_path: Path) -> None:
        result = tools.store_performance("2026-04-24", "2026-04-30", below_target_only=True)
        for store in result["stores"]:
            assert store["variance_pct"] < 0

    def test_stores_have_required_fields(self, mock_db_path: Path) -> None:
        result = tools.store_performance("2026-04-24", "2026-04-30")
        store = result["stores"][0]
        assert "store_id" in store
        assert "name" in store
        assert "target" in store
        assert "actual" in store
        assert "variance_pct" in store
        assert "hit_target" in store


class TestStoreTrend:
    """Tests for store_trend tool."""

    def test_returns_trend_for_valid_store(self, mock_db_path: Path) -> None:
        result = tools.store_trend("ST001")
        assert "store" in result
        assert "series" in result
        assert "daily_target" in result
        assert "last_7_days_revenue" in result

    def test_returns_error_for_invalid_store(self, mock_db_path: Path) -> None:
        result = tools.store_trend("INVALID")
        assert "error" in result

    def test_series_length_matches_days(self, mock_db_path: Path) -> None:
        result = tools.store_trend("ST001", days=7)
        assert len(result["series"]) == 7

    def test_clamps_excessive_days(self, mock_db_path: Path) -> None:
        result = tools.store_trend("ST001", days=400)
        assert len(result["series"]) == 90

    def test_rejects_blank_store_id(self, mock_db_path: Path) -> None:
        result = tools.store_trend("   ")
        assert "error" in result


class TestCategoryPerformance:
    """Tests for category_performance tool."""

    def test_returns_categories(self, mock_db_path: Path) -> None:
        result = tools.category_performance("2026-04-24", "2026-04-30")
        assert "categories" in result
        assert len(result["categories"]) > 0

    def test_categories_have_required_fields(self, mock_db_path: Path) -> None:
        result = tools.category_performance("2026-04-24", "2026-04-30")
        cat = result["categories"][0]
        assert "category" in cat
        assert "revenue" in cat
        assert "units" in cat


class TestTopProducts:
    """Tests for top_products tool."""

    def test_returns_products(self, mock_db_path: Path) -> None:
        result = tools.top_products("2026-04-24", "2026-04-30")
        assert "products" in result
        assert len(result["products"]) > 0

    def test_respects_limit(self, mock_db_path: Path) -> None:
        result = tools.top_products("2026-04-24", "2026-04-30", limit=2)
        assert len(result["products"]) <= 2

    def test_clamps_limit(self, mock_db_path: Path) -> None:
        result = tools.top_products("2026-04-24", "2026-04-30", limit=500)
        assert len(result["products"]) <= 50

    def test_filters_by_category(self, mock_db_path: Path) -> None:
        result = tools.top_products("2026-04-24", "2026-04-30", category="Wraps")
        assert result["category_filter"] == "Wraps"
        for product in result["products"]:
            assert product["category"] == "Wraps"


class TestChannelComparison:
    """Tests for channel_comparison tool."""

    def test_returns_channels(self, mock_db_path: Path) -> None:
        result = tools.channel_comparison("2026-04-24", "2026-04-30")
        assert "channels" in result
        assert len(result["channels"]) > 0

    def test_channels_have_required_fields(self, mock_db_path: Path) -> None:
        result = tools.channel_comparison("2026-04-24", "2026-04-30")
        channel = result["channels"][0]
        assert "channel" in channel
        assert "revenue" in channel
        assert "transactions" in channel


class TestInputGuards:
    def test_clamp_int_bounds(self) -> None:
        assert tools._clamp_int(500, 10, 1, 50) == 50
        assert tools._clamp_int(-3, 10, 1, 50) == 1
        assert tools._clamp_int("nope", 10, 1, 50) == 10


class TestToolSchema:
    """Tests for tool schema definitions."""

    def test_all_tools_have_schemas(self) -> None:
        assert len(tools.TOOLS) == 7

    def test_all_tools_have_functions(self) -> None:
        for tool in tools.TOOLS:
            assert tool["name"] in tools.TOOL_FUNCTIONS

    def test_tools_have_required_fields(self) -> None:
        for tool in tools.TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
