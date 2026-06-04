"""Session detail 标签页/面板契约测试（T025 / SD-19）。

验证 session detail 模板（session.html）满足
静态标签页到面板的契约：

1. 标签页区域必须包含以下 data-tab 条目：trace、metrics、payloads。
2. 面板区域必须包含对应的 data-panel 条目：
   trace、metrics、payloads。
3. 每个声明的标签页必须有对应的面板。

这是纯静态（文本）审计；不涉及渲染或运行时执行。
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SESSION_HTML = ROOT / "src" / "session_browser" / "web" / "templates" / "session.html"

# 所需的标签页和面板
# Note: metrics and payloads tabs were removed in 72b3157; only trace remains.
REQUIRED_TABS = {"trace"}


@pytest.fixture(scope="module")
def session_source():
    """加载完整的 session.html 模板源码。"""
    if not SESSION_HTML.exists():
        pytest.skip(f"Template not found at {SESSION_HTML}")
    return SESSION_HTML.read_text(encoding="utf-8")


def _find_data_tabs(source):
    """返回 data-tab="..." 属性中找到的值集合。"""
    return set(re.findall(r'data-tab="([^"]+)"', source))


def _find_data_panels(source):
    """返回面板标识符集合。

    支持显式的 data-panel="name" 和 data-<name>-panel 模式
    （例如 data-trace-panel、data-metrics-panel、data-payloads-panel）。
    """
    panels = set()
    # 模式 1：data-panel="name"
    panels.update(re.findall(r'data-panel="([^"]+)"', source))
    # 模式 2：data-<name>-panel（独立属性，无值）
    panels.update(re.findall(r'data-([a-zA-Z0-9_]+)-panel(?:\s|>|$)', source))
    return panels


class TestTabsPanelsContract:
    """Every required tab must have a matching panel."""

    @pytest.mark.contract_case("UI-SD-023")
    def test_tabs_contain_trace(self, session_source):
        """Tabs must include 'trace'."""
        tabs = _find_data_tabs(session_source)
        assert "trace" in tabs, f"Missing data-tab=\"trace\" in session.html. Found tabs: {tabs}"

    @pytest.mark.contract_case("UI-SD-023")
    @pytest.mark.skip(reason="metrics tab removed in 72b3157")
    def test_tabs_contain_metrics(self, session_source):
        """Tabs must include 'metrics'."""
        tabs = _find_data_tabs(session_source)
        assert "metrics" in tabs, f"Missing data-tab=\"metrics\" in session.html. Found tabs: {tabs}"

    @pytest.mark.contract_case("UI-SD-023")
    @pytest.mark.skip(reason="payloads tab removed in 72b3157")
    def test_tabs_contain_payloads(self, session_source):
        """Tabs must include 'payloads'."""
        tabs = _find_data_tabs(session_source)
        assert "payloads" in tabs, f"Missing data-tab=\"payloads\" in session.html. Found tabs: {tabs}"

    @pytest.mark.contract_case("UI-SD-023")
    def test_panels_contain_trace(self, session_source):
        """Panels must include 'trace'."""
        panels = _find_data_panels(session_source)
        assert "trace" in panels, (
            f"Missing trace panel (data-panel=\"trace\" or data-trace-panel) in session.html. "
            f"Found panels: {panels}"
        )

    @pytest.mark.contract_case("UI-SD-023")
    @pytest.mark.skip(reason="metrics panel removed in 72b3157")
    def test_panels_contain_metrics(self, session_source):
        """Panels must include 'metrics'."""
        panels = _find_data_panels(session_source)
        assert "metrics" in panels, (
            f"Missing metrics panel (data-panel=\"metrics\" or data-metrics-panel) in session.html. "
            f"Found panels: {panels}"
        )

    @pytest.mark.contract_case("UI-SD-023")
    @pytest.mark.skip(reason="payloads panel removed in 72b3157")
    def test_panels_contain_payloads(self, session_source):
        """Panels must include 'payloads'."""
        panels = _find_data_panels(session_source)
        assert "payloads" in panels, (
            f"Missing payloads panel (data-panel=\"payloads\" or data-payloads-panel) in session.html. "
            f"Found panels: {panels}"
        )

    @pytest.mark.contract_case("UI-SD-023")
    def test_tab_panel_one_to_one(self, session_source):
        """Every required tab must have a matching panel (bijection check)."""
        tabs = _find_data_tabs(session_source)
        panels = _find_data_panels(session_source)
        missing = REQUIRED_TABS - panels
        assert not missing, (
            f"The following required tabs have no matching panel: {missing}. "
            f"Found tabs: {tabs}, found panels: {panels}"
        )
