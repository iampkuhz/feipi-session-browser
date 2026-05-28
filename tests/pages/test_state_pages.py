"""State 页面（404.html、error.html）的测试。

State 页面的页面级 pytest，覆盖模板结构、.state-panel 类、
ARIA 角色、图标上的 aria-hidden、导航链接、不含 inline 样式/脚本，
以及条件性错误详情渲染。

T178 -- State Pages：添加页面级 pytest。
"""

from __future__ import annotations

import pytest
import os
import re

_404_PATH = "src/session_browser/web/templates/404.html"
_ERROR_PATH = "src/session_browser/web/templates/error.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_404() -> str:
    return _read(_404_PATH)


def _read_error() -> str:
    return _read(_ERROR_PATH)


# -- Test404Template --------------------------------------------------------


class Test404Template:
    """验证 404.html 的 Jinja2 模板结构。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_template_file_exists(self):
        """404.html 必须存在于磁盘上。"""
        assert os.path.isfile(_404_PATH), \
            f"{_404_PATH} 必须存在"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_extends_base(self):
        """404 必须继承 base.html。"""
        content = _read_404()
        assert '{% extends "base.html" %}' in content, \
            "404 必须继承 base.html"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_title_block(self):
        """404 必须设置描述性的页面标题。"""
        content = _read_404()
        assert "Not Found" in content, \
            "404 标题必须包含 'Not Found'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_states_css_import(self):
        """404 必须通过 head_extra 块导入 states.css。"""
        content = _read_404()
        assert 'href="/static/css/states.css"' in content, \
            "404 必须导入 states.css"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_page_specific_js(self):
        """404 不得导入页面级 JS（静态页面不需要 states.js）。"""
        content = _read_404()
        assert 'states.js' not in content, \
            "404 不得导入 states.js（静态页面无需 JS）"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_head_extra_block(self):
        """404 必须使用 head_extra 块来导入 CSS。"""
        content = _read_404()
        assert '{% block head_extra %}' in content, \
            "404 必须使用 head_extra 块"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_topbar_toggles_empty(self):
        """404 必须抑制 topbar 切换按钮。"""
        content = _read_404()
        assert '{% block topbar_toggles %}{% endblock %}' in content, \
            "404 必须定义空的 topbar_toggles 块"


# -- Test404Breadcrumb ------------------------------------------------------


class Test404Breadcrumb:
    """验证 404 面包屑结构。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_dashboard_link(self):
        """面包屑必须链接到 /dashboard。"""
        content = _read_404()
        assert 'href="/dashboard"' in content, \
            "404 面包屑必须链接到 /dashboard"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_current(self):
        """面包屑必须显示当前页面标签。"""
        content = _read_404()
        assert "Not Found" in content, \
            "404 面包屑必须显示 'Not Found' 为当前页"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_separator(self):
        """面包屑必须使用分隔符 span。"""
        content = _read_404()
        assert 'class="sep"' in content, \
            "404 面包屑必须使用分隔符 span"


# -- Test404StatePanel ------------------------------------------------------


