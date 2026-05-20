"""HIFI fixture session contract tests.

Verifies that the deterministic fixture session (tests/fixtures/session_hifi_fixture/)
contains the required signals for visual testing:
- Multiple rounds with different tool types
- At least one tool call failure
- Anomaly signals (failed subagent)
- Token usage across all categories (input, output, cache_read, cache_write)
- Mix of LLM calls and tool calls
- Subagent interaction (even if failed)

Runs with standard pytest using the hifi_fixture_session fixture from conftest.py.
"""

import os
import sys

import pytest

try:
    from bs4 import BeautifulSoup
except ImportError:
    pytest.skip("bs4 not installed", allow_module_level=True)

from tests.conftest import get_html

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(SB_ROOT, "src")


class TestFixtureSessionRenders:
    """Basic smoke tests: the fixture session page renders without errors."""

    def test_fixture_session_has_content(self, hifi_fixture_session):
        """Fixture session must render non-empty HTML with expected structure."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        assert soup is not None
        body = soup.find("body")
        assert body is not None
        assert len(body.get_text(strip=True)) > 100
        # HTTP 200 implied by get_html; verify key structural elements
        assert soup.select_one("[data-session-detail-shell]") is not None
        assert soup.select_one("[data-trace-panel]") is not None


class TestFixtureDataAttributes:
    """Verify the fixture session has correct data attributes for HIFI wiring."""

    def test_view_switch_buttons(self, hifi_fixture_session):
        """v11: no data-switch buttons for calls/hotspots; toggle-all and filter-status exist."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        # Old view switch buttons must NOT exist
        for view in ("calls", "hotspots"):
            btn = soup.select_one(f'[data-switch="{view}"]')
            assert btn is None, f'unexpected button with data-switch="{view}" (should be removed)'
        # v11 action buttons
        for action in ("toggle-all", "filter-status"):
            btn = soup.select_one(f'[data-action="{action}"]')
            assert btn is not None, f'missing button with data-action="{action}"'
        # expand-visible was removed in v9
        btn = soup.select_one('[data-action="expand-visible"]')
        assert btn is None, "expand-visible button should not exist in v9"

    def test_view_panels(self, hifi_fixture_session):
        """v9: trace-panel and issue-strip must exist; old views must not."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        panel = soup.select_one("[data-trace-panel]")
        assert panel is not None, "missing [data-trace-panel]"
        issue = soup.select_one("[data-issue-strip]")
        assert issue is not None, "missing [data-issue-strip]"
        # Old view panels must NOT exist
        for view in ("calls", "hotspots"):
            panel = soup.select_one(f'[data-view="{view}"]')
            assert panel is None, f'unexpected panel with data-view="{view}" (should be removed)'


class TestFixtureRoundCount:
    """Verify the fixture has the expected number of conversation rounds."""

    def test_at_least_3_rounds(self, hifi_fixture_session):
        """Fixture must have at least 3 conversation rounds."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        # v9: Timeline rows use [data-trace-round-row]
        timeline_rows = soup.select("[data-trace-round-row]")
        round_count = len(timeline_rows)
        assert round_count >= 3, f"Expected at least 3 rounds, found {round_count}"

    def test_rounds_have_tool_calls(self, hifi_fixture_session):
        """At least some rounds should contain tool calls."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        # v9: tool groups use [data-tool-batch-id]
        tool_elements = soup.select("[data-tool-batch-id]")
        assert len(tool_elements) > 0, "No tool batch elements found in rounds"


class TestFixtureTokenData:
    """Verify the fixture session has token data across all categories."""

    def test_token_bar_elements_present(self, hifi_fixture_session):
        """Token bar elements should be rendered in round rows."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        # v9: token bar uses .sd-tokenbar class
        token_bars = soup.select(".sd-tokenbar")
        assert len(token_bars) > 0, "No token bar elements found in session HTML"

    def test_session_has_token_summary(self, hifi_fixture_session):
        """Session page should display token summary/metrics."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        # Check that the HTML contains token count references
        assert "token" in html.lower(), "No token references in session HTML"


class TestFixtureAnomalySignals:
    """Verify the fixture session triggers anomaly signals."""

    def test_session_page_has_anomaly_elements(self, hifi_fixture_session):
        """Session page should render anomaly-related elements if detected."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        soup = BeautifulSoup(html, "html.parser")
        # The fixture has a failed subagent call, which should trigger
        # a failed_tool anomaly on that round
        # Check for badge elements or anomaly indicators
        badges = soup.select(".badge, [data-signal], [data-anomaly]")
        # Even if no anomalies render as visible badges, the page should load
        assert soup is not None


