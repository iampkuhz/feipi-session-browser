"""Tests verifying scroll shadow feature has been removed.

These tests verify that the scroll shadow feature is ABSENT from CSS/JS,
as required by the Hi-Fi refactoring (Plan A: remove the feature entirely).

Usage:
    cd <repo-root>
    ./scripts/session-browser.sh test tests/test_scroll_shadow_behavior.py
"""

from __future__ import annotations

import pytest

from scripts.check_scroll_shadow_behavior import (
    check_right_shadow_absent,
    check_left_shadow_absent,
    check_js_shadow_absent,
    _reset_counters,
    _pass,
    _fail,
)

CSS_PATH = "src/session_browser/web/static/style.css"
JS_PATH = "src/session_browser/web/static/js/app.js"


class TestCSSAbsent:
    """Verify scroll shadow pseudo-elements are removed from CSS."""

    def test_no_before_pseudo(self):
        css = open(CSS_PATH).read()
        assert ".table-wrap::before" not in css, ".table-wrap::before should be removed"

    def test_no_after_pseudo(self):
        css = open(CSS_PATH).read()
        assert ".table-wrap::after" not in css, ".table-wrap::after should be removed"

    def test_no_scroll_state_classes(self):
        css = open(CSS_PATH).read()
        assert "is-scroll-left" not in css, "is-scroll-left class should be removed"
        assert "is-scroll-right" not in css, "is-scroll-right class should be removed"


class TestJSAbsent:
    """Verify scroll shadow functions are removed from JS."""

    def test_no_update_scroll_shadow(self):
        js = open(JS_PATH).read()
        assert "updateScrollShadow" not in js, "updateScrollShadow should be removed"

    def test_no_init_scroll_shadows(self):
        js = open(JS_PATH).read()
        assert "initScrollShadows" not in js, "initScrollShadows should be removed"

    def test_no_init_all_scroll_shadows(self):
        js = open(JS_PATH).read()
        assert "initAllScrollShadows" not in js, "initAllScrollShadows should be removed"

    def test_no_scroll_shadow_resize(self):
        js = open(JS_PATH).read()
        # resize listener for scroll shadows should be gone
        assert "resize" not in js or "scroll" not in js, \
            "resize+scroll shadow listeners should be removed"

    def test_no_profile_loaded_shadow(self):
        js = open(JS_PATH).read()
        assert "profile-loaded" not in js, "profile-loaded shadow reinit should be removed"


class TestTableWrapLayoutPreserved:
    """Verify .table-wrap layout CSS itself is NOT removed."""

    def test_table_wrap_base_exists(self):
        css = open(CSS_PATH).read()
        assert ".table-wrap" in css, ".table-wrap base rule must still exist"
        assert "overflow-x" in css, "overflow-x:auto must be preserved for scrolling"
