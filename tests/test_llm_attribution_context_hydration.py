"""Tests for LLM attribution context hydration.

Verifies:
1. prior_messages contains messages before current call.
2. available_tools from observed tool calls.
3. available_tools fallback to default list when no observed tools.
4. local_instructions from CLAUDE.md fixture.
5. MCP metadata does not return secrets.
6. Content truncation.
"""

import json
import tempfile
from pathlib import Path

from session_browser.attribution.context import (
    _TRUNCATE_CONTENT_PREVIEW,
    _TRUNCATE_LOCAL_INSTRUCTIONS,
    _read_local_instructions,
    _read_mcp_metadata,
    build_attribution_session_context,
)
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    SessionSummary,
    ToolCall,
)


def _make_lc(**kwargs):
    defaults = dict(
        id='test-call',
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


# ── prior_messages tests ─────────────────────────────────────────────


def test_prior_messages_contains_messages_before_current_call():
    """prior_messages should contain messages from the session."""
    all_messages = [
        {'role': 'user', 'content': 'Hello'},
        {'role': 'assistant', 'content': 'Hi there'},
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
    assert ctx['prior_messages'][0]['role'] == 'user'
    assert ctx['prior_messages'][1]['role'] == 'assistant'


def test_prior_messages_empty_when_no_all_messages():
    """prior_messages should be empty when all_messages is None."""
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=None,
    )

    assert ctx['prior_messages'] == []


def test_prior_messages_content_preview_has_length_limit():
    """content_preview should be truncated to 200 chars."""
    long_content = 'A' * 500
    all_messages = [{'role': 'user', 'content': long_content}]
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    preview = ctx['prior_messages'][0]['content_preview']
    assert len(preview) <= _TRUNCATE_CONTENT_PREVIEW
    assert ctx['prior_messages'][0]['full_content'] == long_content
    assert ctx['prior_messages'][0]['content'] == long_content


def test_prior_messages_token_estimate():
    """content_token_estimate should be > 0 for non-empty content."""
    all_messages = [{'role': 'user', 'content': 'Hello world, this is a test.'}]
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_messages=all_messages,
    )

    assert ctx['prior_messages'][0]['content_token_estimate'] > 0


def test_full_messages_array_uses_current_call_request_full_and_stops_before_response():
    """Claude Code messages reconstruction should be scoped to the current call."""
    current_request = 'Tool result for tool_1:\n' + ('important tool output ' * 200)
    prior = ChatMessage(
        role='assistant',
        content='prior assistant text',
        timestamp='2025-01-01T00:00:01Z',
        llm_call_id='call-1',
        request_full='initial user prompt',
        tool_calls=[{'id': 'tool_1', 'name': 'Read', 'parameters': {'file_path': 'a.py'}}],
    )
    current = ChatMessage(
        role='assistant',
        content='current assistant output should not be request input',
        timestamp='2025-01-01T00:00:02Z',
        llm_call_id='call-2',
        request_full=current_request,
    )
    future = ChatMessage(
        role='assistant',
        content='future assistant text',
        timestamp='2025-01-01T00:00:03Z',
        llm_call_id='call-3',
        request_full='future user prompt',
    )
    current_lc = _make_lc(id='call-2', request_full=current_request)

    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(interactions=[current_lc]),
        interaction_index=0,
        interactions=[current_lc],
        round_tool_calls=[],
        all_messages=[prior, current, future],
    )

    items = ctx['full_messages_array']
    summaries = '\n'.join(item['content_preview'] for item in items)
    content_types = [item['content_type'] for item in items]

    assert 'initial user prompt' in summaries
    assert 'prior assistant text' in summaries
    assert 'important tool output' in summaries
    assert 'current assistant output' not in summaries
    assert 'future assistant text' not in summaries
    assert 'future user prompt' not in summaries
    assert 'tool_result' in content_types
    tool_item = next(item for item in items if item['content_type'] == 'tool_result')
    assert tool_item['content_token_estimate'] > 200
    assert 'important tool output' in tool_item['full_content']
    assert all('full_content' in item for item in items)


def test_full_messages_array_falls_back_to_current_call_when_transcript_call_missing():
    """Subagent attribution must not borrow the parent session transcript."""
    parent = ChatMessage(
        role='assistant',
        content='parent assistant text',
        timestamp='2025-01-01T00:00:01Z',
        llm_call_id='parent-call',
        request_full='parent request',
    )
    subagent_lc = _make_lc(id='subagent-call', request_full='subagent private request')

    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(interactions=[subagent_lc]),
        interaction_index=0,
        interactions=[subagent_lc],
        round_tool_calls=[],
        all_messages=[parent],
    )

    items = ctx['full_messages_array']
    assert len(items) == 1
    assert items[0]['content_preview'] == 'subagent private request'
    assert items[0]['full_content'] == 'subagent private request'


