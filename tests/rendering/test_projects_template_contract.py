"""Projects 模板-JS 契约测试（T029）。

验证：
1. projects.html 的 filter-footer 包含活跃的筛选标签容器。
2. JS 的 updateFilterChip 选择器与模板结构匹配。

覆盖 P-23 修复验证：活跃筛选标签在 filter-footer 中的可见性。
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_JS = ROOT / "src" / "session_browser" / "web" / "static" / "js"

PROJECTS_HTML = TEMPLATE_DIR / "projects.html"
PROJECTS_JS = STATIC_JS / "projects.js"


def _projects_template():
    """返回 projects.html 文本，如果文件缺失则跳过测试。"""
    if not PROJECTS_HTML.exists():
        pytest.fail(f"projects.html not found at {PROJECTS_HTML}")
    return PROJECTS_HTML.read_text(encoding="utf-8")


def _projects_js():
    """返回 projects.js 文本，如果文件缺失则跳过测试。"""
    if not PROJECTS_JS.exists():
        pytest.fail(f"projects.js not found at {PROJECTS_JS}")
    return PROJECTS_JS.read_text(encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def projects_html():
    return _projects_template()


@pytest.fixture(scope="module")
def projects_js():
    return _projects_js()


# ── Template: filter-footer structure ─────────────────────────────────────


class TestProjectsFilterFooterStructure:
    """projects.html 的 filter-footer 必须包含活跃筛选标签容器。"""

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_filter_footer_exists(self, projects_html):
        """filter-footer 容器必须存在。"""
        assert "filter-footer" in projects_html, (
            "projects.html lacks .filter-footer container"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_active_filters_container_in_footer(self, projects_html):
        """filter-footer 必须包含 active-filters 容器或计数元素。"""
        # 接受 .active-filters 父元素或 .active-filters__count BEM 类
        has_container = (
            "active-filters" in projects_html
        )
        assert has_container, (
            "projects.html filter-footer lacks .active-filters container/element"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_active_filters_count_element(self, projects_html):
        """filter-footer 必须显示活跃筛选计数文本。"""
        # 模板应显示类似 "X matching projects" 的计数
        assert "matching projects" in projects_html or "active-filters__count" in projects_html, (
            "projects.html filter-footer lacks active filter count display"
        )


# ── JS: updateFilterChip selector ────────────────────────────────────────


class TestProjectsJsUpdateFilterChipSelector:
    """projects.js 的 updateFilterChip 必须定位 active-filters 容器。"""

    def _extract_update_filter_chip(self, js_text):
        """从 JS 文本中提取 updateFilterChip 函数体。"""
        match = re.search(
            r'function\s+updateFilterChip\s*\([^)]*\)\s*\{([^}]+)\}',
            js_text,
            re.DOTALL,
        )
        if not match:
            pytest.fail("updateFilterChip function not found in projects.js")
        return match.group(1)

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_update_filter_chip_function_exists(self, projects_js):
        """updateFilterChip 函数必须已定义。"""
        assert "updateFilterChip" in projects_js, (
            "projects.js lacks updateFilterChip function"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_update_filter_chip_has_selector(self, projects_js):
        """updateFilterChip 必须定位 projects-active-filters 容器。"""
        body = self._extract_update_filter_chip(projects_js)
        assert "getElementById('projects-active-filters')" in body

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_update_filter_chip_selector_value(self, projects_js):
        """验证定位目标指向 active-filters 元素。"""
        body = self._extract_update_filter_chip(projects_js)
        assert "projects-active-filters" in body


# ── Template-JS contract: selector matches template structure ────────────


class TestTemplateJsContractMatch:
    """JS 选择器必须与模板结构兼容。

    这是一个静态契约检查：验证如果 JS 选择器
    查找后代元素（例如 `.active-filters .filter-chip`），
    模板必须包含兼容的结构，或者选择器必须
    足够宽泛以匹配现有元素。
    """

    def _extract_filter_target(self, js_text):
        """从 updateFilterChip 中提取 DOM 定位目标。"""
        match = re.search(
            r'function\s+updateFilterChip\s*\([^)]*\)\s*\{(?P<body>.*?)\n    \}',
            js_text,
            re.DOTALL,
        )
        assert match, "updateFilterChip function not found"
        body = match.group("body")
        id_match = re.search(r"getElementById\(['\"]([^'\"]+)['\"]\)", body)
        if id_match:
            return "#" + id_match.group(1)
        selector_match = re.search(r"querySelector\(['\"]([^'\"]+)['\"]\)", body)
        assert selector_match, "Cannot extract selector from updateFilterChip"
        return selector_match.group(1)

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_js_selector_compatible_with_template(self, projects_html, projects_js):
        """JS updateFilterChip 选择器必须与模板结构兼容。

        契约规则：
        - 如果选择器是后代组合器如 `.parent .child`，
          模板必须包含 .parent 和 .child（或同时 serving
          两个角色的单一组合类）。
        - 如果选择器指向模板中定义的类，则通过。
        """
        selector = self._extract_filter_target(projects_js)

        if selector.startswith("#"):
            assert selector[1:] in projects_html, (
                f"Template projects.html does not contain id '{selector[1:]}' "
                f"referenced by JS selector '{selector}'"
            )
            return

        # 将选择器拆分为各部分（按空格拆分为后代选择器）
        parts = selector.split()

        for part in parts:
            # 去除前缀组合器（>、+、~）
            part = re.sub(r'^[>+~]\s*', '', part).strip()
            if not part:
                continue

            # 从选择器部分中提取类名（例如 ".foo.bar" -> ["foo", "bar"]）
            classes = re.findall(r'\.([a-zA-Z_][\w-]*)', part)
            if not classes:
                # 可能是不带类的标签名 — 可以接受
                continue

            for cls in classes:
                assert cls in projects_html, (
                    f"Template projects.html does not contain class '{cls}' "
                    f"referenced by JS selector '{selector}'"
                )
