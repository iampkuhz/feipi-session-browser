#!/usr/bin/env python3
"""提供 检查 language policy 脚本能力。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.checks._trigger import (  # noqa: E402
    add_changed_files_arg,
    parse_changed_files,
    skip_if_not_triggered,
)

TRIGGER_PATTERNS = [
    'AGENTS.md',
    'CLAUDE.md',
    'skills/**',
    '.agents/skills/**',
    '.codex/**',
    '.claude/agents/**',
    '.claude/skills/**',
    '.qoder/**',
    'harness/**',
    'openspec/changes/**',
    'scripts/checks/check_language_policy.py',
]

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


# 规范化注释文本。
def _normalize(path: str) -> str:
    """参数：
        path: 原始路径从CLI 输入, environment JSON, 或 git 状态 输出。

    返回：
        normalize 字符串。
    """
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


# 维护glob 匹配。
def _glob_match(path: str, pattern: str) -> bool:
    """参数：
        path: 待检查的路径。
        pattern: Policy 路径 pattern从``POLICY_PATTERNS``。

    返回：
        满足条件时返回 true，否则返回 false。
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


# 判断是否policy 路径。
def _is_policy_path(path: str) -> bool:
    """参数：
        path: 待检查的路径。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    p = _normalize(path)
    if '__pycache__/' in p or p.startswith('tmp/'):
        return False
    return any(_glob_match(p, pattern) for pattern in POLICY_PATTERNS)


# 维护Git changed-files 文件。
def _git_changed_files(root: Path) -> list[str]:
    """参数：
        root: 扫描根目录。

    返回：
        结果列表。
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


# 解析changed-files 文件。
def _parse_changed_files(value: str | None) -> list[str] | None:
    """参数：
        value: JSON array 字符串 supplied by ``--changed-文件`` 或。

    返回：
        规范化 文件路径s, ``None`` 当 payload 缺失 或 无效。
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


# 维护target 文件。
def _target_files(root: Path, explicit_changed: str | None) -> list[Path]:
    """参数：
        root: 扫描根目录。
        explicit_changed: 显式传入的 changed-files 列表。

    返回：
        结果列表。
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


# 维护去除 noise。
def _strip_noise(text: str) -> str:
    """参数：
        text: 待检查的文本。

    返回：
        strip noise 字符串。
    """
    value = re.sub(r'`[^`]+`', ' ', text)
    value = re.sub(r'https?://\S+', ' ', value)
    value = re.sub(r'[\w./-]+\.(md|py|toml|json|yaml|yml|sh|css|js|html)\b', ' ', value, flags=re.I)
    value = re.sub(r'[/~.][\w./-]+', ' ', value)
    value = re.sub(r'\b[A-Z_]{2,}\b', ' ', value)
    return re.sub(r'\b[a-zA-Z]+[-_][\w-]+\b', ' ', value)


# 判断是否标量 配置 行。
def _is_scalar_config_line(line: str) -> bool:
    """参数：
        line: 待检查的源码行。

    返回：
        满足条件时返回 true，否则返回 false。
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


# 维护行 violates。
def _line_violates(line: str) -> bool:
    """参数：
        line: 原始行从a target policy document。

    返回：
        满足条件时返回 true，否则返回 false。
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


# 检查文件。
def check_file(path: Path) -> list[str]:
    """参数：
        path: 现有 repository 文件 selected by ``运行_check``。

    返回：
        结果列表。
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


# 运行检查。
def run_check(root: Path, changed_files: str | None = None) -> list[str]:
    """参数：
        root: repo root used用于changed-文件 discovery 和 路径 输出。
        changed_files: 待检查的文件列表。

    返回：
        失败项 messages. 空 列表 means gate passes。
    """
    failures: list[str] = []
    for path in _target_files(root, changed_files):
        failures.extend(check_file(path))
    return failures


# 运行脚本自测试场景。
def _self_test() -> None:
    assert _line_violates('Use this skill only for this repository.')
    assert _line_violates(
        'developer_instructions = "Run deterministic validation and report evidence."'
    )
    assert not _line_violates('默认使用简体中文, 命令名如 `pytest` 保持英文。')
    assert not _line_violates('model = "gpt-5.4-mini"')
    assert not _line_violates(
        '- Validation: `python3 scripts/gates/cli.py --target harness` passed.'
    )


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
    进程退出码。
    """
    parser = argparse.ArgumentParser(description='检查仓库语言策略')
    add_changed_files_arg(parser)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()

    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    skip_if_not_triggered(parse_changed_files(args.changed_files), TRIGGER_PATTERNS)

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
