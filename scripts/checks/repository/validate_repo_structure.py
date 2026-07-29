#!/usr/bin/env python3
"""本模块负责执行 `validate_repo_structure` 对应的确定性仓库检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __package__ in {None, ''}:
    # 该结构校验保留公开的文件路径入口；仅在直接执行时补齐 package import 根。
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.checks._framework import repository_root

REPO_ROOT = repository_root()


# 仓库运行和维护契约要求始终存在的路径。
REQUIRED_PATHS = [
    'scripts/gates/catalog.py',
    'scripts/gates/model.py',
    'scripts/gates/planner.py',
    'scripts/gates/cli.py',
    'scripts/gates/executor.py',
    'scripts/gates/report.py',
    'scripts/checks/repository/validate_acceptance_contracts.py',
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


def git_tracked_files(root: Path) -> list[str]:
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


def validate(root: Path) -> list[str]:
    """检查必需路径与禁入追踪的运行态文件，返回全部阻断性问题。"""
    failures: list[str] = []

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            failures.append(f'缺少必需路径: {rel}')

    tracked = git_tracked_files(root)
    for item in tracked:
        is_generated = any(
            item == prefix.rstrip('/') or item.startswith(prefix) for prefix in GENERATED_PREFIXES
        )
        if is_generated:
            failures.append(f'运行态/生成物不应进入 git tracked: {item}')
        if item.endswith(('.sqlite', '.sqlite3', '.db')):
            failures.append(f'数据库文件不应进入 git tracked: {item}')

    return failures


def main() -> int:
    """执行仓库结构检查；发现任一问题时返回失败。"""

    root = Path.cwd()
    failures = validate(root)
    if failures:
        for item in failures:
            print(f'[FAIL] {item}')
        return 1
    print('validate_repo_structure PASS')
    return 0
