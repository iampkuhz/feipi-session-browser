"""验证 ConversationRound 中时间线预览文本生成的测试。"""

from __future__ import annotations

import pytest

from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
)
from session_browser.web.session_detail.preview import (
    apply_round_preview,
    compact_preview_text,
    format_tool_counts,
)

# ── _compact_preview_text 辅助函数 ────────────────────────────────────


class TestCompactPreviewText:
    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_compresses_multiple_spaces(self):
        result = compact_preview_text('hello    world')
        assert result == 'hello world'

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_compresses_newlines(self):
        result = compact_preview_text('line1\nline2\nline3')
        assert result == 'line1 line2 line3'

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_compresses_mixed_whitespace(self):
        result = compact_preview_text('hello\t\tworld   ok')
        assert result == 'hello world ok'

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_strips_leading_trailing(self):
        result = compact_preview_text('  hello world  ')
        assert result == 'hello world'

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_truncates_at_limit(self):
        long_text = 'a' * 200
        result = compact_preview_text(long_text, limit=120)
        assert len(result) == 121  # 120 个字符 + 省略号
        assert result.endswith('…')

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_no_truncation_under_limit(self):
        text = 'short text'
        result = compact_preview_text(text, limit=120)
        assert result == 'short text'
        assert '…' not in result

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_empty_string(self):
        assert compact_preview_text('') == ''

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_none(self):
        assert compact_preview_text(None) == ''


# ── _format_tool_counts 辅助函数 ──────────────────────────────────────


class TestFormatToolCounts:
    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_empty_list(self):
        assert format_tool_counts([]) == ''

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_single_tool(self):
        tools = [ToolCall(name='Read')]
        result = format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>&times;1' in result

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_two_same_tools(self):
        tools = [ToolCall(name='Read'), ToolCall(name='Read')]
        result = format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>&times;2' in result

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_two_different_tools(self):
        tools = [ToolCall(name='Read'), ToolCall(name='Bash')]
        result = format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>&times;1' in result
        assert '<span class="preview-tool">Bash</span>&times;1' in result
        assert '·' in result

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_multiple_tools_with_counts(self):
        tools = [
            ToolCall(name='Read'),
            ToolCall(name='Bash'),
            ToolCall(name='Read'),
            ToolCall(name='Bash'),
            ToolCall(name='Edit'),
            ToolCall(name='Bash'),
        ]
        result = format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>&times;2' in result
        assert '<span class="preview-tool">Bash</span>&times;3' in result
        assert '<span class="preview-tool">Edit</span>&times;1' in result

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_tool_names_wrapped_in_spans(self):
        """工具名称现在包装在 preview-tool span 中以便 CSS 样式化。"""
        tools = [ToolCall(name='Read'), ToolCall(name='Bash')]
        result = format_tool_counts(tools)
        assert '<span class="preview-tool">Read</span>' in result
        assert '<span class="preview-tool">Bash</span>' in result


# ── presenter preview 场景 ─────────────────────────────────────


class TestComputePreviewLLMResponse:
    """优先级 1：LLM 响应文本 + 工具计数（如果存在）。"""

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_response_with_tools(self):
        assistant = ChatMessage(role='assistant', content='Let me check', timestamp='')
        user = ChatMessage(role='user', content='question', timestamp='')
        tools = [ToolCall(name='Read'), ToolCall(name='Bash')]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview='Let me check',
                tool_calls=tools,
            )
        ]
        apply_round_preview(r)
        # preview_text：仅文本，无工具徽章
        assert 'Let me check' in r.preview_text
        assert 'preview-tool' not in r.preview_text
        # 工具计数在 tool_summary_html 中
        assert '<span class="preview-tool">Read</span>&times;1' in r.tool_summary_html
        assert '<span class="preview-tool">Bash</span>&times;1' in r.tool_summary_html

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_response_truncated_when_long(self):
        long_response = 'word ' * 50  # 250 个字符
        assistant = ChatMessage(role='assistant', content=long_response, timestamp='')
        user = ChatMessage(role='user', content='question', timestamp='')
        tools = [ToolCall(name='Read')]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview=long_response,
                tool_calls=tools,
            )
        ]
        apply_round_preview(r)
        # preview_text：截断的响应，无工具徽章
        assert '…' in r.preview_text
        assert 'preview-tool' not in r.preview_text
        # 工具计数在 tool_summary_html 中
        assert '<span class="preview-tool">Read</span>&times;1' in r.tool_summary_html

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_response_long_with_no_tools(self):
        """当响应文本较长但没有工具时，预览显示截断的 assistant 内容。"""
        long_response = 'word ' * 50  # 250 个字符
        assistant = ChatMessage(role='assistant', content=long_response, timestamp='')
        user = ChatMessage(role='user', content='q', timestamp='')
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview=long_response,
            )
        ]
        apply_round_preview(r)
        # 有 assistant 内容 → 显示 assistant（截断）
        assert '…' in r.preview_text
        assert r.tool_summary_html == ''

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_user_input_only_when_no_tools(self):
        """当 assistant 内容为空时，预览回退到用户输入文本。"""
        assistant = ChatMessage(role='assistant', content='', timestamp='')
        user = ChatMessage(role='user', content='Please explain this', timestamp='')
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview='',
            )
        ]
        apply_round_preview(r)
        # 无 assistant 内容 + 无工具 → 显示用户输入
        assert 'Please explain this' in r.preview_text
        assert r.tool_summary_html == ''


