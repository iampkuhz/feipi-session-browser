#!/usr/bin/env python3
"""中文注释检查器单元测试。"""
from __future__ import annotations
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).with_name('check_code_comment_language.py')
spec = importlib.util.spec_from_file_location('comment_checker', MODULE)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


class TestChecker(unittest.TestCase):
    """中文注释检查器的核心测试用例。"""

    def scan(self, source: str, forbidden: tuple[str, ...] = ()) -> set[str]:
        """辅助方法：将源码写入临时文件并扫描违规。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'X.java'
            p.write_text(source, encoding='utf-8')
            out: list[checker.Violation] = []
            for c in checker.extract(p):
                out.extend(checker.check(c, set(checker.TERMS), forbidden))
            return {x.code for x in out}

    def test_chinese_with_terms(self) -> None:
        """含中文和已知术语的 Javadoc 应当通过。"""
        self.assertEqual(
            set(),
            self.scan('/** 使用 Jackson 读取 JSON，并保持 session 顺序稳定。 */\nclass X {}'),
        )

    def test_english_fails(self) -> None:
        """纯英文 Javadoc 应当失败。"""
        self.assertIn(
            'COMMENT_NOT_CHINESE_DOMINANT',
            self.scan('/** Reads the session artifact from disk. */\nclass X {}'),
        )

    def test_string_marker_ignored(self) -> None:
        """字符串字面量中的注释样文本不应被提取。"""
        self.assertEqual(
            set(),
            self.scan('class X { String s = "// English"; }'),
        )

    def test_placeholder_fails(self) -> None:
        """占位注释（TODO 等）应当失败。"""
        self.assertIn(
            'COMMENT_LOW_INFORMATION',
            self.scan('/** TODO 待补充。 */\nclass X {}'),
        )

    def test_inheritdoc_fails(self) -> None:
        """仅包含 {@inheritDoc} 的 Javadoc 应当失败。"""
        self.assertIn(
            'INHERITDOC_WITHOUT_CHINESE',
            self.scan('/** {@inheritDoc} */\nclass X {}'),
        )

    def test_bad_translation_fails(self) -> None:
        """禁止的非规范术语翻译应当失败。"""
        self.assertIn(
            'TECH_TERM_NOT_CANONICAL',
            self.scan('/** 使用爪哇实现。 */\nclass X {}', ('爪哇',)),
        )

    def test_text_block_ignored(self) -> None:
        """Kotlin/Java text block 中的注释样文本不应被提取。"""
        source = 'class X {\n  String s = """\n  // English in text block\n  """;\n}'
        self.assertEqual(set(), self.scan(source))

    def test_block_comment_chinese_passes(self) -> None:
        """包含中文的块注释应当通过。"""
        self.assertEqual(
            set(),
            self.scan('/* 这是一个中文块注释。 */\nclass X {}'),
        )

    def test_empty_comment_passes(self) -> None:
        """空注释不产生违规。"""
        self.assertEqual(set(), self.scan('/** */\nclass X {}'))


if __name__ == '__main__':
    unittest.main()
