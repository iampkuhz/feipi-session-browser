"""Presenter 与路由集成测试。

覆盖范围：
- 所有路由正确调用其对应的 presenter 并返回预期的视图模型键。
- Presenter 输出可被 Jinja 模板消费（无渲染错误）。
- 当 fixture 服务器可用时，每个页面路由返回 HTTP 200。
- Presenter 是纯函数——仅依赖显式参数（sqlite3.Connection、raw_params 等），
  不访问 HTTP 上下文或全局状态。
"""
from __future__ import annotations

import pytest
import os
import sqlite3
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from session_browser.web.presenters.dashboard import build_dashboard_view_model
from session_browser.web.presenters.projects import (
    build_projects_view_model,
    build_project_detail_view_model,
)
from session_browser.web.presenters.sessions import (
    parse_sessions_query_params,
    compute_pagination,
    fetch_sessions_view_model,
    build_sessions_context,
)

# ─── Presenter 模块映射（用于 parametrize）────────────────────────────

_PRESENTER_MODULES = {
    "dashboard": "session_browser.web.presenters.dashboard",
    "projects": "session_browser.web.presenters.projects",
    "sessions": "session_browser.web.presenters.sessions",
}

# ─── 纯函数断言辅助 ───────────────────────────────────────────────────

# Presenter 不得访问的全局状态
_FORBIDDEN_GLOBALS = [
    "request",
    "flask",
    "http.server",
    "BaseHTTPRequestHandler",
    "self.path",
    "self.headers",
]


# ─── Dashboard presenter 路由集成 ────────────────────────────────────

_DASHBOARD_INDEXERS = [
    "get_dashboard_stats",
    "list_projects",
    "get_trend_data",
    "get_prompt_activity_trend",
    "get_agent_distribution",
    "get_token_breakdown",
    "compute_aggregate_metrics",
    "list_sessions",
    "compute_derived_metrics",
    "detect_all_anomalies",
    "get_needs_attention",
    "list_agents",
    "list_model_stats",
    "_compute_kpis",
]


def _patch_dashboard_indexers():
    """返回一个 ExitStack，patch 所有 dashboard presenter 依赖。"""
    stack = ExitStack()
    patchers = {}
    for name in _DASHBOARD_INDEXERS:
        p = patch(f"session_browser.web.presenters.dashboard.{name}")
        patchers[name] = stack.enter_context(p)
    stack.get_patchers = lambda: patchers
    return stack


def _default_dashboard_mocks(patchers):
    """对所有 dashboard patcher 应用零数据默认值。"""
    patchers["get_dashboard_stats"].return_value = {"total_sessions": 0}
    patchers["list_projects"].return_value = []
    patchers["get_trend_data"].return_value = []
    patchers["get_prompt_activity_trend"].return_value = []
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
    patchers["list_agents"].return_value = []
    patchers["list_model_stats"].return_value = []
    patchers["_compute_kpis"].return_value = []


class TestDashboardRoutePresenter:
    """验证 /dashboard 路由正确调用 presenter。"""

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_route_presenter_returns_expected_keys(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)

        expected_keys = {
            "agent_scope", "grain", "is_single_agent",
            "stats", "kpis", "trend", "prompt_activity",
            "all_agents_branch", "single_agent_branch",
            "agent_sessions_total", "agent_sessions_page",
            "agent_sessions_total_pages", "agent_sessions_page_size",
            "needs_attention", "cache_health",
            "active_page",
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
        """Presenter 仅使用 conn 参数，不依赖 HTTP 全局变量。"""
        import inspect
        source = inspect.getsource(build_dashboard_view_model)
        for forbidden in _FORBIDDEN_GLOBALS:
            assert forbidden not in source, (
                f"Presenter references forbidden global: {forbidden}"
            )


# ─── Projects presenter 路由集成 ────────────────────────────────────

class TestProjectsRoutePresenter:
    """验证 /projects 和 /projects/<key> 路由正确调用 presenter。"""

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
            "filter_q", "sort_by", "sort_dir",
            "total_pages", "total_count", "page_start", "page_end",
            "has_prev", "has_next",
        }
        assert set(result.keys()) == expected_keys
        assert result["active_page"] == "projects"
        assert result["page"] == 1
        assert result["current_page"] == 1
        assert result["page_size"] == 25
        assert result["total_pages"] == 1
        assert result["total_count"] == 0

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_project_detail_returns_expected_keys(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.count_sessions") as mock_count, \
             patch("session_browser.web.presenters.projects.get_project_stats") as mock_stats, \
             patch("session_browser.web.presenters.projects.list_sessions") as mock_sessions:
            mock_count.return_value = 0
            mock_stats.return_value = {
                "project_key": "test-proj",
                "project_name": "Test Project",
                "total_sessions": 5,
            }
            mock_sessions.return_value = []
            result = build_project_detail_view_model(conn, "test-proj")

        expected_keys = {
            "project", "project_detail", "sessions", "project_key", "active_page",
            "error", "filter_q", "sort_by", "sort_dir", "trend_grain",
            "page", "current_page", "page_size", "total_pages",
            "total_count", "page_start", "page_end", "has_prev", "has_next",
        }
        assert set(result.keys()) == expected_keys
        assert result["project_key"] == "test-proj"
        assert result["active_page"] == "projects"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_presenters_are_pure_functions(self):
        import inspect
        for fn in (build_projects_view_model, build_project_detail_view_model):
            source = inspect.getsource(fn)
            for forbidden in _FORBIDDEN_GLOBALS:
                assert forbidden not in source, (
                    f"Presenter references forbidden global: {forbidden}"
                )


# ─── Sessions presenter 路由集成 ────────────────────────────────────

class TestSessionsRoutePresenter:
    """验证 /sessions 路由正确调用 presenter。"""

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
            "filter_project", "filter_q", "filter_status", "sort_by", "sort_dir",
            "model_list", "project_list", "sessions_aggregate",
        }
        assert set(result.keys()) == expected_keys

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_sessions_parse_query_params_integration(self):
        """parse_sessions_query_params 是 /sessions 查询的入口。"""
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
            result = build_sessions_context({"page": ["3"], "page_size": ["25"]}, conn)

        assert result["page"] == 3
        assert result["total_pages"] == 4
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
                filter_status=None,
                sort_by="ended_at",
                sort_dir="desc",
                limit=25,
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


