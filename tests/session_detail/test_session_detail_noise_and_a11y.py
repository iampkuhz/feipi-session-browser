"""Tests for trace/issue noise reduction and accessibility.

Architecture:
- Issue strip in hero macro (capped at 4 issues)
- Round toggles use data-action="toggle-round" with aria-expanded/aria-controls
- Payload modal in base.html with tabs and close button
- Filter buttons in trace header (All/Failed segmented control)
- Raw JSON in <script type="application/json"> tag
"""

import pytest

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"
BASE_TEMPLATE = TEMPLATE_DIR / "base.html"
SESSION_TEMPLATE = TEMPLATE_DIR / "session.html"
COMPONENTS = TEMPLATE_DIR / "components"
CSS_PATH = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "static" / "css" / "session-detail.css"
CSS_DIR = CSS_PATH.parent / "session-detail"
TIMELINE_FILE = COMPONENTS / "session_detail_timeline.html"
TIMELINE_DIR = COMPONENTS / "session_detail_timeline"


def _read_source_with_splits(main_file, split_dir, ext="*.css"):
    """Read main file and all split subdirectory files (if they exist)."""
    parts = []
    if main_file.exists():
        parts.append(main_file.read_text(encoding="utf-8"))
    if split_dir.is_dir():
        for f in sorted(split_dir.glob(ext)):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _read_css():
    return _read_source_with_splits(CSS_PATH, CSS_DIR, "*.css")


def _session_source():
    return SESSION_TEMPLATE.read_text(encoding="utf-8")


def _base_source():
    return BASE_TEMPLATE.read_text(encoding="utf-8")


def _timeline_component():
    return _read_source_with_splits(TIMELINE_FILE, TIMELINE_DIR, "*.html")


# ── 问题条 ──────────────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-029")
def test_issue_strip_exists():
    """Template must contain an issue strip via sdt.hero."""
    timeline = _timeline_component()
    assert "data-issue-strip" in timeline, "Issue strip must exist"


@pytest.mark.contract_case("UI-SD-029")
def test_issue_cards_capped():
    """Issue cards must be capped (limited to 4)."""
    timeline = _timeline_component()
    assert "[:4]" in timeline, "Issue cards must be capped"


# ── 轮次切换可访问性 ──────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-029")
def test_round_toggle_has_aria_expanded():
    """Round toggle button must have aria-expanded."""
    timeline = _timeline_component()
    assert "aria-expanded" in timeline, "Round toggle must have aria-expanded"


@pytest.mark.contract_case("UI-SD-029")
def test_round_toggle_has_aria_controls():
    """Round toggle button must have aria-controls."""
    timeline = _timeline_component()
    assert "aria-controls" in timeline, "Round toggle must have aria-controls"


# ── Modal accessibility ─────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-029")
def test_modal_close_has_aria_label():
    """Modal close button must have aria-label."""
    source = _base_source()
    pattern = re.compile(
        r'class="payload-modal__close"[^>]*aria-label="[^"]*"'
    )
    matches = pattern.findall(source)
    assert len(matches) > 0, "Modal close button must have aria-label"


@pytest.mark.contract_case("UI-SD-029")
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


@pytest.mark.contract_case("UI-SD-029")
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


@pytest.mark.contract_case("UI-SD-029")
def test_no_visible_raw_json_pre():
    """Must not have a visible <pre id=\"raw-json\"> in normal page flow."""
    source = _session_source()
    pre_pattern = re.compile(r'<pre\s+id="raw-json"')
    pre_matches = pre_pattern.findall(source)
    assert len(pre_matches) == 0, (
        f"Found visible <pre id=\"raw-json\"> in template: {pre_matches}"
    )


@pytest.mark.contract_case("UI-SD-029")
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


@pytest.mark.contract_case("UI-SD-029")
def test_filter_buttons_exist():
    """Filter status chips must exist."""
    timeline = _timeline_component()
    # 使用 status-all / status-failed actions（HIFI 表格迁移）
    chips_all = re.findall(
        r'<button[^>]*data-action="status-all"[^>]*>',
        timeline
    )
    chips_failed = re.findall(
        r'<button[^>]*data-action="status-failed"[^>]*>',
        timeline
    )
    assert len(chips_all) > 0 or len(chips_failed) > 0, "Filter status chips must exist"
    # Also accept legacy filter-status pattern
    chips_legacy = re.findall(
        r'<button[^>]*data-action="filter-status"[^>]*>',
        timeline
    )
    if len(chips_all) == 0 and len(chips_failed) == 0:
        assert len(chips_legacy) > 0, "Filter status chips must exist (legacy pattern)"


# ── Payload tabs accessibility ──────────────────────────────────────


@pytest.mark.contract_case("UI-SD-029")
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


# ── CSS for session detail features ─────────────────────────────────


@pytest.mark.contract_case("UI-SD-029")
def test_css_has_issue_strip_styles():
    """CSS must define issue strip styles."""
    css = _read_css()
    assert "sd-issue-strip" in css or "sd-issue-link" in css, (
        "CSS must include issue strip styles"
    )


@pytest.mark.contract_case("UI-SD-029")
def test_css_has_aria_styles():
    """CSS must have aria-related styles for interactive states."""
    css = _read_css()
    assert "aria-" in css or "is-active" in css or "is-open" in css, (
        "CSS must include interactive state styles"
    )
