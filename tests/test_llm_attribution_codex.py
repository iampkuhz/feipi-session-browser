"""Codex 专属 attribution 测试。"""

import json
from types import SimpleNamespace

from session_browser.attribution.agents.codex_attribution_builder import CodexAttributionBuilder
from session_browser.attribution.contracts import ValuePrecision, ValueSource
from session_browser.attribution.serializers import (
    request_attribution_to_payload,
    response_attribution_to_payload,
)
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
)


def _make_lc(**kwargs):
    defaults = dict(
        id='codex-call-001',
        model='o3-pro',
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
        finish_reason='stop',
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


def _source_unit(
    *,
    source_id: str,
    candidate: str,
    direction: str,
    text: str = '',
    payload: dict | None = None,
    unit_type: str = 'fixture_unit',
) -> dict:
    return {
        'source_id': source_id,
        'dedupe_key': f'dedupe:{source_id}',
        'origin_path': f'fixture.{source_id}',
        'canonical_source_locator': f'fixture.{source_id}',
        'unit_type': unit_type,
        'candidate': candidate,
        'direction': direction,
        'event_order': 1,
        'part_index': 0,
        'byte_range': [0, len((text or json.dumps(payload or {}, sort_keys=True)).encode('utf-8'))],
        'text': text,
        'payload': payload,
        'label': candidate,
        'preview': text or json.dumps(payload or {}, sort_keys=True),
    }


def test_codex_cache_split_unknown():
    """Codex must NOT fabricate cache_read / cache_write values."""
    lc = _make_lc(input_tokens=10000, output_tokens=5000)
    ro = _make_ro(user_content='test user message content here')
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.fresh_input.value == 10000
    assert result.fresh_input.precision == ValuePrecision.PROVIDER_REPORTED
    assert (
        result.cache_read.value is None or result.cache_read.precision == ValuePrecision.UNAVAILABLE
    )
    assert result.cache_read.precision == ValuePrecision.UNAVAILABLE
    # cache_write is 0 with UNAVAILABLE precision — OpenAI/Codex does not expose cache_write
    assert result.cache_write.value == 0 or result.cache_write.value is None
    assert result.cache_write.precision == ValuePrecision.UNAVAILABLE


def test_codex_session_jsonl_source():
    """Codex should label source as session jsonl."""
    lc = _make_lc(
        input_tokens=10000, output_tokens=5000, request_full='session context\n\nfile content'
    )
    ro = _make_ro(user_content='user prompt text')
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    assert result.agent == 'codex'
    assert result.source_label == 'session jsonl'


def test_codex_bucket_sum_within_total():
    lc = _make_lc(
        input_tokens=10000,
        output_tokens=5000,
        request_full='context\n\nmore\n\ndata\n\nFile: test.py',
    )
    ro = _make_ro(user_content='test user message')
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    total = result.total_input.value or 0
    bucket_sum = sum(b.tokens for b in result.buckets)
    assert bucket_sum <= total


def test_codex_response_attribution():
    lc = _make_lc(
        output_tokens=3000,
        response_full='response text here',
        content_blocks=[
            {'type': 'text', 'content': 'Hello world'},
            {
                'type': 'tool_use',
                'name': 'Bash',
                'id': 'tu-001',
                'parameters': {'command': 'echo hello'},
            },
        ],
    )
    ro = _make_ro()
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_response()

    assert result.agent == 'codex'
    assert result.total_output.value == 3000
    assert result.visible_text.value is not None
    assert result.visible_text.value > 0


def test_codex_repo_context_estimation():
    """Codex should estimate repo context tokens from file references."""
    lc = _make_lc(
        input_tokens=15000,
        request_full='File: src/main.py\nimport sys\n\nFile: src/utils.py\ndef helper(): pass',
    )
    ro = _make_ro(user_content='analyze these files')
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    repo_bucket = next((b for b in result.buckets if b.key == 'repository_file_context'), None)
    if repo_bucket is not None:
        assert repo_bucket.tokens > 0


def test_codex_availability_notes_cache_unknown():
    lc = _make_lc(input_tokens=5000)
    ro = _make_ro(user_content='test')
    builder = CodexAttributionBuilder(lc, ro)
    result = builder.build_request()

    for row in result.availability_rows:
        field_val = row.field if hasattr(row, 'field') else row['field']
        avail_val = row.available if hasattr(row, 'available') else row['available']
        if field_val == 'fresh_input':
            assert avail_val is True
        if field_val in ('cache_read', 'cache_write'):
            assert avail_val is False


def test_codex_visible_rollout_instructions_are_request_bucket(tmp_path):
    """Codex request attribution should count visible rollout instructions."""
    session_file = tmp_path / 'rollout.jsonl'
    events = [
        {
            'type': 'session_meta',
            'payload': {
                'base_instructions': {
                    'text': 'Base instruction text. ' * 200,
                }
            },
        },
        {
            'type': 'response_item',
            'payload': {
                'type': 'message',
                'role': 'developer',
                'content': [{'type': 'input_text', 'text': 'Developer instruction text. ' * 120}],
            },
        },
        {
            'type': 'event_msg',
            'payload': {'type': 'user_message', 'message': 'current task'},
        },
    ]
    session_file.write_text(
        '\n'.join(json.dumps(ev, ensure_ascii=False) for ev in events),
        encoding='utf-8',
    )

    lc = _make_lc(input_tokens=5000, request_full='current task')
    ro = _make_ro(user_content='current task')
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_summary=SimpleNamespace(file_path=str(session_file)),
    )

    result = builder.build_request()
    instructions = next((b for b in result.buckets if b.key == 'instructions'), None)

    assert instructions is not None
    assert instructions.tokens > 0
    assert instructions.source == ValueSource.TRANSCRIPT
    assert 'base_instructions' in instructions.summary
    assert instructions.details['kind'] == 'source_items'
    full_sources = '\n'.join(item['full_content'] for item in instructions.details['items'])
    assert 'Base instruction text' in full_sources
    assert 'Developer instruction text' in full_sources
    assert any('base_instructions' in note for note in result.attribution_notes)


