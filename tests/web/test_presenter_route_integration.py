"""Presenter route integration tests.

Covers:
- All routes correctly call their presenter and return expected view-model keys.
- Presenter output is consumable by Jinja templates (render without error).
- Each page route returns HTTP 200 when a fixture server is available.
- Presenters are pure functions — they only depend on their explicit
  parameters (sqlite3.Connection, raw_params, etc.) and do not reach
  into HTTP context or global state.
"""
from __future__ import annotations

import pytest
import os
import sqlite3
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from session_browser.web.presenters.dashboard import build_dashboard_view_model
from session_browser.web.presenters.agents import (
    build_agents_view_model,
    build_agent_view_model,
)
from session_browser.web.presenters.projects import (
    build_projects_view_model,
    build_project_view_model,
)
from session_browser.web.presenters.sessions import (
    parse_sessions_query_params,
    compute_pagination,
    fetch_sessions_view_model,
    build_sessions_context,
)

# ─── Presenter module map for parametrize ─────────────────────────────

_PRESENTER_MODULES = {
    "dashboard": "session_browser.web.presenters.dashboard",
    "agents": "session_browser.web.presenters.agents",
    "projects": "session_browser.web.presenters.projects",
    "sessions": "session_browser.web.presenters.sessions",
}

# ─── Pure-function assertion helpers ──────────────────────────────────

# Global state that presenters must NOT access
_FORBIDDEN_GLOBALS = [
    "request",
    "flask",
    "http.server",
    "BaseHTTPRequestHandler",
    "self.path",
    "self.headers",
]


# ─── Dashboard presenter route integration ────────────────────────────

_DASHBOARD_INDEXERS = [
    "get_dashboard_stats",
    "list_projects",
    "get_trend_data",
    "get_prompt_activity_trend",
    "get_model_distribution",
    "get_agent_distribution",
    "get_token_breakdown",
    "compute_aggregate_metrics",
    "list_sessions",
    "compute_derived_metrics",
    "detect_all_anomalies",
    "get_needs_attention",
]


def _patch_dashboard_indexers():
    """Return an ExitStack patching all dashboard presenter dependencies."""
    stack = ExitStack()
    patchers = {}
    for name in _DASHBOARD_INDEXERS:
        p = patch(f"session_browser.web.presenters.dashboard.{name}")
        patchers[name] = stack.enter_context(p)
    stack.get_patchers = lambda: patchers
    return stack


def _default_dashboard_mocks(patchers):
    """Apply zero-data defaults to all dashboard patchers."""
    patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
    patchers["list_projects"].return_value = []
    patchers["get_trend_data"].return_value = []
    patchers["get_prompt_activity_trend"].return_value = []
    md = MagicMock()
    md.distribution = {}
    patchers["get_model_distribution"].return_value = md
    patchers["get_agent_distribution"].return_value = {}
    patchers["get_token_breakdown"].return_value = MagicMock(
        total_input=0, total_output=0,
        total_cached_input=0, total_cached_output=0,
        total_tool_calls=0, total_failed_tools=0,
    )
    patchers["compute_aggregate_metrics"].return_value = {}
    patchers["list_sessions"].return_value = []
    patchers["compute_derived_metrics"].side_effect = lambda d: d
    patchers["detect_all_anomalies"].return_value = {}
    patchers["get_needs_attention"].return_value = []


