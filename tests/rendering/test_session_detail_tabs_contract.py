"""Session detail 标签页/面板契约测试（T025 / SD-19）。

验证 session detail 模板（session.html）满足
静态标签页到面板的契约：

1. 标签页区域必须包含以下 data-tab 条目：trace、payload。
2. 面板区域必须包含对应的 data-panel 条目：
   trace、payload。
3. 每个声明的标签页必须有对应的面板。

这是纯静态（文本）审计；不涉及渲染或运行时执行。
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SESSION_HTML = ROOT / "src" / "session_browser" / "web" / "templates" / "session.html"

# 所需的标签页和面板
REQUIRED_TABS = {"trace", "payload"}


@pytest.fixture(scope="module")
def session_source():
    """加载完整的 session.html 模板源码。"""
    if not SESSION_HTML.exists():
        pytest.fail(f"Template not found at {SESSION_HTML}")
    return SESSION_HTML.read_text(encoding="utf-8")


def _find_data_tabs(source):
    """返回 data-tab="..." 属性中找到的值集合。"""
    return set(re.findall(r'data-tab="([^"]+)"', source))


def _find_data_panels(source):
    """返回面板标识符集合。

    支持显式的 data-panel/data-tab-panel 和 data-<name>-panel 模式
    （例如 data-trace-panel、data-metrics-panel、data-payloads-panel）。
    """
    panels = set()
    # 模式 1：data-panel="name"
    panels.update(re.findall(r'data-panel="([^"]+)"', source))
    panels.update(re.findall(r'data-tab-panel="([^"]+)"', source))
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
    def test_tabs_contain_payload(self, session_source):
        """Tabs must include 'payload'."""
        tabs = _find_data_tabs(session_source)
        assert "payload" in tabs, f"Missing data-tab=\"payload\" in session.html. Found tabs: {tabs}"

    @pytest.mark.contract_case("UI-SD-023")
    def test_panels_contain_trace(self, session_source):
        """Panels must include 'trace'."""
        panels = _find_data_panels(session_source)
        assert "trace" in panels, (
            f"Missing trace panel (data-panel=\"trace\" or data-trace-panel) in session.html. "
            f"Found panels: {panels}"
        )

    @pytest.mark.contract_case("UI-SD-023")
    def test_panels_contain_payload(self, session_source):
        """Panels must include 'payload'."""
        panels = _find_data_panels(session_source)
        assert "payload" in panels, (
            f"Missing payload panel (data-panel=\"payload\" or data-tab-panel=\"payload\") in session.html. "
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
