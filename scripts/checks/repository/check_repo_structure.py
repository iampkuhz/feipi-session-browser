#!/usr/bin/env python3
"""检查仓库必需路径以及 Git 追踪内容的结构边界。

该检查防止维护入口缺失，或运行态、数据库文件进入版本控制。唯一入口 ``check(arguments)``
返回按必需路径和 Git index 顺序排列的诊断；任一诊断都表示仓库结构不可发布。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.checks._framework import CheckResult, argument_parser

# 仓库运行和维护契约要求始终存在的路径。
REQUIRED_PATHS = [
    'scripts/gates/catalog.py',
    'scripts/gates/model.py',
    'scripts/gates/planner.py',
    'scripts/gates/cli.py',
    'scripts/gates/executor.py',
    'scripts/gates/report.py',
    'scripts/checks/repository/check_acceptance_contracts.py',
    'harness/agent-policy.manifest.yaml',
    'harness/skill-registry.yaml',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'harness/README.md',
    'docs/acceptance-contracts/README.md',
]


# 运行态或生成目录不得进入 Git 追踪。
GENERATED_PREFIXES = [
    'tmp/',
    '.agent/',
    'data/',
    'output/',
    '.local/',
    '.pytest_cache/',
]


def _git_tracked_files(root: Path) -> list[str]:
    """读取仍存在的 Git 追踪路径；Git 不可用或目录非 checkout 时返回空列表。"""
    try:
        out = subprocess.check_output(
            ['git', 'ls-files'], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
        return [
            line.strip()
            for line in out.splitlines()
            if line.strip() and (root / line.strip()).exists()
        ]
    except Exception:
        return []


def _validate(root: Path) -> list[str]:
    """检查必需路径与禁入追踪的运行态文件，返回全部阻断性问题。"""
    failures: list[str] = []

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            failures.append(f'缺少必需路径: {rel}')

    tracked = _git_tracked_files(root)
    for item in tracked:
        is_generated = any(
            item == prefix.rstrip('/') or item.startswith(prefix) for prefix in GENERATED_PREFIXES
        )
        if is_generated:
            failures.append(f'运行态/生成物不应进入 git tracked: {item}')
        if item.endswith(('.sqlite', '.sqlite3', '.db')):
            failures.append(f'数据库文件不应进入 git tracked: {item}')

    return failures


def check(arguments: list[str]) -> CheckResult:
    """解析仓库根目录并返回必需路径或 Git 追踪结构问题。"""
    parser = argument_parser(description='Validate repository structure.')
    parser.add_argument('--root', default='.', help='Repository root to inspect')
    args = parser.parse_args(arguments)
    return CheckResult.from_errors(
        f'[FAIL] {item}' for item in _validate(Path(args.root).resolve())
    )
