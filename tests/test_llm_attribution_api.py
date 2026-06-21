"""按需 Attribution API endpoint 测试。"""

from session_browser.attribution.agents.claude_code_attribution_builder import (
    ClaudeCodeAttributionBuilder,
)
from session_browser.attribution.agents.codex_attribution_builder import CodexAttributionBuilder
from session_browser.attribution.context import build_attribution_session_context
from session_browser.attribution.contracts import AttributedValue, ValuePrecision, ValueSource
from session_browser.attribution.mapping.agents.claude_code_token_accounting_mapping import (
    ClaudeCodeTokenAccountingMapper,
)
from session_browser.attribution.serializers import (
    attribution_error_to_payload,
    request_attribution_to_payload,
    response_attribution_to_payload,
)
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
)


def _make_lc(**kwargs):
    defaults = dict(
        id='cc-call-001',
        model='claude-sonnet-4',
        scope='main',
        subagent_id='',
        round_index=0,
        parent_id='',
        parent_tool_name='',
        timestamp='2025-01-01T00:00:00Z',
        status='ok',
        input_tokens=8200,
        output_tokens=3000,
        cache_read_tokens=5000,
        cache_write_tokens=1000,
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


class _FakeSession:
    agent = 'claude_code'
    session_id = 'test-session-001'
    project_key = '/tmp/test'


# ── Serializer / envelope 结构测试 ─────────────────────────────


def test_request_attribution_payload_contains_envelope_fields():
    """Request attribution payload 应包含 envelope 字段。"""
    lc = _make_lc()
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()
    payload = request_attribution_to_payload(result)

    assert payload['kind'] == 'llm.request_attribution'
    assert payload['agent'] == 'claude_code'
    assert 'buckets' in payload
    assert 'usage' in payload
    assert 'availability_rows' in payload
    assert 'timing' in payload


def test_codex_request_api_payload_has_complete_tool_schema_details():
    """Codex request payload 不应暴露 observed-tools-only schema。"""
    lc = _make_lc(
        id='codex-call-001',
        model='openai',
        input_tokens=10000,
        cache_read_tokens=1000,
    )
    ro = _make_ro(
        user_content='optimize repo',
        tool_calls=[
            ToolCall(name='exec_command', parameters={'cmd': 'pwd'}, result='ok'),
            ToolCall(name='apply_patch', parameters={}, result='ok'),
        ],
    )
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_context={'available_tools': ['exec_command', 'apply_patch']},
    )
    payload = request_attribution_to_payload(builder.build_request())
    tool_definitions = next((b for b in payload['buckets'] if b['key'] == 'tool_definitions'), None)

    assert tool_definitions is not None
    assert tool_definitions['tokens'] >= 3000
    assert tool_definitions['count_label'] == '5 tools'
    assert 'observed tools' not in tool_definitions['summary']
    details = tool_definitions['details']
    assert details['kind'] == 'tools'
    assert details['total_items'] == 5
    assert len(details['items']) == 5
    for item in details['items']:
        assert item['name']
        assert item['source_type']
        assert item['estimated_tokens'] > 0
        assert item['tokens'] == item['estimated_tokens']
        assert item['description_preview']
        assert item['input_schema']
        assert item['full_content']


def test_response_attribution_payload_contains_envelope_fields():
    """Response attribution payload 应包含 envelope 字段。"""
    lc = _make_lc()
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_response()
    payload = response_attribution_to_payload(result)

    assert payload['kind'] == 'llm.response_attribution'
    assert payload['agent'] == 'claude_code'
    assert 'buckets' in payload
    assert 'usage' in payload
    assert 'availability_rows' in payload


def test_error_payload_structure():
    """Error payload 应包含 kind、error_type、message 和 fallback。"""
    payload = attribution_error_to_payload(
        agent='claude_code',
        call_id='test-call',
        round_id='1',
        error_type='NotFound',
        message='call not found',
    )

    assert payload['kind'] == 'llm.attribution_error'
    assert payload['error_type'] == 'NotFound'
    assert 'call not found' in payload['message']
    assert 'fallback' in payload


# ── Context hydration 集成测试 ──────────────────────────────


def test_context_hydration_with_all_messages():
    """build_attribution_session_context 应填充 prior_messages。"""
    all_messages = [
        {'role': 'user', 'content': 'Hello there'},
        {'role': 'assistant', 'content': 'Hi!'},
        {'role': 'user', 'content': 'Analyze this code'},
    ]
    lc = _make_lc()
    ro = _make_ro()
    ctx = build_attribution_session_context(
        session=None,
        round_obj=ro,
        interaction_index=0,
        interactions=[lc],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    assert len(ctx['prior_messages']) == 3
    assert ctx['prior_messages'][0]['role'] == 'user'
    assert 'Hello there' in ctx['prior_messages'][0]['content_preview']
    assert ctx['prior_messages'][0]['content_token_estimate'] > 0


def test_content_preview_truncated_to_200_chars():
    """prior_messages content_preview 应截断到 200 字符。"""
    long_content = 'x' * 500
    all_messages = [{'role': 'user', 'content': long_content}]
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    assert len(ctx['prior_messages'][0]['content_preview']) == 200


def test_available_tools_from_observed_calls():
    """available_tools 可从 observed tool calls 收集。"""
    tc1 = ToolCall(name='Read', parameters={'file_path': '/tmp/a.py'}, result='content')
    tc2 = ToolCall(name='Bash', parameters={'command': 'echo hi'}, result='ok')
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[tc1, tc2],
        all_tool_calls=[tc1, tc2],
    )

    assert 'Read' in ctx['available_tools']
    assert 'Bash' in ctx['available_tools']


