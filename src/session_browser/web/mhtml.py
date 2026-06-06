"""MHTML/self-contained rendering helper.

Provides cached access to CSS and JS files for inlining into HTML output.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Ordered list of JS files that must be inlined for a self-contained session page.
# Order matches base.html load order.
JS_LOAD_ORDER = [
    "js/arp-storage.js",
    "js/view-state.js",
    "js/payload_viewer.js",
    "js/app.js",
    "js/data-table.js",
    "js/timeline.js",
    "js/keyboard.js",
    "js/view-switching.js",
]


# Ordered list of CSS files that must be inlined for a self-contained page.
# Order matches base.html <link> load order.
CSS_LOAD_ORDER = [
    "css/tokens.css",
    "css/base.css",
    "css/shell.css",
    "css/ui-primitives.css",
]

# Page-specific CSS files keyed by page identifier used in routes.
# These are appended after the shared CSS_LOAD_ORDER layers.
PAGE_CSS = {
    "session": "css/session-detail.css",
}

_IMPORT_RE = re.compile(
    r'^\s*@import\s+(?:url\(\s*)?["\']?([^"\')\s;]+)["\']?\s*\)?\s*;',
    re.MULTILINE,
)


def _read_css_bundle(rel: str, seen: set[Path] | None = None) -> str:
    """Read a CSS file and inline its local @import dependencies.

    MHTML export places multiple CSS files into one <style> block. Plain
    @import wrappers are valid as standalone linked files, but invalid after
    earlier style rules once concatenated. Expanding imports here keeps the
    browser-loading structure unchanged while making exported CSS compilable.
    """
    seen = seen or set()
    css_path = _STATIC_DIR / rel
    if not css_path.exists():
        return f"/* {rel} not found */\n"

    css_path = css_path.resolve()
    if css_path in seen:
        return f"/* skipped circular CSS import: {rel} */\n"
    seen.add(css_path)

    text = css_path.read_text(encoding="utf-8")

    def replace_import(match: re.Match[str]) -> str:
        import_ref = match.group(1)
        import_path = (_STATIC_DIR / rel).parent / import_ref
        try:
            import_rel = import_path.resolve().relative_to(_STATIC_DIR.resolve()).as_posix()
        except ValueError:
            return f"/* skipped external CSS import: {import_ref} */"
        return _read_css_bundle(import_rel, seen)

    return _IMPORT_RE.sub(replace_import, text)


@lru_cache(maxsize=1)
def get_css() -> str:
    """Read and bundle all modular CSS files in base.html load order."""
    parts = []
    for rel in CSS_LOAD_ORDER:
        parts.append(f"/* === {rel} === */\n")
        parts.append(_read_css_bundle(rel))
    return "\n\n".join(parts)


def get_page_css(page: str) -> str:
    """Return inline CSS for a specific page, or empty string if none."""
    rel = PAGE_CSS.get(page)
    if not rel:
        return ""
    return f"/* === {rel} === */\n{_read_css_bundle(rel)}"


@lru_cache(maxsize=1)
def get_js() -> str:
    """Read and merge all JS files in base.html load order."""
    parts = []
    for rel in JS_LOAD_ORDER:
        js_path = _STATIC_DIR / rel
        if js_path.exists():
            parts.append(f"/* === {rel} === */\n")
            parts.append(js_path.read_text(encoding="utf-8"))
        else:
            parts.append(f"/* {rel} not found */\n")
    return "\n\n".join(parts)


def get_context(page: str = "session", export_mhtml: bool = True) -> dict:
    """Return template context vars for MHTML rendering."""
    if not export_mhtml:
        return {}
    return {
        "export_mhtml": True,
        "mhtml_css": get_css(),
        "mhtml_page_css": get_page_css(page),
        "mhtml_js": get_js(),
    }
