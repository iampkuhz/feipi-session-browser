"""T031 · info 图标组件契约测试。

验证 projects.html 和 project.html 不直接嵌入 Unicode info 字符
ⓘ（U+24D8）作为原始文本。info 图标应通过宏或组件渲染，
使用语义化/可访问的模式（如 SVG 图标、实体引用或 CSS 伪元素）。

覆盖 P-25：页面有乱码/特殊字符图标 ⓘ
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / 'src' / 'session_browser' / 'web' / 'templates'

PROJECTS_HTML = TEMPLATE_DIR / 'projects.html'
PROJECT_HTML = TEMPLATE_DIR / 'project.html'

# 问题 Unicode 字符
INFO_CHAR = 'ⓘ'  # ⓘ


def _read_template(path: Path) -> str:
    if not path.exists():
        pytest.fail(f'{path.name} not found at {path}')
    return path.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def projects_html():
    return _read_template(PROJECTS_HTML)


@pytest.fixture(scope='module')
def project_html():
    return _read_template(PROJECT_HTML)


class TestInfoIconNotRawEmbedded:
    """模板不得直接嵌入 ⓘ 作为原始文本。

    info 图标应通过宏/组件生成，而非将原始 Unicode 字符
    粘贴到模板源码中。
    """

    @pytest.mark.contract_case('UI-SD-001')
    def test_projects_no_raw_info_icon(self, projects_html):
        """projects.html 不得包含原始 ⓘ 字符。"""
        assert INFO_CHAR not in projects_html, (
            'projects.html contains raw ⓘ (U+24D8) character. '
            'Use a macro/component or SVG icon instead.'
        )

    @pytest.mark.contract_case('UI-SD-001')
    def test_project_no_raw_info_icon(self, project_html):
        """project.html 不得包含原始 ⓘ 字符。"""
        assert INFO_CHAR not in project_html, (
            'project.html contains raw ⓘ (U+24D8) character. '
            'Use a macro/component or SVG icon instead.'
        )

    @pytest.mark.contract_case('UI-SD-001')
    def test_projects_uses_info_button_component(self, projects_html):
        """projects.html 应使用语义化 info 按钮模式。

        可接受的模式：
        - icon_button 宏调用
        - icon-button 类 + info 变体
        - data-action="metric-info" 或 data-action="info"
        """
        has_icon_button = 'icon-button--info' in projects_html or 'icon_button' in projects_html
        has_data_action = 'metric-info' in projects_html or 'data-action="info"' in projects_html
        assert has_icon_button or has_data_action, (
            'projects.html lacks a semantic info button pattern. '
            'Expected icon-button--info class or icon_button macro usage.'
        )

    @pytest.mark.contract_case('UI-SD-001')
    def test_project_uses_info_button_component(self, project_html):
        """project.html 应使用语义化说明模式。"""
        has_icon_button = 'icon-button--info' in project_html or 'icon_button' in project_html
        has_data_action = 'data-action="info"' in project_html
        has_tooltip = 'data-tooltip=' in project_html
        assert has_icon_button or has_data_action or has_tooltip, (
            'project.html lacks a semantic info button pattern. '
            'Expected icon-button--info, icon_button macro, info action, or data-tooltip usage.'
        )
