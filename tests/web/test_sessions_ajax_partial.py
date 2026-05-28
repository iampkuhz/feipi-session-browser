"""T017 · Sessions AJAX 局部结构门禁测试。

验证 /sessions 在携带 X-Requested-With: XMLHttpRequest 头时返回的 HTML
局部包含预期的结构标记（#sessions-ajax-response、tbody、#ajax-pagination、页码输入）。

参见 S-09：会话列表下一页从第 1 页跳到第 3 页且出现空页的问题。
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, PropertyMock
from bs4 import BeautifulSoup

from session_browser.web.template_env import env as _template_env


# ─── 模拟会话行 ────────────────────────────────────────────────────────────

def _make_mock_session(
    index: int = 1,
    agent: str = "claude_code",
    session_id: str = None,
    title: str = None,
) -> MagicMock:
    """创建匹配模板属性访问的模拟 session 对象。"""
    if session_id is None:
        session_id = f"sess-000000-{index:04d}"
    if title is None:
        title = f"Test Session {index}"
    m = MagicMock()
    m.agent = agent
    m.session_id = session_id
    m.title = title
    m.model = "sonnet-4-20250514"
    m.project_key = f"proj-{index}"
    m.project_name = f"Project {index}"
    m.cwd = f"/home/user/projects/proj-{index}"
    m.git_branch = "main"
    m.input_tokens = 1000 * index
    m.cached_input_tokens = 500 * index
    m.cached_output_tokens = 200 * index
    m.output_tokens = 300 * index
    m.assistant_message_count = 10 * index
    m.tool_call_count = 5 * index
    m.duration_seconds = 60.0 * index
    m.ended_at = f"2026-05-26T{10 + index:02d}:00:00+00:00"
    return m


# ─── 默认 AJAX 上下文 ──────────────────────────────────────────────────────

def _make_ajax_context(
    sessions: list = None,
    page: int = 2,
    page_size: int = 20,
    total_count: int = 60,
    total_pages: int = 3,
) -> dict:
    """构建 routes.py 传递给 AJAX 局部模板的上下文字典。"""
    if sessions is None:
        sessions = [_make_mock_session(i) for i in range(1, page_size + 1)]

    # 最小化 actions 模拟——模板访问 .remove_filter_urls 和 .sort_urls
    actions = MagicMock()
    actions.remove_filter_urls = {}
    actions.sort_urls = {"tokens": "/sessions?sort=tokens", "rounds": "/sessions?sort=rounds",
                         "tools": "/sessions?sort=tools", "duration": "/sessions?sort=duration",
                         "updated": "/sessions?sort=updated"}

    return {
        "sessions": sessions,
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "page_start": (page - 1) * page_size + 1,
        "page_end": min(page * page_size, total_count),
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "sort_key": "updated",
        "sort_dir": "desc",
        "actions": actions,
        "filter_q": "",
        "filter_agent": "",
        "filter_model": "",
        "filter_project": "",
    }


# ─── 测试 ────────────────────────────────────────────────────────────────────

class TestSessionsAjaxPartialStructure:
    """渲染 sessions_ajax_page.html 并断言结构标记存在。"""

    def _render_ajax(self, **overrides) -> str:
        ctx = _make_ajax_context(**overrides)
        return _template_env.get_template("partials/sessions_ajax_page.html").render(**ctx)

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_outer_wrapper_exists(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        wrapper = soup.find(id="sessions-ajax-response")
        assert wrapper is not None, "Missing #sessions-ajax-response wrapper"

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_tbody_exists(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        tbody = soup.find("tbody")
        assert tbody is not None, "Missing <tbody> in AJAX partial"

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_pagination_exists(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.find(id="ajax-pagination")
        assert pagination is not None, "Missing #ajax-pagination in AJAX partial"

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_tbody_has_rows(self):
        html = self._render_ajax()
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find("tbody").find_all("tr")
        assert len(rows) >= 1, "Expected at least 1 row in tbody"

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_page_input_value_matches_requested_page(self):
        """第 2 页 AJAX 响应：页码输入应显示 2。"""
        html = self._render_ajax(page=2, total_count=60, total_pages=3)
        soup = BeautifulSoup(html, "html.parser")
        # 分页宏渲染页码输入——在 #ajax-pagination 内查找匹配的 input
        pagination = soup.find(id="ajax-pagination")
        assert pagination is not None
        inputs = pagination.find_all("input")
        page_inputs = [i for i in inputs if i.get("type") == "text" or i.get("type") == "number" or (i.get("value") and i.get("value").isdigit())]
        assert len(page_inputs) >= 1, "No page input found in pagination"
        # 主页码输入的值应等于当前页
        # （可能也有隐藏 input；通过数值存在性过滤）
        found_page_2 = any(
            inp.get("value") == "2"
            for inp in page_inputs
        )
        assert found_page_2, (
            f"Page input value should be 2, found values: {[i.get('value') for i in page_inputs]}"
        )

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_page_input_value_page_3(self):
        """第 3 页 AJAX 响应：页码输入应显示 3。"""
        html = self._render_ajax(page=3, total_count=100, total_pages=5)
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.find(id="ajax-pagination")
        assert pagination is not None
        inputs = pagination.find_all("input")
        page_inputs = [i for i in inputs if i.get("value") and i.get("value").isdigit()]
        found_page_3 = any(inp.get("value") == "3" for inp in page_inputs)
        assert found_page_3, (
            f"Page input value should be 3, found values: {[i.get('value') for i in page_inputs]}"
        )


class TestSessionsAjaxPartialEmptyState:
    """不存在会话时的 AJAX 局部。"""

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_empty_tbody_shows_message(self):
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=[], total_count=0, total_pages=1)
        )
        soup = BeautifulSoup(html, "html.parser")
        tbody = soup.find("tbody")
        assert tbody is not None
        # 空状态应包含无会话的文本提示
        text = tbody.get_text()
        assert "no sessions" in text.lower() or "no sessions" in text.lower(), (
            f"Empty tbody should show 'no sessions' message, got: {text[:200]}"
        )

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_empty_has_no_pagination_div(self):
        """当 total_count=0 时，不应渲染 #ajax-pagination _div。"""
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=[], total_count=0, total_pages=1)
        )
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.find(id="ajax-pagination")
        assert pagination is None, (
            "Expected no #ajax-pagination when total_count=0"
        )


class TestSessionsAjaxPartialMultiPage:
    """多页会话的 AJAX 局部。"""

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_page_2_has_20_rows(self):
        sessions = [_make_mock_session(i) for i in range(21, 41)]
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=sessions, page=2, total_count=60, total_pages=3)
        )
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find("tbody").find_all("tr")
        assert len(rows) == 20

    @pytest.mark.contract_case("ROUTE-API-012", "UI-INTERACTION-003")
    def test_session_rows_have_data_attributes(self):
        sessions = [_make_mock_session(1)]
        html = _template_env.get_template("partials/sessions_ajax_page.html").render(
            **_make_ajax_context(sessions=sessions, page=1, total_count=1, total_pages=1)
        )
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr", class_="sessions-row")
        assert row is not None
        assert row.get("data-agent") == "claude_code"
        assert row.get("data-session-id") is not None
        assert row.get("data-project") is not None