def test_available_tools_fallback_when_empty():
    """没有 observed tools 时 available_tools 回退到默认列表。"""
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_tool_calls=None,
    )

    assert 'Read' in ctx['available_tools']
    assert 'Write' in ctx['available_tools']
    assert 'Bash' in ctx['available_tools']


def test_prior_messages_not_contain_current_user_message():
    """prior_messages 保留输入消息，由调用方按 call 边界过滤。"""
    all_messages = [
        {'role': 'user', 'content': 'First message'},
        {'role': 'assistant', 'content': 'Response'},
    ]
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    assert len(ctx['prior_messages']) == 2


# ── Field-first source_units mapping 测试 ────────────────────────────────────────


def test_claude_code_mapper_scales_candidates_to_fresh_field():
    """source_units candidate 总量超过 fresh field 时按 field 分母缩放。"""
    mapper = ClaudeCodeTokenAccountingMapper()
    source_units = [
        {
            'source_id': 'u1',
            'origin_path': 'fixture.user',
            'unit_type': 'user',
            'candidate': 'user_input',
            'direction': 'request',
            'text': 'x' * 200,
            'preview': 'x' * 20,
        },
        {
            'source_id': 'u2',
            'origin_path': 'fixture.tools',
            'unit_type': 'tools',
            'candidate': 'tool_definitions',
            'direction': 'request',
            'text': 'y' * 200,
            'preview': 'y' * 20,
        },
    ]
    payload = mapper.build_request_accounting(
        source_units=source_units,
        fresh_input=AttributedValue(
            40, 'tokens', ValuePrecision.PROVIDER_REPORTED, ValueSource.PROVIDER_USAGE, 'fresh'
        ),
        cache_read=AttributedValue(
            80, 'tokens', ValuePrecision.PROVIDER_REPORTED, ValueSource.PROVIDER_USAGE, 'cache read'
        ),
        cache_write=AttributedValue(
            0, 'tokens', ValuePrecision.PROVIDER_REPORTED, ValueSource.PROVIDER_USAGE, 'cache write'
        ),
    )

    fresh = payload['fresh_input_tokens']
    assert fresh['candidate_total_tokens'] <= 40
    assert payload['cache_read_tokens']['tokens'] == 80
    assert payload['cache_read_tokens']['candidates'] == []


def test_builder_includes_normalization_note():
    """Claude Code builder 缺少 source_units 时提示重新 scan。"""
    lc = _make_lc(input_tokens=8200, cache_read_tokens=88500, cache_write_tokens=3300)
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    notes = result.attribution_notes
    assert any('normalized source_units' in n for n in notes), (
        f'Expected source_units note in: {notes}'
    )


def test_located_rate_never_exceeds_100():
    """Coverage value 不应超过 1.0。"""
    lc = _make_lc(
        input_tokens=8200, output_tokens=3000, cache_read_tokens=88500, cache_write_tokens=3300
    )
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.coverage.value <= 1.0


def test_bucket_tokens_sum_not_exceed_request_content_denominator():
    """Contributing buckets 之和不应超过 Fresh denominator。"""
    lc = _make_lc(
        input_tokens=5000, output_tokens=2000, cache_read_tokens=1000, cache_write_tokens=500
    )
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_request()

    request_content_denominator = result.fresh_input.value or 0
    contributing_sum = sum(
        b.tokens for b in result.buckets if b.key != 'unlocated_residual' and b.contributes_to_total
    )
    assert contributing_sum <= request_content_denominator


# ── Details field in serialized buckets ──────────────────────────────


def test_request_bucket_serialization_includes_details():
    """序列化 request bucket 应包含 source_units details。"""
    lc = _make_lc(input_tokens=10000, cache_read_tokens=5000, cache_write_tokens=1000)
    ro = _make_ro()
    ctx = {
        'normalized_call': {
            'call_id': 'test-call-001',
            'source_units': [
                {
                    'source_id': 'test:tool_definitions:1',
                    'dedupe_key': 'dedupe:tool_definitions:1',
                    'origin_path': 'fixture.tools',
                    'canonical_source_locator': 'fixture:tools',
                    'unit_type': 'tool_definitions_unit',
                    'candidate': 'tool_definitions',
                    'direction': 'request',
                    'event_order': 1,
                    'part_index': 1,
                    'byte_range': [0, 24],
                    'text': 'Read Write Bash schemas',
                    'label': '工具定义',
                    'preview': 'Read Write Bash schemas',
                }
            ],
        }
    }
    builder = ClaudeCodeAttributionBuilder(lc, ro, session_context=ctx)
    result = builder.build_request()
    payload = request_attribution_to_payload(result)

    buckets = payload['buckets']
    assert len(buckets) > 0

    tool_definitions = next((b for b in buckets if b['key'] == 'tool_definitions'), None)
    assert tool_definitions is not None
    assert 'details' in tool_definitions
    assert tool_definitions['details'].get('kind') == 'source_units'
    assert len(tool_definitions['details'].get('items', [])) > 0


def test_response_bucket_serialization_includes_details():
    """序列化 response bucket 应包含 details 字段。"""
    lc = _make_lc()
    ro = _make_ro()
    builder = ClaudeCodeAttributionBuilder(lc, ro)
    result = builder.build_response()
    payload = response_attribution_to_payload(result)

    buckets = payload['buckets']
    for b in buckets:
        assert 'details' in b
