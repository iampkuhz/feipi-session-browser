"""Session Evidence collectors 测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from session_browser.attribution.collectors.session.current_user_message import (
    extract_current_user_message,
)
from session_browser.attribution.collectors.session.jsonl_reader import read_jsonl_events
from session_browser.attribution.collectors.session.llm_call_locator import (
    find_preceding_events,
    locate_call_boundary,
)


def _write_jsonl(events: list[dict]) -> str:
    """写入临时 JSONL 文件，返回路径。"""
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
    for ev in events:
        tmp.write(json.dumps(ev) + '\n')
    tmp.close()
    return tmp.name


class TestJsonlReader:
    def test_read_valid_jsonl(self):
        path = _write_jsonl(
            [{'type': 'user', 'content': 'hello'}, {'type': 'assistant', 'content': 'hi'}]
        )
        try:
            events = read_jsonl_events(path)
            assert len(events) == 2
            assert events[0]['type'] == 'user'
            assert events[1]['type'] == 'assistant'
        finally:
            Path(path).unlink()

    def test_read_missing_file(self):
        events = read_jsonl_events('/nonexistent/path/file.jsonl')
        assert events == []

    def test_read_invalid_json_line(self):
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        tmp.write('{"type": "user"}\n')
        tmp.write('NOT JSON\n')
        tmp.write('{"type": "assistant"}\n')
        tmp.close()
        try:
            events = read_jsonl_events(tmp.name)
            assert len(events) == 2  # 跳过无效行
        finally:
            Path(tmp.name).unlink()


class TestLlmCallLocator:
    def test_locate_existing_call(self):
        events = [
            {'id': 'call-001', 'type': 'user_message'},
            {'id': 'call-001', 'type': 'llm_request'},
            {'id': 'call-002', 'type': 'user_message'},
        ]
        start, end = locate_call_boundary(events, 'call-001')
        assert start == 0
        assert end == 1

    def test_locate_missing_call(self):
        events = [{'id': 'call-001'}]
        start, end = locate_call_boundary(events, 'call-999')
        assert start == -1
        assert end == -1

    def test_find_preceding_events(self):
        events = [
            {'id': 'call-001'},
            {'id': 'call-001'},
            {'id': 'call-002'},
            {'id': 'call-002'},
        ]
        preceding = find_preceding_events(events, 'call-002')
        assert len(preceding) == 2


class TestCurrentUserMessageExtractor:
    def test_extract_user_message(self):
        events = [
            {'id': 'call-001', 'role': 'user', 'content': 'Fix the bug', '_line': 5},
            {'id': 'call-001', 'role': 'assistant', 'content': 'OK'},
        ]
        ev = extract_current_user_message(events, 'call-001')
        assert ev is not None
        assert ev.kind == 'user_message'
        assert ev.scope == 'current_session'
        assert ev.precision == 'extracted'
        assert 'Fix the bug' in ev.text_preview

    def test_no_user_message(self):
        events = [{'id': 'call-001', 'role': 'assistant', 'content': 'OK'}]
        ev = extract_current_user_message(events, 'call-001')
        assert ev is None
