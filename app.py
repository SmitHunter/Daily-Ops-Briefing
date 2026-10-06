"""
Daily Ops Briefing - Flask service.

Endpoints:
  GET  /             - Simple HTML dashboard showing the latest briefing
  POST /run          - Trigger a fresh briefing run. Optionally protected by URL token.
  GET  /latest.json  - Latest briefing as JSON
  GET  /health       - Health check for uptime monitoring

Designed for deployment on Render (free tier). Wakes on first request after idle.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import UTC, datetime
from html import escape as _esc
from typing import Any
from urllib.parse import quote

from flask import Flask, Response, jsonify, request

from agents import run_briefing

app = Flask(__name__)

# In-memory cache of the latest briefing. In production this would be a DB
# or object store, but for the demo this keeps everything self-contained.
_latest_briefing: dict[str, Any] | None = None
_last_error: dict[str, Any] | None = None
_run_lock = threading.Lock()

ACCESS_TOKEN = os.environ.get("BRIEFING_TOKEN")


def _check_token() -> tuple[Response, int] | None:
    """Return None if access OK, else a Flask response.

    /health is intentionally public so uptime checks do not need the token.
    """
    if not ACCESS_TOKEN:
        return None
    provided = request.args.get("key") or request.headers.get("X-Access-Token")
    if provided != ACCESS_TOKEN:
        return jsonify({"error": "unauthorized"}), 401
    return None


def _query_with_key(path: str) -> str:
    """Keep ?key= on in-app links so a token-protected session does not 401 after redirect."""
    if not ACCESS_TOKEN:
        return path
    key = request.args.get("key")
    if not key:
        return path
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}key={quote(key, safe='')}"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _error_details(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    raw = payload.get("details")
    return raw if isinstance(raw, dict) else {}


def _to_float(value: Any) -> float:
    if value is None:
        raise TypeError("value is None")
    return float(value)


def _loading_page() -> str:
    return _LOADING_PAGE.replace("url=/", f"url={_query_with_key('/')}")


@app.route("/health")
def health() -> Response:
    last_error_summary = None
    if _last_error is not None:
        details = _error_details(_last_error)
        last_error_summary = {
            "stage": _last_error.get("stage"),
            "error": details.get("error"),
        }
    return jsonify(
        {
            "status": "ok",
            "has_briefing": _latest_briefing is not None,
            "latest_briefing_date": (_latest_briefing or {}).get("date"),
            "run_in_progress": _run_lock.locked(),
            "last_error": last_error_summary,
        }
    )


@app.route("/run", methods=["POST", "GET"])
def run() -> Response | tuple[Response, int]:
    """Trigger an agent run. Returns the new briefing.
    GET is allowed for convenience during demos / Make.com testing."""
    err = _check_token()
    if err:
        return err

    if _run_lock.locked() or not _run_lock.acquire(blocking=False):
        return Response(_loading_page(), mimetype="text/html")

    def _worker() -> None:
        global _latest_briefing, _last_error
        try:
            result = run_briefing()
            if result.get("status") == "ok":
                result["generated_at"] = _utc_now()
                _latest_briefing = result
                _last_error = None
            else:
                _last_error = result
        except Exception as exc:
            _last_error = {"status": "error", "stage": "run", "details": {"error": type(exc).__name__}}
        finally:
            _run_lock.release()

    threading.Thread(target=_worker, daemon=True).start()
    return Response(_loading_page(), mimetype="text/html")


@app.route("/latest.json")
def latest_json() -> Response | tuple[Response, int]:
    err = _check_token()
    if err:
        return err
    if _latest_briefing is None:
        if _last_error is not None:
            details = _error_details(_last_error)
            return jsonify(
                {
                    "error": "last briefing run failed",
                    "stage": _last_error.get("stage"),
                    "details": {"error": details.get("error")},
                }
            ), 502
        return jsonify({"error": "no briefing has been run yet. POST /run first."}), 404
    return jsonify(_latest_briefing)


@app.route("/")
def dashboard() -> Response | tuple[Response, int]:
    """Minimal HTML dashboard rendering the latest briefing."""
    err = _check_token()
    if err:
        return err

    if _run_lock.locked():
        return Response(_loading_page(), mimetype="text/html")

    if _latest_briefing is None:
        if _last_error is not None:
            details = _error_details(_last_error)
            err_text = _esc(str(details.get("error") or "Briefing run failed"))
            stage = _esc(str(_last_error.get("stage") or "run"))
            body = (
                '<section class="empty">'
                "<h2>Last run failed</h2>"
                f"<p>{err_text} (stage: {stage})</p>"
                f'<p><a class="btn" href="{_esc(_query_with_key("/run"))}">Retry briefing</a></p>'
                "</section>"
            )
            date_label = "—"
            meta_label = "Last run failed"
        else:
            body = (
                '<section class="empty">'
                "<h2>No briefing yet</h2>"
                "<p>Trigger one to populate the dashboard.</p>"
                f'<p><a class="btn" href="{_esc(_query_with_key("/run"))}">Run briefing now</a></p>'
                "</section>"
            )
            date_label = "—"
            meta_label = "Awaiting first run"
    else:
        body = _render_body(_latest_briefing)
        date_label = _latest_briefing.get("date", "—")
        gen = _latest_briefing.get("generated_at", "")
        meta_label = f"Generated {gen} · {_latest_briefing['metadata']['analyst_iterations']} analyst iterations"

    return Response(_PAGE.format(date=date_label, meta=meta_label, body=body), mimetype="text/html")


# ============================================================================
# Render the briefing into structured HTML (hero + tiles + finding cards).
# ============================================================================

_SEV_CLASS = {"high": "sev-high", "medium": "sev-med", "low": "sev-low"}
_STORE_ID_RE = re.compile(r"^\s*ST\d{2,4}[\s:\-–—]*", re.IGNORECASE)  # noqa: RUF001
_STORE_ID_PAREN_RE = re.compile(r"\s*\(ST\d+\)\s*", re.IGNORECASE)
_SERIES_KEYS = (
    "daily_series",
    "series",
    "last_7_days",
    "last_7d",
    "daily_revenue",
    "revenue_by_day",
    "weekly_trend",
    "daily",
    "trend_7d",
)
_CATEGORY_KEYS = (
    "categories",
    "top_categories",
    "category_breakdown",
    "breakdown",
    "category_mix",
    "categories_top",
)


def _inline_bold(text: str) -> str:
    """Convert *segment* markers into <strong> tags. Escapes HTML first."""
    safe = _esc(text)
    rendered = ""
    in_bold = False
    for ch in safe:
        if ch == "*":
            rendered += "</strong>" if in_bold else "<strong>"
            in_bold = not in_bold
        else:
            rendered += ch
    if in_bold:
        rendered += "</strong>"
    return rendered


def _extract_title_and_headline(md: str, fallback_headline: str) -> tuple[str, str]:
    """Pull the title (first *...* line) and headline paragraph from markdown."""
    title = "Daily Ops Briefing"
    headline = fallback_headline or ""
    paras = [p.strip() for p in md.split("\n\n") if p.strip()]
    if paras:
        first = paras[0]
        if first.startswith("*") and first.endswith("*") and len(first) > 2:
            title = first.strip("*").strip()
            if not headline and len(paras) > 1:
                headline = paras[1]
        else:
            if not headline:
                headline = first
    return title, headline


def _format_money(v: Any) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _format_pct(v: Any) -> str:
    try:
        f = float(v)
        sign = "+" if f >= 0 else "−"  # noqa: RUF001 - intentional minus sign for display
        return f"{sign}{abs(f):.1f}%"
    except (TypeError, ValueError):
        return "—"


def _format_int(v: Any) -> str:
    try:
        return f"{int(v)}"
    except (TypeError, ValueError):
        return "—"


def _render_tiles(stats: dict[str, Any]) -> str:
    if not stats:
        return ""
    variance = stats.get("variance_pct")
    try:
        var_class = "tile-pos" if _to_float(variance) >= 0 else "tile-neg"
    except (TypeError, ValueError):
        var_class = ""

    above = stats.get("stores_above_target")
    below = stats.get("stores_below_target")
    try:
        total_stores = int(above or 0) + int(below or 0)
        below_n = int(below or 0)
        below_class = "tile-neg" if total_stores and (below_n / total_stores) > 0.2 else ""
    except (TypeError, ValueError):
        below_class = ""

    tiles = [
        ("Network revenue", _format_money(stats.get("network_revenue")), ""),
        ("Target", _format_money(stats.get("network_target")), ""),
        ("Variance", _format_pct(variance), var_class),
        ("Stores above target", _format_int(above), "tile-pos"),
        ("Stores below target", _format_int(below), below_class),
    ]
    parts: list[str] = []
    for label, value, cls in tiles:
        parts.append(
            f'<div class="tile"><div class="tile-label">{_esc(label)}</div>'
            f'<div class="tile-value {cls}">{_esc(value)}</div></div>'
        )
    return f'<div class="tiles">{"".join(parts)}</div>'


def _strip_store_id(title: str) -> str:
    """Remove a leading store-ID prefix (e.g. 'ST008: ', 'ST08 - ') from a title."""
    if not title:
        return title
    cleaned = _STORE_ID_RE.sub("", title, count=1)
    cleaned = _STORE_ID_PAREN_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or title


def _format_value(v: Any) -> str | None:
    """Format an evidence value for the mini-table.
    Returns None if the value is a long free-text string that should be hidden."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:,.1f}".rstrip("0").rstrip(".")
    if isinstance(v, (list, dict)):
        return None
    s = str(v).strip()
    if not s:
        return None
    if len(s) > 24:
        return None
    return s


