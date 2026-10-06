"""Tests for the agent system with mocked Claude API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import anthropic
import httpx2

from tests.conftest import create_mock_response, create_text_block, create_tool_use_block
from tests.test_eval import findings_errors


def _api_connection_error() -> anthropic.APIConnectionError:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APIConnectionError(request=request)


class TestAnalystAgent:
    """Tests for the Analyst agent."""

    def test_analyst_returns_findings_on_success(
        self,
        mock_today: str,
        sample_analyst_findings: dict[str, Any],
    ) -> None:
        """Test that analyst correctly parses Claude's JSON response."""
        with patch("agents.client") as mock_client:
            # Simulate Claude returning JSON directly
            mock_response = create_mock_response(
                content=[create_text_block(json.dumps(sample_analyst_findings))],
                stop_reason="end_turn",
            )
            mock_client.messages.create.return_value = mock_response

            import agents

            result = agents.run_analyst()

            assert "findings" in result
            assert "iterations" in result
            assert result["iterations"] == 1
            assert result["findings"]["headline"] == sample_analyst_findings["headline"]

    def test_analyst_handles_tool_calls(self, mock_today: str, mock_db_path: Path) -> None:
        """Test that analyst correctly handles tool use flow."""
        with patch("agents.client") as mock_client:
            findings = {
                "headline": "Network healthy",
                "findings": [],
                "stats": {
                    "stores_above_target": 3,
                    "stores_below_target": 0,
                    "network_revenue": 10000,
                    "network_target": 9500,
                    "variance_pct": 5.3,
                },
            }

            # First call: tool use
            tool_response = create_mock_response(
                content=[
                    create_tool_use_block(
                        "tool_123",
                        "network_summary",
                        {"start_date": "2026-04-24", "end_date": "2026-04-30"},
                    )
                ],
                stop_reason="tool_use",
            )

            # Second call: final response
            final_response = create_mock_response(
                content=[create_text_block(json.dumps(findings))],
                stop_reason="end_turn",
            )

            mock_client.messages.create.side_effect = [tool_response, final_response]

            import agents

            result = agents.run_analyst()

            assert "findings" in result
            assert result["iterations"] == 2
            assert mock_client.messages.create.call_count == 2
            second_messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]
            tool_result = second_messages[-1]["content"][0]
            assert tool_result["type"] == "tool_result"
            payload = json.loads(tool_result["content"])
            assert "total_revenue" in payload
            assert payload["period"]["days"] == 7

    def test_analyst_handles_json_in_code_block(
        self,
        mock_today: str,
        sample_analyst_findings: dict[str, Any],
    ) -> None:
        """Test that analyst extracts JSON from markdown code blocks."""
        with patch("agents.client") as mock_client:
            # Claude sometimes wraps JSON in code blocks
            wrapped_json = f"```json\n{json.dumps(sample_analyst_findings)}\n```"
            mock_response = create_mock_response(
                content=[create_text_block(wrapped_json)],
                stop_reason="end_turn",
            )
            mock_client.messages.create.return_value = mock_response

            import agents

            result = agents.run_analyst()

            assert "findings" in result
            assert result["findings"]["headline"] == sample_analyst_findings["headline"]

    def test_analyst_handles_invalid_json(self, mock_today: str) -> None:
        """Test that analyst gracefully handles invalid JSON responses."""
        with patch("agents.client") as mock_client:
            mock_response = create_mock_response(
                content=[create_text_block("This is not valid JSON {broken")],
                stop_reason="end_turn",
            )
            mock_client.messages.create.return_value = mock_response

            import agents

            result = agents.run_analyst()

            assert "error" in result
            assert "non-JSON" in result["error"]

    def test_analyst_respects_max_iterations(self, mock_today: str, mock_db_path: Path) -> None:
        """Test that analyst stops after max iterations."""
        with patch("agents.client") as mock_client:
            # Always return tool_use to force iteration
            tool_response = create_mock_response(
                content=[
                    create_tool_use_block(
                        "tool_123",
                        "list_stores",
                        {},
                    )
                ],
                stop_reason="tool_use",
            )
            mock_client.messages.create.return_value = tool_response

            import agents

            result = agents.run_analyst()

            assert "error" in result
            assert "exceeded" in result["error"]

    def test_analyst_unknown_tool_is_returned_to_model(self, mock_today: str, mock_db_path: Path) -> None:
        with patch("agents.client") as mock_client:
            findings = {
                "headline": "Network healthy",
                "findings": [
                    {
                        "title": "All clear",
                        "severity": "low",
                        "category": "trend",
                        "evidence": {},
                        "interpretation": "Fine",
                    }
                ],
                "stats": {
                    "stores_above_target": 3,
                    "stores_below_target": 0,
                    "network_revenue": 10000,
                    "network_target": 9500,
                    "variance_pct": 5.3,
                },
            }
            tool_response = create_mock_response(
                content=[create_tool_use_block("tool_999", "drop_database", {})],
                stop_reason="tool_use",
            )
            final_response = create_mock_response(
                content=[create_text_block(json.dumps(findings))],
                stop_reason="end_turn",
            )
            mock_client.messages.create.side_effect = [tool_response, final_response]

            import agents

            result = agents.run_analyst()
            assert "findings" in result
            tool_result = mock_client.messages.create.call_args_list[1].kwargs["messages"][-1]["content"][0]
            assert "Unknown tool" in tool_result["content"]

    def test_analyst_rejects_incomplete_json_shape(self, mock_today: str) -> None:
        with patch("agents.client") as mock_client:
            mock_client.messages.create.return_value = create_mock_response(
                content=[create_text_block('{"headline": "only a headline"}')],
                stop_reason="end_turn",
            )
            import agents

            result = agents.run_analyst()
            assert "error" in result
            assert "required keys" in result["error"]

    def test_analyst_handles_api_connection_error(self, mock_today: str) -> None:
        with patch("agents.client") as mock_client:
            mock_client.messages.create.side_effect = _api_connection_error()
            import agents

            result = agents.run_analyst()
            assert result["error"] == "Could not reach the Claude API."

    def test_analyst_handles_missing_api_key(self, mock_today: str) -> None:
        with patch("agents.client") as mock_client:
            mock_client.messages.create.side_effect = TypeError(
                "Could not resolve authentication method. Expected one of api_key, "
                "auth_token, or credentials to be set."
            )
            import agents

            result = agents.run_analyst()
            assert result["error"] == "Claude API authentication failed. Check ANTHROPIC_API_KEY."

    def test_analyst_handles_refusal(self, mock_today: str) -> None:
        with patch("agents.client") as mock_client:
            mock_client.messages.create.return_value = create_mock_response(
                content=[create_text_block("no")],
                stop_reason="refusal",
            )
            import agents

            result = agents.run_analyst()
            assert "refused" in result["error"]


