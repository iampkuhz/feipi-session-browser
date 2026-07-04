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
    """表示 TestChecker。
    """

    # 扫描目标文件。
    def scan(self, source: str, forbidden: tuple[str, ...] = ()) -> set[str]:
        """参数：
            source: 输入来源标识。
            forbidden: forbidden 参数。

        返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'X.java'
            p.write_text(source, encoding='utf-8')
            out: list[checker.Violation] = []
            for c in checker.extract(p):
                out.extend(checker.check(c, set(checker.TERMS), forbidden))
            return {x.code for x in out}

    # 维护扫描 脚本。
    def scan_script(self, source: str) -> set[str]:
        """参数：
            source: 输入来源标识。

        返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'tool.sh'
            p.write_text(source, encoding='utf-8')
            out: list[checker.Violation] = []
            for c in checker.extract_script_comments(p):
                out.extend(checker.check(c, set(checker.TERMS), ()))
            out.extend(checker.check_function_comments(p, set(checker.TERMS), ()))
            return {x.code for x in out}

    # 维护扫描 Python 脚本。
    def scan_python_script(self, source: str) -> set[str]:
        """参数：
            source: 输入来源标识。

        返回：
            解析后的 HookContext；失败时携带 parse_error。
        """
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'tool.py'
            p.write_text(source, encoding='utf-8')
            out: list[checker.Violation] = []
            for c in checker.extract_script_comments(p):
                out.extend(checker.check(c, set(checker.TERMS), ()))
            out.extend(checker.check_function_comments(p, set(checker.TERMS), ()))
            return {x.code for x in out}

    # 验证chinese terms。
    def test_chinese_with_terms(self) -> None:
        self.assertEqual(
            set(),
            self.scan('/** 使用 Jackson 读取 JSON，并保持 session 顺序稳定。 */\nclass X {}'),
        )

    # 验证english fails。
    def test_english_fails(self) -> None:
        self.assertIn(
            'COMMENT_NOT_CHINESE_DOMINANT',
            self.scan('/** Reads the session artifact from disk. */\nclass X {}'),
        )

    # 验证string marker ignored。
    def test_string_marker_ignored(self) -> None:
        self.assertEqual(
            set(),
            self.scan('class X { String s = "// English"; }'),
        )

    # 验证placeholder fails。
    def test_placeholder_fails(self) -> None:
        self.assertIn(
            'COMMENT_LOW_INFORMATION',
            self.scan('/** TODO 待补充。 */\nclass X {}'),
        )

    # 验证inheritdoc fails。
    def test_inheritdoc_fails(self) -> None:
        self.assertIn(
            'INHERITDOC_WITHOUT_CHINESE',
            self.scan('/** {@inheritDoc} */\nclass X {}'),
        )

    # 验证bad translation fails。
    def test_bad_translation_fails(self) -> None:
        self.assertIn(
            'TECH_TERM_NOT_CANONICAL',
            self.scan('/** 使用爪哇实现。 */\nclass X {}', ('爪哇',)),
        )

    # 验证文本 阻断 ignored。
    def test_text_block_ignored(self) -> None:
        source = 'class X {\n  String s = """\n  // English in text block\n  """;\n}'
        self.assertEqual(set(), self.scan(source))

    # 验证阻断 注释 chinese passes。
    def test_block_comment_chinese_passes(self) -> None:
        self.assertEqual(
            set(),
            self.scan('/* 这是一个中文块注释。 */\nclass X {}'),
        )

    # 验证空 注释 passes。
    def test_empty_comment_passes(self) -> None:
        self.assertEqual(set(), self.scan('/** */\nclass X {}'))

    # 验证脚本 chinese 注释 terms passes。
    def test_script_chinese_comment_with_terms_passes(self) -> None:
        self.assertEqual(
            set(),
            self.scan_script('# Stop hook 读取 JSON evidence，并按 session_id 归因。\n'),
        )

    # 验证脚本 english 注释 fails。
    def test_script_english_comment_fails(self) -> None:
        self.assertIn(
            'COMMENT_NOT_CHINESE_DOMINANT',
            self.scan_script('# Record changed files for stop hook evidence.\n'),
        )

    # 验证脚本 chinese prefix cannot hide english body。
    def test_script_chinese_prefix_cannot_hide_english_body(self) -> None:
        self.assertIn(
            'COMMENT_ENGLISH_FRAGMENT',
            self.scan_script(
                '# 说明：Record changed files for stop hook evidence。'
            ),
        )

    # 验证脚本 directives ignored。
    def test_script_directives_are_ignored(self) -> None:
        self.assertEqual(
            set(),
            self.scan_script(
                '#!/usr/bin/env bash\n'
                '# shellcheck disable=SC2034\n'
                '# noqa: E501\n'
                '# pragma: no cover\n'
            ),
        )

    # 验证shell 函数 requires chinese 注释。
    def test_shell_function_requires_chinese_comment(self) -> None:
        self.assertIn(
            'FUNCTION_COMMENT_MISSING',
            self.scan_script('run_check() {\n  echo ok\n}\n'),
        )
        self.assertEqual(
            set(),
            self.scan_script('# 运行 check 命令。\nrun_check() {\n  echo ok\n}\n'),
        )

    # 验证Python 函数 accepts chinese docstring 注释。
    def test_python_function_accepts_chinese_docstring_or_comment(self) -> None:
        self.assertIn(
            'FUNCTION_COMMENT_MISSING',
            self.scan_python_script('def run_check():\n    return True\n'),
        )
        self.assertEqual(
            set(),
            self.scan_python_script(
                '# 运行 check 命令。\ndef run_check():\n    return True\n'
            ),
        )
        self.assertIn(
            'COMMENT_NOT_CHINESE_DOMINANT',
            self.scan_python_script('def run_check():\n    """Run check."""\n    return True\n'),
        )
        violations = self.scan_python_script(
            'def run_check():\n    """运行 check 命令。"""\n    return True\n'
        )
        self.assertIn('FUNCTION_COMMENT_MISSING', violations)
        self.assertIn('FUNCTION_DOCSTRING_SUMMARY_IN_BODY', violations)
        self.assertEqual(
            set(),
            self.scan_python_script(
                '# 运行 check 命令。\n'
                'def run_check(path: str) -> bool:\n'
                '    """参数：\n'
                '        path: 待检查的路径。\n'
                '\n'
                '    返回：\n'
                '        满足条件时返回 true，否则返回 false。\n'
                '    """\n'
                '    return bool(path)\n'
            ),
        )

    # 验证Python docstring english 章节 still fail。
    def test_python_docstring_english_sections_still_fail(self) -> None:
        violations = self.scan_python_script(
            '# 运行 check 命令。\n'
            'def run_check(path):\n'
            '    """Args:\n'
            '        path: Path to inspect.\n'
            '\n'
            '    Returns:\n'
            '        Boolean result.\n'
            '    """\n'
            '    return True\n'
        )

        self.assertIn('DOCSTRING_ENGLISH_SECTION_LABEL', violations)
        self.assertIn('COMMENT_NOT_CHINESE_DOMINANT', violations)

    # 验证filter changed-files 路径 limits roots。
    def test_filter_changed_paths_limits_to_roots(self) -> None:
        self.assertEqual(
            ['scripts/tool.py', '.claude/hooks/stop.sh'],
            checker.filter_changed_paths(
                ['scripts', '.claude/hooks'],
                ['scripts/tool.py', '.claude/hooks/stop.sh', 'tests/test_tool.py'],
            ),
        )


if __name__ == '__main__':
    unittest.main()