def _render_evidence_table(evidence: dict[str, Any]) -> str:
    if not isinstance(evidence, dict) or not evidence:
        return ""
    rows: list[str] = []
    for key, value in evidence.items():
        if isinstance(value, (list, dict)):
            continue
        formatted = _format_value(value)
        if formatted is None:
            continue
        label = str(key).replace("_", " ")
        label = label[:1].upper() + label[1:]
        rows.append(f'<tr><td class="kv-key">{_esc(label)}</td><td class="kv-val">{_esc(formatted)}</td></tr>')
        if len(rows) >= 4:
            break
    if not rows:
        return ""
    return f'<table class="kv">{"".join(rows)}</table>'


def _coerce_series(evidence: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Find a daily revenue series in evidence under any plausible key.
    Returns a normalised list of {revenue, target} dicts, or None."""
    if not isinstance(evidence, dict):
        return None
    raw = None
    for key in _SERIES_KEYS:
        if key in evidence and isinstance(evidence[key], list) and evidence[key]:
            raw = evidence[key]
            break
    if raw is None:
        return None
    series: list[dict[str, Any]] = []
    for item in raw[-7:]:
        if isinstance(item, dict):
            rev = item.get("revenue", item.get("value", item.get("actual")))
            tgt = item.get("target")
            try:
                rev = _to_float(rev)
            except (TypeError, ValueError):
                continue
            try:
                tgt = float(tgt) if tgt is not None else None
            except (TypeError, ValueError):
                tgt = None
            series.append({"revenue": rev, "target": tgt})
        else:
            try:
                series.append({"revenue": float(item), "target": None})
            except (TypeError, ValueError):
                continue
    if not series:
        return None
    if all(s["target"] is None for s in series):
        avg = sum(s["revenue"] for s in series) / len(series)
        for s in series:
            s["target"] = avg
    return series


def _render_sparkline(series: list[dict[str, Any]]) -> str:
    """Render a 200x50 SVG bar chart for up to 7 days. Red below target, green above."""
    if not series:
        return ""
    n = len(series)
    width, height = 200, 50
    pad_y = 4
    gap = 3
    bar_w = (width - gap * (n - 1)) / n
    max_val = max(
        max(s["revenue"] for s in series),
        max((s["target"] or 0) for s in series),
        1.0,
    )
    bars: list[str] = []
    for i, s in enumerate(series):
        h = (s["revenue"] / max_val) * (height - pad_y * 2)
        x = i * (bar_w + gap)
        y = height - pad_y - h
        below = s["target"] is not None and s["revenue"] < s["target"]
        colour = "#f85149" if below else "#3fb950"
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{colour}" rx="1"/>')
        if s["target"] is not None:
            ty = height - pad_y - (s["target"] / max_val) * (height - pad_y * 2)
            bars.append(
                f'<line x1="{x:.1f}" y1="{ty:.1f}" x2="{(x + bar_w):.1f}" '
                f'y2="{ty:.1f}" stroke="#8b949e" stroke-width="1" '
                f'stroke-dasharray="2,2"/>'
            )
    return (
        f'<div class="chart"><div class="chart-label">Last {n} days · revenue vs target</div>'
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(bars)}</svg></div>'
    )


def _coerce_categories(evidence: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(evidence, dict):
        return None
    raw = None
    for key in _CATEGORY_KEYS:
        if key in evidence and isinstance(evidence[key], list) and evidence[key]:
            raw = evidence[key]
            break
    if raw is None:
        return None
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("category") or item.get("name") or item.get("label")
        rev = item.get("revenue", item.get("value"))
        try:
            rev = _to_float(rev)
        except (TypeError, ValueError):
            continue
        if not name:
            continue
        out.append({"name": str(name), "revenue": rev})
    if not out:
        return None
    out.sort(key=lambda x: -x["revenue"])
    return out[:4]


def _render_category_chart(categories: list[dict[str, Any]]) -> str:
    if not categories:
        return ""
    max_rev = max(c["revenue"] for c in categories) or 1.0
    row_h = 22
    label_w = 110
    value_w = 70
    bar_track_w = 200
    width = label_w + bar_track_w + value_w + 16
    height = row_h * len(categories) + 18
    parts = [
        f'<div class="chart"><div class="chart-label">Top categories by revenue</div>'
        f'<svg width="100%" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMinYMin meet">'
    ]
    for i, cat in enumerate(categories):
        y = 12 + i * row_h
        bw = (cat["revenue"] / max_rev) * bar_track_w
        parts.append(
            f'<text x="0" y="{y + 4}" fill="#e6edf3" font-size="12" '
            f'font-family="-apple-system,Segoe UI,sans-serif">{_esc(cat["name"][:18])}</text>'
        )
        parts.append(f'<rect x="{label_w}" y="{y - 8}" width="{bar_track_w}" height="14" fill="#1f262e" rx="3"/>')
        parts.append(f'<rect x="{label_w}" y="{y - 8}" width="{bw:.1f}" height="14" fill="#58a6ff" rx="3"/>')
        parts.append(
            f'<text x="{label_w + bar_track_w + 8}" y="{y + 4}" fill="#8b949e" '
            f'font-size="11" font-family="-apple-system,Segoe UI,sans-serif">'
            f"${cat['revenue']:,.0f}</text>"
        )
    parts.append("</svg></div>")
    return "".join(parts)


def _render_finding(finding: dict[str, Any]) -> str:
    sev = (finding.get("severity") or "").lower()
    sev_class = _SEV_CLASS.get(sev, "sev-low")
    sev_label = sev.capitalize() if sev else "Info"
    raw_title = finding.get("title") or "Untitled finding"
    title = _esc(_strip_store_id(raw_title))
    interp = _inline_bold(finding.get("interpretation") or "")

    evidence = finding.get("evidence") or {}
    table_html = _render_evidence_table(evidence)

    category = (finding.get("category") or "").lower()
    chart_html = ""
    if category == "store_performance":
        series = _coerce_series(evidence)
        if series:
            chart_html = _render_sparkline(series)
    elif category in ("product", "trend"):
        cats = _coerce_categories(evidence)
        if cats:
            chart_html = _render_category_chart(cats)

    action = finding.get("recommended_action")
    action_html = ""
    if action:
        action_html = f'<div class="action"><span class="action-glyph">▸</span>{_esc(action)}</div>'

    return (
        f'<article class="card {sev_class}">'
        f'<div class="card-head">'
        f'<span class="sev-tag">{_esc(sev_label)}</span>'
        f"<h2>{title}</h2>"
        f"</div>"
        f'<p class="interp">{interp}</p>'
        f"{chart_html}"
        f"{table_html}"
        f"{action_html}"
        f"</article>"
    )


def _render_body(briefing: dict[str, Any]) -> str:
    findings_data = briefing.get("analyst_findings") or {}
    md = briefing.get("briefing_markdown") or ""
    title, headline = _extract_title_and_headline(md, findings_data.get("headline", ""))

    hero = f'<section class="hero"><h1>{_esc(title)}</h1><p class="headline">{_inline_bold(headline)}</p></section>'

    tiles = _render_tiles(findings_data.get("stats") or {})

    findings = findings_data.get("findings") or []
    if findings:
        cards = "".join(_render_finding(f) for f in findings)
        findings_html = f'<div class="findings">{cards}</div>'
    else:
        findings_html = '<p class="empty">No findings in this briefing.</p>'

    return hero + tiles + findings_html


_LOADING_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <meta http-equiv="refresh" content="3;url=/">
  <title>Running briefing...</title>
  <style>
    html, body {
      background: #0e1116; color: #e6edf3; margin: 0; height: 100%;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    }
    .wrap {
      min-height: 100%; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 20px;
      padding: 24px; text-align: center;
    }
    .spinner {
      width: 36px; height: 36px; border-radius: 50%;
      border: 3px solid #2a313a; border-top-color: #58a6ff;
      animation: spin 0.9s linear infinite;
    }
    .msg { font-size: 17px; font-weight: 500; letter-spacing: 0.01em; }
    .sub { color: #8b949e; font-size: 13px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="spinner" aria-hidden="true"></div>
    <div class="msg">Running briefing...</div>
    <div class="sub">This page will refresh automatically.</div>
  </div>
</body>
</html>"""


_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Daily Ops Briefing</title>
  <style>
    :root {{
      --bg: #0e1116;
      --surface: #161b22;
      --surface-2: #1f262e;
      --fg: #e6edf3;
      --muted: #8b949e;
      --border: #2a313a;
      --accent: #58a6ff;
      --sev-high: #f85149;
      --sev-med: #d29922;
      --sev-low: #3fb950;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ background: var(--bg); }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter",
        system-ui, sans-serif;
      color: var(--fg);
      margin: 0;
      padding: 28px 20px 64px;
      max-width: 960px; margin-left: auto; margin-right: auto;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}
    .topbar {{
      display: flex; justify-content: space-between; align-items: center;
      color: var(--muted); font-size: 12px; letter-spacing: 0.02em;
      margin-bottom: 18px;
    }}
    .topbar .brand {{
      color: var(--fg); font-weight: 600; letter-spacing: 0.04em;
      text-transform: uppercase; font-size: 11px;
    }}
    .topbar .refresh {{
      color: var(--muted); text-decoration: none; border: 1px solid var(--border);
      padding: 5px 10px; border-radius: 6px; font-size: 11px;
      text-transform: uppercase; letter-spacing: 0.06em;
    }}
    .topbar .refresh:hover {{ color: var(--fg); border-color: var(--accent); }}
    .hero {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 28px; margin-bottom: 16px;
    }}
    .hero h1 {{
      margin: 0 0 10px 0; font-size: 26px; font-weight: 600;
      letter-spacing: -0.01em;
    }}
    .hero .headline {{
      margin: 0; color: var(--muted); font-size: 16px; line-height: 1.55;
    }}
    .hero .headline strong {{ color: var(--fg); font-weight: 600; }}
    .tiles {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px; margin-bottom: 20px;
    }}
    .tile {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 10px; padding: 14px 16px;
    }}
    .tile-label {{
      color: var(--muted); font-size: 11px; text-transform: uppercase;
      letter-spacing: 0.08em; margin-bottom: 6px;
    }}
    .tile-value {{
      font-size: 22px; font-weight: 600; letter-spacing: -0.01em;
    }}
    .tile-pos {{ color: var(--sev-low); }}
    .tile-neg {{ color: var(--sev-high); }}
    .findings {{ display: flex; flex-direction: column; gap: 12px; }}
    .card {{
      background: var(--surface); border: 1px solid var(--border);
      border-left: 4px solid var(--border);
      border-radius: 10px; padding: 22px 24px;
      display: flex; flex-direction: column; gap: 16px;
    }}
    .card.sev-high {{ border-left-color: var(--sev-high); }}
    .card.sev-med {{ border-left-color: var(--sev-med); }}
    .card.sev-low {{ border-left-color: var(--sev-low); }}
    .card-head {{
      display: flex; align-items: center; gap: 10px; margin: 0;
    }}
    .card h2 {{
      font-size: 17px; font-weight: 600; margin: 0;
    }}
    .sev-tag {{
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
      padding: 3px 8px; border-radius: 999px; font-weight: 600;
      background: var(--surface-2); color: var(--muted);
    }}
    .card.sev-high .sev-tag {{ color: var(--sev-high); }}
    .card.sev-med .sev-tag {{ color: var(--sev-med); }}
    .card.sev-low .sev-tag {{ color: var(--sev-low); }}
    .card .interp {{
      margin: 0; color: var(--fg); font-size: 15px; line-height: 1.55;
    }}
    .card .interp strong {{ color: var(--accent); font-weight: 600; }}
    .kv {{
      width: 100%; border-collapse: collapse;
      background: var(--surface-2); border-radius: 8px;
      overflow: hidden;
    }}
    .kv tr + tr td {{ border-top: 1px solid var(--border); }}
    .kv td {{ padding: 8px 14px; font-size: 13px; vertical-align: middle; }}
    .kv .kv-key {{
      color: var(--muted); width: 50%;
      text-transform: capitalize; letter-spacing: 0.01em;
    }}
    .kv .kv-val {{
      color: var(--fg); font-weight: 600; text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .chart {{
      background: var(--surface-2); border-radius: 8px;
      padding: 12px 14px;
    }}
    .chart-label {{
      color: var(--muted); font-size: 11px;
      text-transform: uppercase; letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .chart svg {{ display: block; }}
    .action {{
      background: rgba(88, 166, 255, 0.08);
      border: 1px solid rgba(88, 166, 255, 0.2);
      color: var(--accent);
      padding: 12px 16px; border-radius: 8px;
      font-size: 14px; font-weight: 500;
      display: flex; gap: 10px; align-items: flex-start;
    }}
    .action-glyph {{ font-weight: 700; }}
    .empty {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 32px; text-align: center;
      color: var(--muted);
    }}
    .empty h2 {{ color: var(--fg); margin: 0 0 8px 0; font-size: 18px; }}
    .empty p {{ margin: 4px 0; }}
    .btn {{
      display: inline-block; margin-top: 12px;
      background: var(--accent); color: #0e1116;
      padding: 8px 16px; border-radius: 6px; text-decoration: none;
      font-weight: 600; font-size: 13px;
    }}
    .btn:hover {{ filter: brightness(1.1); }}
    footer {{
      margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border);
      color: var(--muted); font-size: 12px; text-align: center;
    }}
    @media (max-width: 600px) {{
      body {{ padding: 20px 14px 48px; }}
      .hero {{ padding: 22px; }}
      .hero h1 {{ font-size: 22px; }}
      .hero .headline {{ font-size: 15px; }}
      .tile-value {{ font-size: 19px; }}
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <span class="brand">Daily Ops Briefing</span>
    <span>{date} · {meta}</span>
  </div>
  {body}
  <footer>
    Two-agent system (Analyst + Writer) running on Claude Sonnet 5.5.
    Synthetic dataset modelled on multi-site QSR patterns.
  </footer>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
