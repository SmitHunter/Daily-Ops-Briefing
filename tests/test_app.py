"""Tests for the Flask application."""

from __future__ import annotations

import contextlib
import time
from unittest.mock import patch

import pytest

import app as app_module
from app import app


def _reset_app_state() -> None:
    app_module._latest_briefing = None
    app_module._last_error = None
    if app_module._run_lock.locked():
        with contextlib.suppress(RuntimeError):
            app_module._run_lock.release()


def _wait_for_run(timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while app_module._run_lock.locked() and time.time() < deadline:
        time.sleep(0.01)


@pytest.fixture
def client():
    """Create a test client for the Flask app with isolated in-memory state."""
    app.config["TESTING"] = True
    _reset_app_state()
    with app.test_client() as test_client:
        yield test_client
    _reset_app_state()


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_returns_ok(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "ok"
        assert "has_briefing" in data

    def test_health_shows_no_briefing_initially(self, client) -> None:
        response = client.get("/health")
        data = response.get_json()
        assert data["has_briefing"] is False
        assert data["last_error"] is None
        assert data["run_in_progress"] is False

    def test_health_stays_public_when_token_configured(self, client) -> None:
        with patch("app.ACCESS_TOKEN", "secret123"):
            response = client.get("/health")
            assert response.status_code == 200


class TestDashboard:
    """Tests for the dashboard endpoint."""

    def test_dashboard_returns_html(self, client) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"
        assert b"Daily Ops Briefing" in response.data

    def test_dashboard_shows_empty_state(self, client) -> None:
        response = client.get("/")
        assert b"No briefing yet" in response.data
        assert b"Run briefing now" in response.data

    def test_empty_state_run_link_keeps_token(self, client) -> None:
        with patch("app.ACCESS_TOKEN", "secret123"):
            response = client.get("/?key=secret123")
            assert b'href="/run?key=secret123"' in response.data

    def test_example_briefing_flag_labels_dashboard(self, client, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXAMPLE_BRIEFING", "1")
        assert app_module.apply_example_briefing_if_enabled() is True
        response = client.get("/")
        assert response.status_code == 200
        assert b"illustrative example (not a live Claude run)" in response.data
        assert b"No briefing yet" not in response.data
        assert b"Snacks softening" in response.data
        assert b"Sandwiches" not in response.data

    def test_example_briefing_flag_off_keeps_empty_state(self, client, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXAMPLE_BRIEFING", "0")
        assert app_module.apply_example_briefing_if_enabled() is False
        response = client.get("/")
        assert b"No briefing yet" in response.data

    def test_illustrative_payload_passes_output_validators(self) -> None:
        from tests.test_eval import briefing_errors, findings_errors

        payload = app_module.load_illustrative_briefing()
        assert payload["illustrative"] is True
        assert findings_errors(payload["analyst_findings"]) == []
        assert briefing_errors(payload["briefing_markdown"]) == []


class TestLatestJson:
    """Tests for the /latest.json endpoint."""

    def test_latest_returns_404_when_no_briefing(self, client) -> None:
        response = client.get("/latest.json")
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data


class TestAccessToken:
    """Tests for token-based access control."""

    def test_endpoints_work_without_token_when_not_configured(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_endpoints_require_token_when_configured(self, client) -> None:
        with patch.dict("os.environ", {"BRIEFING_TOKEN": "secret123"}):
            # Need to reload the module to pick up the env var
            import importlib

            import app as app_module

            importlib.reload(app_module)

            # Create new test client with reloaded app
            app_module.app.config["TESTING"] = True
            with app_module.app.test_client() as protected_client:
                response = protected_client.get("/")
                assert response.status_code == 401

    def test_token_accepted_in_query_param(self, client) -> None:
        with patch("app.ACCESS_TOKEN", "secret123"):
            response = client.get("/?key=secret123")
            # Should not be 401
            assert response.status_code != 401

    def test_token_accepted_in_header(self, client) -> None:
        with patch("app.ACCESS_TOKEN", "secret123"):
            response = client.get("/", headers={"X-Access-Token": "secret123"})
            assert response.status_code != 401


class TestRunEndpoint:
    """Tests for the /run endpoint."""

    def test_run_accepts_get_for_demo_convenience(self, client) -> None:
        with patch("app.ACCESS_TOKEN", None), patch("app.run_briefing") as mock_run:
            mock_run.return_value = {
                "status": "ok",
                "date": "2026-04-30",
                "analyst_findings": {},
                "briefing_markdown": "ok",
                "metadata": {"analyst_iterations": 1, "model": "claude-sonnet-5-5"},
            }
            response = client.get("/run")
            assert response.status_code == 200
            assert b"Running briefing" in response.data
            _wait_for_run()
            assert app_module._latest_briefing is not None
            assert app_module._latest_briefing["date"] == "2026-04-30"

    def test_run_accepts_post(self, client) -> None:
        with patch("app.ACCESS_TOKEN", None), patch("app.run_briefing") as mock_run:
            mock_run.return_value = {"status": "ok", "date": "2026-04-30"}
            response = client.post("/run")
            assert response.status_code == 200
            _wait_for_run()

    def test_run_preserves_access_key_on_refresh(self, client) -> None:
        with patch("app.ACCESS_TOKEN", "secret123"), patch("app.run_briefing") as mock_run:
            mock_run.return_value = {"status": "ok", "date": "2026-04-30"}
            response = client.get("/run?key=secret123")
            assert response.status_code == 200
            assert b"url=/?key=secret123" in response.data
            _wait_for_run()

    def test_run_failure_is_exposed_on_latest_and_dashboard(self, client) -> None:
        with patch("app.ACCESS_TOKEN", None), patch("app.run_briefing") as mock_run:
            mock_run.return_value = {
                "status": "error",
                "stage": "analyst",
                "details": {"error": "Could not reach the Claude API."},
            }
            client.post("/run")
            _wait_for_run()

            latest = client.get("/latest.json")
            assert latest.status_code == 502
            assert latest.get_json()["stage"] == "analyst"

            dashboard = client.get("/")
            assert b"Last run failed" in dashboard.data
            assert b"Could not reach the Claude API." in dashboard.data


class TestHtmlRendering:
    """Tests for HTML rendering functions."""

    def test_inline_bold_converts_asterisks(self) -> None:
        from app import _inline_bold

        result = _inline_bold("This is *bold* text")
        assert "<strong>bold</strong>" in result
        assert "*" not in result

    def test_inline_bold_escapes_html(self) -> None:
        from app import _inline_bold

        result = _inline_bold("<script>alert('xss')</script>")
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_format_money(self) -> None:
        from app import _format_money

        assert _format_money(1234567) == "$1,234,567"
        assert _format_money(1234.56) == "$1,235"
        assert _format_money(None) == "—"
        assert _format_money("invalid") == "—"

    def test_format_pct(self) -> None:
        from app import _format_pct

        assert _format_pct(5.5) == "+5.5%"
        assert _format_pct(-3.2) == "−3.2%"  # noqa: RUF001 - intentional minus sign
        assert _format_pct(0) == "+0.0%"
        assert _format_pct(None) == "—"

    def test_strip_store_id(self) -> None:
        from app import _strip_store_id

        assert _strip_store_id("ST008: Westbridge under target") == "Westbridge under target"
        assert _strip_store_id("ST08 - Test Store") == "Test Store"
        assert _strip_store_id("No store ID here") == "No store ID here"

    def test_render_tiles_handles_empty_stats(self) -> None:
        from app import _render_tiles

        result = _render_tiles({})
        assert result == ""

    def test_render_finding_produces_valid_html(self) -> None:
        from app import _render_finding

        finding = {
            "title": "Test Finding",
            "severity": "high",
            "category": "store_performance",
            "evidence": {"revenue": 10000},
            "interpretation": "Test interpretation with *bold* text",
            "recommended_action": "Take action",
        }
        result = _render_finding(finding)

        assert '<article class="card sev-high">' in result
        assert "Test Finding" in result
        assert "<strong>bold</strong>" in result
        assert "Take action" in result
