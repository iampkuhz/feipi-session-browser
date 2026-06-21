"""测试 Qoder 模型提取契约.

覆盖范围:
a. assistant message.model 流入 SessionSummary.model.
b. cache 固件(无 model)不应捏造 model.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

import pytest

from session_browser.sources.qoder import (
    _assistant_records,
    _build_qoder_session_model_map,
    _build_summary_from_events,
    _extract_qoder_model,
    _parse_cache_session,
    _resolve_qoder_model_config_name,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_event(typ: str, message: dict, **extra: object) -> dict:
    """构建最小 Qoder 事件字典的辅助函数."""
    ev = {'type': typ, 'message': message, 'timestamp': '2025-01-01T00:00:00Z'}
    ev.update(extra)
    return ev


def _assistant_event(
    model: str = '',
    text: str = '',
    msg_id: str = 'msg-1',
    **extra: object,
) -> dict:
    """构建带可选 model 和 text 的 assistant 事件."""
    content = []
    if text:
        content.append({'type': 'text', 'text': text})
    msg = {'id': msg_id, 'content': content}
    if model:
        msg['model'] = model
    return _make_event('assistant', msg, **extra)


def _user_event(text: str = '') -> dict:
    """构建 user 事件."""
    return _make_event('user', {'content': text})


class TestQoderModelContract:
    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    @pytest.mark.contract_case('DATA-SOURCE-012')
    def test_model_from_assistant_message(self):
        """Assistant message.model 应流入 SessionSummary.model."""
        events = [
            _user_event('hello'),
            _assistant_event(model='qwen3.6-plus', text='hi', msg_id='msg-1'),
        ]

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'qwen3.6-plus', (
            f"Expected model 'qwen3.6-plus' but got {summary.model!r}"
        )

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_model_from_first_assistant_with_model(self):
        """多条 assistant 消息时,model 取自第一条带 model 的消息."""
        events = [
            _user_event('hello'),
            _assistant_event(model='', text='thinking', msg_id='msg-0'),
            _assistant_event(model='qwen3.6-plus', text='answer', msg_id='msg-1'),
        ]

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'qwen3.6-plus'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_cache_fixture_no_model(self):
        """Cache 固件(assistant 消息中无 model)不应捏造 model."""
        events = [
            _user_event('hello'),
            _assistant_event(text='hi', msg_id='msg-1'),
        ]

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == '', f'Expected empty model but got {summary.model!r}'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_assistant_records_preserve_model(self):
        """_assistant_records 应保留 message 中的 model."""
        events = [
            _assistant_event(model='qwen3.6-plus', text='response', msg_id='msg-1'),
        ]

        records = _assistant_records(events)
        assert len(records) == 1
        assert records[0]['model'] == 'qwen3.6-plus'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_model_fallback_top_level(self):
        """优先级 2:message.model 为空时使用顶层 event.model."""
        events = [
            _user_event('hello'),
            _assistant_event(model='', text='hi', msg_id='msg-1'),
        ]
        # 将顶层 model 注入原始事件
        events[1]['model'] = 'claude-sonnet-4-20250514'

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'claude-sonnet-4-20250514'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_model_fallback_metadata(self):
        """优先级 3:message.model 和顶层都为空时使用 metadata.model."""
        events = [
            _user_event('hello'),
            _assistant_event(model='', text='hi', msg_id='msg-1'),
        ]
        # 将 metadata.model 注入原始事件
        events[1]['metadata'] = {'model': 'claude-opus-4-20250514'}

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'claude-opus-4-20250514'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_model_fallback_content_item(self):
        """优先级 4:最后手段使用 content item 中的 model."""
        events = [
            _user_event('hello'),
            _assistant_event(model='', text='hi', msg_id='msg-1'),
        ]
        # 将 model 注入 content 项
        events[1]['message']['content'].append({'type': 'text', 'text': '', 'model': 'gpt-4.1'})

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'gpt-4.1'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_model_priority_message_wins_over_top_level(self):
        """message.model(优先级 1)应优先于顶层 model(优先级 2)."""
        events = [
            _user_event('hello'),
            _assistant_event(model='qwen3.6-plus', text='hi', msg_id='msg-1'),
        ]
        events[1]['model'] = 'should-not-be-used'

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'qwen3.6-plus'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_extract_qoder_model_returns_none(self):
        """所有字段为空时 _extract_qoder_model 应返回 None."""
        record = {
            'model': '',
            'top_level_model': '',
            'metadata_model': '',
            'raw_model': '',
        }
        assert _extract_qoder_model(record) is None

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_extract_qoder_model_first_non_empty_wins(self):
        """_extract_qoder_model 返回第一个非空字段."""
        record = {
            'model': '',
            'top_level_model': 'fallback-model',
            'metadata_model': 'metadata-model',
            'raw_model': 'raw-model',
        }
        assert _extract_qoder_model(record) == 'fallback-model'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_custom_model_config_resolves_to_alias(self):
        """custom:model_x 应通过 aicoding.customModels 别名解析."""
        custom_names = {
            'model_123': 'Qwen-3.6-Plus',
            'custom:model_123': 'Qwen-3.6-Plus',
        }

        assert (
            _resolve_qoder_model_config_name(
                'custom:model_123',
                custom_names=custom_names,
                selector_names={},
                auth_names={},
            )
            == 'Qwen-3.6-Plus'
        )

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_builtin_model_config_resolves_to_dynamic_label(self):
        """Qmodel 等内置 id 应解析为选择器标签."""
        assert (
            _resolve_qoder_model_config_name(
                'qmodel',
                custom_names={},
                selector_names={'qmodel': 'Qwen3.6-Plus'},
                auth_names={},
            )
            == 'Qwen3.6-Plus'
        )

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_session_model_map_from_agent_log_custom_model(self, tmp_path: Path):
        """Qoder agent.log 会话 model config 应映射到自定义 model 别名."""
        app_support = tmp_path / 'Qoder'
        global_storage = app_support / 'User' / 'globalStorage'
        global_storage.mkdir(parents=True)
        conn = sqlite3.connect(global_storage / 'state.vscdb')
        conn.execute('CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)')
        conn.execute(
            'INSERT INTO ItemTable (key, value) VALUES (?, ?)',
            (
                'aicoding.customModels',
                json.dumps(
                    [
                        {
                            'id': 'model_123',
                            'provider': 'bailian',
                            'model': 'qwen3.6-plus-cp',
                            'alias': 'Qwen-3.6-Plus',
                            'hasApiKey': True,
                        }
                    ]
                ),
            ),
        )
        conn.commit()
        conn.close()

        log_dir = app_support / 'logs' / '20260512T221746' / 'window1'
        log_dir.mkdir(parents=True)
        (log_dir / 'agent.log').write_text(
            '2026-05-12 22:17:51.528 [info] [ModelSelector] '
            'activeModelConfig=custom:model_123, sessionType=assistant, '
            'sessionId=session-abc\n',
            encoding='utf-8',
        )

        assert _build_qoder_session_model_map(app_support)['session-abc'] == 'Qwen-3.6-Plus'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_session_model_map_adds_unique_short_id_prefix(self, tmp_path: Path):
        """Cache JSONL 短 id 应从完整 GUI 会话 UUID 解析."""
        app_support = tmp_path / 'Qoder'
        user_dir = app_support / 'User'
        user_dir.mkdir(parents=True)
        (user_dir / 'dynamic-text-cache.json').write_text(
            json.dumps({'zh-cn': {'modelSelector.item.qmodel': 'Qwen3.6-Plus'}}),
            encoding='utf-8',
        )
        log_dir = app_support / 'logs' / '20260527T000152' / 'window1'
        log_dir.mkdir(parents=True)
        (log_dir / 'agent.log').write_text(
            '2026-05-27 00:01:57.765 [info] [ModelConfigService] '
            'getCurrentModelConfig: '
            'sessionId=4df638fa-ab30-413d-b155-7fc550f19703, '
            'returning from storage: qmodel\n',
            encoding='utf-8',
        )

        model_map = _build_qoder_session_model_map(app_support)
        assert model_map['4df638fa-ab30-413d-b155-7fc550f19703'] == 'Qwen3.6-Plus'
        assert model_map['4df638fa'] == 'Qwen3.6-Plus'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_summary_model_falls_back_to_agent_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """JSONL 缺少 model 时 SessionSummary.model 应使用 Qoder GUI agent 日志."""
        app_support = tmp_path / 'Qoder'
        user_dir = app_support / 'User'
        user_dir.mkdir(parents=True)
        (user_dir / 'dynamic-text-cache.json').write_text(
            json.dumps({'zh-cn': {'modelSelector.item.qmodel': 'Qwen3.6-Plus'}}),
            encoding='utf-8',
        )
        log_dir = app_support / 'logs' / '20260512T221746' / 'window1'
        log_dir.mkdir(parents=True)
        (log_dir / 'agent.log').write_text(
            '2026-05-12 22:17:51.528 [info] [ModelSelector] '
            'activeModelConfig=qmodel, sessionType=assistant, sessionId=sess-1\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('QODER_APP_SUPPORT_DIR', str(app_support))

        events = [
            _user_event('hello'),
            _assistant_event(model='', text='hi', msg_id='msg-1'),
        ]

        summary = _build_summary_from_events(events, 'sess-1', '/tmp')
        assert summary.model == 'Qwen3.6-Plus'

    @pytest.mark.contract_case('DATA-SOURCE-008', 'DATA-SOURCE-009')
    def test_cache_session_model_falls_back_to_agent_log(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Cache 格式会话也应从 Qoder agent 日志获取 model."""
        app_support = tmp_path / 'Qoder'
        user_dir = app_support / 'User'
        user_dir.mkdir(parents=True)
        (user_dir / 'dynamic-text-cache.json').write_text(
            json.dumps({'zh-cn': {'modelSelector.item.lite': 'Lite'}}),
            encoding='utf-8',
        )
        log_dir = app_support / 'logs' / '20260512T221746' / 'window1'
        log_dir.mkdir(parents=True)
        (log_dir / 'agent.log').write_text(
            '2026-05-12 22:17:51.528 [info] [ModelConfigService] '
            'getCurrentModelConfig: sessionId=cache-1, returning from memory: lite\n',
            encoding='utf-8',
        )
        monkeypatch.setenv('QODER_APP_SUPPORT_DIR', str(app_support))

        session_file = tmp_path / 'cache-1.jsonl'
        session_file.write_text(
            json.dumps({'role': 'user', 'message': {'content': 'hello'}})
            + '\n'
            + json.dumps(
                {
                    'role': 'assistant',
                    'message': {'content': [{'type': 'text', 'text': 'hi'}]},
                }
            )
            + '\n',
            encoding='utf-8',
        )

        summary = _parse_cache_session('project', 'cache-1', session_file)
        assert summary.model == 'Lite'
