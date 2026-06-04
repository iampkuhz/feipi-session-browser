"""Apply 按钮 dirty-state 静态契约测试。

注意：Apply 按钮及 dirty state 逻辑已在 9d137e1 中移除，
搜索改为实时过滤、下拉选择自动提交。此文件保留作为历史参考。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Apply button removed in 9d137e1: real-time search")

import pytest
import os
import re

# ── 路径（相对于仓库根目录）────────────────────────────────────────
_REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')

_SESSIONS_HTML = os.path.join(_REPO_ROOT,
    "src/session_browser/web/templates/sessions.html")
_SESSIONS_LIST_JS = os.path.join(_REPO_ROOT,
    "src/session_browser/web/static/js/sessions-list.js")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_sessions_html() -> str:
    return _read(_SESSIONS_HTML)


def _read_sessions_js() -> str:
    return _read(_SESSIONS_LIST_JS)


# ─── 1. Apply 按钮具有可识别的 selector ─────────────────────────────

class TestApplyButtonSelector:
    """Apply 按钮必须有可被 JS 识别的 selector（data-action 或 id）。"""

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_apply_button_has_data_action(self):
        """模板中的 Apply 按钮应包含 data-action="apply"。"""
        html = _read_sessions_html()
        # Jinja2 宏调用渲染为 data-action="apply"
        assert 'data_action=' in html and "'apply'" in html, \
            "Apply 按钮必须在模板宏调用中包含 data_action='apply'"

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_apply_button_in_filter_form(self):
        """Apply 按钮必须位于筛选表单内部。"""
        html = _read_sessions_html()
        # 表单 id='session-filter-form'；apply 按钮应在同一个 filter_card 上下文中
        assert "session-filter-form" in html, \
            "筛选表单必须有 id='session-filter-form'"


# ─── 2. 筛选表单具有可识别的 ID ─────────────────────────────────────

class TestFilterFormId:
    """筛选表单必须有可被 JS 绑定的 ID。"""

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_form_has_session_filter_form_id(self):
        """表单应声明 id='session-filter-form'。"""
        html = _read_sessions_html()
        assert "session-filter-form" in html, \
            "筛选表单必须有 id='session-filter-form'"

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_form_is_used_as_event_target_in_js(self):
        """JS 中应通过 getElementById('session-filter-form') 获取表单。"""
        js = _read_sessions_js()
        assert "session-filter-form" in js, \
            "JS 必须引用 'session-filter-form' 以绑定事件"


# ─── 3. JS 中的 dirty-state 管理逻辑 ────────────────────────────────

class TestDirtyStateContract:
    """JS 中必须存在 Apply 按钮 dirty-state 管理逻辑。"""

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_js_has_apply_button_selector(self):
        """JS 中应有选择 Apply 按钮的代码（通过 data-action、class 或 id）。"""
        js = _read_sessions_js()
        # 接受任何合理的 Apply 按钮 selector 模式
        has_selector = (
            "data-action='apply'" in js
            or 'data-action="apply"' in js
            or "[data-action='apply']" in js
            or '[data-action="apply"]' in js
            or "apply-btn" in js.lower()
            or "apply-button" in js.lower()
            or "btn-apply" in js.lower()
        )
        assert has_selector, (
            "JS 必须包含定位 Apply 按钮的 selector（如 [data-action='apply']、#apply-btn、.btn-apply）"
        )

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_js_listens_for_form_input_or_change(self):
        """JS 中应监听表单的 input 或 change 事件以检测 dirty 状态。"""
        js = _read_sessions_js()
        # 检查筛选表单上的事件监听模式
        has_input_listener = (
            "'input'" in js or '"input"' in js
        )
        has_change_listener = (
            "'change'" in js or '"change"' in js
        )
        # 也接受 addEventListener 绑定这些事件名
        assert has_input_listener or has_change_listener, (
            "JS 必须监听筛选表单的 'input' 或 'change' 事件以跟踪 dirty 状态"
        )

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_js_toggles_disabled_or_is_dirty(self):
        """JS 中应有设置 Apply 按钮 disabled 属性或 is-dirty 类的代码。"""
        js = _read_sessions_js()
        js_lower = js.lower()

        has_disabled = (
            ".disabled" in js
            or "disabled =" in js
            or "disabled=" in js
            or ".setAttribute" in js and "disabled" in js_lower
        )
        has_is_dirty = (
            "is-dirty" in js
            or "isDirty" in js
            or "is_dirty" in js
        )
        # 也接受 toggle/addClass/removeClass 模式
        has_toggle = (
            "classList.toggle" in js
            or "classList.add" in js
            or "classList.remove" in js
        ) and ("dirty" in js_lower or "disabled" in js_lower)

        assert has_disabled or has_is_dirty or has_toggle, (
            "JS 必须切换 Apply 按钮的 disabled 属性或 is-dirty 类以反映表单 dirty 状态"
        )

    @pytest.mark.contract_case("UI-INTERACTION-009")
    def test_dirty_logic_is_coherent(self):
        """dirty-state 逻辑应包含初始快照 + 变更检测的基本模式。"""
        js = _read_sessions_js()
        js_lower = js.lower()

        # 查找表明表单状态跟踪的模式：
        # - 存储初始/默认值（serialize, snapshot, default, initial）
        # - 比较当前值与存储值（compare, diff, changed）
        # - 根据比较结果禁用/启用
        has_serialize = any(kw in js_lower for kw in [
            "serialize", "formdata", "form_data", "new formdata",
        ])
        has_comparison = any(kw in js for kw in [
            "compare", "diff", "changed", "dirty", "modified",
        ])
        has_state_var = any(kw in js for kw in [
            "initialState", "initial_state", "defaultState", "default_state",
            "snapshot", "originalState", "original_state",
            "formState", "form_state", "isDirty", "is_dirty",
        ])

        assert has_serialize or has_comparison or has_state_var, (
            "JS 应有表单状态跟踪模式（serialize + compare，或显式 dirty 标志）"
        )
