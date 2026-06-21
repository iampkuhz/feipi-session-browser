"""Feipi Session Browser 的 Markdown renderer..

Provides a shared MarkdownIt instance and a Jinja2-compatible filter
that renders markdown to HTML with XSS-safe escaping.
"""

from __future__ import annotations

import html

from markdown_it import MarkdownIt

# 说明:─── Shared MarkdownIt renderer ──────────────────────────────────────

_md = MarkdownIt().enable('table')


def render_markdown(text: str) -> str:
    """说明:Render markdown text to HTML.

    Escapes raw HTML in the input to prevent XSS attacks.
    Returns empty string for empty/None input.
    """
    if not text:
        return ''
    escaped = html.escape(text)
    return _md.render(escaped)
