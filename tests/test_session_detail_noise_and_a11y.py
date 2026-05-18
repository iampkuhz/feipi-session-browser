"""Tests for trace/issue noise reduction and accessibility.

Verifies that:
1. Issue cards default count <= 8 unless expanded.
2. Generic Payload button count <= 3.
3. Modal has accessible close button.
4. Round toggles have aria-expanded/aria-controls.
5. No visible raw-json pre in normal page flow.
6. Toolbar filter buttons have active state markers (aria-pressed).
7. Payload tabs have role=tab and aria-selected.
8. Dialog has accessible title (aria-labelledby).
9. Issue aggregation summary exists.
10. Expand button text is 'Expand visible' not 'Expand All'.
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"
BASE_TEMPLATE = TEMPLATE_DIR / "base.html"
SESSION_TEMPLATE = TEMPLATE_DIR / "session.html"
CSS_PATH = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "style.css"


def _session_source():
    return SESSION_TEMPLATE.read_text(encoding="utf-8")


def _base_source():
    return BASE_TEMPLATE.read_text(encoding="utf-8")


# ── Issue aggregation ──────────────────────────────────────────────


def test_issue_aggregate_section_exists():
    """Template must contain an issue aggregation section."""
    source = _session_source()
    assert 'data-issue-aggregate' in source or 'issue-summary__aggregate' in source, (
        "Issue summary must have an aggregation section"
    )


def test_issue_cards_capped_at_8():
    """Detailed issue cards must be capped at 8 (ISSUE_MAX_DEFAULT)."""
    source = _session_source()
    # The template must use ISSUE_MAX_DEFAULT or a slice [:8] for failed_rounds
    assert 'ISSUE_MAX_DEFAULT' in source or '[:8]' in source or '[: ISSUE_MAX_DEFAULT]' in source, (
        "Issue cards must be capped at a maximum default count"
    )


def test_issue_expand_button_exists():
    """Template must have a 'Show affected rounds' expand button when there are >8 issues."""
    source = _session_source()
    assert 'toggle-issue-expand' in source, (
        "Issue expand toggle action must exist"
    )
    assert 'Show affected rounds' in source, (
        "Expand button must say 'Show affected rounds'"
    )


def test_issue_expand_has_aria_expanded():
    """Issue expand button must have aria-expanded attribute."""
    source = _session_source()
    # The button should set aria-expanded="false" initially
    assert 'aria-expanded="false"' in source or "aria-expanded='false'" in source, (
        "Issue expand button must have aria-expanded"
    )


def test_hidden_cards_container_exists():
    """Extra issue cards beyond the cap must be in a hidden container."""
    source = _session_source()
    assert 'data-issue-cards-hidden' in source or 'issue-summary__cards--hidden' in source, (
        "Hidden issue cards container must exist"
    )


# ── Generic Payload button count ─────────────────────────────────────


def test_generic_payload_button_count_low():
    """Generic 'Payload' button text count must be <= 3."""
    source = _session_source()
    payload_buttons = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>\s*Payload\s*</button>',
        source
    )
    assert len(payload_buttons) <= 3, (
        f"Generic 'Payload' button count must be <= 3, found {len(payload_buttons)}"
    )


def test_no_massive_payload_buttons():
    """Must not have 400+ generic 'Payload' buttons."""
    source = _session_source()
    payload_buttons = re.findall(
        r'<button[^>]*data-action="open-payload"[^>]*>\s*Payload\s*</button>',
        source
    )
    assert len(payload_buttons) < 400, (
        f"Must not have 400+ generic 'Payload' buttons, found {len(payload_buttons)}"
    )


# ── Modal accessibility ─────────────────────────────────────────────


def test_modal_close_has_aria_label():
    """Modal close button must have aria-label."""
    source = _base_source()
    pattern = re.compile(
        r'class="payload-modal__close"[^>]*aria-label="[^"]*"'
    )
    matches = pattern.findall(source)
    assert len(matches) > 0, (
        "Modal close button must have aria-label"
    )


def test_dialog_has_aria_labelledby():
    """Dialog must have aria-labelledby pointing to title element."""
    source = _base_source()
    assert 'aria-labelledby=' in source, (
        "Dialog must have aria-labelledby"
    )
    # The id referenced by aria-labelledby must exist
    labelledby_match = re.search(r'aria-labelledby="([^"]+)"', source)
    assert labelledby_match, "aria-labelledby must have a value"
    title_id = labelledby_match.group(1)
    assert f'id="{title_id}"' in source or f"id='{title_id}'" in source, (
        f"Title element with id='{title_id}' must exist"
    )


def test_modal_title_has_id():
    """Modal title span must have an id for aria-labelledby."""
    source = _base_source()
    pattern = re.compile(
        r'class="payload-modal__title"[^>]*id="[^"]*"'
    )
    if not pattern.search(source):
        pattern2 = re.compile(
            r'id="[^"]*"[^>]*class="payload-modal__title"'
        )
        assert pattern2.search(source), (
            "Modal title must have an id attribute"
        )


# ── Round toggle accessibility ──────────────────────────────────────


def test_round_toggle_has_aria_expanded():
    """Round toggle button must have aria-expanded."""
    source = _session_source()
    pattern = re.compile(
        r'class="trace-round-toggle"[^>]*aria-expanded="[^"]*"'
    )
    if not pattern.search(source):
        pattern2 = re.compile(
            r'aria-expanded="[^"]*"[^>]*class="trace-round-toggle"'
        )
        assert pattern2.search(source), (
            "Round toggle must have aria-expanded"
        )
    else:
        assert True


def test_round_toggle_has_aria_controls():
    """Round toggle button must have aria-controls."""
    source = _session_source()
    pattern = re.compile(
        r'class="trace-round-toggle"[^>]*aria-controls="[^"]*"'
    )
    if not pattern.search(source):
        pattern2 = re.compile(
            r'aria-controls="[^"]*"[^>]*class="trace-round-toggle"'
        )
        assert pattern2.search(source), (
            "Round toggle must have aria-controls"
        )
    else:
        assert True


# ── No visible raw-json pre ─────────────────────────────────────────


def test_no_visible_raw_json_pre():
    """Must not have a visible <pre id=\"raw-json\"> in normal page flow."""
    source = _session_source()
    # Should NOT have <pre id="raw-json"> without a proper hidden mechanism
    # Script tag is OK; visible pre is not
    pre_pattern = re.compile(r'<pre\s+id="raw-json"')
    pre_matches = pre_pattern.findall(source)
    assert len(pre_matches) == 0, (
        f"Found visible <pre id=\"raw-json\"> in template: {pre_matches}"
    )


