"""测试 routes.py 中的轮次构建和 token 提取.

验证 _make_round 是否正确提取所有提供逐消息用量信息的
agent(claude_code,qoder,codex)的 token 数据.
"""

from __future__ import annotations

import pytest

from session_browser.domain.models import ChatMessage
from session_browser.web.presenters.session_detail import _make_round


def _assistant_msg(usage: dict | None = None, llm_call_id: str = 'msg-1') -> ChatMessage:
    return ChatMessage(
        role='assistant',
        content='test response',
        timestamp='2025-01-01T00:00:00+00:00',
        usage=usage,
        llm_call_id=llm_call_id,
    )


USER_MSG = ChatMessage(role='user', content='hello', timestamp='2025-01-01T00:00:00+00:00')

USAGE_CLAUDE = {
    'input_tokens': 100,
    'output_tokens': 50,
    'cache_read_input_tokens': 200,
    'cache_creation_input_tokens': 300,
}
CLAUDE_INPUT_TOKENS = 100
CLAUDE_OUTPUT_TOKENS = 50
CLAUDE_CACHE_READ_TOKENS = 200
CLAUDE_CACHE_WRITE_TOKENS = 300
TOTAL_TOKENS = 650
MAX_SESSION_TOKENS = 1000
QODER_ESTIMATED_INPUT = 500
QODER_ESTIMATED_OUTPUT = 200
QODER_ESTIMATED_TOTAL = 700


class TestMakeRoundTokenExtraction:
    """验证 _make_round 为带逐消息用量的 agent 提取 token 信息."""

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_claude_code_extracts_tokens(self):
        r = _make_round(
            USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], MAX_SESSION_TOKENS, 'claude_code'
        )
        assert r.total_tokens == TOTAL_TOKENS
        assert r.token_ratio == pytest.approx(TOTAL_TOKENS / MAX_SESSION_TOKENS)

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_qoder_extracts_tokens(self):
        """Qoder 的 token 提取方式应与 Claude Code 一致."""
        r = _make_round(
            USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], MAX_SESSION_TOKENS, 'qoder'
        )
        assert r.total_tokens == TOTAL_TOKENS
        assert r.token_ratio == pytest.approx(TOTAL_TOKENS / MAX_SESSION_TOKENS)

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_codex_token_extraction(self):
        """Codex cached_input_tokens 是 input_tokens 子集,不应重复计入总量."""
        codex_usage = {
            'input_tokens': QODER_ESTIMATED_INPUT,
            'output_tokens': 150,
            'cached_input_tokens': 200,
        }
        r = _make_round(
            USER_MSG, _assistant_msg(usage=codex_usage), [], MAX_SESSION_TOKENS, 'codex'
        )
        assert r.total_tokens == TOTAL_TOKENS
        assert r.token_ratio == pytest.approx(TOTAL_TOKENS / MAX_SESSION_TOKENS)

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_qoder_no_usage_dict(self):
        """Qoder 无用量字典时 token 应为零."""
        r = _make_round(USER_MSG, _assistant_msg(usage=None), [], MAX_SESSION_TOKENS, 'qoder')
        assert r.total_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_qoder_empty_usage_dict(self):
        """Qoder 空用量字典时 token 应为零."""
        r = _make_round(USER_MSG, _assistant_msg(usage={}), [], MAX_SESSION_TOKENS, 'qoder')
        assert r.total_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_qoder_estimated_usage(self):
        """Qoder 带估算用量时,token 提取方式应与 Claude Code 一致."""
        estimated_usage = {
            'input_tokens': QODER_ESTIMATED_INPUT,
            'output_tokens': QODER_ESTIMATED_OUTPUT,
            'cache_read_input_tokens': 0,
            'cache_creation_input_tokens': 0,
            'estimated': True,
            'estimation_method': 'qoder-fast-bytes-v1',
        }
        r = _make_round(
            USER_MSG, _assistant_msg(usage=estimated_usage), [], MAX_SESSION_TOKENS, 'qoder'
        )
        assert r.total_tokens == QODER_ESTIMATED_TOTAL
        assert r.token_ratio == pytest.approx(QODER_ESTIMATED_TOTAL / MAX_SESSION_TOKENS)
        # 估算用量的 cache 字段应为 0
        assert r.input_tokens == QODER_ESTIMATED_INPUT
        assert r.output_tokens == QODER_ESTIMATED_OUTPUT
        assert r.cached_tokens == 0
        assert r.cache_write_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_claude_no_usage_dict(self):
        """Claude 无用量字典时 token 应为零."""
        r = _make_round(USER_MSG, _assistant_msg(usage=None), [], MAX_SESSION_TOKENS, 'claude_code')
        assert r.total_tokens == 0

    @pytest.mark.contract_case('DATA-PRESENTER-005')
    def test_token_breakdown_method_uses_usage_dict(self):
        """ConversationRound.token_breakdown() 直接从 usage 读取.

        直接从 assistant_msg.usage 读取,
        因此即使 total_tokens 为 0,Qoder 也应正常工作.
        """
        r = _make_round(
            USER_MSG, _assistant_msg(usage=USAGE_CLAUDE), [], MAX_SESSION_TOKENS, 'qoder'
        )
        bd = r.token_breakdown()
        assert bd['input'] == CLAUDE_INPUT_TOKENS
        assert bd['output'] == CLAUDE_OUTPUT_TOKENS
        assert bd['cache_read'] == CLAUDE_CACHE_READ_TOKENS
        assert bd['cache_write'] == CLAUDE_CACHE_WRITE_TOKENS
