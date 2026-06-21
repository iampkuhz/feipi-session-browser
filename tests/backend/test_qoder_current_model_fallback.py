"""Qoder 当前模型选择器回退测试."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from session_browser.sources import qoder

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write_qoder_state(app_support: Path, assistant_model_config: str) -> None:
    global_storage = app_support / 'User' / 'globalStorage'
    global_storage.mkdir(parents=True)
    conn = sqlite3.connect(global_storage / 'state.vscdb')
    conn.execute('CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)')
    conn.execute(
        'INSERT INTO ItemTable(key, value) VALUES (?, ?)',
        (
            'aicoding.customModels',
            json.dumps(
                [
                    {
                        'id': 'model_123',
                        'model': 'qwen3.6-plus-cp',
                        'alias': 'Qwen-3.6-Plus',
                        'hasApiKey': True,
                    }
                ]
            ),
        ),
    )
    conn.execute(
        'INSERT INTO ItemTable(key, value) VALUES (?, ?)',
        ('chat.modelConfig.assistant', assistant_model_config),
    )
    conn.commit()
    conn.close()


def test_uuid_session_model_falls_back_to_current_assistant_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """无逐会话 model 的项目会话使用 Qoder 的当前选择器."""
    app_support = tmp_path / 'Qoder'
    _write_qoder_state(app_support, 'custom:model_123')
    monkeypatch.setenv('QODER_APP_SUPPORT_DIR', str(app_support))
    qoder._load_qoder_custom_model_names.cache_clear()
    qoder._load_qoder_model_selector_names.cache_clear()
    qoder._load_qoder_current_assistant_model.cache_clear()
    qoder._build_qoder_session_model_map.cache_clear()

    summary = qoder._build_summary_from_events(
        [
            {
                'type': 'user',
                'timestamp': '2026-05-28T14:34:00Z',
                'message': {'content': 'hello'},
            },
            {
                'type': 'assistant',
                'timestamp': '2026-05-28T14:34:05Z',
                'message': {'content': [{'type': 'text', 'text': 'hi'}]},
            },
        ],
        '26ecb12d-3026-4890-bae6-9429b1a84d16',
        '/tmp/project',
    )

    assert summary.model == 'Qwen-3.6-Plus'


def test_current_selector_fallback_does_not_fabricate_for_short_cache_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """缓存短 id 仍需逐会话映射."""
    app_support = tmp_path / 'Qoder'
    _write_qoder_state(app_support, 'custom:model_123')
    monkeypatch.setenv('QODER_APP_SUPPORT_DIR', str(app_support))
    qoder._load_qoder_custom_model_names.cache_clear()
    qoder._load_qoder_model_selector_names.cache_clear()
    qoder._load_qoder_current_assistant_model.cache_clear()
    qoder._build_qoder_session_model_map.cache_clear()

    assert qoder._infer_qoder_model_for_session('26ecb12d') == ''
