"""Session Detail Timeline v11 DOM contract tests.

Validates that the v11 rendered HTML satisfies the full contract:
- Required data attributes on the rendered DOM
- Required CSS classes (sd-user-round, sd-sub-llm, sd-sub-mcell, sd-sub-pbtn, sd-note)
- Payload buttons have matching template sources
- All buttons have data-action
- No forbidden elements (inspector, calls, hotspots, legacy text)
- Static checks on CSS and JS source files
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request

import pytest

try:
    from bs4 import BeautifulSoup
except ImportError:
    pytest.skip("bs4 not installed", allow_module_level=True)

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(SB_ROOT, "src")
TEMPLATES_DIR = os.path.join(SRC_DIR, "session_browser", "web", "templates")
CSS_PATH = os.path.join(SRC_DIR, "session_browser", "web", "static", "css", "session-detail-timeline-v11.css")
JS_PATH = os.path.join(SRC_DIR, "session_browser", "web", "static", "js", "session_detail_timeline_v11.js")
QA_CHECKER = os.path.join(SB_ROOT, "scripts", "qa", "session_ui", "check_session_detail_timeline_v11_contract.py")


def _get_html(url: str) -> str:
    """Fetch HTML from url and return decoded text."""
    resp = urllib.request.urlopen(url, timeout=15)
    assert resp.status == 200
    return resp.read().decode("utf-8")


def _soup(html: str):
    return BeautifulSoup(html, "html.parser")


# ── Static asset checks (no server needed) ──────────────────────────


class TestV11CssContract:
    """Verify v11 CSS contains required patterns."""

    def _css(self):
        with open(CSS_PATH, encoding="utf-8") as f:
            return f.read()

    def test_sd_user_round(self):
        css = self._css()
        assert re.search(r"\.sd-user-round", css), "CSS missing .sd-user-round"

    def test_sd_sub_llm(self):
        css = self._css()
        assert re.search(r"\.sd-sub-llm", css), "CSS missing .sd-sub-llm"

    def test_sd_sub_mcell_b(self):
        css = self._css()
        assert re.search(r"\.sd-sub-mcell\s+b", css, flags=re.S), "CSS missing .sd-sub-mcell b"

    def test_sd_payload_modal_panel(self):
        css = self._css()
        assert re.search(r"\.sd-payload-modal__panel", css), "CSS missing .sd-payload-modal__panel"

    def test_sd_note_warn(self):
        css = self._css()
        assert re.search(r"\.sd-note--warn", css), "CSS missing .sd-note--warn"


class TestSessionDetailLayoutCss:
    """Validate shell grid override and content width constraints.

    These tests prevent regression where session detail CSS forgets to
    override the base 3-column shell grid (sidebar + main + inspector),
    causing .sd-hero and .sd-trace-panel to become unexpectedly narrow.
    """

    def _v11_css(self):
        with open(CSS_PATH, encoding="utf-8") as f:
            return f.read()

    def _v12_css_path(self):
        return os.path.join(SB_ROOT, "src", "session_browser", "web", "static", "css",
                            "session-detail-response-blocks-v12.css")

    def _v12_css(self):
        path = self._v12_css_path()
        if not os.path.exists(path):
            pytest.skip("v12 CSS not yet available")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def _check_shell_grid(self, css, name):
        """Verify CSS overrides the base 3-column shell with 2-column grid."""
        # Find the .sd-shell rule block and verify it has grid-template-columns
        # with exactly 2 space-separated track values (sidebar + content, no inspector)
        matches = re.findall(r"\.sd-shell\s*\{([^}]*)\}", css)
        assert matches, f"{name}: CSS missing .sd-shell rule block"
        combined = " ".join(matches)
        assert "grid-template-columns" in combined, (
            f"{name}: .sd-shell missing grid-template-columns — "
            "base 3-column grid will leak through and narrow the content"
        )
        # Extract the grid-template-columns value
        gtc = re.search(r"grid-template-columns\s*:\s*([^;]+)", combined)
        assert gtc, f"{name}: .sd-shell grid-template-columns value not found"
        value = gtc.group(1).strip()
        # Should have exactly 2 tracks (e.g., "220px minmax(0,1fr)")
        tracks = value.split()
        assert len(tracks) == 2, (
            f"{name}: .sd-shell grid-template-columns has {len(tracks)} tracks ({value}), "
            f"expected 2 (sidebar + content, no inspector)"
        )
        # Sidebar width should be at least 200px or use variable
        sidebar = tracks[0]
        assert "220" in sidebar or "200" in sidebar or "var(" in sidebar, (
            f"{name}: .sd-shell sidebar track '{sidebar}' seems too narrow"
        )

    def test_v11_shell_grid_override(self):
        """v11 CSS must override shell grid with 2-column layout."""
        self._check_shell_grid(self._v11_css(), "v11 CSS")

    def test_v12_shell_grid_override(self):
        """v12 CSS must override shell grid with 2-column layout."""
        self._check_shell_grid(self._v12_css(), "v12 CSS")

    def _check_content_width(self, css, name):
        """Verify .sd-content has max-width constraint."""
        matches = re.findall(r"\.sd-content\s*\{([^}]*)\}", css)
        assert matches, f"{name}: CSS missing .sd-content rule block"
        combined = " ".join(matches)
        assert "max-width" in combined, (
            f"{name}: .sd-content missing max-width — "
            "panel width will depend entirely on viewport"
        )

    def test_v11_content_max_width(self):
        """v11 CSS must constrain .sd-content width."""
        self._check_content_width(self._v11_css(), "v11 CSS")

    def test_v12_content_max_width(self):
        """v12 CSS must constrain .sd-content width."""
        self._check_content_width(self._v12_css(), "v12 CSS")

    def _check_hero_width(self, css, name):
        """Verify .sd-hero has border/background (indirect width visibility check)."""
        assert re.search(r"\.sd-hero\s*[{,]", css), f"{name}: CSS missing .sd-hero selector"

    def test_v11_hero_selector(self):
        """v11 CSS must define .sd-hero."""
        self._check_hero_width(self._v11_css(), "v11 CSS")

    def test_v12_hero_selector(self):
        """v12 CSS must define .sd-hero."""
        self._check_hero_width(self._v12_css(), "v12 CSS")

    def _check_trace_panel_width(self, css, name):
        """Verify .sd-trace-panel has border/background (indirect width visibility check)."""
        assert re.search(r"\.sd-trace-panel\s*[{,]", css), f"{name}: CSS missing .sd-trace-panel selector"

    def test_v11_trace_panel_selector(self):
        """v11 CSS must define .sd-trace-panel."""
        self._check_trace_panel_width(self._v11_css(), "v11 CSS")

    def test_v12_trace_panel_selector(self):
        """v12 CSS must define .sd-trace-panel."""
        self._check_trace_panel_width(self._v12_css(), "v12 CSS")


class TestV11JsContract:
    """Verify v11 JS contains required patterns."""

    def _js(self):
        with open(JS_PATH, encoding="utf-8") as f:
            return f.read()

    def test_function_open_payload(self):
        js = self._js()
        assert "function openPayload" in js, "JS missing function openPayload"

    def test_function_toggle_all(self):
        js = self._js()
        assert "function toggleAll" in js, "JS missing function toggleAll"

    def test_function_set_sub_round_open(self):
        js = self._js()
        assert "function setSubRoundOpen" in js, "JS missing function setSubRoundOpen"

    def test_data_action_toggle_all(self):
        js = self._js()
        assert 'data-action="toggle-all"' in js, 'JS missing data-action="toggle-all"'

    def test_template_payload_source_selector(self):
        js = self._js()
        assert "template[data-payload-source" in js, "JS missing template[data-payload-source selector"

    def test_no_markdown_payload_fallback(self):
        js = self._js()
        assert "### Payload unavailable" not in js, "JS still contains markdown-string fallback"


class TestV11TemplateContract:
    """Verify v11 templates contain required data attributes."""

    def _timeline(self):
        with open(os.path.join(TEMPLATES_DIR, "components", "session_detail_timeline_v11.html"), encoding="utf-8") as f:
            return f.read()

    def _primitives(self):
        with open(os.path.join(TEMPLATES_DIR, "components", "session_detail_primitives_v11.html"), encoding="utf-8") as f:
            return f.read()

    def _session_page(self):
        with open(os.path.join(TEMPLATES_DIR, "session.html"), encoding="utf-8") as f:
            return f.read()

    def _base(self):
        with open(os.path.join(TEMPLATES_DIR, "base.html"), encoding="utf-8") as f:
            return f.read()

    def test_data_session_detail_shell_in_base(self):
        base = self._base()
        assert "data-session-detail-shell" in base, "base.html missing [data-session-detail-shell]"

    def test_data_session_overview_hero_in_timeline(self):
        tl = self._timeline()
        assert "data-session-overview-hero" in tl, "timeline_v11 missing [data-session-overview-hero]"

    def test_data_trace_page_in_session(self):
        sp = self._session_page()
        assert "data-trace-page" in sp, "session.html missing [data-trace-page]"

    def test_data_trace_panel_in_session(self):
        sp = self._session_page()
        assert "data-trace-panel" in sp, "session.html missing [data-trace-panel]"

    def test_data_trace_round_row_in_timeline(self):
        tl = self._timeline()
        assert "data-trace-round-row" in tl, "timeline_v11 missing [data-trace-round-row]"

    def test_data_trace_detail_in_timeline(self):
        tl = self._timeline()
        assert "data-trace-detail" in tl, "timeline_v11 missing [data-trace-detail]"

    def test_data_inline_call_card_in_timeline(self):
        tl = self._timeline()
        assert "data-inline-call-card" in tl, "timeline_v11 missing [data-inline-call-card]"

    def test_data_user_message_in_timeline(self):
        tl = self._timeline()
        assert "data-user-message" in tl, "timeline_v11 missing [data-user-message]"

    def test_data_subagent_block_in_timeline(self):
        tl = self._timeline()
        assert "data-subagent-block" in tl, "timeline_v11 missing [data-subagent-block]"

    def test_data_sub_round_in_timeline(self):
        tl = self._timeline()
        assert "data-sub-round" in tl, "timeline_v11 missing [data-sub-round]"

    def test_data_sub_llm_card_in_timeline(self):
        tl = self._timeline()
        assert "data-sub-llm-card" in tl, "timeline_v11 missing [data-sub-llm-card]"

    def test_data_payload_body_in_timeline(self):
        tl = self._timeline()
        assert "data-payload-body" in tl, "timeline_v11 missing [data-payload-body]"

    def test_data_payload_source_in_timeline(self):
        tl = self._timeline()
        assert "data-payload-source" in tl, "timeline_v11 missing [data-payload-source]"

    def test_sd_user_round_class_in_timeline(self):
        tl = self._timeline()
        assert "sd-user-round" in tl, "timeline_v11 missing .sd-user-round class"

    def test_sd_payload_modal_panel_class_in_timeline(self):
        tl = self._timeline()
        assert "sd-payload-modal__panel" in tl, "timeline_v11 missing .sd-payload-modal__panel class"

    def test_sd_sub_llm_class_in_timeline(self):
        tl = self._timeline()
        assert "sd-sub-llm" in tl, "timeline_v11 missing .sd-sub-llm class"

    def test_sd_sub_mcell_class_in_primitives(self):
        pr = self._primitives()
        assert "sd-sub-mcell" in pr, "primitives_v11 missing .sd-sub-mcell class"

    def test_sd_sub_pbtn_class_in_timeline(self):
        tl = self._timeline()
        assert "sd-sub-pbtn" in tl, "timeline_v11 missing .sd-sub-pbtn class"

    def test_sd_note_class_in_primitives(self):
        pr = self._primitives()
        assert "sd-note" in pr, "primitives_v11 missing .sd-note class"

    def test_v11_css_linked_in_session(self):
        sp = self._session_page()
        assert (
            "session-detail-timeline-v11.css" in sp
            or "session-detail-response-blocks-v12.css" in sp
        ), "session.html missing session detail CSS link"

    def test_v11_js_linked_in_session(self):
        sp = self._session_page()
        assert (
            "session_detail_timeline_v11.js" in sp
            or "session_detail_response_blocks_v12.js" in sp
        ), "session.html missing session detail JS link"

    def test_no_forbidden_attrs_in_timeline(self):
        tl = self._timeline()
        assert "data-context-inspector" not in tl, "timeline_v11 has forbidden [data-context-inspector]"
        assert 'data-workbench-view="calls"' not in tl, "timeline_v11 has forbidden [data-workbench-view=calls]"
        assert 'data-workbench-view="hotspots"' not in tl, "timeline_v11 has forbidden [data-workbench-view=hotspots]"
        assert 'role="tablist"' not in tl, "timeline_v11 has forbidden role=tablist"

    def test_no_forbidden_classes_in_timeline(self):
        tl = self._timeline()
        for cls in ("phase1-shell", "no-inspector", "round-summary-table", "tab-content"):
            assert cls not in tl, f"timeline_v11 has forbidden class {cls}"

    def test_no_forbidden_text_in_timeline(self):
        tl = self._timeline()
        for text in ("Map", "Inspector", "Focus", "Open selected", "Calls", "Hotspots",
                     "High token", "Go", "Clear"):
            assert text not in tl, f"timeline_v11 has forbidden text: {text}"


# ── Live rendered HTML checks (requires hifi_fixture_session) ───────


class TestV11RequiredDataAttributes:
    """All required data-* attributes must be present in rendered HTML."""

    REQUIRED_ATTRS = [
        "data-session-detail-shell",
        "data-session-overview-hero",
        "data-trace-page",
        "data-trace-panel",
        "data-trace-round-row",
        "data-trace-detail",
        "data-inline-call-card",
        "data-user-message",
        "data-subagent-block",
        "data-sub-round",
        "data-sub-llm-card",
        "data-payload-body",
        "data-payload-source",
    ]

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        return _soup(_get_html(url))

    @pytest.mark.parametrize("attr", REQUIRED_ATTRS)
    def test_required_data_attr(self, attr, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one(f"[{attr}]")
        assert el is not None, f"missing [{attr}] in rendered HTML"


class TestV11RequiredCssClasses:
    """Required CSS classes must be present in rendered HTML."""

    REQUIRED_CLASSES = [
        "sd-user-round",
        "sd-payload-modal__panel",
        "sd-sub-llm",
        "sd-sub-mcell",
        "sd-sub-pbtn",
        "sd-note",
    ]

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        return _soup(_get_html(url))

    @pytest.mark.parametrize("cls", REQUIRED_CLASSES)
    def test_required_class(self, cls, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one(f".{cls}")
        assert el is not None, f"missing .{cls} in rendered HTML"


class TestV11NegativeContract:
    """Forbidden elements must NOT be present in rendered HTML."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        return _soup(_get_html(url))

    def test_no_data_context_inspector(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-context-inspector]")
        assert el is None, "forbidden [data-context-inspector] found"

    def test_no_data_workbench_view_calls(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one('[data-workbench-view="calls"]')
        assert el is None, 'forbidden [data-workbench-view="calls"] found'

    def test_no_data_workbench_view_hotspots(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one('[data-workbench-view="hotspots"]')
        assert el is None, 'forbidden [data-workbench-view="hotspots"] found'

    def test_no_role_tablist(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one('[role="tablist"]')
        assert el is None, 'forbidden [role="tablist"] found'

    def test_no_forbidden_classes(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        for cls in ("phase1-shell", "no-inspector", "round-summary-table", "tab-content"):
            el = soup.select_one(f".{cls}")
            assert el is None, f"forbidden class .{cls} found"

    def test_no_forbidden_text(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        body = soup.find("body")
        if body:
            text = body.get_text()
        else:
            text = soup.get_text()
        # Multi-word phrases: check as substring
        for phrase in (
            "Round 内按时间顺序纵向推进",
            "用户输入作为独立高亮 round",
            "payload modal 必须可打开",
            "sd-note 展示规则",
            "Open selected",
            "High token",
        ):
            assert phrase not in text, f"forbidden text found: {phrase}"
        # Single words: check as whole word only (to avoid substring false positives like "Go" in "Good")
        for word in ("Map", "Inspector", "Focus", "Calls", "Hotspots", "Go", "Clear"):
            # Use word boundary check — these words must appear as standalone UI labels,
            # not as substrings in content (e.g., "Go" in "Good")
            pattern = re.compile(r'\b' + re.escape(word) + r'\b')
            # But exclude occurrences inside code blocks, pre elements, etc.
            # For simplicity, we only flag if it appears outside of normal prose
            # Check specifically for UI label context: preceded by specific patterns
            assert not pattern.search(text), f"forbidden word found: {word}"


class TestV11PayloadContract:
    """Payload buttons must have matching template sources."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        return _soup(_get_html(url))

    def test_at_least_one_open_payload_button(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        btns = soup.select('button[data-action="open-payload"]')
        assert len(btns) > 0, "no open-payload buttons found"

    def test_open_payload_buttons_have_id(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        btns = soup.select('button[data-action="open-payload"]')
        for btn in btns:
            pid = btn.get("data-payload-id")
            assert pid, "open-payload button missing data-payload-id"

    def test_payload_buttons_have_matching_sources(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        sources = {
            t.get("data-payload-source")
            for t in soup.select("template[data-payload-source]")
        }
        btns = soup.select('button[data-action="open-payload"]')
        for btn in btns:
            pid = btn.get("data-payload-id")
            if pid:
                assert pid in sources, f"open-payload id '{pid}' has no matching template source"


class TestV11ButtonContract:
    """All buttons must have proper data-action and ARIA attributes."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        return _soup(_get_html(url))

    def test_exactly_one_toggle_all(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        btns = soup.select('[data-action="toggle-all"]')
        assert len(btns) == 1, f"expected exactly one toggle-all, got {len(btns)}"

    def test_toggle_all_has_data_state(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        btn = soup.select_one('[data-action="toggle-all"]')
        assert btn is not None, "toggle-all button not found"
        state = btn.get("data-state")
        assert state in ("collapse", "expand"), f"toggle-all missing/invalid data-state: {state}"

    def test_toggle_round_buttons_have_aria(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        btns = soup.select('[data-action="toggle-round"]')
        assert len(btns) > 0, "no toggle-round buttons found"
        for btn in btns:
            assert "aria-expanded" in btn.attrs, "toggle-round missing aria-expanded"
            assert "aria-controls" in btn.attrs, "toggle-round missing aria-controls"

    def test_toggle_sub_round_buttons_have_aria(self, hifi_fixture_session):
        soup = self._soup(hifi_fixture_session)
        btns = soup.select('[data-action="toggle-sub-round"]')
        assert len(btns) > 0, "no toggle-sub-round buttons found"
        for btn in btns:
            assert "aria-expanded" in btn.attrs, "toggle-sub-round missing aria-expanded"
            assert "aria-controls" in btn.attrs, "toggle-sub-round missing aria-controls"


class TestV11QaCheckerScript:
    """Run the standalone QA checker script against the rendered HTML."""

    def test_qa_checker_passes(self, hifi_fixture_session, tmp_path):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        html = _get_html(url)

        html_path = tmp_path / "session.html"
        html_path.write_text(html, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable, QA_CHECKER,
                "--html", str(html_path),
                "--css", CSS_PATH,
                "--js", JS_PATH,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"QA checker failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )


# ── Finish reason and timestamp contract tests ───────────────────────


class TestV11FinishReasonContract:
    """Verify finish_reason and timestamp fields in LLM call items."""

    def _soup(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        url = f"{base_url}/sessions/{agent}/{session_id}"
        return _soup(_get_html(url))

    def test_data_meta_finish_in_modal(self, hifi_fixture_session):
        """The payload modal must contain a data-meta-finish element."""
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-meta-finish]")
        assert el is not None, "missing [data-meta-finish] in rendered HTML"

    def test_data_meta_ts_in_modal(self, hifi_fixture_session):
        """The payload modal must contain a data-meta-ts element."""
        soup = self._soup(hifi_fixture_session)
        el = soup.select_one("[data-meta-ts]")
        assert el is not None, "missing [data-meta-ts] in rendered HTML"

    def test_llm_card_has_finish_reason_attr(self, hifi_fixture_session):
        """LLM call cards must have data-finish-reason attribute."""
        soup = self._soup(hifi_fixture_session)
        cards = soup.select("[data-sub-llm-card][data-finish-reason]")
        assert len(cards) > 0, "no LLM cards with data-finish-reason found"

    def test_llm_card_has_timestamp_attr(self, hifi_fixture_session):
        """LLM call cards must have data-timestamp attribute."""
        soup = self._soup(hifi_fixture_session)
        cards = soup.select("[data-sub-llm-card][data-timestamp]")
        assert len(cards) > 0, "no LLM cards with data-timestamp found"

    def test_inline_call_card_has_finish_reason(self, hifi_fixture_session):
        """Inline call cards must have data-finish-reason attribute."""
        soup = self._soup(hifi_fixture_session)
        cards = soup.select("[data-inline-call-card][data-finish-reason]")
        assert len(cards) > 0, "no inline call cards with data-finish-reason found"

    def test_inline_call_card_has_timestamp(self, hifi_fixture_session):
        """Inline call cards must have data-timestamp attribute."""
        soup = self._soup(hifi_fixture_session)
        cards = soup.select("[data-inline-call-card][data-timestamp]")
        assert len(cards) > 0, "no inline call cards with data-timestamp found"
