"""API Family enum values and capability table.

API Family identifies the protocol semantics for one LLM call mapping output:
- anthropic_messages: Anthropic Messages API.
- anthropic_messages_like: Anthropic-compatible usage payloads.
- openai_responses: OpenAI Responses API.
- openai_chat: OpenAI Chat Completions API.
- openai_like: OpenAI-compatible usage payloads.
- qoder_broker: Qoder broker calls with dynamic underlying provider semantics.
- estimate_only: local token estimation without provider usage.
- unknown: insufficient model, request, response, and usage evidence.
"""

from __future__ import annotations

API_FAMILY_VALUES = frozenset(
    {
        'anthropic_messages',
        'anthropic_messages_like',
        'openai_responses',
        'openai_chat',
        'openai_like',
        'qoder_broker',
        'estimate_only',
        'unknown',
    }
)

# API family cache semantics used after mapping resolver output is selected.
# cache_write_available: whether Anthropic-style cache_creation_input_tokens is present.
# cache_read_field: usage payload field path for cache reads.
# provider_request_input_field: provider raw request input field.
# fresh_formula: UI Fresh component formula.
# input_side_component_total_formula: input-side component total formula.
API_FAMILY_CAPABILITIES: dict[str, dict[str, object]] = {
    'anthropic_messages': {
        'cache_write_available': True,
        'cache_read_field': 'cache_read_input_tokens',
        'cache_write_field': 'cache_creation_input_tokens',
        'provider_request_input_field': 'input_tokens',
        'fresh_formula': 'input_tokens',
        'input_side_component_total_formula': 'fresh + cache_read + cache_write',
    },
    'anthropic_messages_like': {
        'cache_write_available': True,
        'cache_read_field': 'cache_read_input_tokens',
        'cache_write_field': 'cache_creation_input_tokens',
        'provider_request_input_field': 'input_tokens',
        'fresh_formula': 'input_tokens',
        'input_side_component_total_formula': 'fresh + cache_read + cache_write',
    },
    'openai_responses': {
        'cache_write_available': False,
        'cache_read_field': 'input_tokens_details.cached_tokens',
        'cache_write_field': None,
        'provider_request_input_field': 'input_tokens',
        'fresh_formula': 'input_tokens - input_tokens_details.cached_tokens',
        'input_side_component_total_formula': 'fresh + cache_read',
    },
    'openai_chat': {
        'cache_write_available': False,
        'cache_read_field': 'prompt_tokens_details.cached_tokens',
        'cache_write_field': None,
        'provider_request_input_field': 'prompt_tokens',
        'fresh_formula': 'prompt_tokens - prompt_tokens_details.cached_tokens',
        'input_side_component_total_formula': 'fresh + cache_read',
    },
    'openai_like': {
        'cache_write_available': False,
        'cache_read_field': 'cached_tokens',
        'cache_write_field': None,
        'provider_request_input_field': 'input_tokens',
        'fresh_formula': 'input_tokens - cached_tokens when cached is an input subset',
        'input_side_component_total_formula': 'fresh + cache_read',
    },
    'qoder_broker': {
        'cache_write_available': True,
        'cache_read_field': 'dynamic',
        'cache_write_field': 'dynamic',
        'provider_request_input_field': 'dynamic',
        'fresh_formula': 'dynamic',
        'input_side_component_total_formula': 'dynamic',
    },
    'estimate_only': {
        'cache_write_available': False,
        'cache_read_field': None,
        'cache_write_field': None,
        'provider_request_input_field': None,
        'fresh_formula': 'reconstructed',
        'input_side_component_total_formula': 'reconstructed',
    },
    'unknown': {
        'cache_write_available': False,
        'cache_read_field': None,
        'cache_write_field': None,
        'provider_request_input_field': None,
        'fresh_formula': 'unavailable',
        'input_side_component_total_formula': 'unavailable',
    },
}