class Test404StatePanel:
    """验证 404 页面的 .state-panel 结构。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_class(self):
        """404 必须有 .state-panel 容器。"""
        content = _read_404()
        assert 'class="state-panel"' in content, \
            "404 必须有 state-panel 类"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_role_status(self):
        """404 的 state-panel 必须有 role='status'。"""
        content = _read_404()
        assert 'role="status"' in content, \
            "404 的 state-panel 必须有 role='status'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_aria_live(self):
        """404 的 state-panel 必须有 aria-live='polite'。"""
        content = _read_404()
        assert 'aria-live="polite"' in content, \
            "404 的 state-panel 必须有 aria-live='polite'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon(self):
        """404 必须有 .state-panel__icon 元素。"""
        content = _read_404()
        assert 'class="state-panel__icon"' in content, \
            "404 必须有 state-panel__icon"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_aria_hidden(self):
        """404 图标必须有 aria-hidden='true'。"""
        content = _read_404()
        icon_section = content[content.find('state-panel__icon'):]
        icon_section = icon_section[:icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in icon_section, \
            "404 的 state-panel__icon 必须有 aria-hidden='true'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_value(self):
        """404 图标必须显示 '404'。"""
        content = _read_404()
        assert '>404<' in content, \
            "404 的 state-panel__icon 必须显示 '404'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_title(self):
        """404 必须有 .state-panel__title 且内容为 'Page Not Found'。"""
        content = _read_404()
        assert 'class="state-panel__title"' in content, \
            "404 必须有 state-panel__title"
        assert "Page Not Found" in content, \
            "404 标题必须包含 'Page Not Found'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_desc(self):
        """404 必须有 .state-panel__desc 元素。"""
        content = _read_404()
        assert 'class="state-panel__desc"' in content, \
            "404 必须有 state-panel__desc"


# -- Test404Navigation ------------------------------------------------------


class Test404Navigation:
    """验证 404 导航链接。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_links_nav(self):
        """404 必须有带 .state-panel__links 的 nav。"""
        content = _read_404()
        assert 'class="state-panel__links"' in content, \
            "404 必须有 state-panel__links"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_nav_aria_label(self):
        """404 的 nav 必须有 aria-label。"""
        content = _read_404()
        assert 'aria-label="Navigation links"' in content, \
            "404 的 nav 必须有 aria-label='Navigation links'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_dashboard_link(self):
        """404 必须链接回 /dashboard。"""
        content = _read_404()
        assert 'href="/dashboard"' in content, \
            "404 必须有 /dashboard 链接"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_projects_link(self):
        """404 必须链接到 /projects。"""
        content = _read_404()
        assert 'href="/projects"' in content, \
            "404 必须有 /projects 链接"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_sessions_link(self):
        """404 必须链接到 /sessions。"""
        content = _read_404()
        assert 'href="/sessions"' in content, \
            "404 必须有 /sessions 链接"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_agents_link(self):
        """404 必须链接到 /agents。"""
        content = _read_404()
        assert 'href="/agents"' in content, \
            "404 必须有 /agents 链接"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_four_nav_links(self):
        """404 必须恰好有 4 个导航链接。"""
        content = _read_404()
        links = re.findall(r'class="state-panel__link"', content)
        assert len(links) == 4, \
            f"404 必须有 4 个 state-panel__link 元素，发现 {len(links)} 个"


# -- TestErrorTemplate ------------------------------------------------------


class TestErrorTemplate:
    """验证 error.html 的 Jinja2 模板结构。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_template_file_exists(self):
        """error.html 必须存在于磁盘上。"""
        assert os.path.isfile(_ERROR_PATH), \
            f"{_ERROR_PATH} 必须存在"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_extends_base(self):
        """Error 必须继承 base.html。"""
        content = _read_error()
        assert '{% extends "base.html" %}' in content, \
            "Error 必须继承 base.html"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_title_block(self):
        """Error 必须设置描述性的页面标题。"""
        content = _read_error()
        assert "Error" in content, \
            "Error 标题必须包含 'Error'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_states_css_import(self):
        """Error 必须通过 head_extra 块导入 states.css。"""
        content = _read_error()
        assert 'href="/static/css/states.css"' in content, \
            "Error 必须导入 states.css"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_page_specific_js(self):
        """Error 不得导入页面级 JS（静态页面不需要 states.js）。"""
        content = _read_error()
        assert 'states.js' not in content, \
            "Error 不得导入 states.js（静态页面无需 JS）"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_head_extra_block(self):
        """Error 必须使用 head_extra 块来导入 CSS。"""
        content = _read_error()
        assert '{% block head_extra %}' in content, \
            "Error 必须使用 head_extra 块"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_topbar_toggles_empty(self):
        """Error 必须抑制 topbar 切换按钮。"""
        content = _read_error()
        assert '{% block topbar_toggles %}{% endblock %}' in content, \
            "Error 必须定义空的 topbar_toggles 块"


# -- TestErrorBreadcrumb ----------------------------------------------------


class TestErrorBreadcrumb:
    """验证 error 面包屑结构。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_dashboard_link(self):
        """面包屑必须链接到 /dashboard。"""
        content = _read_error()
        assert 'href="/dashboard"' in content, \
            "Error 面包屑必须链接到 /dashboard"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_current(self):
        """面包屑必须显示当前页面标签。"""
        content = _read_error()
        # 面包屑显示 "Error" 为当前页
        assert "Error" in content, \
            "Error 面包屑必须显示 'Error' 为当前页"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_breadcrumb_separator(self):
        """面包屑必须使用分隔符 span。"""
        content = _read_error()
        assert 'class="sep"' in content, \
            "Error 面包屑必须使用分隔符 span"