def test_codex_request_full_tool_outputs_are_buckets_cache_read_is_summary_only():
    """request_full tool outputs are content buckets; provider cache read is accounting-only."""
    request_full = 'Tool output for call_1:\n' + ('tool output body ' * 200)
    lc = _make_lc(
        input_tokens=2800,
        cache_read_tokens=800,
        request_full=request_full,
    )
    ro = _make_ro(user_content='')
    builder = CodexAttributionBuilder(lc, ro)

    result = builder.build_request()
    tool_outputs = next((b for b in result.buckets if b.key == 'tool_outputs'), None)
    cache_bucket = next((b for b in result.buckets if b.key == 'provider_cached_context'), None)
    payload = request_attribution_to_payload(result)

    assert result.total_input.value == 2800
    assert result.fresh_input.value == 2000
    assert result.cache_read.value == 800
    assert tool_outputs is not None
    assert tool_outputs.tokens > 0
    assert tool_outputs.source == ValueSource.TOOL_LOGS
    assert tool_outputs.details['kind'] == 'tool_results'
    assert 'tool output body' in tool_outputs.details['items'][0]['full_content']
    assert cache_bucket is None
    assert all(b['key'] != 'provider_cached_context' for b in payload['buckets'])
    assert payload['coverage']['provider_request_input'] == 2800
    assert payload['coverage']['request_content_denominator'] == 2000
    assert payload['coverage']['accounting_cache_read_tokens'] == 800
    assert result.coverage.value is not None
    assert 0 <= result.coverage.value <= 1


def test_codex_request_builder_prefers_normalized_candidates():
    candidates = {
        'request': {
            'user_input': [{'source': 'event_msg.user_message', 'text': 'Run tests'}],
            'tool_results': [
                {
                    'source': 'response_item.function_call_output',
                    'text': '2 passed',
                    'payload': {'call_id': 'call_1', 'output': '2 passed'},
                }
            ],
        },
        'response': {},
    }
    lc = _make_lc(input_tokens=1000, cache_read_tokens=400, request_full='legacy should not win')
    ro = _make_ro(user_content='Run tests')
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_context={'normalized_call': {'attribution_candidates': candidates}},
    )

    result = builder.build_request()
    payload = request_attribution_to_payload(result)

    assert result.source_label == 'normalized artifact candidates'
    assert result.fresh_input.value == 600
    assert result.cache_read.value == 400
    assert any(b.key == 'current_user_instruction' for b in result.buckets)
    assert any(b.key == 'tool_outputs' for b in result.buckets)
    accounting = payload['accounting_attribution']['fresh_input_tokens']['candidates']
    assert {item['candidate'] for item in accounting} >= {'user_input', 'tool_results'}


def test_codex_request_builder_prefers_normalized_source_units():
    source_units = [
        _source_unit(source_id='u1', candidate='user_input', direction='request', text='Run tests'),
        _source_unit(
            source_id='u2',
            candidate='tool_results',
            direction='request',
            text='2 passed',
            payload={'call_id': 'call_1', 'output': '2 passed'},
            unit_type='request_tool_result',
        ),
    ]
    lc = _make_lc(input_tokens=1000, cache_read_tokens=400, request_full='legacy should not win')
    ro = _make_ro(user_content='Run tests')
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_context={
            'normalized_call': {
                'source_units': source_units,
                'attribution_candidates': {
                    'request': {'repo_context': [{'text': 'legacy candidate should not win'}]},
                    'response': {},
                },
            }
        },
    )

    result = builder.build_request()
    payload = request_attribution_to_payload(result)

    assert result.source_label == 'normalized artifact source_units'
    assert result.fresh_input.value == 600
    assert result.cache_read.value == 400
    assert any(b.key == 'current_user_instruction' for b in result.buckets)
    assert any(b.key == 'tool_outputs' for b in result.buckets)
    accounting = payload['accounting_attribution']
    assert accounting['cache_read_tokens']['tokens'] == 400
    assert accounting['cache_write_tokens']['tokens'] == 0
    fresh_candidates = accounting['fresh_input_tokens']['candidates']
    assert {item['candidate'] for item in fresh_candidates} >= {
        'user_input',
        'tool_results',
    }
    assert all(item['tokens'] == 0 for item in fresh_candidates)
    assert all(item['token_status'] == 'unknown_mass' for item in fresh_candidates)
    assert accounting['fresh_input_tokens']['candidate_total_tokens'] == 0
    assert accounting['fresh_input_tokens']['unattributed_tokens'] == 600
    assert all(b['key'] != 'provider_cached_context' for b in payload['buckets'])


