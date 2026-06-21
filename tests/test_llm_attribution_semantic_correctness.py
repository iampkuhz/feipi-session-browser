"""LLM attribution 数据层语义正确性测试。"""

import pytest

from session_browser.attribution.agents.claude_code_attribution_builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.serializers import request_attribution_to_payload
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.taxonomy import CATEGORY_BY_KEY
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
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
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        finish_reason='end_turn',
        content_blocks=[],
        response_full='',
        request_full='',
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


def _unit(candidate: str, direction: str, text: str, index: int = 1) -> dict:
    return {
        'source_id': f'test:{direction}:{candidate}:{index}',
        'dedupe_key': f'dedupe:{direction}:{candidate}:{index}',
        'origin_path': f'fixture.{candidate}',
        'canonical_source_locator': f'fixture:{candidate}:{index}',
        'unit_type': f'{candidate}_unit',
        'candidate': candidate,
        'direction': direction,
        'event_order': 1,
        'part_index': index,
        'byte_range': [0, len(text.encode('utf-8'))],
        'text': text,
        'label': candidate,
        'preview': text[:120],
    }


def _ctx(agent: str, *units: dict) -> dict | None:
    if agent in {'claude_code', 'qoder'}:
        return {'normalized_call': {'call_id': 'test-call-001', 'source_units': list(units)}}
    return None


# ─── 工具定义来源 ───────────────────────────


@pytest.mark.parametrize('agent', ['claude_code', 'qoder', 'codex'])
def test_tool_definitions_zero_without_available_tools(agent):
    """Claude/Qoder 只接受 normalized source_units；Codex 保留自身默认 catalog。"""
    tc = ToolCall(name='Read', parameters={'file_path': '/tmp/a.py'}, result='ok')
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content='test', tool_calls=[tc])
    result = build_llm_request_attribution(agent, lc, ro, session_context=_ctx(agent))

    schema_bucket = next((b for b in result.buckets if b.key == 'tool_definitions'), None)
    if agent in {'claude_code', 'qoder'}:
        assert schema_bucket is None
    else:
        assert schema_bucket is not None
        assert schema_bucket.tokens > 0
        assert 'Codex builtin tool catalog' in schema_bucket.summary
        assert schema_bucket.count_label == '5 tools'


def test_claude_code_tool_definitions_from_available_tools():
    """Claude Code 工具定义由 normalized source_units 提供。"""
    tc = ToolCall(name='Read', parameters={'file_path': '/tmp/a.py'}, result='ok')
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content='test', tool_calls=[tc])
    ctx = {
        'available_tools': ['Read', 'Bash', 'Edit'],
        **_ctx('claude_code', _unit('tool_definitions', 'request', 'Read Bash Edit schema')),
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == 'tool_definitions'), None)
    assert schema_bucket is not None
    assert schema_bucket.details['kind'] == 'source_units'