# -- TestErrorStatePanel ----------------------------------------------------


class TestErrorStatePanel:
    """验证 error 页面的 .state-panel 结构。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_class(self):
        """Error 必须有 .state-panel 容器。"""
        content = _read_error()
        assert 'class="state-panel"' in content, \
            "Error 必须有 state-panel 类"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_role_alert(self):
        """Error 的 state-panel 必须有 role='alert'。"""
        content = _read_error()
        assert 'role="alert"' in content, \
            "Error 的 state-panel 必须有 role='alert'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_aria_live_assertive(self):
        """Error 的 state-panel 必须有 aria-live='assertive'。"""
        content = _read_error()
        assert 'aria-live="assertive"' in content, \
            "Error 的 state-panel 必须有 aria-live='assertive'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon(self):
        """Error 必须有 .state-panel__icon 元素。"""
        content = _read_error()
        assert 'class="state-panel__icon' in content, \
            "Error 必须有 state-panel__icon"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_error_modifier(self):
        """Error 图标必须有 .state-panel__icon--error 修饰类。"""
        content = _read_error()
        assert 'state-panel__icon--error' in content, \
            "Error 图标必须有 state-panel__icon--error 修饰类"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_aria_hidden(self):
        """Error 图标必须有 aria-hidden='true'。"""
        content = _read_error()
        icon_section = content[content.find('state-panel__icon'):]
        icon_section = icon_section[:icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in icon_section, \
            "Error 的 state-panel__icon 必须有 aria-hidden='true'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_icon_value(self):
        """Error 图标必须显示 '!'。"""
        content = _read_error()
        # 图标 div 包含 "!" — 在图标元素内检查
        icon_start = content.find('state-panel__icon--error')
        assert icon_start != -1, "Error 必须有 state-panel__icon--error"
        icon_snippet = content[icon_start:icon_start + 100]
        assert '!' in icon_snippet, \
            "Error 的 state-panel__icon 必须显示 '!'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_title(self):
        """Error 必须有 .state-panel__title。"""
        content = _read_error()
        assert 'class="state-panel__title"' in content, \
            "Error 必须有 state-panel__title"
        assert "Something Went Wrong" in content, \
            "Error 标题必须包含 'Something Went Wrong'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_desc(self):
        """Error 必须有 .state-panel__desc 元素。"""
        content = _read_error()
        assert 'class="state-panel__desc"' in content, \
            "Error 必须有 state-panel__desc"


# -- TestErrorNavigation ----------------------------------------------------


class TestErrorNavigation:
    """验证 error 导航链接。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_links_nav(self):
        """Error 必须有带 .state-panel__links 的 nav。"""
        content = _read_error()
        assert 'class="state-panel__links"' in content, \
            "Error 必须有 state-panel__links"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_nav_aria_label(self):
        """Error 的 nav 必须有 aria-label。"""
        content = _read_error()
        assert 'aria-label="Navigation links"' in content, \
            "Error 的 nav 必须有 aria-label='Navigation links'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_dashboard_link(self):
        """Error 必须链接回 /dashboard。"""
        content = _read_error()
        assert 'href="/dashboard"' in content, \
            "Error 必须有 /dashboard 链接"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_single_nav_link(self):
        """Error 必须恰好有 1 个导航链接（仅 Dashboard）。"""
        content = _read_error()
        links = re.findall(r'class="state-panel__link"', content)
        assert len(links) == 1, \
            f"Error 必须有 1 个 state-panel__link，发现 {len(links)} 个"


