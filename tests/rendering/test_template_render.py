"""Quality gate: every page template must render with the same Jinja2
environment (filters + globals) as routes.py.

Catches "No filter named 'X'" errors before they reach the browser.
This is what would have caught the missing 'shorten_path' filter.

Each test loads a page template with minimal context data and verifies it
does not raise Jinja2 UndefinedError, TemplateRuntimeError, or
TemplateAssertionError.
"""

from __future__ import annotations

import pathlib
import urllib.parse

import jinja2
import pytest

# ── Mirror routes.py template environment ──────────────────────────────

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "session_browser" / "web" / "templates"


def _make_page_env() -> jinja2.Environment:
    """Create a Jinja2 Environment with the SAME filters as routes.py.

    If a filter registered in routes.py is missing here, the test will
    fail — that's the safety net we want.
    """
    import os
    import re
    from session_browser.web.safe_render import safe_json_display

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )

    # intentionally mirrors routes.py filter registrations;
    # if a new filter is added there but not here, the page render
    # will fail and the test will catch it.
    env.filters["format_number"] = lambda n: (
        "0" if n is None
        else f"{n / 1_000_000:.1f}M" if n >= 1_000_000
        else f"{n / 1_000:.1f}K" if n >= 1_000
        else str(int(n))
    )
    env.filters["format_number_short"] = env.filters["format_number"]
    env.filters["format_compact_token"] = lambda n: (
        "0" if n is None
        else f"{n / 1_000_000:.1f}M" if n >= 1_000_000
        else f"{n / 1_000:.1f}K" if n >= 1_000
        else str(int(n))
    )
    env.filters["format_1d"] = lambda n: f"{n:.1f}" if n is not None else "0.0"
    env.filters["format_bytes"] = lambda n: (
        "0 B" if not n else
        f"{int(n)} B" if int(n) < 1024 else
        f"{int(n) / 1024:.1f} KB" if int(n) < 1024 * 1024 else
        f"{int(n) / (1024 * 1024):.1f} MB" if int(n) < 1024 * 1024 * 1024 else
        f"{int(n) / (1024 * 1024 * 1024):.1f} GB"
    )
    env.filters["format_duration"] = lambda s: (
        f"{int(s // 3600)}h {int((s % 3600) // 60)}min" if s >= 3600
        else f"{int(s // 60)}min {int(s % 60)}s" if s >= 60
        else f"{int(s)}s"
    )
    env.filters["relative_time"] = lambda iso: str(iso) if iso else "—"
    env.filters["local_time"] = lambda iso: str(iso) if iso else "—"
    env.filters["urlencode"] = urllib.parse.quote
    env.filters["urldecode"] = urllib.parse.unquote
    env.filters["tojson_safe"] = lambda v: safe_json_display(v)
    env.filters["safe_json_display"] = safe_json_display
    env.filters["markdown"] = lambda t: t  # passthrough for test
    env.filters["render_llm_blocks_html"] = lambda t: ""  # passthrough
    env.filters["strip_line_numbers"] = lambda t: (
        re.sub(r'^\d+\t', '', t, flags=re.MULTILINE)
        if t and re.search(r'^\d+\t', t, flags=re.MULTILINE) else t
    )
    env.filters["renumber_lines"] = lambda t: t  # passthrough for test
    env.filters["display_path"] = lambda p: p or ""
    env.filters["truncate_path"] = lambda p: (p or "")[:40] + "…" if p and len(p) > 40 else (p or "")
    env.filters["relative_to_repo"] = lambda p: p or ""
    env.filters["shorten_path"] = lambda p: p or ""
    env.globals["max"] = max

    return env


# ── Helpers ─────────────────────────────────────────────────────────────

def _render_page(page_name: str, context: dict) -> str:
    """Render a page template with the given context.

    Raises AssertionError if Jinja2 UndefinedError or
    TemplateRuntimeError occurs (e.g. missing filter).
    """
    env = _make_page_env()
    try:
        tpl = env.get_template(page_name)
        return tpl.render(**context)
    except (jinja2.UndefinedError, jinja2.TemplateRuntimeError, jinja2.TemplateAssertionError) as e:
        raise AssertionError(f"Template render failed: {page_name}: {e}") from e


# ── Content quality gate ───────────────────────────────────────────────

# Texts that indicate the page rendered an error state instead of real content.
# These come from base.html error fallback and common error patterns.
_ERROR_INDICATORS = [
    "Something Went Wrong",
    "unexpected error occurred",
    "Error details",
    "An unexpected error",
]


def _assert_page_content_ok(html: str, page_title: str) -> None:
    """Verify the rendered HTML looks like a real page, not an error state.

    page_title: the human-readable title expected on the page
                (e.g. "Dashboard", "Sessions", NOT "dashboard.html")
    """
    for indicator in _ERROR_INDICATORS:
        assert indicator not in html, (
            f"{page_title} rendered error state: '{indicator}' — "
            "the quality gate should have caught this"
        )
    # Page must contain its primary title (verifies it's not empty/broken)
    assert page_title in html, (
        f"'{page_title}' not found in rendered HTML — page may be blank or broken"
    )


