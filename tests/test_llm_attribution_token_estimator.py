"""Token estimator tests.

Verifies:
1. Token estimator returns stable output for Chinese, English, code, JSON.
2. Empty text returns 0.
3. Non-empty text returns >= 1.
4. Character classification helpers work correctly.
"""

import pytest

from session_browser.attribution.token_estimator import (
    estimate_tokens_from_text,
    estimate_tokens_from_list,
    count_cjk,
    count_ascii,
    count_code_punctuation,
)


def test_empty_text_returns_zero():
    assert estimate_tokens_from_text("") == 0
    assert estimate_tokens_from_text(None) == 0  # type: ignore
    assert estimate_tokens_from_text("   ") == 0  # only whitespace


def test_non_empty_returns_at_least_one():
    assert estimate_tokens_from_text("a") >= 1
    assert estimate_tokens_from_text("你好") >= 1
    assert estimate_tokens_from_text("{}") >= 1


def test_english_estimation():
    """English text should estimate ~4 chars/token."""
    text = "The quick brown fox jumps over the lazy dog."
    tokens = estimate_tokens_from_text(text)
    # ~44 chars / 4 ≈ 11 tokens
    assert 5 <= tokens <= 25, f"English tokens {tokens} out of range for '{text}'"


def test_chinese_estimation():
    """Chinese text should estimate ~1.8 chars/token."""
    text = "这是一个中文测试文本"
    tokens = estimate_tokens_from_text(text)
    # ~10 chars / 1.8 ≈ 6 tokens
    assert 3 <= tokens <= 20, f"Chinese tokens {tokens} out of range"


def test_code_estimation():
    """Code/JSON should estimate ~3 chars/token for punctuation."""
    text = '{"key": "value", "list": [1, 2, 3]}'
    tokens = estimate_tokens_from_text(text)
    assert tokens >= 1


def test_json_estimation():
    """JSON objects should be handled reasonably."""
    text = '{"name": "test", "value": 42, "nested": {"a": 1, "b": 2}}'
    tokens = estimate_tokens_from_text(text)
    assert tokens >= 1


def test_mixed_text_estimation():
    """Mixed Chinese/English text should produce reasonable estimate."""
    text = "Hello 世界! This is a mixed text 测试。"
    tokens = estimate_tokens_from_text(text)
    assert tokens >= 1


def test_code_block_estimation():
    """Code blocks with braces, brackets, etc. should work."""
    text = """
def hello():
    print("Hello, World!")
    return [1, 2, 3]
"""
    tokens = estimate_tokens_from_text(text)
    assert tokens >= 1


def test_count_cjk():
    assert count_cjk("你好世界") == 4
    assert count_cjk("hello") == 0
    assert count_cjk("hello 世界") == 2
    assert count_cjk("") == 0


def test_count_ascii():
    assert count_ascii("hello") == 5
    assert count_ascii("你好") == 0
    assert count_ascii("hi 好") == 3  # 'h', 'i', ' '
    assert count_ascii("") == 0


def test_count_code_punctuation():
    assert count_code_punctuation("{}()[]") == 6
    assert count_code_punctuation("hello") == 0
    assert count_code_punctuation('{"a": 1}') >= 4  # {, ", :, ", }


def test_estimate_tokens_from_list():
    """Estimate from a list of text fragments."""
    texts = ["hello", "world", "测试"]
    total = estimate_tokens_from_list(texts)
    assert total >= 1
    # Should be sum of individual estimates
    assert total == (estimate_tokens_from_text("hello")
                     + estimate_tokens_from_text("world")
                     + estimate_tokens_from_text("测试"))


def test_estimate_tokens_from_list_empty():
    assert estimate_tokens_from_list([]) == 0
    assert estimate_tokens_from_list(["", ""]) == 0


def test_model_parameter_ignored():
    """Model parameter is reserved for future use; should not change output."""
    text = "hello world test"
    t1 = estimate_tokens_from_text(text, model="")
    t2 = estimate_tokens_from_text(text, model="claude-sonnet-4")
    t3 = estimate_tokens_from_text(text, model="gpt-4")
    assert t1 == t2 == t3


def test_consistency():
    """Same input should always return same output (deterministic)."""
    text = "The quick brown fox 跳过 lazy dog {}"
    results = [estimate_tokens_from_text(text) for _ in range(10)]
    assert len(set(results)) == 1