class TestWriterAgent:
    """Tests for the Writer agent."""

    def test_writer_produces_briefing(
        self,
        mock_today: str,
        sample_analyst_findings: dict[str, Any],
    ) -> None:
        """Test that writer produces markdown output."""
        with patch("agents.client") as mock_client:
            expected_briefing = "*Daily Ops Briefing - Thursday 30 April 2026*\n\nNetwork performing well."
            mock_response = create_mock_response(
                content=[create_text_block(expected_briefing)],
                stop_reason="end_turn",
            )
            mock_client.messages.create.return_value = mock_response

            import agents

            result = agents.run_writer(sample_analyst_findings)

            assert "*Daily Ops Briefing" in result
            assert mock_client.messages.create.call_count == 1


class TestBriefingPipeline:
    """Tests for the full briefing pipeline."""

    def test_run_briefing_success(
        self,
        mock_today: str,
        sample_analyst_findings: dict[str, Any],
    ) -> None:
        """Test successful end-to-end briefing run."""
        with patch("agents.client") as mock_client:
            # Analyst response
            analyst_response = create_mock_response(
                content=[create_text_block(json.dumps(sample_analyst_findings))],
                stop_reason="end_turn",
            )

            # Writer response
            briefing_md = "*Daily Ops Briefing*\n\nTest briefing content."
            writer_response = create_mock_response(
                content=[create_text_block(briefing_md)],
                stop_reason="end_turn",
            )

            mock_client.messages.create.side_effect = [analyst_response, writer_response]

            import agents

            result = agents.run_briefing()

            assert result["status"] == "ok"
            assert result["analyst_findings"] == sample_analyst_findings
            assert result["briefing_markdown"] == briefing_md
            assert result["metadata"]["model"] == agents.MODEL
            assert findings_errors(result["analyst_findings"]) == []

    def test_run_briefing_handles_analyst_error(self, mock_today: str) -> None:
        """Test that pipeline handles analyst errors gracefully."""
        with patch("agents.client") as mock_client:
            # Analyst returns invalid response
            mock_response = create_mock_response(
                content=[create_text_block("invalid json")],
                stop_reason="end_turn",
            )
            mock_client.messages.create.return_value = mock_response

            import agents

            result = agents.run_briefing()

            assert result["status"] == "error"
            assert result["stage"] == "analyst"

    def test_run_briefing_handles_empty_writer_output(
        self,
        mock_today: str,
        sample_analyst_findings: dict[str, Any],
    ) -> None:
        with patch("agents.client") as mock_client:
            analyst_response = create_mock_response(
                content=[create_text_block(json.dumps(sample_analyst_findings))],
                stop_reason="end_turn",
            )
            writer_response = create_mock_response(
                content=[create_text_block("   ")],
                stop_reason="end_turn",
            )
            mock_client.messages.create.side_effect = [analyst_response, writer_response]

            import agents

            result = agents.run_briefing()
            assert result["status"] == "error"
            assert result["stage"] == "writer"
            assert "empty" in result["details"]["error"]

    def test_run_briefing_handles_writer_api_error(
        self,
        mock_today: str,
        sample_analyst_findings: dict[str, Any],
    ) -> None:
        with patch("agents.client") as mock_client:
            analyst_response = create_mock_response(
                content=[create_text_block(json.dumps(sample_analyst_findings))],
                stop_reason="end_turn",
            )
            mock_client.messages.create.side_effect = [analyst_response, _api_connection_error()]

            import agents

            result = agents.run_briefing()
            assert result["status"] == "error"
            assert result["stage"] == "writer"
            assert result["details"]["error"] == "Could not reach the Claude API."
