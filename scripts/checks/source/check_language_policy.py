"""检查维护策略文件的叙述语言是否符合中文优先约定。

这项检查保证共享规则对中文维护者清晰可读。公开入口是 ``check(arguments)``，失败表示选中的
策略文件含有应改写为中文的英文叙述。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import TYPE_CHECKING

from scripts.checks._framework import (
    CheckResult,
    add_changed_files_arg,
    argument_parser,
    repository_root,
)

REPO_ROOT = repository_root()

if TYPE_CHECKING:
    from pathlib import Path

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


def _normalize(path: str) -> str:
    """将 CLI、环境变量或 Git 输出中的路径统一为仓库相对形式。"""
    value = path.replace('\\', '/')
    while value.startswith('./'):
        value = value[2:]
    return value.strip('/')


def _glob_match(path: str, pattern: str) -> bool:
    """判断仓库相对路径是否匹配策略文件的 glob 模式。"""
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
    """判断路径是否属于语言策略的扫描范围。"""
    p = _normalize(path)
    if '__pycache__/' in p or p.startswith('tmp/'):
        return False
    return any(_glob_match(p, pattern) for pattern in POLICY_PATTERNS)


def _git_changed_files(root: Path) -> list[str]:
    """从 Git 工作区读取变更路径；Git 不可用时抛出异常，禁止把空扫描误报为通过。"""
    output = subprocess.check_output(
        ['git', 'status', '--short', '--untracked-files=all'],
        cwd=root,
        text=True,
        stderr=subprocess.DEVNULL,
    )

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
    """解析 changed-files JSON；缺失时返回 ``None``，无效输入抛错避免降级扫描。"""
    if not value:
        return None
    data = json.loads(value)
    if not isinstance(data, list):
        raise ValueError('changed-files 必须是 JSON array')
    return [_normalize(str(item)) for item in data if str(item).strip()]


def _target_files(root: Path, explicit_changed: str | None) -> list[Path]:
    """按显式输入、环境变量、Git 状态的顺序选择实际策略文件。"""
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
    """移除代码、链接、路径和技术标识，留下可用于语言判定的叙述文本。"""
    value = re.sub(r'`[^`]+`', ' ', text)
    value = re.sub(r'https?://\S+', ' ', value)
    value = re.sub(r'[\w./-]+\.(md|py|toml|json|yaml|yml|sh|css|js|html)\b', ' ', value, flags=re.I)
    value = re.sub(r'[/~.][\w./-]+', ' ', value)
    value = re.sub(r'\b[A-Z_]{2,}\b', ' ', value)
    return re.sub(r'\b[a-zA-Z]+[-_][\w-]+\b', ' ', value)


def _is_scalar_config_line(line: str) -> bool:
    """识别无需中文叙述的单值配置行。"""
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
    """判断一行是否包含达到阈值且没有中文主体的英文叙述。"""
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


def _check_file(path: Path) -> list[str]:
    """检查单个策略文件，代码围栏内的示例不参与语言判定。"""
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


def _run_check(root: Path, changed_files: str | None = None) -> list[str]:
    """检查选中的策略文件并汇总违规；无法解析 changed-files 时回退到 Git 状态。"""
    failures: list[str] = []
    for path in _target_files(root, changed_files):
        failures.extend(_check_file(path))
    return failures


def _self_test() -> None:
    """验证语言判定的关键正反例。"""
    assert _line_violates('Use this skill only for this repository.')
    assert _line_violates(
        'developer_instructions = "Run deterministic validation and report evidence."'
    )
    assert not _line_violates('默认使用简体中文, 命令名如 `pytest` 保持英文。')
    assert not _line_violates('model = "gpt-5.4-mini"')
    assert not _line_violates(
        '- Validation: `python3 scripts/gates/cli.py --target harness` passed.'
    )


def check(arguments: list[str]) -> CheckResult:
    """解析统一入口参数，执行自测或返回语言策略违规诊断。"""
    parser = argument_parser(description='检查仓库语言策略')
    add_changed_files_arg(parser)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(arguments)

    if args.self_test:
        _self_test()
        return CheckResult()

    try:
        return CheckResult.from_errors(_run_check(REPO_ROOT, args.changed_files))
    except (json.JSONDecodeError, ValueError) as exc:
        return CheckResult.execution_failure(
            [f'changed-files 输入无效: {exc}'], reason='input-unavailable'
        )
    except subprocess.SubprocessError as exc:
        return CheckResult.execution_failure(
            [f'Git 状态读取失败: {exc}'], reason='dependency-unavailable'
        )
    except OSError as exc:
        return CheckResult.execution_failure(
            [f'策略文件读取失败: {exc}'], reason='input-unavailable'
        )
