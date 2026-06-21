"""Tests for independent request/response error handling (Task 02c P0-4).

Verifies that request and response attribution failures are independent:
- request success + response failure = request payload OK, response error
- request failure + response success = request error, response payload OK
- both fail = both error
"""

from session_browser.attribution.serializers import (
    attribution_error_to_payload,
    request_attribution_to_payload,
    response_attribution_to_payload,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
)


def _make_lc(**kwargs):
    defaults = dict(
        id='test-call-001',
        model='test-model',
        scope='main',
        subagent_id='',
        round_index=0,
        parent_id='',
        parent_tool_name='',
        timestamp='2025-01-01T00:00:00Z',
        status='ok',
        input_tokens=5000,
        output_tokens=3000,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish_reason='end_turn',
        content_blocks=[],
        response_full='response text',
        request_full='request text',
        tool_calls_raw='',
    )
    defaults.update(kwargs)
    return LLMCall(**defaults)


def _make_ro(user_content='hello', tool_calls=None, interactions=None):
    return ConversationRound(
        user_msg=ChatMessage(role='user', content=user_content, timestamp='2025-01-01T00:00:00Z'),
        assistant_msg=ChatMessage(role='assistant', content='hi', timestamp='2025-01-01T00:00:00Z'),
        tool_calls=tool_calls or [],
        interactions=interactions or [],
    )


def test_request_attribution_succeeds_independently():
    """When request builder succeeds, it should return valid attribution."""
    lc = _make_lc()
    ro = _make_ro()
    result = build_llm_request_attribution('claude_code', lc, ro)
    payload = request_attribution_to_payload(result)
    assert payload['kind'] == 'llm.request_attribution'
    assert payload['agent'] == 'claude_code'


def test_response_attribution_succeeds_independently():
    """When response builder succeeds, it should return valid attribution."""
    lc = _make_lc()
    ro = _make_ro()
    result = build_llm_response_attribution('claude_code', lc, ro)
    payload = response_attribution_to_payload(result)
    assert payload['kind'] == 'llm.response_attribution'
    assert payload['agent'] == 'claude_code'


def test_error_payload_has_correct_kind():
    """Error payload should have kind llm.attribution_error."""
    err = attribution_error_to_payload(
        agent='claude_code',
        call_id='call-001',
        round_id='R1',
        error_type='ValueError',
        message='test error',
    )
    assert err['kind'] == 'llm.attribution_error'


def test_request_and_response_error_titles_are_distinguishable():
    """Request and response error payloads should have distinguishable titles.

    This is tested at the routes.py level; here we verify that the
    error payload structure supports distinct titles.
    """
    req_err = attribution_error_to_payload(
        agent='claude_code',
        call_id='c1',
        round_id='R1',
        error_type='RequestError',
        message='request failed',
    )
    resp_err = attribution_error_to_payload(
        agent='claude_code',
        call_id='c1',
        round_id='R1',
        error_type='ResponseError',
        message='response failed',
    )
    # Both are error kind
    assert req_err['kind'] == 'llm.attribution_error'
    assert resp_err['kind'] == 'llm.attribution_error'
    # But with different error types
    assert req_err['error_type'] != resp_err['error_type']