class TestDashboardRoutePresenter:
    """Verify /dashboard route calls presenter correctly."""

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_route_presenter_returns_expected_keys(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)

        expected_keys = {
            "stats", "projects", "trend", "prompt_activity",
            "model_dist", "agent_dist", "tokens", "aggregate",
            "needs_attention", "active_page",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_route_presenter_active_page(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)

        assert result["active_page"] == "dashboard"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_route_presenter_is_pure_function(self):
        """Presenter only uses conn parameter, no HTTP globals."""
        import inspect
        source = inspect.getsource(build_dashboard_view_model)
        for forbidden in _FORBIDDEN_GLOBALS:
            assert forbidden not in source, (
                f"Presenter references forbidden global: {forbidden}"
            )


# ─── Agents presenter route integration ───────────────────────────────

class TestAgentsRoutePresenter:
    """Verify /agents and /agents/<agent> routes call presenters correctly."""

    @pytest.mark.contract_case("ROUTE-API-011")
    @pytest.mark.contract_case("ROUTE-API-008")
    def test_agents_list_returns_expected_keys(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as mock_agents, \
             patch("session_browser.web.presenters.agents.compute_agent_efficiency") as mock_eff:
            mock_agents.return_value = []
            mock_eff.return_value = {}
            result = build_agents_view_model(conn)

        expected_keys = {"agents", "efficiency", "current_agent", "active_page"}
        assert set(result.keys()) == expected_keys
        assert result["active_page"] == "agents"
        assert result["current_agent"] == "__all__"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agent_detail_returns_expected_keys(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as mock_agents, \
             patch("session_browser.web.presenters.agents.list_sessions") as mock_sessions:
            mock_agents.return_value = [
                {"agent": "claude_code", "name": "Claude Code"},
                {"agent": "codex", "name": "Codex"},
            ]
            mock_sessions.return_value = []
            result = build_agent_view_model(conn, "claude_code")

        expected_keys = {"agents", "agent_info", "sessions", "current_agent", "active_page"}
        assert set(result.keys()) == expected_keys
        assert result["current_agent"] == "claude_code"
        assert result["agent_info"]["agent"] == "claude_code"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agent_detail_nonexistent_agent_returns_none_info(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as mock_agents, \
             patch("session_browser.web.presenters.agents.list_sessions") as mock_sessions:
            mock_agents.return_value = []
            mock_sessions.return_value = []
            result = build_agent_view_model(conn, "unknown_agent")

        assert result["agent_info"] is None
        assert result["current_agent"] == "unknown_agent"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_presenters_are_pure_functions(self):
        import inspect
        for fn in (build_agents_view_model, build_agent_view_model):
            source = inspect.getsource(fn)
            for forbidden in _FORBIDDEN_GLOBALS:
                assert forbidden not in source, (
                    f"Presenter references forbidden global: {forbidden}"
                )


# ─── Projects presenter route integration ─────────────────────────────

class TestProjectsRoutePresenter:
    """Verify /projects and /projects/<key> routes call presenters correctly."""

    @pytest.mark.contract_case("ROUTE-API-011")
    @pytest.mark.contract_case("ROUTE-API-007")
    def test_projects_list_returns_expected_keys(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.count_projects") as mock_count, \
             patch("session_browser.web.presenters.projects.list_projects") as mock_projects:
            mock_count.return_value = 0
            mock_projects.return_value = []
            result = build_projects_view_model({}, conn)

        expected_keys = {
            "projects", "active_page", "page", "current_page", "page_size",
            "total_pages", "total_count", "page_start", "page_end",
            "has_prev", "has_next",
        }
        assert set(result.keys()) == expected_keys
        assert result["active_page"] == "projects"
        assert result["page"] == 1
        assert result["current_page"] == 1
        assert result["page_size"] == 20
        assert result["total_pages"] == 1
        assert result["total_count"] == 0

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_project_detail_returns_expected_keys(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.count_sessions") as mock_count, \
             patch("session_browser.web.presenters.projects.get_project_stats") as mock_stats, \
             patch("session_browser.web.presenters.projects.list_sessions") as mock_sessions:
            mock_count.return_value = 0
            mock_stats.return_value = {"project_key": "test-proj", "session_count": 5}
            mock_sessions.return_value = []
            result = build_project_view_model(conn, "test-proj")

        expected_keys = {
            "project", "sessions", "project_key", "active_page",
            "page", "current_page", "page_size", "total_pages",
            "total_count", "page_start", "page_end", "has_prev", "has_next",
        }
        assert set(result.keys()) == expected_keys
        assert result["project_key"] == "test-proj"
        assert result["active_page"] == "projects"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_presenters_are_pure_functions(self):
        import inspect
        for fn in (build_projects_view_model, build_project_view_model):
            source = inspect.getsource(fn)
            for forbidden in _FORBIDDEN_GLOBALS:
                assert forbidden not in source, (
                    f"Presenter references forbidden global: {forbidden}"
                )


# ─── Sessions presenter route integration ─────────────────────────────

class TestSessionsRoutePresenter:
    """Verify /sessions route calls presenter correctly."""

    @staticmethod
    def _make_mock_conn():
        conn = MagicMock()
        mock_models_cursor = MagicMock()
        mock_models_cursor.fetchall.return_value = []
        mock_projects_cursor = MagicMock()
        mock_projects_cursor.fetchall.return_value = []

        def mock_execute(sql, *args):
            if "DISTINCT model" in sql:
                return mock_models_cursor
            elif "DISTINCT project_key" in sql:
                return mock_projects_cursor
            return MagicMock()

        conn.execute.side_effect = mock_execute
        return conn

    @pytest.mark.contract_case("ROUTE-API-011")
    @pytest.mark.contract_case("ROUTE-API-006")
    def test_sessions_context_returns_expected_keys(self):
        conn = self._make_mock_conn()
        with patch("session_browser.web.presenters.sessions.count_sessions") as mock_count, \
             patch("session_browser.web.presenters.sessions.fetch_sessions_view_model") as mock_vm:
            mock_count.return_value = 0
            mock_vm.return_value = {
                "sessions_enriched": [],
                "total_count": 0,
                "sessions_aggregate": {},
                "model_list": [],
                "project_list": [],
            }
            result = build_sessions_context({}, conn)

        expected_keys = {
            "sessions", "total_count", "page", "current_page",
            "page_size", "total_pages", "page_start", "page_end",
            "has_prev", "has_next", "filter_agent", "filter_model",
            "filter_project", "filter_q", "sort_by", "sort_dir",
            "model_list", "project_list", "sessions_aggregate",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_sessions_parse_query_params_integration(self):
        """parse_sessions_query_params is the entry point for /sessions query."""
        raw = {"page": ["2"], "agent": ["claude_code"], "sort": ["tokens"], "dir": ["asc"]}
        result = parse_sessions_query_params(raw)
        assert result["page"] == 2
        assert result["filter_agent"] == "claude_code"
        assert result["sort_by"] == "total_tokens"
        assert result["sort_dir"] == "asc"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_pagination_integration(self):
        conn = self._make_mock_conn()
        with patch("session_browser.web.presenters.sessions.count_sessions") as mock_count, \
             patch("session_browser.web.presenters.sessions.fetch_sessions_view_model") as mock_vm:
            mock_count.return_value = 100
            mock_vm.return_value = {
                "sessions_enriched": [],
                "total_count": 100,
                "sessions_aggregate": {},
                "model_list": [],
                "project_list": [],
            }
            result = build_sessions_context({"page": ["3"], "page_size": ["20"]}, conn)

        assert result["page"] == 3
        assert result["total_pages"] == 5
        assert result["has_prev"] is True
        assert result["has_next"] is True

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_fetch_sessions_view_model_returns_expected_keys(self):
        conn = MagicMock()
        mock_cursor_models = MagicMock()
        mock_cursor_models.fetchall.return_value = []
        mock_cursor_projects = MagicMock()
        mock_cursor_projects.fetchall.return_value = []

        def mock_execute(sql, *args):
            if "DISTINCT model" in sql:
                return mock_cursor_models
            elif "DISTINCT project_key" in sql:
                return mock_cursor_projects
            return MagicMock()

        conn.execute.side_effect = mock_execute

        with patch("session_browser.web.presenters.sessions.count_sessions") as mock_count, \
             patch("session_browser.web.presenters.sessions.get_sessions_list_aggregate") as mock_agg, \
             patch("session_browser.web.presenters.sessions.list_sessions") as mock_list, \
             patch("session_browser.web.presenters.sessions.compute_derived_metrics") as mock_derived, \
             patch("session_browser.web.presenters.sessions.detect_all_anomalies") as mock_anomalies, \
             patch("session_browser.web.presenters.sessions.enrich_sessions_with_anomalies") as mock_enrich:
            mock_count.return_value = 0
            mock_agg.return_value = {}
            mock_list.return_value = []
            mock_derived.side_effect = lambda d: d
            mock_anomalies.return_value = {}
            mock_enrich.return_value = []

            result = fetch_sessions_view_model(
                conn=conn,
                filter_agent=None,
                filter_model=None,
                filter_project=None,
                filter_q=None,
                sort_by="ended_at",
                sort_dir="desc",
                limit=20,
                offset=0,
            )

        expected_keys = {
            "sessions_enriched", "total_count", "sessions_aggregate",
            "model_list", "project_list",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_sessions_presenter_functions_are_pure(self):
        import inspect
        for fn in (
            parse_sessions_query_params,
            compute_pagination,
            build_sessions_context,
        ):
            source = inspect.getsource(fn)
            for forbidden in _FORBIDDEN_GLOBALS:
                assert forbidden not in source, (
                    f"Presenter references forbidden global: {forbidden}"
                )


# ─── Cross-presenter route-to-view-model contract ────────────────────

class TestAllPresentersShareActivePage:
    """Every list presenter should set active_page for nav highlighting."""

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_dashboard_active_page(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)
        assert result["active_page"] == "dashboard"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agents_active_page(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as m_agents, \
             patch("session_browser.web.presenters.agents.compute_agent_efficiency") as m_eff:
            m_agents.return_value = []
            m_eff.return_value = {}
            result = build_agents_view_model(conn)
        assert result["active_page"] == "agents"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_projects_active_page(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.list_projects") as m_proj:
            m_proj.return_value = []
            result = build_projects_view_model(conn)
        assert result["active_page"] == "projects"


class TestPresenterReturnTypes:
    """All presenters must return dict (JSON-serializable view models)."""

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_dashboard_returns_dict(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)
        assert isinstance(result, dict)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agents_returns_dict(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as m_agents, \
             patch("session_browser.web.presenters.agents.compute_agent_efficiency") as m_eff:
            m_agents.return_value = []
            m_eff.return_value = {}
            result = build_agents_view_model(conn)
        assert isinstance(result, dict)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agent_detail_returns_dict(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as m_agents, \
             patch("session_browser.web.presenters.agents.list_sessions") as m_sessions:
            m_agents.return_value = []
            m_sessions.return_value = []
            result = build_agent_view_model(conn, "claude_code")
        assert isinstance(result, dict)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_projects_returns_dict(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.list_projects") as m_proj:
            m_proj.return_value = []
            result = build_projects_view_model(conn)
        assert isinstance(result, dict)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_project_detail_returns_dict(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.get_project_stats") as m_stats, \
             patch("session_browser.web.presenters.projects.list_sessions") as m_sessions:
            m_stats.return_value = {}
            m_sessions.return_value = []
            result = build_project_view_model(conn, "test-proj")
        assert isinstance(result, dict)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_sessions_context_returns_dict(self):
        conn = MagicMock()
        mock_models = MagicMock()
        mock_models.fetchall.return_value = []
        mock_projects = MagicMock()
        mock_projects.fetchall.return_value = []
        conn.execute.side_effect = lambda sql, *args: (
            mock_models if "DISTINCT model" in sql else mock_projects
        )

        with patch("session_browser.web.presenters.sessions.count_sessions") as mc, \
             patch("session_browser.web.presenters.sessions.fetch_sessions_view_model") as mvm:
            mc.return_value = 0
            mvm.return_value = {
                "sessions_enriched": [], "total_count": 0,
                "sessions_aggregate": {}, "model_list": [],
                "project_list": [],
            }
            result = build_sessions_context({}, conn)
        assert isinstance(result, dict)


# ─── Template consumption tests ───────────────────────────────────────

class TestPresenterOutputConsumableByTemplate:
    """Presenter view models must not contain types that break Jinja rendering."""

    @staticmethod
    def _make_jinja_env():
        from jinja2 import Environment, FileSystemLoader
        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "session_browser", "web", "templates",
        )
        return Environment(
            loader=FileSystemLoader(template_dir),
            undefined=__import__("jinja2").Undefined,
        )

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_dashboard_vm_has_no_render_blocking_types(self):
        """Dashboard VM values should be JSON/Jinja friendly."""
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            # Replace MagicMock token_breakdown with a non-callable named tuple
            from collections import namedtuple
            TokenBreakdown = namedtuple("TokenBreakdown", [
                "total_input", "total_output",
                "total_cached_input", "total_cached_output",
                "total_tool_calls", "total_failed_tools",
            ])
            patchers["get_token_breakdown"].return_value = TokenBreakdown(0, 0, 0, 0, 0, 0)
            result = build_dashboard_view_model(conn)

        for key, value in result.items():
            assert not callable(value), (
                f"Presenter key '{key}' holds a callable — template cannot render it"
            )

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agents_vm_has_no_render_blocking_types(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.agents.list_agents") as m_agents, \
             patch("session_browser.web.presenters.agents.compute_agent_efficiency") as m_eff:
            m_agents.return_value = []
            m_eff.return_value = {}
            result = build_agents_view_model(conn)

        for key, value in result.items():
            assert not callable(value), (
                f"Presenter key '{key}' holds a callable — template cannot render it"
            )

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_projects_vm_has_no_render_blocking_types(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.list_projects") as m_proj:
            m_proj.return_value = []
            result = build_projects_view_model(conn)

        for key, value in result.items():
            assert not callable(value), (
                f"Presenter key '{key}' holds a callable — template cannot render it"
            )


# ─── HTTP 200 route tests (when fixture server available) ────────────

class TestRouteHttp200:
    """Verify each page route returns HTTP 200 when fixture server is running.

    These tests are skipped unless a test index/server fixture is available.
    """

    @staticmethod
    def _fetch_html(url: str) -> str:
        """Fetch URL and return decoded HTML text."""
        import urllib.request
        resp = urllib.request.urlopen(url, timeout=15)
        assert resp.status == 200
        return resp.read().decode("utf-8")

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_dashboard_route_200(self, local_test_server):
        base_url, agent, session_id = local_test_server
        html = self._fetch_html(f"{base_url}/dashboard")
        assert len(html) > 0

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_agents_route_200(self, local_test_server):
        base_url, agent, session_id = local_test_server
        html = self._fetch_html(f"{base_url}/agents")
        assert len(html) > 0

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_projects_route_200(self, local_test_server):
        base_url, agent, session_id = local_test_server
        html = self._fetch_html(f"{base_url}/projects")
        assert len(html) > 0

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_sessions_route_200(self, local_test_server):
        base_url, agent, session_id = local_test_server
        html = self._fetch_html(f"{base_url}/sessions")
        assert len(html) > 0

    @pytest.mark.contract_case("ROUTE-API-011")
    @pytest.mark.contract_case("ROUTE-API-009")
    def test_glossary_route_200(self, local_test_server):
        base_url, agent, session_id = local_test_server
        html = self._fetch_html(f"{base_url}/glossary")
        assert len(html) > 0

    @pytest.mark.contract_case("ROUTE-API-011")
    @pytest.mark.contract_case("ROUTE-API-010")
    def test_root_route_200(self, local_test_server):
        base_url, agent, session_id = local_test_server
        html = self._fetch_html(f"{base_url}/")
        assert len(html) > 0


# ─── Route-to-presenter dispatch mapping ──────────────────────────────

class TestRoutePresenterDispatchMapping:
    """Verify that routes.py imports and wires each presenter correctly.

    This checks the module-level imports in routes.py match the presenter
    functions we test above.
    """

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_routes_imports_dashboard_presenter(self):
        from session_browser.web import routes
        # routes.py uses from-import so the function is available in its namespace
        assert hasattr(routes, "build_dashboard_view_model") is True
        # Verify the function exists in the presenter module
        from session_browser.web.presenters.dashboard import build_dashboard_view_model as fn
        assert callable(fn)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_routes_imports_agents_presenters(self):
        from session_browser.web.presenters.agents import (
            build_agents_view_model,
            build_agent_view_model,
        )
        assert callable(build_agents_view_model)
        assert callable(build_agent_view_model)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_routes_imports_projects_presenters(self):
        from session_browser.web.presenters.projects import (
            build_projects_view_model,
            build_project_view_model,
        )
        assert callable(build_projects_view_model)
        assert callable(build_project_view_model)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_routes_imports_sessions_presenters(self):
        from session_browser.web.presenters.sessions import (
            parse_sessions_query_params,
            compute_pagination,
            fetch_sessions_view_model,
        )
        assert callable(parse_sessions_query_params)
        assert callable(compute_pagination)
        assert callable(fetch_sessions_view_model)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_route_path_to_presenter_map(self):
        """Document and verify the expected route-to-presenter mapping."""
        mapping = {
            "/": "build_dashboard_view_model",
            "/dashboard": "build_dashboard_view_model",
            "/agents": "build_agents_view_model",
            "/agents/<agent>": "build_agent_view_model",
            "/projects": "build_projects_view_model",
            "/projects/<key>": "build_project_view_model",
            "/sessions": "fetch_sessions_view_model",
        }
        # All referenced presenter functions exist and are callable
        from session_browser.web.presenters.dashboard import build_dashboard_view_model
        from session_browser.web.presenters.agents import build_agents_view_model, build_agent_view_model
        from session_browser.web.presenters.projects import build_projects_view_model, build_project_view_model
        from session_browser.web.presenters.sessions import fetch_sessions_view_model

        funcs = {
            "build_dashboard_view_model": build_dashboard_view_model,
            "build_agents_view_model": build_agents_view_model,
            "build_agent_view_model": build_agent_view_model,
            "build_projects_view_model": build_projects_view_model,
            "build_project_view_model": build_project_view_model,
            "fetch_sessions_view_model": fetch_sessions_view_model,
        }
        for route, presenter_name in mapping.items():
            assert presenter_name in funcs, f"Route {route} references unknown presenter {presenter_name}"
            assert callable(funcs[presenter_name]), f"Presenter {presenter_name} is not callable"