def test_tool_definitions_count_label_from_available_not_observed():
    """工具定义不再从 observed tool_calls 或 available_tools 反推。"""
    tc = ToolCall(name='Read', parameters={'file_path': '/tmp/a.py'}, result='ok')
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content='test', tool_calls=[tc])
    ctx = {
        'available_tools': ['Read', 'Bash', 'Edit', 'Grep', 'Glob'],
        **_ctx('claude_code', _unit('tool_definitions', 'request', 'five tool schema')),
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()

    schema_bucket = next((b for b in result.buckets if b.key == 'tool_definitions'), None)
    assert schema_bucket is not None
    assert schema_bucket.count_label == '1 sources'


# ─── 历史与 cache 语义 ─────────────────────


@pytest.mark.parametrize('agent', ['claude_code', 'qoder', 'codex'])
def test_no_history_without_prior_messages(agent):
    """没有历史 source_units 时不应产生正数 history bucket。"""
    lc = _make_lc(input_tokens=10000, request_full='role: user\n\nHello world\n\n')
    ro = _make_ro(user_content='test')
    result = build_llm_request_attribution(
        agent, lc, ro, session_context=_ctx(agent, _unit('user_input', 'request', 'test'))
    )

    history_bucket = next(
        (
            b
            for b in result.buckets
            if b.key in ('prior_conversation_messages', 'history_messages', 'conversation_history')
        ),
        None,
    )
    if history_bucket is not None:
        assert history_bucket.tokens == 0, (
            f'history_messages should be 0 without prior_messages for {agent}'
        )


@pytest.mark.parametrize('agent', ['claude_code', 'qoder', 'codex'])
def test_captured_context_when_request_full_exists(agent):
    """Claude/Qoder 不再从 request_full 生成旧 captured_context_fragment。"""
    lc = _make_lc(
        input_tokens=10000,
        request_full='some context data here that is not classifiable as history',
    )
    ro = _make_ro(user_content='test')
    result = build_llm_request_attribution(agent, lc, ro, session_context=_ctx(agent))

    ctx_bucket = next(
        (b for b in result.buckets if b.key == 'captured_context_fragment'),
        None,
    )
    if ctx_bucket is not None:
        assert ctx_bucket.tokens > 0


@pytest.mark.parametrize(
    ('agent', 'cache_read_tokens', 'cache_write_tokens'),
    [
        ('codex', 3000, 0),
        ('qoder', 3000, 700),
    ],
)
def test_provider_cache_accounting_is_not_a_request_content_bucket(
    agent, cache_read_tokens, cache_write_tokens
):
    """Provider cache 只作为 accounting metadata，不作为 request content bucket。"""
    provider_input_tokens = 5000 if agent == 'codex' else 2000
    request_content_denominator = 2000
    lc = _make_lc(
        input_tokens=provider_input_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        request_full='Tool output for call_1:\n' + ('result payload ' * 200),
    )
    ro = _make_ro(user_content='summarize the previous tool result')

    result = build_llm_request_attribution(
        agent,
        lc,
        ro,
        session_context=_ctx(agent, _unit('tool_results', 'request', 'result payload ' * 200)),
    )
    payload = request_attribution_to_payload(result)

    assert result.cache_read.value == cache_read_tokens
    assert all(b.key != 'provider_cached_context' for b in result.buckets)
    assert all(b['key'] != 'provider_cached_context' for b in payload['buckets'])
    assert all(b['canonical_key'] != 'provider_cache_read_context' for b in payload['buckets'])
    assert 'provider_cache_read_context' not in CATEGORY_BY_KEY

    coverage = payload['coverage']
    assert (
        coverage['input_side_component_total']
        == request_content_denominator + cache_read_tokens + cache_write_tokens
    )
    assert coverage['request_content_denominator'] == request_content_denominator
    assert coverage['accounting_cache_read_tokens'] == cache_read_tokens
    assert (
        coverage['reconstructed_total'] + coverage['residual_tokens'] == request_content_denominator
    )


@pytest.mark.parametrize('agent', ['claude_code', 'qoder', 'codex'])
def test_current_user_message_not_double_counted(agent):
    """当前用户输入只在 user_input 中出现，不在 history 中重复。"""
    lc = _make_lc(input_tokens=10000)
    ro = _make_ro(user_content='unique user message text that should not appear in history')
    result = build_llm_request_attribution(
        agent,
        lc,
        ro,
        session_context=_ctx(
            agent,
            _unit(
                'user_input',
                'request',
                'unique user message text that should not appear in history',
            ),
        ),
    )

    user_bucket = next(
        (
            b
            for b in result.buckets
            if b.key in ('current_user_message', 'current_user_instruction')
        ),
        None,
    )
    if agent in {'claude_code', 'qoder'}:
        user_bucket = next(
            (b for b in result.buckets if b.key == 'current_user_input'), user_bucket
        )
    assert user_bucket is not None
    assert user_bucket.tokens > 0


# ─── Response bucket 语义 ─────────────────────


def test_claude_response_tool_use_children_not_contribute_to_total():
    """Claude Code 最终版只保留 tool_calls aggregate，不再维护旧 child buckets。"""
    lc = _make_lc(
        output_tokens=3000,
        response_full='text response',
        content_blocks=[
            {'type': 'text', 'content': 'Hello'},
            {
                'type': 'tool_use',
                'name': 'Read',
                'id': 'tu-001',
                'parameters': {'file_path': '/tmp/test.py'},
            },
            {
                'type': 'tool_use',
                'name': 'Bash',
                'id': 'tu-002',
                'parameters': {'command': 'echo hello'},
            },
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution(
        'claude_code',
        lc,
        ro,
        session_context=_ctx(
            'claude_code',
            _unit('assistant_output', 'response', 'Hello'),
            _unit('tool_calls', 'response', 'Read Bash tool calls', 2),
        ),
    )

    aggregate = next((b for b in result.buckets if b.key == 'tool_call'), None)
    assert aggregate is not None
    assert aggregate.contributes_to_total is True

    children = [
        b for b in result.buckets if b.key.startswith('tool_call:') and b.key != 'tool_call'
    ]
    assert children == []


def test_coverage_only_counts_contributes_to_total():
    """Coverage 只统计 contributes_to_total=True 的 bucket。"""
    lc = _make_lc(
        output_tokens=5000,
        response_full='response text here',
        content_blocks=[
            {'type': 'text', 'content': 'Hello world this is a response'},
            {
                'type': 'tool_use',
                'name': 'Read',
                'id': 'tu-001',
                'parameters': {'file_path': '/tmp/test.py'},
            },
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution(
        'claude_code',
        lc,
        ro,
        session_context=_ctx(
            'claude_code', _unit('assistant_output', 'response', 'Hello world this is a response')
        ),
    )

    contributing_sum = sum(
        b.tokens for b in result.buckets if b.contributes_to_total and b.key != 'unknown'
    )
    total = result.total_output.value or 0
    if total > 0:
        expected_coverage = min(contributing_sum / total, 1.0)
    else:
        expected_coverage = 0.0

    assert abs(result.coverage.value - expected_coverage) < 0.01


def test_bucket_sum_not_exceeding_total_with_children():
    """输出侧 contributing bucket 之和不超过 output total。"""
    lc = _make_lc(
        output_tokens=3000,
        response_full='text',
        content_blocks=[
            {'type': 'text', 'content': 'Hello'},
            {
                'type': 'tool_use',
                'name': 'Read',
                'id': 'tu-001',
                'parameters': {'file_path': '/tmp/test.py'},
            },
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution(
        'claude_code',
        lc,
        ro,
        session_context=_ctx('claude_code', _unit('assistant_output', 'response', 'Hello')),
    )

    total = result.total_output.value or 0
    contributing_sum = sum(b.tokens for b in result.buckets if b.contributes_to_total)
    assert contributing_sum <= total, (
        f'Contributing bucket sum {contributing_sum} exceeds total {total}'
    )


# ─── 所有 bucket 都带 contributes_to_total ─────────────────────────────


@pytest.mark.parametrize('agent', ['claude_code', 'qoder', 'codex'])
def test_every_bucket_has_contributes_to_total_request(agent):
    """所有 request bucket 都有 contributes_to_total 字段。"""
    lc = _make_lc(input_tokens=10000, request_full='some context', response_full='some response')
    ro = _make_ro(user_content='test user message')
    result = build_llm_request_attribution(
        agent,
        lc,
        ro,
        session_context=_ctx(agent, _unit('user_input', 'request', 'test user message')),
    )

    for b in result.buckets:
        assert hasattr(b, 'contributes_to_total'), (
            f'Bucket {b.key} missing contributes_to_total attribute'
        )


@pytest.mark.parametrize('agent', ['claude_code', 'qoder', 'codex'])
def test_every_bucket_has_contributes_to_total_response(agent):
    """所有 response bucket 都有 contributes_to_total 字段。"""
    lc = _make_lc(
        output_tokens=3000,
        content_blocks=[
            {'type': 'text', 'content': 'hello'},
            {
                'type': 'tool_use',
                'name': 'Read',
                'id': 'tu-001',
                'parameters': {'file_path': '/tmp/test.py'},
            },
        ],
    )
    ro = _make_ro()
    result = build_llm_response_attribution(
        agent, lc, ro, session_context=_ctx(agent, _unit('assistant_output', 'response', 'hello'))
    )

    for b in result.buckets:
        assert hasattr(b, 'contributes_to_total'), (
            f'Bucket {b.key} missing contributes_to_total attribute'
        )
