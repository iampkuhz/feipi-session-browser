#!/usr/bin/env python3
"""Language policy gate for Chinese-first agent and process documents."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

POLICY_PATTERNS = [
    'AGENTS.md',
    'CLAUDE.md',
    'skills/**/*.md',
    '.agents/skills/**/*.md',
    '.codex/skills/**/*.md',
    '.claude/skills/**/*.md',
    '.codex/agents/*.toml',
    '.codex/config.toml',
    '.codex/model-instructions.md',
    'harness/**/*.md',
    'openspec/changes/**/*.md',
]

ALLOWED_WORDS = {
    'agent',
    'agents',
    'api',
    'bash',
    'browser',
    'claude',
    'cli',
    'code',
    'codex',
    'css',
    'data',
    'detail',
    'gate',
    'git',
    'github',
    'gpt',
    'html',
    'id',
    'js',
    'json',
    'llm',
    'mcp',
    'mhtml',
    'openspec',
    'pytest',
    'python',
    'qoder',
    'session',
    'shall',
    'skill',
    'skills',
    'subagent',
    'subagents',
    'toml',
    'ui',
    'url',
    'yaml',
}

CJK_RE = re.compile(r'[\u3400-\u9fff]')
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
GIT_STATUS_PREFIX_LEN = 3
MIN_MEANINGFUL_ENGLISH_WORDS = 3


def _normalize(path: str) -> str:
    """Normalize a repository-relative path for policy glob matching.

    Args:
        path: Raw path from CLI input, environment JSON, or git status output.

    Returns:
        Slash-separated path without leading current-directory markers.
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def _glob_match(path: str, pattern: str) -> bool:
    """Match a normalized path against the gate's limited glob syntax.

    Args:
        path: Repository-relative path being considered by the quality gate.
        pattern: Policy path pattern from ``POLICY_PATTERNS``.

    Returns:
        True when the path should be checked by the language policy gate.
    """
    p = _normalize(path)
    pat = _normalize(pattern)
    regex = re.escape(pat)
    regex = regex.replace(r'\*\*', '\x00')
    regex = regex.replace(r'\*', '[^/]*')
    regex = regex.replace(r'\?', '.')
    regex = regex.replace('\x00/', '(?:.+/)?')
    regex = regex.replace('\x00', '.*')
    return bool(re.match(f'^{regex}$', p))


def _is_policy_path(path: str) -> bool:
    """Decide whether a changed file belongs to the language policy surface.

    Args:
        path: Repository-relative file path from the quality gate trigger.

    Returns:
        True when the file is a tracked policy, skill, OpenSpec, harness, or
        agent document and should be scanned for English narrative.
    """
    p = _normalize(path)
    if '__pycache__/' in p or p.startswith('tmp/'):
        return False
    return any(_glob_match(p, pattern) for pattern in POLICY_PATTERNS)


