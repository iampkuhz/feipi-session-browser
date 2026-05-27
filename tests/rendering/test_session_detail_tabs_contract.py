"""Session detail tabs/panels contract test (T025 / SD-19).

Verifies that the session detail template (session.html) satisfies the
static tabs-to-panels contract:

1. The tabs region must contain data-tab entries for: trace, metrics, payloads.
2. The panels region must contain corresponding data-panel entries for:
   trace, metrics, payloads.
3. Every declared tab must have a matching panel.

This is a pure-static (textual) audit; no rendering or runtime execution.
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SESSION_HTML = ROOT / "src" / "session_browser" / "web" / "templates" / "session.html"

# Tabs and panels we require
REQUIRED_TABS = {"trace", "metrics", "payloads"}


@pytest.fixture(scope="module")
def session_source():
    """Load the full session.html template source."""
    if not SESSION_HTML.exists():
        pytest.skip(f"Template not found at {SESSION_HTML}")
    return SESSION_HTML.read_text(encoding="utf-8")


def _find_data_tabs(source):
    """Return the set of values found in data-tab=\"...\" attributes."""
    return set(re.findall(r'data-tab="([^"]+)"', source))


def _find_data_panels(source):
    """Return the set of panel identifiers.

    Supports both explicit data-panel="name" and data-<name>-panel patterns
    (e.g. data-trace-panel, data-metrics-panel, data-payloads-panel).
    """
    panels = set()
    # Pattern 1: data-panel="name"
    panels.update(re.findall(r'data-panel="([^"]+)"', source))
    # Pattern 2: data-<name>-panel (standalone attribute, no value)
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
    def test_tabs_contain_metrics(self, session_source):
        """Tabs must include 'metrics'."""
        tabs = _find_data_tabs(session_source)
        assert "metrics" in tabs, f"Missing data-tab=\"metrics\" in session.html. Found tabs: {tabs}"

    @pytest.mark.contract_case("UI-SD-023")
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
    def test_panels_contain_metrics(self, session_source):
        """Panels must include 'metrics'."""
        panels = _find_data_panels(session_source)
        assert "metrics" in panels, (
            f"Missing metrics panel (data-panel=\"metrics\" or data-metrics-panel) in session.html. "
            f"Found panels: {panels}"
        )

    @pytest.mark.contract_case("UI-SD-023")
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
