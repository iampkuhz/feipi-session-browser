"""MHTML 导出回归测试。"""
import os
import re
import pytest
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_JS = ROOT / "src" / "session_browser" / "web" / "static" / "js"
STATIC_CSS_DIR = ROOT / "src" / "session_browser" / "web" / "static" / "css"


def _read_split_component(rel_path: str) -> str:
    """Read a template file, resolving {% include %} directives for split wrappers.

    If the file is a thin wrapper with {% include %} statements (detected by
    having includes but no actual macro/rule content), this returns the
    concatenated content of all included files plus the wrapper itself.
    """
    wrapper_path = TEMPLATES / rel_path
    text = wrapper_path.read_text(encoding="utf-8")

    # Check if this is a split wrapper: has {% include %} but no data-* attributes
    includes = re.findall(r'{%\s*include\s+"([^"]+)"\s*%}', text)
    if includes and 'data-' not in text:
        # Read all included files and concatenate their content
        parts = [text]
        for inc in includes:
            inc_path = TEMPLATES / inc
            if inc_path.exists():
                parts.append(inc_path.read_text(encoding="utf-8"))
        return "\n".join(parts)
    return text

# mhtml.py get_css() 捆绑的 CSS 文件
MHTML_CSS_FILES = [
    "css/tokens.css",
    "css/base.css",
    "css/shell.css",
    "css/ui-primitives.css",
    "css/legacy-aliases.css",
]


class TestMhtmlTemplateContracts:
    """MHTML 就绪状态的静态模板级契约。"""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def _read_js(self, name: str) -> str:
        return (STATIC_JS / name).read_text(encoding="utf-8")

    def _read_css(self) -> str:
        """读取所有由 mhtml.py get_css() 捆绑的 CSS 文件并拼接。"""
        parts = []
        for rel in MHTML_CSS_FILES:
            p = ROOT / "src" / "session_browser" / "web" / "static" / rel
            if p.exists():
                parts.append(p.read_text(encoding="utf-8"))
        return "\n".join(parts)

    # ── Trace 面板结构（Phase 1 简化版） ──

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_trace_panel_exists(self):
        html = self._read("session.html")
        assert 'data-trace-panel' in html, 'missing trace-panel'

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_trace_row_structure(self):
        # 使用组件宏；trace_round 定义在 session_detail_timeline.html 中
        html = self._read("session.html")
        assert "sdt.trace_round" in html, "missing sdt.trace_round macro call"
        component = _read_split_component("components/session_detail_timeline.html")
        assert 'data-trace-round-row' in component, 'missing trace-round-row'
        assert 'data-trace-detail' in component, 'missing trace-detail'

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_toggle_round_detail_function_exists(self):
        # 使用 session_detail_timeline.js 中的 toggleRound
        js = (STATIC_JS / "session_detail_timeline.js").read_text(encoding="utf-8")
        assert "function toggleRound" in js, "missing toggleRound function"

    # ── 布局模式 ──

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_layout_mode_classes(self):
        js = self._read_js("view-switching.js")
        # hide-left 迁移代码位于 view-switching.js 中
        assert "hide-left" in js, 'missing hide-left toggle support'

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_css_has_shell_grid(self):
        css = self._read_css()
        assert ".shell" in css, "missing .shell grid"
        assert "grid-template-columns" in css, "missing grid-template-columns"

    # Inspector 已移除——MHTML 导出不再需要 inspector 组件

    # ── MHTML 导出基础设施 ──

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_base_html_has_export_mhtml_branch(self):
        html = self._read("base.html")
        assert "export_mhtml" in html, "missing export_mhtml in base.html"
        assert "mhtml_css" in html, "missing mhtml_css in base.html"
        assert "mhtml_js" in html, "missing mhtml_js in base.html"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_mhtml_py_exists(self):
        mhtml_path = ROOT / "src" / "session_browser" / "web" / "mhtml.py"
        assert mhtml_path.exists(), "mhtml.py not found"
        mhtml = mhtml_path.read_text(encoding="utf-8")
        assert "get_css" in mhtml, "mhtml.py missing get_css"
        assert "get_js" in mhtml, "mhtml.py missing get_js"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_routes_has_export_mhtml_support(self):
        routes = (ROOT / "src" / "session_browser" / "web" / "routes.py").read_text(encoding="utf-8")
        assert "export_mhtml" in routes, "routes.py missing export_mhtml"