# -- TestErrorConditionalDetails --------------------------------------------


class TestErrorConditionalDetails:
    """验证 error.html 中条件性错误详情渲染。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_jinja_if_error_block(self):
        """Error 模板必须条件性地渲染错误详情。"""
        content = _read_error()
        assert '{% if error %}' in content, \
            "Error 必须有 {% if error %} 条件块"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_state_panel_details(self):
        """Error 必须有 .state-panel__details 可折叠区域。"""
        content = _read_error()
        assert 'class="state-panel__details"' in content, \
            "Error 必须有 state-panel__details"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_details_summary(self):
        """Error 详情必须有 summary 元素。"""
        content = _read_error()
        assert "<summary>" in content, \
            "Error 详情必须有 summary 元素"
        assert "Error details" in content, \
            "Error 详情的 summary 必须显示 'Error details'"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_raw_error_output(self):
        """Error 必须有 .state-panel__raw 用于原始错误输出。"""
        content = _read_error()
        assert 'class="state-panel__raw"' in content, \
            "Error 必须有 state-panel__raw"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_jinja_error_variable(self):
        """Error 模板必须渲染 error 变量。"""
        content = _read_error()
        assert "{{ error }}" in content, \
            "Error 必须渲染 {{ error }} 变量"


# -- TestNoInlinePatterns (shared) -----------------------------------------


class Test404NoInlinePatterns:
    """验证 404 不含 inline 样式或脚本。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_onclick(self):
        """404 不得使用 inline onclick 处理器。"""
        content = _read_404()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"404 不得有 inline onclick，发现 {len(matches)} 处"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_script_tags(self):
        """404 不得有 inline 脚本块。"""
        content = _read_404()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"404 不得有 inline 脚本标签，发现 {len(script_tags)} 个"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_blocks(self):
        """404 不得有 inline 样式块。"""
        content = _read_404()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"404 不得有 inline 样式块，发现 {len(style_blocks)} 个"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_attribute(self):
        """404 不得有 inline style= 属性。"""
        content = _read_404()
        inline_styles = re.findall(r'\bstyle\s*="[^"]*"', content, re.IGNORECASE)
        assert len(inline_styles) == 0, \
            f"404 不得有 inline 样式属性，发现 {len(inline_styles)} 处"


class TestErrorNoInlinePatterns:
    """验证 error.html 不含 inline 样式或脚本。"""

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_onclick(self):
        """Error 不得使用 inline onclick 处理器。"""
        content = _read_error()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Error 不得有 inline onclick，发现 {len(matches)} 处"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_script_tags(self):
        """Error 不得有 inline 脚本块。"""
        content = _read_error()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Error 不得有 inline 脚本标签，发现 {len(script_tags)} 个"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_blocks(self):
        """Error 不得有 inline 样式块。"""
        content = _read_error()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Error 不得有 inline 样式块，发现 {len(style_blocks)} 个"

    @pytest.mark.contract_case("UI-VISUAL-015")
    def test_no_inline_style_attribute(self):
        """Error 不得有 inline style= 属性。"""
        content = _read_error()
        inline_styles = re.findall(r'\bstyle\s*="[^"]*"', content, re.IGNORECASE)
        assert len(inline_styles) == 0, \
            f"Error 不得有 inline 样式属性，发现 {len(inline_styles)} 处"