class TestComputePreviewSubagent:
    """Subagent round 显示响应而非仅标签。"""

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_subagent_with_response_text(self):
        assistant = ChatMessage(role='assistant', content='', timestamp='')
        user = ChatMessage(role='user', content='task', timestamp='')
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [
            LLMCall(
                id='2',
                model='test',
                scope='subagent',
                subagent_id='agent-1',
                round_index=0,
                parent_id='1',
                parent_tool_name='Agent',
                timestamp='',
                status='ok',
                response_preview='Subagent found 3 files',
            )
        ]
        apply_round_preview(r)
        assert 'Subagent found 3 files' in r.preview_text

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_subagent_with_tools(self):
        assistant = ChatMessage(role='assistant', content='', timestamp='')
        user = ChatMessage(role='user', content='task', timestamp='')
        tools = [ToolCall(name='Read'), ToolCall(name='Read')]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [
            LLMCall(
                id='2',
                model='test',
                scope='subagent',
                subagent_id='agent-1',
                round_index=0,
                parent_id='1',
                parent_tool_name='Agent',
                timestamp='',
                status='ok',
                response_preview='Done',
                tool_calls=tools,
            )
        ]
        apply_round_preview(r)
        assert 'Done' in r.preview_text
        # 工具计数在 tool_summary_html 中，不在 preview_text 中
        assert 'preview-tool' not in r.preview_text
        assert '<span class="preview-tool">Read</span>&times;2' in r.tool_summary_html

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_subagent_no_response_text(self):
        assistant = ChatMessage(role='assistant', content='', timestamp='')
        user = ChatMessage(role='user', content='task', timestamp='')
        tools = [ToolCall(name='Bash')]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [
            LLMCall(
                id='2',
                model='test',
                scope='subagent',
                subagent_id='agent-1',
                round_index=0,
                parent_id='1',
                parent_tool_name='Agent',
                timestamp='',
                status='ok',
                response_preview='',
                tool_calls=tools,
            )
        ]
        apply_round_preview(r)
        assert 'Subagent' in r.preview_text
        assert 'Agent' in r.preview_text
        # 工具计数在 tool_summary_html 中
        assert '<span class="preview-tool">Bash</span>&times;1' in r.tool_summary_html
        assert 'preview-tool' not in r.preview_text


class TestComputePreviewFallback:
    """回退：当无 LLM 响应时使用用户输入文本。"""

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_user_input_only(self):
        assistant = ChatMessage(role='assistant', content='', timestamp='')
        user = ChatMessage(
            role='user', content='Please analyze this codebase for bugs', timestamp=''
        )
        r = ConversationRound(user_msg=user, assistant_msg=assistant)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview='',
            )
        ]
        apply_round_preview(r)
        assert 'Please analyze this codebase for bugs' in r.preview_text

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_tools_only(self):
        assistant = ChatMessage(role='assistant', content='', timestamp='')
        user = ChatMessage(role='user', content='', timestamp='')
        tools = [ToolCall(name='Read'), ToolCall(name='Bash')]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview='',
                tool_calls=tools,
            )
        ]
        apply_round_preview(r)
        # assistant 和 user 都为空 → 仅 tool_summary_html
        assert r.preview_text == ''
        assert '<span class="preview-tool">Read</span>&times;1' in r.tool_summary_html
        assert '<span class="preview-tool">Bash</span>&times;1' in r.tool_summary_html


class TestComputePreviewNoHTML:
    """预览文本渲染：模板必须使用转义输出，而非 | safe。"""

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_compact_preview_preserves_raw_text(self):
        """_compact_preview_text 仅压缩空白；不执行清理。"""
        text = 'use `<code>` here'
        result = compact_preview_text(text)
        # 该辅助函数只是压缩空白 — 保留原始文本
        assert '`<code>`' in result

    @pytest.mark.contract_case('UI-INTERACTION-008')
    def test_preview_text_from_integration(self):
        """集成测试：presenter preview 拆分文本和工具摘要。"""
        assistant = ChatMessage(role='assistant', content='See the code section', timestamp='')
        user = ChatMessage(role='user', content='task', timestamp='')
        tools = [ToolCall(name='Read')]
        r = ConversationRound(user_msg=user, assistant_msg=assistant, tool_calls=tools)
        r.interactions = [
            LLMCall(
                id='1',
                model='test',
                scope='main',
                subagent_id='',
                round_index=0,
                parent_id='',
                parent_tool_name='',
                timestamp='',
                status='ok',
                response_preview='See the code section',
                tool_calls=tools,
            )
        ]
        apply_round_preview(r)
        # preview_text：仅文本，无工具徽章
        assert 'See the code section' in r.preview_text
        assert 'preview-tool' not in r.preview_text
        # tool_summary_html：工具芯片
        assert '<span class="preview-tool">Read</span>&times;1' in r.tool_summary_html
