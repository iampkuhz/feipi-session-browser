"""ui_primitives.html 宏和 JS 的单元测试。

覆盖：
- 所有 Jinja2 宏使用最小参数可无报错渲染
- 宏包含预期的 aria 属性
- 宏包含预期的 data-action 属性
- Token 格式化器产生预期输出
- 分页宏正确渲染 prev/next/input
- 按钮宏渲染正确的变体
- ui_primitives.js 语法和 data-action 委托模式
"""

from __future__ import annotations

import pytest
import pathlib
import re
import urllib.parse

import jinja2
# ── Jinja2 环境配置 ────────────────────────────────────────────────────────────

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "templates"


def _make_env() -> jinja2.Environment:
    """创建与 routes.py 相同的 Jinja2 环境。"""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    env.filters["format_compact_token"] = lambda n: (
        "0" if n is None
        else f"{n / 1_000_000:.1f}M" if n >= 1_000_000
        else f"{n / 1_000:.1f}K" if n >= 1_000
        else str(int(n))
    )
    env.filters["format_number"] = lambda n: (
        "0" if n is None
        else f"{n / 1_000_000:.1f}M" if n >= 1_000_000
        else f"{n / 1_000:.1f}K" if n >= 1_000
        else str(n)
    )
    env.filters["format_number_short"] = env.filters["format_compact_token"]
    env.filters["format_duration"] = lambda seconds: (
        f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}min" if seconds >= 3600
        else f"{int(seconds // 60)}min {int(seconds % 60)}s" if seconds >= 60
        else f"{int(seconds)}s"
    )
    env.filters["relative_time"] = lambda iso_str: str(iso_str) if iso_str else "—"
    env.filters["urlencode"] = urllib.parse.quote
    return env


def _render_macro(macro_name: str, _context=None, **kwargs) -> str:
    """使用给定参数渲染 ui_primitives.html 中的指定宏。

    _context: 可选字典，直接传入渲染上下文变量（用于无法用
        Python 字面量表示的复杂对象如 session stub）。
        _context 中的键也可按名作为宏参数引用。
    """
    env = _make_env()
    args_parts = []
    # 先传入上下文变量（可作为宏参数按名引用）
    if _context:
        for key in _context:
            args_parts.append(key)
    # 再传入关键字参数（在模板中渲染为 Python 字面量）
    for k, v in kwargs.items():
        args_parts.append(f"{k}={v!r}")
    all_args = ", ".join(args_parts)
    tmpl_str = (
        '{% from "components/ui_primitives.html" import ' + macro_name + ' %}'
        "{{ " + macro_name + "(" + all_args + ") }}"
    )
    render_ctx = dict(_context) if _context else {}
    return env.from_string(tmpl_str).render(**render_ctx)


# ── 宏渲染：使用最小参数无报错 ────────────────────────────────────────────


class TestMacroMinimalRender:
    """所有宏使用最小参数调用时无报错渲染。"""

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_button_renders(self):
        html = _render_macro("button", label="Test")
        assert "Test" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_icon_button_renders(self):
        html = _render_macro("icon_button", icon="✎")
        assert "✎" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_badge_renders(self):
        html = _render_macro("badge", label="info")
        assert "info" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_metric_card_renders(self):
        html = _render_macro("metric_card", label="Sessions", value="42")
        assert "Sessions" in html
        assert "42" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_metric_grid_renders(self):
        cards = ['<div class="metric-card">A</div>', '<div class="metric-card">B</div>']
        html = _render_macro("metric_grid", cards=cards)
        assert "metric-grid" in html
        assert "A" in html
        assert "B" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_renders(self):
        html = _render_macro("pagination", current_page=1, total_pages=5)
        assert "pagination" in html
        assert "Page" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_single_page(self):
        """单页场景：prev/next 按钮应禁用。"""
        html = _render_macro("pagination", current_page=1, total_pages=1)
        assert 'disabled' in html  # 按钮和 input 应被禁用
        assert 'data-action="prev-page"' in html
        assert 'data-action="next-page"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_token_bar_renders(self):
        segments = [
            {"kind": "fresh", "value": 100},
            {"kind": "out", "value": 50},
        ]
        html = _render_macro("token_bar", segments=segments)
        assert "tokenbar" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_tooltip_renders(self):
        content = [{"label": "Total", "value": "150"}]
        html = _render_macro("tooltip", content=content, trigger_text="hover me")
        assert "hover me" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_popover_renders(self):
        html = _render_macro("popover", content={"title": "Menu", "body": "Items"}, trigger_element="...")
        assert "Menu" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_section_card_renders(self):
        html = _render_macro("section_card", title="Section", content="<p>body</p>")
        assert "Section" in html
        assert "body" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_data_table_renders(self):
        headers = [{"label": "Name", "key": "name", "sortable": True}]
        rows = [{"name": "Alice"}]
        html = _render_macro("data_table", headers=headers, rows=rows)
        assert "data-table" in html
        assert "Name" in html
        assert "Alice" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_filter_bar_renders(self):
        filters = [
            {"label": "Search", "name": "q", "type": "search", "placeholder": "Search..."},
        ]
        html = _render_macro("filter_bar", filters=filters)
        assert "filter-card" in html
        assert "Apply" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_payload_modal_renders(self):
        html = _render_macro("payload_modal", payload_id="test-1", title="Payload", kind="RESPONSE")
        assert "modal-backdrop" in html
        assert "Payload" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_empty_state_renders(self):
        html = _render_macro("empty_state", message="No results")
        assert "No results" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_error_state_renders(self):
        html = _render_macro("error_state", message="Error occurred")
        assert "Error occurred" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_token_total_renders(self):
        html = _render_macro("token_total", total="1.5K")
        assert "1.5K" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_session_row_renders(self):
        session = _make_session_stub()
        html = _render_macro("session_row", _context={"session": session})
        assert "session-row" in html
        assert 'data-session-id="test-001"' in html
        assert 'data-agent="claude_code"' in html
        assert 'badge cc' in html
        assert "CC" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_session_row_hides_columns(self):
        session = _make_session_stub()
        html = _render_macro("session_row", _context={"session": session}, show_project=False, show_agent=False)
        assert "project-cell" not in html
        assert "badge" not in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_session_row_extra_classes(self):
        session = _make_session_stub()
        html = _render_macro("session_row", _context={"session": session}, extra_classes="custom-class")
        assert "custom-class" in html