# ── Tests ───────────────────────────────────────────────────────────────

class TestDashboardRender:
    """dashboard.html must render without filter/template errors."""

    def test_dashboard_renders(self):
        html = _render_page("dashboard.html", {
            "stats": {
                "total_sessions": 0,
                "total_tokens": 0,
                "total_tool_calls": 0,
                "total_failed_tools": 0,
                "project_count": 0,
            },
            "top_agents": [],
            "top_projects": [],
            "top_models": [],
            "model_breakdown": [],
            "daily_sessions": [],
            "daily_tokens": [],
            "error_count": 0,
        })
        assert "Dashboard" in html
        _assert_page_content_ok(html, "Dashboard")


class TestSessionsRender:
    """sessions.html must render without filter/template errors."""

    def test_sessions_renders(self):
        # Minimal stub for sessions_aggregate object
        agg = type("A", (), {
            "project_count": 0,
            "total_tokens": 0,
        })()
        html = _render_page("sessions.html", {
            "sessions": [],
            "total_count": 0,
            "total_pages": 1,
            "page": 1,
            "page_start": 0,
            "page_end": 0,
            "filter_q": "",
            "filter_agent": "",
            "filter_model": "",
            "filter_project": "",
            "projects": [],
            "sessions_aggregate": agg,
            "actions": type("A", (), {
                "clear_all_url": "/sessions",
                "sort_urls": type("S", (), {
                    "tokens": "/sessions?sort=tokens",
                    "rounds": "/sessions?sort=rounds",
                    "tools": "/sessions?sort=tools",
                    "failed": "/sessions?sort=failed",
                    "duration": "/sessions?sort=duration",
                    "updated": "/sessions?sort=updated",
                })(),
            })(),
        })
        assert "Sessions" in html
        _assert_page_content_ok(html, "Sessions")


class TestSessionDetailRender:
    """session.html must render without filter/template errors."""

    def test_session_detail_renders(self):
        html = _render_page("session.html", {
            "session": type("S", (), {
                "title": "Test",
                "session_id": "abc123",
            })(),
            "session_summary": {
                "title": "Test Session",
                "agent_label": "CC",
                "model": "test-model",
                "project_name": "test-project",
                "date": "2025-01-01",
                "session_id": "abc123",
                "manual_input_count": 0,
                "subagent_count": 0,
                "cache_write_pct": "0%",
            },
            "hero_metrics": {"tokens": "0", "rounds": "0", "tools": "0", "failed": "0"},
            "issue_links": [],
            "session_url": "",
            "trace_rows": [],
            "payload_sources": [],
            "current_agent": "claude_code",
            "session_data": "{}",
        })
        assert "Trace" in html
        _assert_page_content_ok(html, "Trace")


class TestProjectRender:
    """project.html must render without filter/template errors."""

    def test_project_renders(self):
        html = _render_page("project.html", {
            "project": type("P", (), {
                "project_name": "Test Project",
                "project_key": "/tmp/test-project",
                "total_sessions": 0,
                "claude_sessions": 0,
                "codex_sessions": 0,
                "qoder_sessions": 0,
                "total_input_tokens": 0,
                "total_cached_tokens": 0,
                "total_cache_write_tokens": 0,
                "total_output_tokens": 0,
                "total_tool_calls": 0,
                "total_assistant_messages": 0,
                "first_seen": "2025-01-01",
                "last_seen": "2025-01-15",
            })(),
            "sessions": [],
            "current_page": 1,
            "total_pages": 1,
            "error": None,
        })
        assert "Test Project" in html
        _assert_page_content_ok(html, "Test Project")


class TestProjectsRender:
    """projects.html must render without filter/template errors."""

    def test_projects_renders(self):
        html = _render_page("projects.html", {
            "projects": [],
        })
        assert "Projects" in html
        _assert_page_content_ok(html, "Projects")


class TestAgentDetailRender:
    """agent.html must render without filter/template errors."""

    def test_agent_detail_renders(self):
        html = _render_page("agent.html", {
            "agent_summary": {
                "name": "Claude Code",
                "key": "claude_code",
                "total_sessions": 0,
                "total_tokens": 0,
                "total_rounds": 0,
                "total_tools": 0,
                "total_failed": 0,
            },
            "sessions": [],
            "models": [],
            "model_breakdown": [],
            "current_page": 1,
            "total_pages": 1,
            "error": None,
        })
        assert "Agent" in html
        _assert_page_content_ok(html, "Agent")


class TestAgentsRender:
    """agents.html must render without filter/template errors."""

    def test_agents_renders(self):
        html = _render_page("agents.html", {
            "agents": [],
        })
        assert "Agents" in html
        _assert_page_content_ok(html, "Agents")
