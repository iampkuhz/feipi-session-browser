"""claude_code_parts — extracted submodules of claude_code.py.

The top-level `claude_code.py` remains the canonical import path.
This package provides the internal module split for maintainability.
"""

from session_browser.attribution.agents.claude_code_parts.constants import (
    MEASURED_BUCKET_KEYS,
    ESTIMATED_BUCKET_KEYS,
    HEURISTIC_FIXED_KEYS,
    HEURISTIC_SCALED_KEYS,
    NORMALIZATION_NOTE,
    TOOL_DESCRIPTIONS,
)
from session_browser.attribution.agents.claude_code_parts.utils import (
    _pct,
    extract_tool_name,
    mask_sensitive_keys,
    tool_description,
    truncate_preview,
)
from session_browser.attribution.agents.claude_code_parts.normalizer import (
    _scale_bucket_and_details,
    _zero_bucket_preserve_floor,
    normalize_request_reconstruction_buckets,
)
from session_browser.attribution.agents.claude_code_parts.builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.claude_code_parts.request_builder import (
    build_request,
)
from session_browser.attribution.agents.claude_code_parts.response_builder import (
    build_response,
)

__all__ = [
    # Builder
    "ClaudeCodeAttributionBuilder",
    # Standalone builder functions
    "build_request",
    "build_response",
    # Normalization
    "normalize_request_reconstruction_buckets",
    "_scale_bucket_and_details",
    "_zero_bucket_preserve_floor",
    # Utils
    "_pct",
    "mask_sensitive_keys",
    "truncate_preview",
    "extract_tool_name",
    "tool_description",
    # Constants
    "MEASURED_BUCKET_KEYS",
    "ESTIMATED_BUCKET_KEYS",
    "HEURISTIC_FIXED_KEYS",
    "HEURISTIC_SCALED_KEYS",
    "NORMALIZATION_NOTE",
    "TOOL_DESCRIPTIONS",
]