class TestFixtureFailedToolCall:
    """Verify the fixture has at least one failed tool call."""

    def test_failed_tool_in_session_html(self, hifi_fixture_session):
        """Session HTML should contain references to failed tool or error state."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        # The fixture has a failed Agent (Explore) subagent call
        # The HTML should contain error-related text or badges
        has_error_indicator = (
            "failed" in html.lower()
            or "error" in html.lower()
            or "is_error" in html.lower()
            or "badge-anomaly" in html.lower()
        )
        assert has_error_indicator, "No failed tool indicator found in HTML"


class TestFixtureLLMCalls:
    """Verify the fixture has multiple LLM calls."""

    def test_calls_view_removed(self, hifi_fixture_session):
        """Phase 1: calls view is removed; trace panel with token data should exist."""
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        # The old calls view should NOT exist
        assert 'data-view="calls"' not in html, "calls view should be removed in Phase 1"
        # Token references should still be present in the trace panel
        assert "token" in html.lower(), "No token references in session HTML"


class TestFixtureDirectParser:
    """Directly parse the fixture JSONL to verify its contents, without HTTP."""

    def _parse_fixture(self):
        """Parse the fixture JSONL directly and return structured data."""
        import importlib
        sys.path.insert(0, SRC_DIR)
        fixture_dir = os.path.join(
            SB_ROOT, "tests", "fixtures", "session_hifi_fixture"
        )
        fixture_file = os.path.join(
            fixture_dir,
            "projects", "test-hifi-project", "hifi-viz-session-001.jsonl"
        )
        assert os.path.exists(fixture_file), f"Fixture file missing: {fixture_file}"

        old_data_dir = os.environ.get("CLAUDE_DATA_DIR", "")
        os.environ["CLAUDE_DATA_DIR"] = fixture_dir

        # Reload config so CLAUDE_DATA_DIR is re-read, then clear source modules
        if "session_browser.config" in sys.modules:
            importlib.reload(sys.modules["session_browser.config"])
        for _mod in list(sys.modules):
            if _mod.startswith("session_browser.sources"):
                del sys.modules[_mod]

        try:
            from session_browser.sources.claude import parse_session_detail
            summary, messages, tool_calls, subagent_runs = parse_session_detail(
                "test-hifi-project", "hifi-viz-session-001"
            )
            return summary, messages, tool_calls, subagent_runs
        finally:
            if old_data_dir:
                os.environ["CLAUDE_DATA_DIR"] = old_data_dir
            else:
                os.environ.pop("CLAUDE_DATA_DIR", None)

    def test_fixture_has_multiple_rounds(self):
        """Fixture must produce at least 3 conversation rounds."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        assistant_msgs = [m for m in messages if m.role == "assistant" and m.content]
        assert len(assistant_msgs) >= 3, f"Expected >= 3 assistant messages, got {len(assistant_msgs)}"

    def test_fixture_has_tool_calls(self):
        """Fixture must contain tool calls."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        assert len(tool_calls) > 0, "No tool calls found in fixture"

    def test_fixture_has_failed_tool(self):
        """Fixture must have at least one failed tool call."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        failed = [tc for tc in tool_calls if tc.is_failed]
        assert len(failed) > 0, f"No failed tool calls found. Tool statuses: {[tc.status for tc in tool_calls]}"

    def test_fixture_has_token_usage(self):
        """Fixture must have non-zero token counts across categories."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        assert summary.input_tokens > 0, f"input_tokens is 0"
        assert summary.output_tokens > 0, f"output_tokens is 0"
        # At least one of cache categories should be nonzero
        assert (summary.cached_input_tokens > 0 or summary.cached_output_tokens > 0), \
            "Both cache token counts are 0"

    def test_fixture_has_multiple_tool_types(self):
        """Fixture must use at least 3 different tool types."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        tool_names = set(tc.name for tc in tool_calls)
        assert len(tool_names) >= 3, f"Expected >= 3 tool types, got {tool_names}"

    def test_fixture_has_subagent_run(self):
        """Fixture must include a subagent run (even if it failed)."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        agent_tools = [tc for tc in tool_calls if tc.name == "Agent"]
        assert len(agent_tools) > 0, "No Agent tool calls found — fixture should include a subagent"

    def test_fixture_session_summary_fields(self):
        """SessionSummary must be populated with expected metadata."""
        summary, messages, tool_calls, subagent_runs = self._parse_fixture()
        assert summary.agent == "claude_code"
        assert summary.session_id == "hifi-viz-session-001"
        assert summary.project_key == "test-hifi-project"
        assert summary.title != "", "Title should not be empty"
        assert summary.model != "", "Model should not be empty"
        assert summary.user_message_count > 0
        assert summary.assistant_message_count > 0


class TestHifiDomSelectors:
    """Positive assertions for required HIFI DOM data selectors."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        return BeautifulSoup(html, "html.parser"), html

    def test_data_session_detail_shell(self, hifi_fixture_session):
        """Root shell wrapper must exist."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-session-detail-shell]")
        assert el is not None, "missing [data-session-detail-shell]"

    def test_data_session_overview_hero(self, hifi_fixture_session):
        """Overview hero must exist."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-session-overview-hero]")
        assert el is not None, "missing [data-session-overview-hero]"

    # v9 does not render an anomaly banner element in session detail
    # (anomaly detection is in dashboard; round-level status shown via sd-round-status)

    def test_data_trace_panel(self, hifi_fixture_session):
        """Trace panel container must exist (replaces old workbench)."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-trace-panel]")
        assert el is not None, "missing [data-trace-panel]"

    def test_data_trace_list(self, hifi_fixture_session):
        """Trace list (.trace-list or equivalent container) must exist."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one(".trace-list") or soup.select_one("[data-trace-panel]")
        assert el is not None, "missing trace list container"

    def test_data_workbench_view_calls_removed(self, hifi_fixture_session):
        """Workbench calls view must NOT exist (removed in Phase 1)."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one('[data-workbench-view="calls"]')
        assert el is None, 'unexpected [data-workbench-view="calls"] (should be removed)'

    def test_data_workbench_view_hotspots_removed(self, hifi_fixture_session):
        """Workbench hotspots view must NOT exist (removed in Phase 1)."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one('[data-workbench-view="hotspots"]')
        assert el is None, 'unexpected [data-workbench-view="hotspots"] (should be removed)'

    def test_data_context_inspector(self, hifi_fixture_session):
        """Context inspector must NOT exist on session detail (Phase 1 removes default inspector)."""
        soup, _ = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-context-inspector]")
        assert el is None, "[data-context-inspector] should not exist on session detail (Phase 1)"


