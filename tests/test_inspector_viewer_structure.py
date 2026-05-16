"""Tests for Inspector tab structure (Task 11: 3-tab simplified).

Ensures that the LLM Call Inspector has:
- 3 required tabs: Overview, Payload, Tools.
- insp-head / insp-body / insp-tabs structure.
- Empty state when no object selected.
- Safe HTML escaping for raw content.
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "src" / "session_browser" / "web"

_REQUIRED_TABS = [
    "Overview",
    "Payload",
    "Tools",
]


def _read_all_sources() -> dict[str, str]:
    result = {}
    for rel in [
        "templates/components/inspector.html",
        "templates/components/viewer.html",
        "templates/session.html",
        "static/js/inspector.js",
    ]:
        p = TEMPLATE_DIR / rel
        if p.exists():
            result[rel] = p.read_text(encoding="utf-8")
    return result


def _combined(sources: dict[str, str]) -> str:
    return "\n".join(sources.values())


# ── Required tabs ────────────────────────────────────────────────────

def test_all_three_tabs_exist():
    """All 3 required tab labels must be present."""
    sources = _read_all_sources()
    combined = _combined(sources)
    missing = [tab for tab in _REQUIRED_TABS if tab not in combined]
    assert not missing, f"Missing tab labels: {', '.join(missing)}"


# ── Hi-Fi structure ──────────────────────────────────────────────────

def test_insp_head_exists():
    """Inspector must have insp-head header area."""
    sources = _read_all_sources()
    html = sources.get("templates/components/inspector.html", "")
    assert "insp-head" in html, "Missing insp-head in inspector template"


def test_insp_close_exists():
    """Inspector must have a close button."""
    sources = _read_all_sources()
    html = sources.get("templates/components/inspector.html", "")
    assert "insp-close" in html, "Missing insp-close button"


def test_insp_title_exists():
    """Inspector must have insp-title element."""
    sources = _read_all_sources()
    html = sources.get("templates/components/inspector.html", "")
    assert "insp-title" in html, "Missing insp-title element"


def test_empty_state_exists():
    """Inspector must have an empty state for no selection."""
    sources = _read_all_sources()
    html = sources.get("templates/components/inspector.html", "")
    assert "insp-empty-state" in html or "No object selected" in html, (
        "Missing empty state in inspector template"
    )


# ── Tab switching ────────────────────────────────────────────────────

def test_switchTab_function_exists():
    """JS must provide Inspector.switchTab for tab switching."""
    sources = _read_all_sources()
    js = sources.get("static/js/inspector.js", "")
    assert "switchTab" in js, "Missing switchTab function in inspector.js"


def test_no_inspector_open_class():
    """JS should NOT reference inspector-open class (grid column now)."""
    sources = _read_all_sources()
    js = sources.get("static/js/inspector.js", "")
    assert "inspector-open" not in js, (
        "JS still references inspector-open class; should use hide-right instead"
    )


# ── Content escaping ─────────────────────────────────────────────────

def test_raw_content_html_escaping():
    """Raw content must be HTML-escaped in JS."""
    js_path = TEMPLATE_DIR / "static" / "js" / "inspector.js"
    if not js_path.exists():
        return
    js = js_path.read_text(encoding="utf-8")

    assert re.search(r"replace\s*\(\s*/&/g\s*,\s*['\"]&amp;['\"]", js), (
        "Missing & -> &amp; escaping in JS"
    )
    assert re.search(r"replace\s*\(\s*/</g\s*,\s*['\"]&lt;['\"]", js), (
        "Missing < -> &lt; escaping in JS"
    )
    assert re.search(r"/>/g\s*,\s*['\"]&gt;['\"]", js), (
        "Missing > -> &gt; escaping in JS"
    )


# ── CSS styles ───────────────────────────────────────────────────────

def test_insp_css_styles_exist():
    """CSS must define insp-* styles."""
    css_path = TEMPLATE_DIR / "static" / "style.css"
    if not css_path.exists():
        return
    css = css_path.read_text(encoding="utf-8")
    assert ".insp-tabs" in css, "Missing .insp-tabs CSS"
    assert ".insp-head" in css, "Missing .insp-head CSS"
    assert ".insp-title" in css, "Missing .insp-title CSS"


# ── Rendered/raw separation ─────────────────────────────────────────

def test_rendered_raw_separation():
    """Rendered and raw content must have separate containers."""
    sources = _read_all_sources()
    combined = _combined(sources)
    has_viewer = bool(re.search(
        r'(viewer__raw|viewer__raw-pre|viewer--raw)',
        combined,
    ))
    assert has_viewer, "No raw viewer container found"


# ── Grid column behavior ─────────────────────────────────────────────

def test_hide_right_hides_inspector():
    """CSS: body.hide-right should hide .inspector."""
    css_path = TEMPLATE_DIR / "static" / "style.css"
    if not css_path.exists():
        return
    css = css_path.read_text(encoding="utf-8")
    assert "hide-right" in css and ".inspector" in css, (
        "CSS should hide inspector via body.hide-right"
    )
