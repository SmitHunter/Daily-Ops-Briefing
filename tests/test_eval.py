"""Quality checks for briefing outputs.

These are real validators with failing cases — not fixtures that only
assert their own hardcoded happy path. They can also be pointed at a
live Analyst/Writer payload later.
"""

from __future__ import annotations

import re
from typing import Any


def findings_errors(payload: Any) -> list[str]:
    """Return validation errors for an Analyst findings object."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["findings payload must be an object"]

    if not isinstance(payload.get("headline"), str) or not payload["headline"].strip():
        errors.append("headline must be a non-empty string")

    findings = payload.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []
    elif len(findings) < 1:
        errors.append("findings must contain at least one item")
    elif len(findings) > 8:
        errors.append("findings has more than 8 items (poor prioritisation)")

    required_finding = {"title", "severity", "category", "evidence", "interpretation"}
    valid_severities = {"high", "medium", "low"}
    for i, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding[{i}] must be an object")
            continue
        missing = required_finding - finding.keys()
        if missing:
            errors.append(f"finding[{i}] missing keys: {sorted(missing)}")
        if finding.get("severity") not in valid_severities:
            errors.append(f"finding[{i}] has invalid severity")
        if not isinstance(finding.get("evidence"), dict):
            errors.append(f"finding[{i}] evidence must be an object")

    stats = payload.get("stats")
    if not isinstance(stats, dict):
        errors.append("stats must be an object")
    else:
        required_stats = {
            "stores_above_target",
            "stores_below_target",
            "network_revenue",
            "network_target",
            "variance_pct",
        }
        missing_stats = required_stats - stats.keys()
        if missing_stats:
            errors.append(f"stats missing keys: {sorted(missing_stats)}")
        for key, value in stats.items():
            if not isinstance(value, (int, float)):
                errors.append(f"stats.{key} must be numeric")
    return errors


def briefing_errors(markdown: str) -> list[str]:
    """Return validation errors for Writer markdown."""
    errors: list[str] = []
    if "*Daily Ops Briefing" not in markdown:
        errors.append("missing Daily Ops Briefing header")
    if not re.search(r"\d{1,2}\s+\w+\s+\d{4}", markdown):
        errors.append("missing date in header")
    if "🔴" not in markdown and "🟡" not in markdown and "🟢" not in markdown:
        errors.append("missing severity emoji")
    if len(re.findall(r"\*[^*]+\*", markdown)) < 2:
        errors.append("expected bolded key numbers")
    if "🔴" in markdown and "Action:" not in markdown:
        errors.append("high-severity finding is missing an Action line")
    if "stores" not in markdown.lower() and "target" not in markdown.lower():
        errors.append("missing network footer stats")
    if '{"' in markdown or '"findings":' in markdown:
        errors.append("raw JSON leaked into briefing")
    placeholders = ("TODO", "FIXME", "[INSERT", "<PLACEHOLDER>")
    for placeholder in placeholders:
        if placeholder in markdown:
            errors.append(f"placeholder text present: {placeholder}")
    return errors


class TestFindingsValidator:
    def test_valid_payload_has_no_errors(self, sample_analyst_findings: dict[str, Any]) -> None:
        assert findings_errors(sample_analyst_findings) == []

    def test_rejects_missing_headline(self, sample_analyst_findings: dict[str, Any]) -> None:
        bad = dict(sample_analyst_findings)
        bad.pop("headline")
        assert any("headline" in error for error in findings_errors(bad))

    def test_rejects_empty_findings_list(self, sample_analyst_findings: dict[str, Any]) -> None:
        bad = dict(sample_analyst_findings)
        bad["findings"] = []
        assert any("at least one" in error for error in findings_errors(bad))

    def test_rejects_too_many_findings(self, sample_analyst_findings: dict[str, Any]) -> None:
        extra = sample_analyst_findings["findings"][0]
        bad = dict(sample_analyst_findings)
        bad["findings"] = [extra] * 9
        assert any("more than 8" in error for error in findings_errors(bad))

    def test_rejects_invalid_severity(self, sample_analyst_findings: dict[str, Any]) -> None:
        finding = dict(sample_analyst_findings["findings"][0])
        finding["severity"] = "critical"
        bad = dict(sample_analyst_findings)
        bad["findings"] = [finding]
        assert any("severity" in error for error in findings_errors(bad))

    def test_rejects_non_numeric_stats(self, sample_analyst_findings: dict[str, Any]) -> None:
        bad = dict(sample_analyst_findings)
        bad["stats"] = dict(sample_analyst_findings["stats"])
        bad["stats"]["variance_pct"] = "ten"
        assert any("variance_pct" in error for error in findings_errors(bad))

    def test_rejects_list_payload(self) -> None:
        assert findings_errors([]) == ["findings payload must be an object"]


class TestBriefingValidator:
    def test_valid_briefing_has_no_errors(self) -> None:
        markdown = """*Daily Ops Briefing - Thursday 30 April 2026*

Network up *5%* on target this week, with 28 of 31 stores hitting numbers.

🔴 *Westbridge under target by 18%*
Revenue at *$11,885* against a target of *$14,500*.
Action: Check in with store manager.

🟢 *Coffee category strong*
Coffee up *12%* week-over-week.

---
28 of 31 stores above target."""
        assert briefing_errors(markdown) == []

    def test_rejects_missing_header(self) -> None:
        assert any("header" in error for error in briefing_errors("Network looks fine."))

    def test_rejects_json_leak(self) -> None:
        markdown = '*Daily Ops Briefing - Thursday 30 April 2026*\n\n{"findings": []}'
        assert any("JSON" in error for error in briefing_errors(markdown))

    def test_rejects_placeholder_text(self) -> None:
        markdown = "*Daily Ops Briefing - Thursday 30 April 2026*\n\nTODO fill this in"
        assert any("placeholder" in error for error in briefing_errors(markdown))

    def test_high_severity_requires_action(self) -> None:
        markdown = """*Daily Ops Briefing - Thursday 30 April 2026*

Network up *5%* on target.

🔴 *Westbridge under target*
Stores above target.
"""
        assert any("Action" in error for error in briefing_errors(markdown))