# ── available_tools tests ────────────────────────────────────────────


def test_available_tools_from_observed_tool_calls():
    """available_tools should collect unique tool names from all_tool_calls."""
    tc1 = ToolCall(name='Read', parameters={'file_path': '/tmp/a.py'}, result='content')
    tc2 = ToolCall(name='Bash', parameters={'command': 'ls'}, result='ok')
    tc3 = ToolCall(name='Read', parameters={'file_path': '/tmp/b.py'}, result='more')  # duplicate

    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[tc1, tc2, tc3],
        all_tool_calls=[tc1, tc2, tc3],
    )

    assert 'Read' in ctx['available_tools']
    assert 'Bash' in ctx['available_tools']
    # Should be unique
    assert ctx['available_tools'].count('Read') == 1


def test_available_tools_fallback_default_list():
    """Should fallback to default Claude Code tool list when no observed tools."""
    ctx = build_attribution_session_context(
        session=None,
        round_obj=_make_ro(),
        interaction_index=0,
        interactions=[_make_lc()],
        round_tool_calls=[],
        all_tool_calls=[],
    )

    # Default list includes Read, Write, Edit, Bash, Grep, Glob, LS, Agent
    assert 'Read' in ctx['available_tools']
    assert 'Bash' in ctx['available_tools']
    assert len(ctx['available_tools']) >= 4


# ── local_instructions tests ─────────────────────────────────────────


def test_local_instructions_from_claude_md_fixture():
    """Should read CLAUDE.md from project_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        claude_md = Path(tmpdir) / 'CLAUDE.md'
        claude_md.write_text('# Project Rules\nAlways use Python 3.11+\n', encoding='utf-8')

        text = _read_local_instructions(Path(tmpdir), 'claude_code')
        assert 'Project Rules' in text
        assert 'Python 3.11' in text


def test_local_instructions_truncated():
    """local_instructions should be truncated to 2KB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        long_content = 'x' * 5000
        claude_md = Path(tmpdir) / 'CLAUDE.md'
        claude_md.write_text(long_content, encoding='utf-8')

        text = _read_local_instructions(Path(tmpdir), 'claude_code')
        assert len(text) <= _TRUNCATE_LOCAL_INSTRUCTIONS


def test_local_instructions_missing_file():
    """Should return empty string when CLAUDE.md does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        text = _read_local_instructions(Path(tmpdir), 'claude_code')
        assert text == ''


# ── MCP metadata tests ───────────────────────────────────────────────


def test_mcp_metadata_does_not_return_secrets():
    """MCP metadata should only return server/tool names, no credentials."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_json = Path(tmpdir) / '.mcp.json'
        mcp_json.write_text(
            json.dumps(
                {
                    'mcpServers': {
                        'filesystem': {
                            'command': 'npx',
                            'args': ['-y', '@modelcontextprotocol/server-filesystem', '/tmp'],
                            'env': {'API_KEY': 'super-secret-key'},
                        },
                        'github': {
                            'command': 'npx',
                            'args': ['-y', '@modelcontextprotocol/server-github'],
                            'env': {'GITHUB_TOKEN': 'ghp_123456'},
                        },
                    }
                }
            ),
            encoding='utf-8',
        )

        tools, servers = _read_mcp_metadata(Path(tmpdir))

        assert 'filesystem' in servers
        assert 'github' in servers
        # Should NOT contain secrets
        assert not any('super-secret' in t for t in tools)
        assert not any('ghp_' in t for t in tools)
        assert not any('API_KEY' in t for t in tools)
        assert not any('GITHUB_TOKEN' in t for t in tools)


def test_mcp_metadata_missing_file():
    """Should return empty lists when .mcp.json does not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tools, servers = _read_mcp_metadata(Path(tmpdir))
        assert tools == []
        assert servers == []


def test_mcp_metadata_invalid_json():
    """Should handle invalid JSON gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mcp_json = Path(tmpdir) / '.mcp.json'
        mcp_json.write_text('{invalid json', encoding='utf-8')

        tools, servers = _read_mcp_metadata(Path(tmpdir))
        assert tools == []
        assert servers == []