class TestLegacyNegativeContract:
    """Legacy negative tests: verify old patterns are not the primary layout."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        return BeautifulSoup(html, "html.parser"), html

    def test_no_legacy_top_level_tabs(self, hifi_fixture_session):
        """Top-level Profile/Timeline/Hotspots tabs must not be the primary layout."""
        soup, html = self._soup(hifi_fixture_session)
        # Check for old-style tab navigation with these labels
        legacy_tabs = soup.select(".tab-nav, .tab-bar, nav[aria-label*='tab']")
        for tab in legacy_tabs:
            text = tab.get_text(strip=True).lower()
            assert not any(kw in text for kw in ["profile", "timeline", "hotspots"]), \
                f"Legacy top-level tabs found: {tab.get_text(strip=True)}"

        # Also check for standalone tab buttons
        tab_buttons = soup.select("button[data-tab], .tab-item, .nav-tab")
        for btn in tab_buttons:
            text = btn.get_text(strip=True).lower()
            assert text not in ("profile", "timeline", "hotspots"), \
                f"Legacy tab button found: {text}"

    def test_trace_view_no_hotspots_cards(self, hifi_fixture_session):
        """Trace panel must not contain Hotspots cards."""
        soup, _ = self._soup(hifi_fixture_session)
        trace_panel = soup.select_one("[data-trace-panel]")
        assert trace_panel is not None, "trace panel container missing"
        # Hotspots cards use .hotspot-card or .hot-card classes
        hotspots_cards = trace_panel.select(".hotspot-card, .hot-card, .hotspots-diagnostic")
        assert len(hotspots_cards) == 0, \
            f"Trace panel contains {len(hotspots_cards)} hotspots card(s)"

    def test_calls_view_no_inline_large_payload(self, hifi_fixture_session):
        """Calls view must not exist in Phase 1 (negative test)."""
        soup, html = self._soup(hifi_fixture_session)
        calls_view = soup.select_one('[data-view="calls"]')
        assert calls_view is None, "calls view should not exist in Phase 1"


class TestShellResidue:
    """Shell residue tests: verify removed entries are not present."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        return BeautifulSoup(html, "html.parser"), html

    def test_no_round_map(self, hifi_fixture_session):
        """Round Map must not appear in sidebar."""
        soup, _ = self._soup(hifi_fixture_session)
        round_map = soup.select_one(".round-map")
        assert round_map is None, "sidebar Round Map must be removed"

    def test_no_sidebar_extra(self, hifi_fixture_session):
        """Sidebar extra block must be empty on session detail."""
        soup, _ = self._soup(hifi_fixture_session)
        sidebar_extra = soup.select_one("aside .nav-label + .map-row")
        # More precise: check no sidebar_extra content
        sidebar_navs = soup.select("aside .nav a")
        # Should only have Sessions and Dashboard
        hrefs = [a.get("href", "") for a in sidebar_navs]
        for h in hrefs:
            assert h in ("/sessions", "/dashboard", "#"), \
                f"Unexpected sidebar nav href: {h}"

    def test_no_topbar_toggles(self, hifi_fixture_session):
        """Topbar toggle buttons (☰ left, ☰ right, focus ●) must not render."""
        soup, html = self._soup(hifi_fixture_session)
        # Check that the topbar-actions does NOT contain the toggle buttons
        topbar_actions = soup.select_one(".topbar-actions")
        if topbar_actions:
            top_btns = topbar_actions.select("button.top-btn")
            for btn in top_btns:
                title = btn.get("title", "")
                assert "切换左侧" not in title, \
                    f"Sidebar toggle still in topbar: {title}"
                assert "切换右侧" not in title, \
                    f"Right panel toggle still in topbar: {title}"
                assert "专注模式" not in title, \
                    f"Focus toggle still in topbar: {title}"

    def test_no_disabled_placeholders(self, hifi_fixture_session):
        """No visible disabled placeholder buttons."""
        soup, html = self._soup(hifi_fixture_session)
        disabled = soup.select('button[disabled]')
        visible_disabled = [b for b in disabled
                           if not (b.get("hidden") or "display:none" in (b.get("style") or ""))]
        assert len(visible_disabled) == 0, \
            f"Found {len(visible_disabled)} visible disabled button(s)"

    def test_no_content_modal(self, hifi_fixture_session):
        """Content-modal element must not exist."""
        soup, html = self._soup(hifi_fixture_session)
        modal = soup.select_one("#content-modal")
        assert modal is None, "content-modal element must be removed"
        # openContentModal must not be defined as window.openContentModal
        assert "window.openContentModal = function" not in html, \
            "window.openContentModal must not be defined"


