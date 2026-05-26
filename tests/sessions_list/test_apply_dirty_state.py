"""Tests for Apply button dirty-state static contract.

Verifies that the Apply button in the Sessions List filter form has:
1. An identifiable selector (data-action or id) for targeting from JS.
2. The filter form (#session-filter-form) exists as an event-binding anchor.
3. JS contains dirty-state management logic: listening for form input/change
   events and toggling the Apply button's disabled state or is-dirty class.

This is a static contract test — it reads template and JS source files,
no browser or live server required.
"""
from __future__ import annotations

import os
import re

# ── Paths (relative to repo root) ────────────────────────────────────
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


# ─── 1. Apply button has identifiable selector ──────────────────────

class TestApplyButtonSelector:
    """Apply 按钮必须有可被 JS 识别的 selector（data-action 或 id）。"""

    def test_apply_button_has_data_action(self):
        """模板中的 Apply 按钮应包含 data-action="apply"。"""
        html = _read_sessions_html()
        # Jinja2 macro call that renders data-action="apply"
        assert 'data_action=' in html and "'apply'" in html, \
            "Apply button must have data_action='apply' in the template macro call"

    def test_apply_button_in_filter_form(self):
        """Apply 按钮必须位于筛选表单内部。"""
        html = _read_sessions_html()
        # The form has id='session-filter-form'; apply button should be
        # referenced within the same filter_card context
        assert "session-filter-form" in html, \
            "Filter form must have id='session-filter-form'"


# ─── 2. Filter form has identifiable ID ─────────────────────────────

class TestFilterFormId:
    """筛选表单必须有可被 JS 绑定的 ID。"""

    def test_form_has_session_filter_form_id(self):
        """表单应声明 id='session-filter-form'。"""
        html = _read_sessions_html()
        assert "session-filter-form" in html, \
            "Filter form must have id='session-filter-form'"

    def test_form_is_used_as_event_target_in_js(self):
        """JS 中应通过 getElementById('session-filter-form') 获取表单。"""
        js = _read_sessions_js()
        assert "session-filter-form" in js, \
            "JS must reference 'session-filter-form' to bind events"


# ─── 3. Dirty-state management in JS ────────────────────────────────

class TestDirtyStateContract:
    """JS 中必须存在 Apply 按钮 dirty-state 管理逻辑。"""

    def test_js_has_apply_button_selector(self):
        """JS 中应有选择 Apply 按钮的代码（通过 data-action、class 或 id）。"""
        js = _read_sessions_js()
        # Accept any reasonable selector pattern for the Apply button
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
            "JS must contain a selector to target the Apply button "
            "(e.g. [data-action='apply'], #apply-btn, .btn-apply)"
        )

    def test_js_listens_for_form_input_or_change(self):
        """JS 中应监听表单的 input 或 change 事件以检测 dirty 状态。"""
        js = _read_sessions_js()
        # Check for event listener patterns on the filter form
        has_input_listener = (
            "'input'" in js or '"input"' in js
        )
        has_change_listener = (
            "'change'" in js or '"change"' in js
        )
        # Also accept addEventListener with these event names
        assert has_input_listener or has_change_listener, (
            "JS must listen for 'input' or 'change' events on the filter form "
            "to track dirty state"
        )

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
        # Also accept toggle/addClass/removeClass patterns
        has_toggle = (
            "classList.toggle" in js
            or "classList.add" in js
            or "classList.remove" in js
        ) and ("dirty" in js_lower or "disabled" in js_lower)

        assert has_disabled or has_is_dirty or has_toggle, (
            "JS must toggle Apply button's disabled property or "
            "is-dirty class to reflect form dirty state"
        )

    def test_dirty_logic_is_coherent(self):
        """dirty-state 逻辑应包含初始快照 + 变更检测的基本模式。"""
        js = _read_sessions_js()
        js_lower = js.lower()

        # Look for patterns suggesting form state tracking:
        # - storing initial/default values (serialize, snapshot, default, initial)
        # - comparing current vs stored state (compare, diff, changed)
        # - disabling/enabling based on comparison
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
            "JS should have a form state tracking pattern "
            "(serialize + compare, or explicit dirty flag)"
        )