def test_raw_json_moved_to_script_tag():
    """Raw JSON data must be in a <script type=\"application/json\"> tag."""
    source = _session_source()
    script_pattern = re.compile(
        r'<script\s+type="application/json"\s+id="raw-json"'
    )
    if not script_pattern.search(source):
        script_pattern2 = re.compile(
            r'<script\s+id="raw-json"\s+type="application/json"'
        )
        assert script_pattern2.search(source), (
            "Raw JSON must be in <script type=\"application/json\" id=\"raw-json\">"
        )
    else:
        assert True


# ── Toolbar filter buttons ──────────────────────────────────────────


def test_filter_buttons_have_aria_pressed():
    """Filter buttons must have aria-pressed attribute."""
    source = _session_source()
    chips = re.findall(
        r'<button[^>]*data-action="filter-status"[^>]*>',
        source
    )
    assert len(chips) > 0, "Filter status chips must exist"
    for chip in chips:
        assert 'aria-pressed=' in chip, (
            f"Filter chip must have aria-pressed: {chip[:120]}"
        )


def test_filter_active_button_has_aria_pressed_true():
    """The active filter button must have aria-pressed=\"true\"."""
    source = _session_source()
    # The 'All' button is active by default
    pattern = re.compile(
        r'data-status="all"[^>]*aria-pressed="true"'
    )
    if not pattern.search(source):
        pattern2 = re.compile(
            r'aria-pressed="true"[^>]*data-status="all"'
        )
        assert pattern2.search(source), (
            "Active filter button must have aria-pressed=\"true\""
        )
    else:
        assert True


