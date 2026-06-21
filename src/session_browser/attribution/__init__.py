"""LLM call attribution package.

Provides unified interfaces for token usage attribution across
Claude Code, Qoder, and Codex agents.
"""

from session_browser.attribution.contracts import (
    AttributedValue,
    LLMRequestAttribution,
    LLMResponseAttribution,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text

__all__ = [
    'AttributedValue',
    'LLMRequestAttribution',
    'LLMResponseAttribution',
    'RequestAttributionBucket',
    'ResponseAttributionBucket',
    'ValuePrecision',
    'ValueSource',
    'build_llm_request_attribution',
    'build_llm_response_attribution',
    'estimate_tokens_from_text',
]
