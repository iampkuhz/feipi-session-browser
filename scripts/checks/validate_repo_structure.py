#!/usr/bin/env python3
"""本模块负责执行 `validate_repo_structure` 对应的确定性仓库检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.checks._framework import repository_root

# 直接运行时确保 repo root 位于 sys.path。
REPO_ROOT = repository_root()


# 01. 必需路径
REQUIRED_PATHS = [
    '.claude/settings.json',
    'scripts/harness/hook_dispatch.py',
    'scripts/agent_runtime/hook_entry.py',
    'scripts/agent_runtime/context.py',
    'scripts/gates/catalog.py',
    'scripts/gates/model.py',
    'scripts/gates/planner.py',
    'scripts/gates/cli.py',
    'scripts/gates/executor.py',
    'scripts/gates/receipt.py',
    'scripts/gates/report.py',
    'scripts/agent_runtime/events/evidence.py',
    'scripts/checks/validate_acceptance_contracts.py',
    'scripts/harness/change.py',
    'scripts/agent_runtime/stop/evidence.py',
    'scripts/agent_runtime/change/controller.py',
    'scripts/agent_runtime/change/model.py',
    'scripts/agent_runtime/change/store.py',
    'scripts/agent_runtime/change/runtime.py',
    'scripts/agent_runtime/change/candidate.py',
    'scripts/agent_runtime/change/fixture.py',
    'scripts/agent_runtime/change/protocol.py',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'harness/README.md',
    'docs/agent-runtime.md',
    'docs/acceptance-contracts/README.md',
]


# 02. 不得被 git tracked 的运行态路径
GENERATED_PREFIXES = [
    'tmp/',
    '.agent/',
    'data/',
    'output/',
    '.local/',
    '.pytest_cache/',
]


# 维护Git tracked 文件。
def git_tracked_files(root: Path) -> list[str]:
    """参数：
        root: 扫描根目录。

    返回：
        Tracked 文件路径s relative到`root`. 如果 git 不可用 或 the。 目录 is 不 checkout, 返回 空 列表。
    """
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


# 验证输入契约。
def validate(root: Path) -> list[str]:
    """参数：
        root: 扫描根目录。

    返回：
        阻断 失败项 messages. 空 列表 means repo structure gate passes。
    """
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


# 解析命令行参数并运行脚本入口。


def main() -> int:
    """返回：
    Zero 当 structure is 有效, 否则 one。
    """

    root = Path.cwd()
    failures = validate(root)
    if failures:
        for item in failures:
            print(f'[FAIL] {item}')
        return 1
    print('validate_repo_structure PASS')
    return 0
