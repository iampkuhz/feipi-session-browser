"""Claude Code attribution builder.

Claude Code provides the richest signal set: provider usage with
fresh/cache_read/cache_write split, transcript messages, tool results,
and content blocks.

This module is a re-export facade. The implementation lives in
``claude_code_parts/`` submodules.
"""

from __future__ import annotations

# ── Re-exports from claude_code_parts (backward compatible) ─────────────

from session_browser.attribution.agents.claude_code_parts.builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.claude_code_parts.normalizer import (
    normalize_request_reconstruction_buckets,
    _scale_bucket_and_details,
    _zero_bucket_preserve_floor,
)
from session_browser.attribution.agents.claude_code_parts.utils import (
    _pct,
    extract_tool_name,
    mask_sensitive_keys,
    tool_description,
    truncate_preview,
)
from session_browser.attribution.agents.claude_code_parts.constants import (
    MEASURED_BUCKET_KEYS,
    ESTIMATED_BUCKET_KEYS,
    HEURISTIC_FIXED_KEYS,
    HEURISTIC_SCALED_KEYS,
    NORMALIZATION_NOTE,
    TOOL_DESCRIPTIONS,
)

# ── Legacy aliases for backward compatibility ────────────────────────
# These match the original private function names used by external code
# (e.g. routes.py imports _mask_sensitive_keys).

_mask_sensitive_keys = mask_sensitive_keys
_truncate_preview = truncate_preview
_extract_tool_name = extract_tool_name
_tool_description = tool_description

# ── Bucket key aliases (original names for internal use) ─────────────
_MEASURED_BUCKET_KEYS = MEASURED_BUCKET_KEYS
_ESTIMATED_BUCKET_KEYS = ESTIMATED_BUCKET_KEYS
_HEURISTIC_FIXED_KEYS = HEURISTIC_FIXED_KEYS
_HEURISTIC_SCALED_KEYS = HEURISTIC_SCALED_KEYS

__all__ = [
    "ClaudeCodeAttributionBuilder",
    "normalize_request_reconstruction_buckets",
    "_mask_sensitive_keys",
    "_truncate_preview",
    "_extract_tool_name",
    "_tool_description",
    "_pct",
    "_scale_bucket_and_details",
    "_zero_bucket_preserve_floor",
]