def test_codex_response_builder_prefers_normalized_candidates():
    candidates = {
        'request': {},
        'response': {
            'assistant_output': [{'source': 'response_item.message', 'text': 'Done'}],
            'reasoning_output': [
                {'source': 'response_item.reasoning', 'payload': {'has_encrypted_content': True}}
            ],
            'tool_calls': [
                {
                    'source': 'response_item.function_call',
                    'payload': {'call_id': 'call_1', 'name': 'exec_command'},
                }
            ],
        },
    }
    lc = _make_lc(
        output_tokens=100,
        response_full='legacy should not win',
        content_blocks=[{'type': 'text', 'content': 'legacy'}],
    )
    lc.token_breakdown_normalized = SimpleNamespace(
        output_tokens=100,
        raw_fields={'reasoning_output_tokens': 30},
    )
    ro = _make_ro(user_content='')
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_context={'normalized_call': {'attribution_candidates': candidates}},
    )

    result = builder.build_response()
    payload = response_attribution_to_payload(result)

    assert result.source_label == 'normalized artifact candidates'
    assert any(b.key == 'assistant_text' for b in result.buckets)
    reasoning = next(b for b in result.buckets if b.key == 'reasoning_output_tokens')
    assert reasoning.tokens == 30
    accounting = payload['accounting_attribution']['output_tokens']['candidates']
    assert {item['candidate'] for item in accounting} >= {
        'assistant_output',
        'reasoning_output',
        'tool_calls',
    }


def test_codex_response_builder_prefers_normalized_source_units():
    source_units = [
        _source_unit(
            source_id='r1', candidate='assistant_output', direction='response', text='Done'
        ),
        _source_unit(
            source_id='r2',
            candidate='reasoning_output',
            direction='response',
            payload={'has_encrypted_content': True},
            unit_type='reasoning_output',
        ),
        _source_unit(
            source_id='r3',
            candidate='tool_calls',
            direction='response',
            payload={'call_id': 'call_1', 'name': 'exec_command'},
            unit_type='model_tool_call',
        ),
    ]
    lc = _make_lc(
        output_tokens=100,
        response_full='legacy should not win',
        content_blocks=[{'type': 'text', 'content': 'legacy'}],
    )
    lc.token_breakdown_normalized = SimpleNamespace(
        output_tokens=100,
        raw_fields={'reasoning_output_tokens': 30},
    )
    ro = _make_ro(user_content='')
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_context={'normalized_call': {'source_units': source_units}},
    )

    result = builder.build_response()
    payload = response_attribution_to_payload(result)

    assert result.source_label == 'normalized artifact source_units'
    reasoning = next(b for b in result.buckets if b.key == 'reasoning_output_tokens')
    assert reasoning.tokens == 30
    accounting = payload['accounting_attribution']['output_tokens']['candidates']
    assert {item['candidate'] for item in accounting} >= {
        'assistant_output',
        'reasoning_output',
        'tool_calls',
    }
    by_candidate = {item['candidate']: item for item in accounting}
    assert by_candidate['reasoning_output']['tokens'] == 30
    assert by_candidate['reasoning_output']['token_status'] == 'exact_provider'
    assert by_candidate['assistant_output']['tokens'] == 0
    assert by_candidate['tool_calls']['tokens'] == 0
    assert by_candidate['tool_calls']['token_status'] == 'unknown_mass'


def test_codex_prior_message_uses_full_token_estimate_from_context():
    """Prior message bucket must use full estimate, not truncated preview text."""
    lc = _make_lc(input_tokens=10000, request_full='current task')
    ro = _make_ro(user_content='current task')
    builder = CodexAttributionBuilder(
        lc,
        ro,
        session_context={
            'prior_messages': [
                {
                    'role': 'assistant',
                    'content_preview': 'short preview',
                    'content_token_estimate': 321,
                }
            ],
            'available_tools': [],
        },
    )

    result = builder.build_request()
    history = next((b for b in result.buckets if b.key == 'conversation_history'), None)

    assert history is not None
    assert history.tokens == 321
    assert history.details['kind'] == 'source_items'
    assert history.details['items'][0]['full_content'] == 'short preview'