def test_filter_inactive_button_has_aria_pressed_false():
    """Inactive filter buttons must have aria-pressed=\"false\"."""
    source = _session_source()
    pattern = re.compile(
        r'data-status="failed"[^>]*aria-pressed="false"'
    )
    if not pattern.search(source):
        pattern2 = re.compile(
            r'aria-pressed="false"[^>]*data-status="failed"'
        )
        assert pattern2.search(source), (
            "Inactive filter button must have aria-pressed=\"false\""
        )
    else:
        assert True


# ── Expand visible not Expand All ───────────────────────────────────


def test_expand_visible_not_expand_all():
    """Toolbar must have 'Expand visible' button, not 'Expand All'."""
    source = _session_source()
    # The button text should be 'Expand visible'
    assert 'Expand visible' in source, (
        "Toolbar must have 'Expand visible' button text"
    )
    # Should not have standalone "Expand All" button text
    # (old expand-all data-action is OK for backward compat, but visible text must be new)
    expand_all_btn = re.search(
        r'data-action="expand-all"[^>]*>[^<]*Expand All<',
        source
    )
    assert expand_all_btn is None, (
        "Must not have 'Expand All' button text; use 'Expand visible'"
    )


# ── Payload tabs accessibility ──────────────────────────────────────


def test_payload_tabs_have_role_tab():
    """Payload modal tabs must have role=\"tab\"."""
    source = _base_source()
    tabs = re.findall(
        r'<button[^>]*data-action="payload-mode"[^>]*>',
        source
    )
    assert len(tabs) > 0, "Payload mode tabs must exist"
    for tab in tabs:
        assert 'role="tab"' in tab, (
            f"Payload tab must have role=\"tab\": {tab[:120]}"
        )


def test_payload_tabs_have_aria_selected():
    """Payload modal tabs must have aria-selected."""
    source = _base_source()
    tabs = re.findall(
        r'<button[^>]*data-action="payload-mode"[^>]*>',
        source
    )
    for tab in tabs:
        assert 'aria-selected=' in tab, (
            f"Payload tab must have aria-selected: {tab[:120]}"
        )


def test_payload_tablist_has_role():
    """Payload modal tab container must have role=\"tablist\"."""
    source = _base_source()
    assert 'role="tablist"' in source, (
        "Tab container must have role=\"tablist\""
    )


# ── JS handlers ─────────────────────────────────────────────────────


def test_js_handles_expand_visible():
    """JS must handle expand-visible action."""
    source = _session_source()
    assert "expand-visible" in source, (
        "JS must handle 'expand-visible' action"
    )


def test_js_toggles_aria_pressed_on_filter():
    """JS must set aria-pressed on filter buttons."""
    source = _session_source()
    assert "aria-pressed" in source, (
        "JS must manage aria-pressed on filter buttons"
    )


def test_js_toggles_aria_selected_on_tabs():
    """JS must set aria-selected on payload tabs."""
    source = _session_source()
    assert "aria-selected" in source, (
        "JS must manage aria-selected on payload tabs"
    )


def test_js_handles_issue_expand():
    """JS must handle toggle-issue-expand action."""
    source = _session_source()
    assert "toggle-issue-expand" in source, (
        "JS must handle 'toggle-issue-expand' action"
    )


# ── CSS for new features ────────────────────────────────────────────


def test_css_has_issue_aggregate_styles():
    """CSS must define issue aggregation styles."""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "issue-summary__aggregate" in css, (
        "CSS must include .issue-summary__aggregate styles"
    )


def test_css_has_expand_button_styles():
    """CSS must define issue expand button styles."""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "issue-summary__expand-btn" in css, (
        "CSS must include .issue-summary__expand-btn styles"
    )


def test_css_has_aria_pressed_selector():
    """CSS must style aria-pressed state on filter chips."""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "aria-pressed" in css, (
        "CSS must include [aria-pressed] styles for filter state visibility"
    )


def test_css_has_payload_unavailable_styles():
    """CSS must define payload-unavailable styles."""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "llm-call-card__payload-unavailable" in css, (
        "CSS must include .llm-call-card__payload-unavailable styles"
    )