# ─── 跨 Presenter 路由到视图模型契约 ──────────────────────────────────

class TestAllPresentersShareActivePage:
    """每个列表 presenter 都应设置 active_page 用于导航高亮。"""

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_dashboard_active_page(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)
        assert result["active_page"] == "dashboard"

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_projects_active_page(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.list_projects") as m_proj:
            m_proj.return_value = []
            result = build_projects_view_model(conn)
        assert result["active_page"] == "projects"


class TestPresenterReturnTypes:
    """所有 presenter 必须返回 dict（可 JSON 序列化的视图模型）。"""

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_dashboard_returns_dict(self):
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            result = build_dashboard_view_model(conn)
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
            result = build_project_detail_view_model(conn, "test-proj")
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


# ─── 模板消费测试 ─────────────────────────────────────────────────────

class TestPresenterOutputConsumableByTemplate:
    """Presenter 视图模型不得包含破坏 Jinja 渲染的类型。"""

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
        """Dashboard VM 值应为 JSON/Jinja 兼容类型。"""
        conn = MagicMock()
        with _patch_dashboard_indexers() as stack:
            patchers = stack.get_patchers()
            _default_dashboard_mocks(patchers)
            # 用非可调用的 namedtuple 替换 MagicMock token_breakdown
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
    def test_projects_vm_has_no_render_blocking_types(self):
        conn = MagicMock()
        with patch("session_browser.web.presenters.projects.list_projects") as m_proj:
            m_proj.return_value = []
            result = build_projects_view_model(conn)

        for key, value in result.items():
            assert not callable(value), (
                f"Presenter key '{key}' holds a callable — template cannot render it"
            )


# ─── HTTP 200 路由测试（fixture 服务器可用时）────────────────────────

class TestRouteHttp200:
    """验证每个页面路由在 fixture 服务器运行时返回 HTTP 200。

    除非测试 index/server fixture 可用，否则这些测试将被跳过。
    """

    @staticmethod
    def _fetch_html(url: str) -> str:
        """获取 URL 并返回解码后的 HTML 文本。"""
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


# ─── 路由到 presenter 的调度映射 ──────────────────────────────────────

class TestRoutePresenterDispatchMapping:
    """验证 routes.py 正确导入和连接每个 presenter。

    这检查 routes.py 的模块级导入与我们上面测试的 presenter 函数匹配。
    """

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_routes_imports_dashboard_presenter(self):
        from session_browser.web import routes
        # routes.py 使用 from-import，因此该函数在其命名空间中可用
        assert hasattr(routes, "build_dashboard_view_model") is True
        # 验证该函数存在于 presenter 模块中
        from session_browser.web.presenters.dashboard import build_dashboard_view_model as fn
        assert callable(fn)

    @pytest.mark.contract_case("ROUTE-API-011")
    def test_routes_imports_projects_presenters(self):
        from session_browser.web.presenters.projects import (
            build_projects_view_model,
            build_project_detail_view_model,
        )
        assert callable(build_projects_view_model)
        assert callable(build_project_detail_view_model)

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
        """记录并验证预期的路由到 presenter 映射。"""
        mapping = {
            "/": "build_dashboard_view_model",
            "/dashboard": "build_dashboard_view_model",
            "/projects": "build_projects_view_model",
            "/projects/<key>": "build_project_detail_view_model",
            "/sessions": "fetch_sessions_view_model",
        }
        # 所有引用的 presenter 函数均存在且可调用
        from session_browser.web.presenters.dashboard import build_dashboard_view_model
        from session_browser.web.presenters.projects import build_projects_view_model, build_project_detail_view_model
        from session_browser.web.presenters.sessions import fetch_sessions_view_model

        funcs = {
            "build_dashboard_view_model": build_dashboard_view_model,
            "build_projects_view_model": build_projects_view_model,
            "build_project_detail_view_model": build_project_detail_view_model,
            "fetch_sessions_view_model": fetch_sessions_view_model,
        }
        for route, presenter_name in mapping.items():
            assert presenter_name in funcs, f"Route {route} references unknown presenter {presenter_name}"
            assert callable(funcs[presenter_name]), f"Presenter {presenter_name} is not callable"
