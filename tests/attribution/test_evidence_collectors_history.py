"""History Evidence collectors 测试。"""

from __future__ import annotations

from session_browser.attribution.collectors.history.prior_messages_extractor import (
    extract_prior_messages,
)
from session_browser.attribution.collectors.history.prior_tool_results_extractor import (
    extract_prior_tool_results,
)


class TestPriorMessagesExtractor:
    def test_extract_prior_messages(self):
        messages = [
            {'role': 'user', 'content': 'Hello'},
            {'role': 'assistant', 'content': 'Hi there'},
            {'role': 'user', 'content': 'Current message'},  # boundary at index 2
        ]
        results = extract_prior_messages(messages, call_boundary_index=2)
        assert len(results) == 2
        assert results[0].scope == 'prior_session'
        assert results[0].kind == 'conversation_history'
        assert 'Hello' in results[0].text_preview

    def test_empty_messages(self):
        results = extract_prior_messages([], call_boundary_index=0)
        assert results == []

    def test_boundary_at_start(self):
        messages = [{'role': 'user', 'content': 'First'}]
        results = extract_prior_messages(messages, call_boundary_index=0)
        assert results == []

    def test_max_messages_limit(self):
        messages = [{'role': 'user', 'content': f'Message {i}'} for i in range(100)]
        results = extract_prior_messages(messages, call_boundary_index=100, max_messages=10)
        assert len(results) == 10  # 只取最后 10 条


class TestPriorToolResultsExtractor:
    def test_extract_prior_tool_results(self):
        messages = [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 't-001',
                        'content': [{'text': 'Result 1'}],
                    },
                ],
            },
            {'role': 'user', 'content': 'Current message'},
        ]
        results = extract_prior_tool_results(messages, call_boundary_index=2)
        assert len(results) == 1
        assert results[0].kind == 'tool_result'
        assert results[0].source_event_id == 't-001'

    def test_no_tool_results(self):
        messages = [{'role': 'user', 'content': 'Just text'}]
        results = extract_prior_tool_results(messages, call_boundary_index=1)
        assert results == []