# ── Integration: full context with hydration ──────────────────────────


def test_full_context_hydration_with_project_dir():
    """Full context should include all hydrated fields when project_dir is set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CLAUDE.md
        claude_md = Path(tmpdir) / 'CLAUDE.md'
        claude_md.write_text('# Test Project\n', encoding='utf-8')

        # Create .mcp.json
        mcp_json = Path(tmpdir) / '.mcp.json'
        mcp_json.write_text(
            json.dumps(
                {
                    'mcpServers': {
                        'test-server': {'command': 'echo'},
                    }
                }
            ),
            encoding='utf-8',
        )

        tc = ToolCall(name='Read', parameters={'file_path': '/tmp/a.py'}, result='data')
        ctx = build_attribution_session_context(
            session=None,
            round_obj=_make_ro(),
            interaction_index=0,
            interactions=[_make_lc()],
            round_tool_calls=[tc],
            all_tool_calls=[tc],
            project_dir=tmpdir,
            agent_name='claude_code',
        )

        assert ctx['local_instructions'] == '# Test Project\n'
        assert 'test-server' in ctx['mcp_servers']
        assert 'Read' in ctx['available_tools']
        assert ctx['interaction_index'] == 0
        assert ctx['preceding_tool_results'] == []  # first interaction


def test_codex_context_hydrates_normalized_call_from_artifact(tmp_path, monkeypatch):
    import json as _json

    from session_browser import config
    from session_browser.index.schema import _get_connection

    index_dir = tmp_path / 'index'
    monkeypatch.setattr(config, 'INDEX_DIR', index_dir)
    monkeypatch.setattr(config, 'INDEX_PATH', index_dir / 'index.sqlite')

    summary = SessionSummary(
        agent='codex',
        session_id='codex-hydration',
        title='Codex hydration',
        project_key=str(tmp_path),
        project_name='proj',
        cwd=str(tmp_path),
        started_at='2026-06-10T00:00:00Z',
        ended_at='2026-06-10T00:00:10Z',
    )
    normalized = {
        'schema_version': 'session-detail.normalized.v3',
        'agent': 'codex',
        'session': {
            'session_key': summary.session_key,
            'session_id': summary.session_id,
            'agent': 'codex',
        },
        'calls': [
            {'call_id': 'codex-call-0001', 'call_index': 1, 'scope': 'main', 'source_units': []},
            {
                'call_id': 'codex-call-0002',
                'call_index': 2,
                'scope': 'main',
                'source_units': [
                    {
                        'source_id': 'u2',
                        'dedupe_key': 'd2',
                        'origin_path': 'event_msg.user_message.message',
                        'canonical_source_locator': 'event_msg.user_message.message',
                        'unit_type': 'current_user_text',
                        'candidate': 'user_input',
                        'direction': 'request',
                        'event_order': 2,
                        'part_index': 0,
                        'byte_range': [0, 4],
                        'text': 'next',
                    }
                ],
            },
        ],
    }
    conn = _get_connection()
    try:
        from tests.index._test_db_utils import init_test_schema, insert_test_session, insert_test_artifact
        from session_browser.normalized.artifacts import normalized_artifact_path

        init_test_schema(conn)
        insert_test_session(conn, summary)
        # 手动写入 artifact JSON 并关联 SQLite 行（模拟 Java producer 输出）。
        artifact_path = normalized_artifact_path(
            index_dir=index_dir, agent='codex', session_id='codex-hydration',
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            _json.dumps(normalized, ensure_ascii=False, separators=(',', ':')) + '\n',
            encoding='utf-8',
        )
        insert_test_artifact(
            conn,
            session_key=summary.session_key,
            artifact_type='normalized_session_json',
            path=str(artifact_path),
            schema_version=normalized['schema_version'],
            source_path='',
            source_mtime=0,
            size_bytes=artifact_path.stat().st_size,
        )
        conn.commit()
    finally:
        conn.close()

    first = _make_lc(id='synthetic-R1-M1', round_index=0)
    second = _make_lc(id='synthetic-R2-M1', round_index=1)
    ctx = build_attribution_session_context(
        session=summary,
        round_obj=_make_ro(interactions=[second]),
        interaction_index=0,
        interactions=[second],
        round_tool_calls=[],
        all_llm_calls=[first, second],
        agent_name='codex',
    )

    assert ctx['normalized_call']['call_id'] == 'codex-call-0002'
    assert ctx['normalized_call']['source_units'][0]['candidate'] == 'user_input'
