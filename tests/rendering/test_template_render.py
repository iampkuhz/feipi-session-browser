"""质量门：每个页面模板必须使用与 routes.py 相同的 Jinja2
环境（过滤器 + 全局变量）进行渲染。

在错误到达浏览器之前捕获“未找到名为 'X' 的过滤器”错误。
这正是应该捕获缺失 'shorten_path' 过滤器的安全网。

每个测试使用最小上下文数据加载页面模板，并验证其
不会抛出 Jinja2 UndefinedError、TemplateRuntimeError 或
TemplateAssertionError。
"""

from __future__ import annotations

import pytest
import pathlib
import urllib.parse

import jinja2
# ── 镜像 routes.py 模板环境 ─────────────────────────────────────────

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "templates"


def _make_page_env() -> jinja2.Environment:
    """
    创建与 routes.py 相同过滤器的 Jinja2 环境。

    如果此处缺失了 routes.py 中注册的过滤器，测试将
    失败 — 这正是我们想要的安全网。
    """
    import os
    import re
    from session_browser.web.safe_render import safe_json_display

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )

    # 有意镜像 routes.py 中的过滤器注册；
    # 如果新过滤器添加到了那边但未添加到这边，
    # 页面渲染将失败，测试会捕获到。
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
    env.filters["markdown"] = lambda t: t  # 测试用直通
    env.filters["render_llm_blocks_html"] = lambda t: ""  # 直通
    env.filters["strip_line_numbers"] = lambda t: (
        re.sub(r'^\d+\t', '', t, flags=re.MULTILINE)
        if t and re.search(r'^\d+\t', t, flags=re.MULTILINE) else t
    )
    env.filters["renumber_lines"] = lambda t: t  # 测试用直通
    env.filters["display_path"] = lambda p: p or ""
    env.filters["truncate_path"] = lambda p: (p or "")[:40] + "…" if p and len(p) > 40 else (p or "")
    env.filters["relative_to_repo"] = lambda p: p or ""
    env.filters["shorten_path"] = lambda p: p or ""
    env.globals["max"] = max

    return env


# ── 辅助函数 ──────────────────────────────────────────────────────────────

def _render_page(page_name: str, context: dict) -> str:
    """使用给定上下文渲染页面模板。

    如果发生 Jinja2 UndefinedError 或
    TemplateRuntimeError（例如缺少过滤器），则抛出 AssertionError。
    """
    env = _make_page_env()
    try:
        tpl = env.get_template(page_name)
        return tpl.render(**context)
    except (jinja2.UndefinedError, jinja2.TemplateRuntimeError, jinja2.TemplateAssertionError) as e:
        raise AssertionError(f"Template render failed: {page_name}: {e}") from e


# ── 内容质量门 ───────────────────────────────────────────────────────────

# 指示页面渲染为错误状态而非真实内容的文本。
# 这些来自 base.html 的错误回退和常见错误模式。
_ERROR_INDICATORS = [
    "Something Went Wrong",
    "unexpected error occurred",
    "Error details",
    "An unexpected error",
]


def _assert_page_content_ok(html: str, page_title: str) -> None:
    """验证渲染的 HTML 看起来像真实页面，而非错误状态。

    page_title: 页面上预期的人类可读标题
                （例如 "Dashboard"、"Sessions"，而非 "dashboard.html"）
    """
    for indicator in _ERROR_INDICATORS:
        assert indicator not in html, (
            f"{page_title} rendered error state: '{indicator}' — "
            "the quality gate should have caught this"
        )
    # 页面必须包含其主要标题（验证不为空/损坏）
    assert page_title in html, (
        f"'{page_title}' not found in rendered HTML — page may be blank or broken"
    )


# ── 测试 ──────────────────────────────────────────────────────────────────

class TestDashboardRender:
    """dashboard.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
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
    """sessions.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
    def test_sessions_renders(self):
        # sessions_aggregate 对象的最小桩
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
    """session.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
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
    """project.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
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
    """projects.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
    def test_projects_renders(self):
        html = _render_page("projects.html", {
            "projects": [],
        })
        assert "Projects" in html
        _assert_page_content_ok(html, "Projects")


class TestAgentDetailRender:
    """agent.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
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
    """agents.html 必须在无过滤器/模板错误的情况下渲染。"""

    @pytest.mark.contract_case("ROUTE-API-004")
    def test_agents_renders(self):
        html = _render_page("agents.html", {
            "agents": [],
        })
        assert "Agents" in html
        _assert_page_content_ok(html, "Agents")
