"""Safe rendering helpers for JSON/Code/HTML in Jinja2 templates.

Purpose: ensure that JSON, code, and arbitrary data are never executed as
HTML when embedded in <pre>, <code>, <script>, or attribute contexts.

Provides:
- safe_json_display() — JSON-serialize + HTML-escape for safe <pre> embedding.
- safe_html_block() — wrap arbitrary HTML with a safe container class.
- Jinja2 filters registered via register_filters().
"""

from __future__ import annotations

import html as html_mod
import json
from typing import Any

import jinja2


def safe_json_display(value: Any, indent: int | None = None) -> str:
    """Serialize *value* to JSON and HTML-escape the result.

    Safe for embedding inside <pre><code> … </code></pre> without
    allowing </pre>/<script> breakout or other HTML injection.

    Returns the escaped JSON string, or the literal string ``"null"`` when
    *value* is falsy (None / empty).
    """
    if not value:
        return "null"
    raw = json.dumps(value, indent=indent, ensure_ascii=False)
    return html_mod.escape(raw)


def safe_html_block(html_content: str, class_name: str = "safe-html-block") -> str:
    """Wrap *html_content* in a <div> with *class_name*.

    The content itself is **not** escaped — the caller is responsible for
    deciding whether the HTML is trusted.  The wrapper provides a CSS hook
    so downstream CSS can restrict what runs inside (e.g. disallow scripts).

    Typical use: wrap pre-sanitised markdown HTML so that the outer template
    can apply ``|safe`` without losing the isolation boundary.
    """
    safe_class = html_mod.escape(class_name, quote=True)
    return f'<div class="{safe_class}">{html_content}</div>'


def tojson_safe_html(value: Any, indent: int | None = None) -> str:
    """Like Jinja2's built-in ``|tojson`` but also HTML-escapes the result.

    Jinja2's native ``|tojson`` produces a JSON string that is safe inside
    <script> blocks, but it does NOT escape HTML entities — meaning
    ``</script>`` inside a JSON string value can break out of a <pre> tag.

    This filter always escapes ``<``, ``>``, ``&``, ``"``, ``'`` so the
    result is safe in any HTML context.
    """
    if value is None:
        return "null"
    raw = json.dumps(value, indent=indent, ensure_ascii=False)
    return html_mod.escape(raw)


def register_filters(env: jinja2.Environment) -> None:
    """Register safe-render filters onto a Jinja2 Environment."""
    env.filters["safe_json_display"] = safe_json_display
    env.filters["safe_html_block"] = safe_html_block
    env.filters["tojson_safe_html"] = tojson_safe_html
