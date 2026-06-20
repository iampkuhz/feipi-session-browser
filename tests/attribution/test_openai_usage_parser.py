"""OpenAI usage parser token component semantics."""

from __future__ import annotations

from session_browser.attribution.api_families.openai_chat.normalizer import (
    normalize_openai_chat_usage,
)
from session_browser.attribution.api_families.openai_chat.usage_parser import (
    parse_openai_chat_usage,
)
from session_browser.attribution.api_families.openai_responses.normalizer import (
    normalize_openai_responses_usage,
)
from session_browser.attribution.api_families.openai_responses.usage_parser import (
    parse_openai_responses_usage,
)


def test_openai_responses_fresh_subtracts_cache_read_subset():
    usage = {
        "input_tokens": 3500,
        "input_tokens_details": {"cached_tokens": 1200},
        "output_tokens": 780,
        "output_tokens_details": {"reasoning_tokens": 100},
    }

    parsed = parse_openai_responses_usage(usage)
    normalized = normalize_openai_responses_usage(parsed)

    assert normalized.fresh_input == 2300
    assert normalized.cache_read == 1200
    assert normalized.cache_write is None
    assert normalized.output == 780
    assert normalized.total_input == 3500


def test_openai_chat_fresh_subtracts_cache_read_subset():
    usage = {
        "prompt_tokens": 2000,
        "prompt_tokens_details": {"cached_tokens": 500},
        "completion_tokens": 300,
        "completion_tokens_details": {"reasoning_tokens": 40},
    }

    parsed = parse_openai_chat_usage(usage)
    normalized = normalize_openai_chat_usage(parsed)

    assert normalized.fresh_input == 1500
    assert normalized.cache_read == 500
    assert normalized.cache_write is None
    assert normalized.output == 260
    assert normalized.total_input == 2000