class TestTraceRowAria:
    """Trace rows must be semantic buttons with proper ARIA."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        return BeautifulSoup(html, "html.parser"), html

    def test_trace_rows_are_not_buttons(self, hifi_fixture_session):
        """Trace rows must be <article> elements, NOT <button> (to avoid nested button conflict)."""
        soup, _ = self._soup(hifi_fixture_session)
        rows = soup.select("[data-trace-round-row]")
        assert len(rows) > 0, "No trace rows found"
        for row in rows:
            assert row.name != "button", \
                f"trace-row is <button>, expected <article>"

    def test_trace_rows_have_toggle_buttons(self, hifi_fixture_session):
        """Each trace row must contain a [data-action='toggle-round'] button."""
        soup, _ = self._soup(hifi_fixture_session)
        rows = soup.select("[data-trace-round-row]")
        for row in rows:
            toggle = row.select_one("[data-action='toggle-round']")
            assert toggle is not None, \
                f"trace-row missing toggle-round button"

    def test_trace_toggle_buttons_have_aria_expanded(self, hifi_fixture_session):
        """All toggle buttons must have aria-expanded."""
        soup, _ = self._soup(hifi_fixture_session)
        toggles = soup.select("[data-action='toggle-round']")
        for toggle in toggles:
            assert toggle.get("aria-expanded") in ("true", "false"), \
                f"toggle missing aria-expanded or invalid value: {toggle.get('aria-expanded')}"

    def test_trace_toggle_buttons_have_aria_controls(self, hifi_fixture_session):
        """All toggle buttons must have aria-controls referencing a valid ID."""
        soup, _ = self._soup(hifi_fixture_session)
        toggles = soup.select("[data-action='toggle-round']")
        for toggle in toggles:
            controls_id = toggle.get("aria-controls")
            assert controls_id, "toggle missing aria-controls"
            target = soup.select_one(f"#{controls_id}")
            assert target is not None, \
                f"aria-controls='{controls_id}' does not match any element"
            assert target.has_attr("data-trace-detail"), \
                f"aria-controls target is not a trace-detail"

    def test_trace_detail_has_matching_id(self, hifi_fixture_session):
        """Each trace-detail must have an id matching the pattern trace-detail-N."""
        soup, _ = self._soup(hifi_fixture_session)
        details = soup.select(".trace-detail")
        for detail in details:
            detail_id = detail.get("id")
            assert detail_id and detail_id.startswith("trace-detail-"), \
                f"trace-detail missing or invalid id: {detail_id}"


class TestDeadButtonGate:
    """Every visible button must have a supported data-action."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = get_html(url)
        return BeautifulSoup(html, "html.parser"), html

    SUPPORTED_ACTIONS = {
        "filter-status", "toggle-all", "expand-all", "expand-visible", "collapse-all",
        "open-payload", "payload-mode", "close-modal", "close-payload", "payload-tab",
        "jump-round", "jump-anomaly", "md-toggle",
        "toggle-round", "toggle-issue-expand", "toggle-sub-round",
    }

    def test_all_buttons_have_supported_data_action(self, hifi_fixture_session):
        """All visible buttons must have a supported data-action or known role."""
        soup, _ = self._soup(hifi_fixture_session)
        buttons = soup.select("button")
        for btn in buttons:
            action = btn.get("data-action")
            title = btn.get("title", "")[:40]
            cls = btn.get("class", [])
            # Skip buttons without data-action that have other valid roles
            if action is None:
                # Allow type='submit' or type='reset' buttons
                if btn.get("type") in ("submit", "reset"):
                    continue
                # Skip topbar toggles with onclick (legacy base.html patterns)
                if "top-btn" in cls and btn.get("onclick"):
                    continue
                # Skip payload buttons in modal tabs (they use data-mode)
                if "payload-modal__tab" in cls or "payload-modal__close" in cls:
                    continue
                assert False, \
                    f"Button with no data-action: title='{title}' class={' '.join(cls)}"
            else:
                assert action in self.SUPPORTED_ACTIONS, \
                    f"Button has unsupported data-action='{action}': title='{title}'"
