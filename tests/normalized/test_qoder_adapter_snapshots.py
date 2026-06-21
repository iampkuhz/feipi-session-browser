"""Qoder normalized adapter 快照测试。"""

from __future__ import annotations

import json
from pathlib import Path

from session_browser.normalized import validate_normalized_session
from session_browser.normalized.agents.qoder_normalization import parse_qoder_session_file
from session_browser.sources.qoder import parse_normalized_session_file

FIXTURE_DIR = Path('tests/fixtures/normalized/qoder')
TOOL_LOOP_INPUT = FIXTURE_DIR / 'tool_loop.input' / 'session-qoder-001.jsonl'
TOOL_LOOP_EXPECTED = FIXTURE_DIR / 'tool_loop.expected.json'


def _load_expected() -> dict:
    return json.loads(TOOL_LOOP_EXPECTED.read_text(encoding='utf-8'))


def test_qoder_tool_loop_snapshot_matches_expected_json():
    actual = parse_qoder_session_file(
        TOOL_LOOP_INPUT,
        project_key='/repo',
        session_id='session-qoder-001',
    )

    assert actual == _load_expected()


def test_qoder_tool_loop_normalized_semantics():
    actual = parse_qoder_session_file(
        TOOL_LOOP_INPUT,
        project_key='/repo',
        session_id='session-qoder-001',
    )

    validate_normalized_session(actual)

    assert len(actual['calls']) == 2
    c1, c2 = actual['calls']

    assert c1['call_id'] == 'qoder-msg-1'
    assert c1['response']['tool_call_ids'] == ['toolu_qoder_write']
    assert c1['usage'] == {
        'fresh': 800,
        'cache_read': 0,
        'cache_write': 100,
        'output': 70,
        'total': 970,
    }
    assert actual['tool_executions'][0]['files_touched'] == ['diagram.puml']

    assert c2['request']['tool_result_ids'] == ['toolu_qoder_write']
    assert actual['tool_executions'][0]['tool_call_id'] == 'toolu_qoder_write'
    assert actual['tool_executions'][0]['declared_by_call_id'] == 'qoder-msg-1'
    assert actual['tool_executions'][0]['result_consumed_by_call_id'] == 'qoder-msg-2'
    assert 'content_refs' not in c1['response']
    assert 'type' not in actual['tool_executions'][0]
    assert 'status' not in actual['tool_executions'][0]
    assert 'token_sources' not in c1['response']
    assert 'context_sources' not in actual
    assert 'payload_index' not in actual
    _assert_source_units(
        c1, request={'user_input', 'runtime_context'}, response={'assistant_output', 'tool_calls'}
    )
    _assert_source_units(
        c2,
        request={'tool_results', 'conversation_history', 'runtime_context'},
        response={'assistant_output'},
    )


def test_qoder_source_file_entrypoint_matches_adapter_snapshot():
    actual = parse_normalized_session_file(
        TOOL_LOOP_INPUT,
        project_key='/repo',
        session_id='session-qoder-001',
    )

    assert actual == _load_expected()


def _assert_source_units(call: dict, *, request: set[str], response: set[str]) -> None:
    units = call.get('source_units') or []
    assert units
    required = {
        'source_id',
        'dedupe_key',
        'origin_path',
        'canonical_source_locator',
        'unit_type',
        'candidate',
        'direction',
        'event_order',
        'part_index',
        'byte_range',
    }
    for unit in units:
        assert required <= set(unit)
    by_direction = {
        'request': {u['candidate'] for u in units if u['direction'] == 'request'},
        'response': {u['candidate'] for u in units if u['direction'] == 'response'},
    }
    assert request <= by_direction['request']
    assert response <= by_direction['response']