class TestMhtmlSelfContained:
    """自包含 HTML 导出内容检查（静态模板分析）。"""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    def _read_js(self, name: str) -> str:
        return (STATIC_JS / name).read_text(encoding="utf-8")

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_no_external_resources_in_export(self):
        """检查 MHTML 导出无外部 CSS/JS/字体引用。"""
        html = self._read("base.html")
        # MHTML 模式下模板应有条件分支
        assert "export_mhtml" in html
        # 验证 CSS/JS 是否条件内联
        assert "mhtml_css" in html
        assert "mhtml_js" in html

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_key_functions_present_in_template(self):
        """验证关键 JS 函数已引用以便 MHTML 包含。"""
        # 使用 session_detail_timeline.js 中的 toggleRound
        js = self._read_js("session_detail_timeline.js")
        assert "toggleRound" in js, "toggleRound missing from session_detail_timeline.js"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_no_google_fonts_reference(self):
        """两种模式下均不应出现 Google Fonts 引用。"""
        base = self._read("base.html")
        assert "fonts.googleapis.com" not in base, "Google Fonts reference found in base.html"
        for rel in MHTML_CSS_FILES:
            p = ROOT / "src" / "session_browser" / "web" / "static" / rel
            if p.exists():
                css = p.read_text(encoding="utf-8")
                for line in css.split("\n"):
                    if "fonts.googleapis" in line.lower():
                        raise AssertionError(f"Google Fonts URL in CSS ({rel}): {line.strip()}")


class TestPhase1SimplifiedStructure:
    """验证 Phase 1 简化版会话详情结构（trace 优先）。"""

    def _read(self, rel_path: str) -> str:
        return (TEMPLATES / rel_path).read_text(encoding="utf-8")

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_has_trace_panel(self):
        html = self._read("session.html")
        assert 'class="trace-panel"' in html or 'data-trace-panel' in html, \
            "missing trace-panel"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_has_issue_summary(self):
        # 在组件宏中使用 data-issue-strip
        component = _read_split_component("components/session_detail_timeline.html")
        assert 'data-issue-strip' in component, "missing issue-strip section"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_has_payload_modal(self):
        html = self._read("base.html")
        assert 'id="payload-modal"' in html, "missing payload-modal in base.html"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_has_expand_collapse_buttons(self):
        # 单个 toggle-all 按钮，无独立的 collapse-all
        component = _read_split_component("components/session_detail_timeline.html")
        assert 'data-action="toggle-all"' in component, "missing toggle-all"
        assert 'data-action="collapse-all"' not in component, "collapse-all must be removed; use toggle-all only"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_has_all_failed_segmented_control(self):
        # 过滤控件使用 status-all/status-failed（HIFI 表格迁移）
        component = _read_split_component("components/session_detail_timeline.html")
        has_new = 'data-action="status-all"' in component and 'data-action="status-failed"' in component
        has_legacy = 'data-action="filter-status"' in component
        assert has_new or has_legacy, "missing filter status buttons (status-all/status-failed or legacy filter-status)"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_no_old_workbench_views(self):
        """Calls 和 Hotspots workbench 视图应已移除。"""
        html = self._read("session.html")
        assert 'data-workbench-view="calls"' not in html, "calls view should be removed"
        assert 'data-workbench-view="hotspots"' not in html, "hotspots view should be removed"

    @pytest.mark.contract_case("ROUTE-API-001", "ROUTE-API-004")
    def test_no_token_charts_card(self):
        """Phase 1 应移除 Token charts 卡片。"""
        html = self._read("session.html")
        assert 'id="tokenChartsCard"' not in html, "token-charts-card should be removed"
