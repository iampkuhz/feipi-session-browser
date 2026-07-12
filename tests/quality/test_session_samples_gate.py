from pathlib import Path

from scripts.checks.run_session_samples_gate import is_worktree_locator_drift


def _report(expected: str, actual: str, *, category: str = 'volatile_field') -> str:
    return f"""# Session Sample Drift Report

漂移条目总数: 1

### [{category}] $.diagnostics[0].locator
- **分类**: `{category}`
- **差异**: $.diagnostics[0].locator: 值不匹配，期望 \"{expected}\"，实际 \"{actual}\"
"""


def test_accepts_same_sample_suffix_locator_drift(tmp_path: Path) -> None:
    """同一样例后缀的 worktree locator 漂移可判定为环境路径漂移。"""
    suffix = 'codex/demo/rollout.jsonl'
    expected = f'/Users/example/main/docs/session-samples/{suffix}'
    actual = (tmp_path / 'docs' / 'session-samples' / suffix).as_posix()

    assert is_worktree_locator_drift(_report(expected, actual), tmp_path)


def test_rejects_non_locator_drift(tmp_path: Path) -> None:
    """非 locator 字段漂移不能被 gate wrapper 接受。"""
    report = """# Session Sample Drift Report

漂移条目总数: 1

### [unknown] $.messages[0].text
- **分类**: `unknown`
- **差异**: $.messages[0].text: 值不匹配，期望 \"a\"，实际 \"b\"
"""

    assert not is_worktree_locator_drift(report, tmp_path)


def test_rejects_different_sample_suffix(tmp_path: Path) -> None:
    """不同样例文件后缀说明不是单纯 worktree 绝对路径漂移。"""
    expected = '/Users/example/main/docs/session-samples/codex/demo/a.jsonl'
    actual = (tmp_path / 'docs' / 'session-samples' / 'codex/demo/b.jsonl').as_posix()

    assert not is_worktree_locator_drift(_report(expected, actual), tmp_path)
