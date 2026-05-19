"""Tests for trace/issue noise reduction and accessibility (v9).

v9 architecture:
- Issue strip in hero macro (capped at 4 issues)
- Round toggles use data-action="toggle-round" with aria-expanded/aria-controls
- Payload modal in base.html with tabs and close button
- Filter buttons in trace header (All/Failed segmented control)
- Raw JSON in <script type="application/json"> tag
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "templates"
BASE_TEMPLATE = TEMPLATE_DIR / "base.html"
SESSION_TEMPLATE = TEMPLATE_DIR / "session.html"
COMPONENTS = TEMPLATE_DIR / "components"
CSS_PATH = Path(__file__).parent.parent / "src" / "session_browser" / "web" / "static" / "css" / "session-detail-timeline.css"


def _session_source():
    return SESSION_TEMPLATE.read_text(encoding="utf-8")


def _base_source():
    return BASE_TEMPLATE.read_text(encoding="utf-8")


def _timeline_component():
    return (COMPONENTS / "session_detail_timeline.html").read_text(encoding="utf-8")


# ── Issue strip ──────────────────────────────────────────────────────


def test_issue_strip_exists():
    """Template must contain an issue strip via sdt.hero."""
    timeline = _timeline_component()
    assert "data-issue-strip" in timeline, "Issue strip must exist"


def test_issue_cards_capped():
    """Issue cards must be capped (v9 uses [:4])."""
    timeline = _timeline_component()
    assert "[:4]" in timeline, "Issue cards must be capped"


# ── Round toggle accessibility ──────────────────────────────────────


def test_round_toggle_has_aria_expanded():
    """Round toggle button must have aria-expanded."""
    timeline = _timeline_component()
    assert "aria-expanded" in timeline, "Round toggle must have aria-expanded"


def test_round_toggle_has_aria_controls():
    """Round toggle button must have aria-controls."""
    timeline = _timeline_component()
    assert "aria-controls" in timeline, "Round toggle must have aria-controls"


# ── Modal accessibility ─────────────────────────────────────────────


def test_modal_close_has_aria_label():
    """Modal close button must have aria-label."""
    source = _base_source()
    pattern = re.compile(
        r'class="payload-modal__close"[^>]*aria-label="[^"]*"'
    )
    matches = pattern.findall(source)
    assert len(matches) > 0, "Modal close button must have aria-label"


def test_dialog_has_aria_labelledby():
    """Dialog must have aria-labelledby pointing to title element."""
    source = _base_source()
    assert 'aria-labelledby=' in source, "Dialog must have aria-labelledby"
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


# ── No visible raw-json pre ─────────────────────────────────────────


def test_no_visible_raw_json_pre():
    """Must not have a visible <pre id=\"raw-json\"> in normal page flow."""
    source = _session_source()
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


# ── Filter buttons ──────────────────────────────────────────────────


def test_filter_buttons_exist():
    """Filter status chips must exist."""
    timeline = _timeline_component()
    chips = re.findall(
        r'<button[^>]*data-action="filter-status"[^>]*>',
        timeline
    )
    assert len(chips) > 0, "Filter status chips must exist"


# ── Payload tabs accessibility ──────────────────────────────────────


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


# ── CSS for v9 features ────────────────────────────────────────────


def test_css_has_issue_strip_styles():
    """CSS must define issue strip styles."""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "sd-issue-strip" in css or "sd-issue-link" in css, (
        "CSS must include issue strip styles"
    )


def test_css_has_aria_styles():
    """CSS must have aria-related styles for interactive states."""
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "aria-" in css or "is-active" in css or "is-open" in css, (
        "CSS must include interactive state styles"
    )
