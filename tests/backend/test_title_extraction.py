"""Tests for title extraction from Claude Code content."""

from session_browser.sources.claude import (
    _extract_readable_title,
    _summarize_text,
)


class TestTitleExtraction:
    """Test title extraction from various content patterns."""

    def test_command_envelope_with_args(self):
        content = (
            "<command-message>spec-research</command-message>"
            "<command-args>调研 nanopayment 的三种技术方案</command-args>"
        )
        title = _extract_readable_title(content)
        assert "spec-research" in title
        # The args text should be summarized
        assert "·" in title

    def test_command_envelope_without_args(self):
        content = "<command-message>fix-bug</command-message>"
        title = _extract_readable_title(content)
        assert title == "fix-bug"

    def test_normal_user_message(self):
        content = "帮我创建一个 tool，可以查看历史记录"
        title = _extract_readable_title(content)
        # Should summarize the text
        assert len(title) <= 80
        assert title != ""

    def test_empty_content(self):
        title = _extract_readable_title("")
        assert title == ""

    def test_very_long_content(self):
        content = "x" * 500
        title = _extract_readable_title(content)
        assert len(title) <= 80

    def test_content_with_sentence_boundary(self):
        content = "This is the first sentence. And this is the second one."
        title = _extract_readable_title(content)
        assert title == "This is the first sentence."

    def test_content_with_question(self):
        content = "What is the best approach? Let me explain."
        title = _extract_readable_title(content)
        assert title == "What is the best approach?"

    def test_command_envelope_with_text_after(self):
        content = (
            "<command-message>review</command-message>"
            "Please review the changes in the last commit."
        )
        title = _extract_readable_title(content)
        assert "review" in title
        assert "·" in title


class TestSummarizeText:
    """Test text summarization helper."""

    def test_short_text(self):
        text = "Hello world"
        result = _summarize_text(text)
        assert result == "Hello world"

    def test_long_text_truncated(self):
        text = "x" * 200
        result = _summarize_text(text, max_len=50)
        assert len(result) <= 50
        assert result.endswith("…")

    def test_xml_tags_stripped(self):
        text = "<tag>content</tag>"
        result = _summarize_text(text)
        assert "<" not in result
        assert ">" not in result

    def test_whitespace_normalized(self):
        text = "  hello   world  "
        result = _summarize_text(text)
        assert result == "hello world"

    def test_empty_text(self):
        result = _summarize_text("")
        assert result == ""
