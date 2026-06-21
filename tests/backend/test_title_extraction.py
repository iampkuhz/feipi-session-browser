"""测试从 Claude Code 内容中提取标题."""

import pytest

from session_browser.sources.claude import (
    _extract_readable_title,
    _summarize_text,
)

MAX_TITLE_LENGTH = 80
VERY_LONG_CONTENT_LENGTH = 500
LONG_TEXT_LENGTH = 200
SUMMARY_LIMIT = 50


class TestTitleExtraction:
    """测试从各种内容模式中提取标题."""

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_command_envelope_with_args(self):
        content = (
            '<command-message>spec-research</command-message>'
            '<command-args>调研 nanopayment 的三种技术方案</command-args>'
        )
        title = _extract_readable_title(content)
        assert 'spec-research' in title
        # 参数字段文本应被摘要
        assert '·' in title

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_command_envelope_without_args(self):
        content = '<command-message>fix-bug</command-message>'
        title = _extract_readable_title(content)
        assert title == 'fix-bug'

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_normal_user_message(self):
        content = '帮我创建一个 tool,可以查看历史记录'
        title = _extract_readable_title(content)
        # 应摘要化文本
        assert len(title) <= MAX_TITLE_LENGTH
        assert title != ''

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_empty_content(self):
        title = _extract_readable_title('')
        assert title == ''

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_very_long_content(self):
        content = 'x' * VERY_LONG_CONTENT_LENGTH
        title = _extract_readable_title(content)
        assert len(title) <= MAX_TITLE_LENGTH

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_content_with_sentence_boundary(self):
        content = 'This is the first sentence. And this is the second one.'
        title = _extract_readable_title(content)
        assert title == 'This is the first sentence.'

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_content_with_question(self):
        content = 'What is the best approach? Let me explain.'
        title = _extract_readable_title(content)
        assert title == 'What is the best approach?'

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_command_envelope_with_text_after(self):
        content = (
            '<command-message>review</command-message>Please review the changes in the last commit.'
        )
        title = _extract_readable_title(content)
        assert 'review' in title
        assert '·' in title


class TestSummarizeText:
    """测试文本摘要辅助函数."""

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_short_text(self):
        text = 'Hello world'
        result = _summarize_text(text)
        assert result == 'Hello world'

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_long_text_truncated(self):
        text = 'x' * LONG_TEXT_LENGTH
        result = _summarize_text(text, max_len=SUMMARY_LIMIT)
        assert len(result) <= SUMMARY_LIMIT
        assert result.endswith('…')

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_xml_tags_stripped(self):
        text = '<tag>content</tag>'
        result = _summarize_text(text)
        assert '<' not in result
        assert '>' not in result

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_whitespace_normalized(self):
        text = '  hello   world  '
        result = _summarize_text(text)
        assert result == 'hello world'

    @pytest.mark.contract_case('DATA-SOURCE-015')
    def test_empty_text(self):
        result = _summarize_text('')
        assert result == ''
