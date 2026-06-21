"""验证滚动阴影功能已移除的测试。

这些测试验证滚动阴影功能已从 CSS/JS 中移除，
符合 Hi-Fi 重构要求（方案 A：完全移除该功能）。

用法：
    cd <仓库根目录>
    ./scripts/session-browser.sh test tests/test_scroll_shadow_behavior.py
"""

from __future__ import annotations

import glob as _glob
import os

import pytest

CSS_PATH = 'src/session_browser/web/static/css/shell.css'
CSS_TABLE_WRAP = 'src/session_browser/web/static/css/ui-primitives.css'
CSS_TABLE_WRAP_DIR = 'src/session_browser/web/static/css/ui-primitives'
JS_PATH = 'src/session_browser/web/static/js/app.js'


def _read(path: str) -> str:
    with open(path, encoding='utf-8') as f:
        return f.read()


def _read_css_with_splits() -> str:
    """Read ui-primitives CSS wrapper + all split sub-components."""
    parts = [_read(CSS_TABLE_WRAP)]
    for fp in sorted(_glob.glob(os.path.join(CSS_TABLE_WRAP_DIR, '*.css'))):
        parts.append(_read(fp))
    return '\n'.join(parts)


class TestCSSAbsent:
    """验证 CSS 中已移除滚动阴影伪元素。"""

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_before_pseudo(self):
        css = _read(CSS_PATH)
        assert '.table-wrap::before' not in css, '.table-wrap::before 应被移除'

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_after_pseudo(self):
        css = _read(CSS_PATH)
        assert '.table-wrap::after' not in css, '.table-wrap::after 应被移除'

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_scroll_state_classes(self):
        css = _read(CSS_PATH)
        assert 'is-scroll-left' not in css, 'is-scroll-left 类应被移除'
        assert 'is-scroll-right' not in css, 'is-scroll-right 类应被移除'


class TestJSAbsent:
    """验证 JS 中已移除滚动阴影函数。"""

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_update_scroll_shadow(self):
        js = _read(JS_PATH)
        assert 'updateScrollShadow' not in js, 'updateScrollShadow 应被移除'

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_init_scroll_shadows(self):
        js = _read(JS_PATH)
        assert 'initScrollShadows' not in js, 'initScrollShadows 应被移除'

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_init_all_scroll_shadows(self):
        js = _read(JS_PATH)
        assert 'initAllScrollShadows' not in js, 'initAllScrollShadows 应被移除'

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_scroll_shadow_resize(self):
        js = _read(JS_PATH)
        # 滚动阴影的 resize 监听器应已移除
        assert 'resize' not in js or 'scroll' not in js, 'resize+scroll 阴影监听器应被移除'

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_no_profile_loaded_shadow(self):
        js = _read(JS_PATH)
        assert 'profile-loaded' not in js, 'profile-loaded 阴影重新初始化应被移除'


class TestTableWrapLayoutPreserved:
    """验证 .table-wrap 布局 CSS 本身未被移除。"""

    @pytest.mark.contract_case('UI-VISUAL-010')
    def test_table_wrap_base_exists(self):
        css = _read_css_with_splits()
        assert '.table-wrap' in css, '.table-wrap 基础规则必须保留'
        assert 'overflow-x' in css, 'overflow-x:auto 必须保留以支持滚动'