def _git_changed_files(root: Path) -> list[str]:
    """Read changed files from ``git status`` when no explicit trigger is passed.

    Args:
        root: Repository root used as the subprocess working directory.

    Returns:
        Normalized changed paths. Returns an empty list when git is unavailable
        or status cannot be read, which makes the gate a no-op.
    """
    try:
        output = subprocess.check_output(
            ['git', 'status', '--short', '--untracked-files=all'],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    files: list[str] = []
    for raw in output.splitlines():
        if not raw.strip():
            continue
        path = raw[GIT_STATUS_PREFIX_LEN:] if len(raw) > GIT_STATUS_PREFIX_LEN else raw.strip()
        if ' -> ' in path:
            path = path.split(' -> ', 1)[1]
        files.append(_normalize(path))
    return files


def _parse_changed_files(value: str | None) -> list[str] | None:
    """Parse a JSON changed-file payload from the CLI or environment.

    Args:
        value: JSON array string supplied by ``--changed-files`` or
            ``QUALITY_CHANGED_FILES``.

    Returns:
        Normalized file paths, ``None`` when the payload is absent or invalid.
    """
    if not value:
        return None
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    return [_normalize(str(item)) for item in data if str(item).strip()]


def _target_files(root: Path, explicit_changed: str | None) -> list[Path]:
    """Resolve changed policy files that currently exist on disk.

    Args:
        root: Repository root used to resolve relative changed paths.
        explicit_changed: Optional JSON array from the CLI.

    Returns:
        Sorted unique policy files. Missing files are ignored so deletions do
        not block unrelated quality gate runs.
    """
    changed = _parse_changed_files(explicit_changed)
    if changed is None:
        changed = _parse_changed_files(os.environ.get('QUALITY_CHANGED_FILES'))
    if changed is None:
        changed = _git_changed_files(root)

    result: list[Path] = []
    for rel in changed:
        if not _is_policy_path(rel):
            continue
        path = root / rel
        if path.is_file():
            result.append(path)
    return sorted(set(result))


def _strip_noise(text: str) -> str:
    """Remove code, paths, URLs, and identifiers before English word counting.

    Args:
        text: Single line from a policy document.

    Returns:
        Text with non-narrative tokens replaced by spaces.
    """
    value = re.sub(r'`[^`]+`', ' ', text)
    value = re.sub(r'https?://\S+', ' ', value)
    value = re.sub(r'[\w./-]+\.(md|py|toml|json|yaml|yml|sh|css|js|html)\b', ' ', value, flags=re.I)
    value = re.sub(r'[/~.][\w./-]+', ' ', value)
    value = re.sub(r'\b[A-Z_]{2,}\b', ' ', value)
    return re.sub(r'\b[a-zA-Z]+[-_][\w-]+\b', ' ', value)


def _is_scalar_config_line(line: str) -> bool:
    """Allow machine-readable scalar config assignments in agent TOML files.

    Args:
        line: Stripped document line under inspection.

    Returns:
        True when the line is a short config assignment rather than prose.
    """
    stripped = line.strip()
    if not re.match(r'^[A-Za-z0-9_.-]+\s*=', stripped):
        return False
    key, _, value = stripped.partition('=')
    key = key.strip()
    value = value.strip().strip('"')
    if key in {'description', 'developer_instructions'}:
        return False
    return len(value.split()) <= 1


def _line_violates(line: str) -> bool:
    """Check whether one document line violates the Chinese narrative policy.

    Args:
        line: Raw line from a target policy document.

    Returns:
        True when the line lacks CJK text and contains enough non-allowlisted
        English words to be treated as narrative.
    """
    stripped = line.strip()
    if not stripped or CJK_RE.search(stripped):
        return False
    if stripped in {'---', '+++'}:
        return False
    if stripped.startswith('|') and set(stripped) <= {'|', '-', ' ', ':'}:
        return False
    if _is_scalar_config_line(stripped):
        return False

    cleaned = _strip_noise(stripped)
    words = [w.lower().strip("'-") for w in WORD_RE.findall(cleaned)]
    meaningful = [w for w in words if w not in ALLOWED_WORDS]
    return len(meaningful) >= MIN_MEANINGFUL_ENGLISH_WORDS


def check_file(path: Path) -> list[str]:
    """Scan one policy file and return line-level language failures.

    Args:
        path: Existing repository file selected by ``run_check``.

    Returns:
        Human-readable failure lines with relative path and line number. Fenced
        code blocks are ignored because they often contain literal commands.
    """
    failures: list[str] = []
    in_fence = False
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    rel = path.relative_to(REPO_ROOT)
    for index, line in enumerate(lines, start=1):
        if line.strip().startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _line_violates(line):
            message = '英文叙述应改为中文, 英文术语请用反引号或混入中文说明'
            failures.append(f'{rel}:{index}: {message}: {line.strip()}')
    return failures


def run_check(root: Path, changed_files: str | None = None) -> list[str]:
    """Run the language policy gate for changed files.

    Args:
        root: Repository root used for changed-file discovery and path output.
        changed_files: Optional JSON array overriding environment and git
            discovery.

    Returns:
        Failure messages. An empty list means the gate passes.
    """
    failures: list[str] = []
    for path in _target_files(root, changed_files):
        failures.extend(check_file(path))
    return failures


def _self_test() -> None:
    """Exercise policy heuristics used by the quality gate self-test."""
    assert _line_violates('Use this skill only for this repository.')
    assert _line_violates(
        'developer_instructions = "Run deterministic validation and report evidence."'
    )
    assert not _line_violates('默认使用简体中文, 命令名如 `pytest` 保持英文。')
    assert not _line_violates('model = "gpt-5.4-mini"')
    assert not _line_violates(
        '- Validation: `python3 scripts/quality/run_quality_gate.py --target harness` passed.'
    )


def main() -> int:
    """Parse CLI arguments, run the gate, and return shell-style status.

    Returns:
        ``0`` when self-test or policy scan passes, otherwise ``1`` after
        printing every failure to stdout for hook and quality summaries.
    """
    parser = argparse.ArgumentParser(description='检查仓库语言策略')
    parser.add_argument(
        '--changed-files',
        default=None,
        help='JSON 数组; 省略时读取 QUALITY_CHANGED_FILES 或 git status',
    )
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print('language policy self-test PASS')
        return 0

    failures = run_check(REPO_ROOT, args.changed_files)
    if failures:
        print('language policy gate FAIL')
        for item in failures:
            print(f'[FAIL] {item}')
        return 1
    print('language policy gate PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
