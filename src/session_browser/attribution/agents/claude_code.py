"""Claude Code attribution builder.

Claude Code provides the richest signal set: provider usage with
fresh/cache_read/cache_write split, transcript messages, tool results,
and content blocks.

This module exposes the Claude Code builder API. The implementation lives in
``claude_code_parts/`` submodules.
"""

from __future__ import annotations

from session_browser.attribution.agents.claude_code_parts.builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.claude_code_parts.normalizer import (
    normalize_request_reconstruction_buckets,
)

__all__ = [
    "ClaudeCodeAttributionBuilder",
    "normalize_request_reconstruction_buckets",
]