def _make_session_stub():
    """为 session_row 宏测试创建最小 session stub。"""
    class SessionStub:
        session_id = "test-001"
        agent = "claude_code"
        title = "Test Session"
        project_key = "my-project"
        project_name = "My Project"
        model = "claude-sonnet-4-20250514"
        total_tokens = 1500
        assistant_message_count = 12
        tool_call_count = 8
        failed_tool_count = 0
        duration_seconds = 180
        ended_at = "2025-01-15T10:30:00"
    return SessionStub()


# ── Aria 属性 ──────────────────────────────────────────────────────────────


class TestAriaAttributes:
    """宏渲染应包含预期的 aria 属性。"""

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_button_has_aria_label(self):
        # 仅当 aria_label 与 label 不同时才添加 aria-label
        html = _render_macro("button", label="X", data_action="delete-item", aria_label="Delete item")
        assert 'aria-label="Delete item"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_icon_button_has_aria_label(self):
        html = _render_macro("icon_button", icon="✎", aria_label="Edit")
        assert 'aria-label="Edit"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_icon_button_has_title(self):
        html = _render_macro("icon_button", icon="✎", aria_label="Edit")
        assert 'title="Edit"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_badge_has_role(self):
        html = _render_macro("badge", label="ok", variant="ok")
        assert 'role="status"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_metric_card_has_aria_label(self):
        html = _render_macro("metric_card", label="Sessions", value="42")
        assert 'aria-label="Sessions"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_metric_grid_has_role_list(self):
        cards = ['<div>A</div>']
        html = _render_macro("metric_grid", cards=cards)
        assert 'role="list"' in html
        assert 'role="listitem"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_has_aria_label(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert 'role="navigation"' in html
        assert 'aria-label="Pagination"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_prev_has_aria_label(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert 'aria-label="Previous page"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_next_has_aria_label(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert 'aria-label="Next page"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_page_input_has_aria_label(self):
        html = _render_macro("pagination", current_page=3, total_pages=10)
        assert 'aria-label="Page number"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_token_bar_has_aria(self):
        segments = [{"kind": "fresh", "value": 100}]
        html = _render_macro("token_bar", segments=segments)
        assert 'role="progressbar"' in html
        assert 'aria-valuemin="0"' in html
        assert 'aria-label="Token usage"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_tooltip_has_aria(self):
        content = [{"label": "X", "value": "1"}]
        html = _render_macro("tooltip", content=content, trigger_text="info")
        assert 'role="tooltip"' in html
        assert 'aria-hidden="true"' in html
        assert 'aria-haspopup="true"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_popover_has_aria(self):
        html = _render_macro("popover", content={"title": "M", "body": "B"}, trigger_element="...")
        assert 'aria-expanded="false"' in html
        assert 'aria-haspopup="true"' in html
        assert 'aria-controls=' in html
        assert 'role="dialog"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_section_card_has_aria(self):
        html = _render_macro("section_card", title="Title", content="C")
        assert 'aria-label="Title"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_data_table_sortable_has_aria_sort(self):
        headers = [{"label": "Name", "key": "name", "sortable": True}]
        html = _render_macro("data_table", headers=headers, rows=[])
        assert 'aria-sort="none"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_data_table_th_has_scope(self):
        headers = [{"label": "Name", "key": "name", "sortable": True}]
        html = _render_macro("data_table", headers=headers, rows=[])
        assert 'scope="col"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_filter_bar_has_aria(self):
        filters = [{"label": "Q", "name": "q", "type": "search"}]
        html = _render_macro("filter_bar", filters=filters)
        assert 'role="search"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_payload_modal_has_aria(self):
        html = _render_macro("payload_modal", payload_id="p1", title="P")
        assert 'aria-modal="true"' in html
        assert 'role="dialog"' in html
        assert 'aria-hidden="true"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_empty_state_has_aria(self):
        html = _render_macro("empty_state", message="Empty")
        assert 'role="status"' in html
        assert 'aria-live="polite"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_error_state_has_aria(self):
        html = _render_macro("error_state", message="Err")
        assert 'role="alert"' in html
        assert 'aria-live="assertive"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_icon_has_aria_hidden(self):
        html = _render_macro("button", label="Go", icon="→")
        assert 'aria-hidden="true"' in html


# ── data-action 属性 ───────────────────────────────────────────────────────


class TestDataActionAttributes:
    """宏渲染应包含预期的 data-action 属性。"""

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_button_data_action(self):
        html = _render_macro("button", label="Save", data_action="save-item")
        assert 'data-action="save-item"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_button_href_data_action(self):
        html = _render_macro("button", label="View", data_action="view-item", href="/view")
        assert 'data-action="view-item"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_icon_button_data_action(self):
        html = _render_macro("icon_button", icon="✎", data_action="edit-row")
        assert 'data-action="edit-row"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_prev_data_action(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert 'data-action="prev-page"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_next_data_action(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert 'data-action="next-page"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_pagination_input_data_action(self):
        html = _render_macro("pagination", current_page=3, total_pages=10)
        assert 'data-action="page-input"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_data_table_sort_data_action(self):
        headers = [{"label": "Name", "key": "name", "sortable": True}]
        html = _render_macro("data_table", headers=headers, rows=[])
        assert 'data-action="sort"' in html
        assert 'data-sort-key="name"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_filter_bar_apply_data_action(self):
        filters = [{"label": "Q", "name": "q", "type": "search"}]
        html = _render_macro("filter_bar", filters=filters)
        assert 'data-action="filter"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_filter_bar_clear_data_action(self):
        filters = [{"label": "Q", "name": "q", "type": "search"}]
        html = _render_macro("filter_bar", filters=filters)
        assert 'data-action="clear"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_payload_modal_close_data_action(self):
        html = _render_macro("payload_modal", payload_id="p1")
        assert 'data-action="close-modal"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_popover_toggle_data_action(self):
        html = _render_macro("popover", content={"title": "M", "body": "B"}, trigger_element="...")
        assert 'data-action="toggle-popover"' in html


# ── Token 格式化器 ──────────────────────────────────────────────────────


class TestFormatCompactToken:
    """Token 格式化器产生预期输出。"""

    def _fmt(self, n):
        from session_browser.web.template_env import _format_compact_token
        return _format_compact_token(n)

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_none(self):
        assert self._fmt(None) == "0"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_zero(self):
        assert self._fmt(0) == "0"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_sub_k(self):
        assert self._fmt(500) == "500"
        assert self._fmt(999) == "999"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_exactly_k(self):
        assert self._fmt(1000) == "1.0K"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_k_values(self):
        assert self._fmt(1500) == "1.5K"
        assert self._fmt(9999) == "10.0K"
        assert self._fmt(999999) == "1000.0K"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_exactly_m(self):
        assert self._fmt(1_000_000) == "1.0M"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_m_values(self):
        assert self._fmt(2_300_000) == "2.3M"
        assert self._fmt(1_234_567) == "1.2M"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_float_input(self):
        assert self._fmt(1234.5) == "1.2K"


# ── 分页结构 ────────────────────────────────────────────────────────────


class TestPaginationStructure:
    """分页宏正确渲染 prev/next/input。"""

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_multi_page_has_prev(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert "prev" in html.lower()
        assert "&lsaquo;" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_multi_page_has_next(self):
        html = _render_macro("pagination", current_page=2, total_pages=5)
        assert "next" in html.lower()
        assert "&rsaquo;" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_page_input_shows_current(self):
        html = _render_macro("pagination", current_page=7, total_pages=20)
        assert 'value="7"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_total_pages_displayed(self):
        html = _render_macro("pagination", current_page=1, total_pages=42)
        assert "42" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_total_items_displayed(self):
        html = _render_macro("pagination", current_page=1, total_pages=3, total_items=100)
        assert "of 100" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_single_page_no_prev_next(self):
        html = _render_macro("pagination", current_page=1, total_pages=1)
        # 单页时两个按钮都存在但被禁用
        assert "prev-page" in html
        assert "next-page" in html
        assert 'disabled' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_first_page_no_prev(self):
        html = _render_macro("pagination", current_page=1, total_pages=5)
        # 第一页 prev 按钮存在但被禁用
        assert "prev-page" in html
        assert "next-page" in html
        # 检查 prev 按钮被禁用
        assert 'data-action="prev-page"' in html
        assert html.count('disabled') >= 1  # 至少 prev 按钮被禁用

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_last_page_no_next(self):
        html = _render_macro("pagination", current_page=5, total_pages=5)
        # 最后一页 next 按钮存在但被禁用
        assert "prev-page" in html
        assert "next-page" in html
        assert 'data-action="next-page"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_page_input_has_class(self):
        html = _render_macro("pagination", current_page=1, total_pages=3)
        assert 'class="page-input mono"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_nav_class(self):
        html = _render_macro("pagination", current_page=1, total_pages=3)
        assert 'class="pagination unified-pagination"' in html


# ── 按钮变体 ──────────────────────────────────────────────────────────────


class TestButtonVariants:
    """按钮宏渲染正确的变体。"""

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_default_primary(self):
        html = _render_macro("button", label="Save")
        assert 'class="btn primary"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_secondary_variant(self):
        html = _render_macro("button", label="Cancel", variant="secondary")
        assert 'class="btn"' in html
        assert "primary" not in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_ghost_variant(self):
        html = _render_macro("button", label="More", variant="ghost")
        assert 'class="btn ghost"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_danger_variant(self):
        html = _render_macro("button", label="Delete", variant="danger")
        assert 'class="btn danger"' in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_sm_size(self):
        html = _render_macro("button", label="X", size="sm")
        assert "sm" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_md_default_size(self):
        html = _render_macro("button", label="X", size="md")
        assert "sm" not in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_disabled_button(self):
        html = _render_macro("button", label="Save", disabled=True)
        assert "disabled" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_button_with_icon(self):
        html = _render_macro("button", label="Go", icon="→")
        assert 'class="ui-icon"' in html
        assert "→" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_href_renders_anchor(self):
        html = _render_macro("button", label="View", href="/session/123")
        assert "<a " in html
        assert 'href="/session/123"' in html
        assert "<button" not in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_no_href_renders_button(self):
        html = _render_macro("button", label="Click")
        assert "<button" in html
        assert "type=\"button\"" in html
        assert "<a " not in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_extra_classes(self):
        html = _render_macro("button", label="X", extra_classes="custom-class")
        assert "custom-class" in html

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_disabled_href_has_aria_disabled(self):
        html = _render_macro("button", label="X", href="/y", disabled=True)
        assert 'aria-disabled="true"' in html


# ── ui_primitives.js 检查 ────────────────────────────────────────────────────


class TestUIPrimitivesJS:
    """ui_primitives.js 语法和 data-action 委托模式。"""

    JS_PATH = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "static" / "js" / "ui_primitives.js"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_file_exists(self):
        assert self.JS_PATH.exists(), f"ui_primitives.js not found at {self.JS_PATH}"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_valid_syntax(self, capsys):
        """对 JS 文件运行 node --check 语法检查。"""
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(self.JS_PATH)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"JS syntax error: {result.stderr}"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_data_action_delegation_present(self):
        """JS 文件中存在 data-action 委托模式。"""
        js = self.JS_PATH.read_text()
        assert "data-action" in js, "missing data-action pattern"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_document_level_click_listener(self):
        """使用 document 级点击监听器进行委托。"""
        js = self.JS_PATH.read_text()
        assert "document" in js
        assert "addEventListener" in js

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_registered_actions_exist(self):
        """JS 文件定义了 action 处理器。"""
        js = self.JS_PATH.read_text()
        # 验证关键 action 处理器是否存在
        for action in ("sort", "clear", "prev-page", "next-page", "close-modal", "toggle-popover"):
            assert action in js, f"missing handler for {action}"

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_no_inline_onclick_in_js(self):
        """JS 文件不含内联 onclick 赋值。"""
        js = self.JS_PATH.read_text()
        # 不得直接赋值 .onclick
        assert ".onclick =" not in js

    @pytest.mark.contract_case("UI-VISUAL-012")
    def test_global_api_exposed(self):
        """暴露全局 API (UiPrimitives)。"""
        js = self.JS_PATH.read_text()
        assert "UiPrimitives" in js
        assert "showToast" in js
        assert "closestTable" in js
