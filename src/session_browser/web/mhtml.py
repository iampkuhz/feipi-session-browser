"""MHTML/self-contained rendering helper.

Provides cached access to CSS and JS files for inlining into HTML output.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Ordered list of JS files that must be inlined for a self-contained session page.
# Order matches base.html load order.
JS_LOAD_ORDER = [
    "js/inspector.js",
    "js/view-state.js",
    "js/payload_viewer.js",
    "js/app.js",
    "js/data-table.js",
    "js/timeline.js",
    "js/keyboard.js",
]


@lru_cache(maxsize=1)
def get_css() -> str:
    """Read and cache the main stylesheet."""
    css_path = _STATIC_DIR / "style.css"
    if not css_path.exists():
        return "/* style.css not found */"
    return css_path.read_text(encoding="utf-8")


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


def get_context(export_mhtml: bool = True) -> dict:
    """Return template context vars for MHTML rendering."""
    if not export_mhtml:
        return {}
    return {
        "export_mhtml": True,
        "mhtml_css": get_css(),
        "mhtml_js": get_js(),
    }
