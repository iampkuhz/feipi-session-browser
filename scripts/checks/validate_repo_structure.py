#!/usr/bin/env python3
"""本模块负责执行 `validate_repo_structure` 对应的确定性仓库检查。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 直接运行时确保 repo root 位于 sys.path。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    '.claude/**',
    '.codex/**',
    '.github/workflows/**',
    '.pre-commit-config.yaml',
    'skills/**',
    '.agents/skills/**',
    '.qoder/**',
    'scripts/**/*.py',
    'scripts/**/*.sh',
    'AGENTS.md',
    'CLAUDE.md',
    'README.md',
    'pyproject.toml',
    'requirements*.txt',
    'requirements*.lock',
    'uv.lock',
    'docs/**',
]


# 01. 必需路径
REQUIRED_PATHS = [
    '.claude/settings.json',
    '.claude/hooks/stop.sh',
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
    'scripts/harness/stop_entry.py',
    'scripts/agent_runtime/stop/evidence.py',
    'scripts/agent_runtime/stop/model.py',
    'scripts/agent_runtime/stop/pipeline.py',
    'scripts/agent_runtime/stop/recovery.py',
    'scripts/agent_runtime/stop/report.py',
    'skills/authoring/feipi-openspec-orchestrate-change/SKILL.md',
    '.agents/skills/feipi-openspec-orchestrate-change',
    '.codex/skills/feipi-openspec-orchestrate-change',
    '.claude/skills/feipi-openspec-orchestrate-change',
    'harness/README.md',
    'harness/agent-runtime.md',
    'harness/context/repo-map.md',
    'harness/context/ui-context.md',
    'harness/workflow/change-lifecycle.md',
    'harness/workflow/subagent-execution.md',
    'harness/quality/deterministic-quality-gate.md',
    'harness/quality/quality-gate-matrix.md',
    'docs/acceptance-contracts/README.md',
    '.codex/hooks/stop_check.sh',
    '.qoder/hooks/stop_check.sh',
    'tmp/.gitkeep',
]


# 02. 不得被 git tracked 的运行态路径
GENERATED_PREFIXES = [
    'tmp/agent_logs/',
    '.agent/',
    'data/',
    'output/',
    '.venv/',
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
        return [line.strip() for line in out.splitlines() if line.strip()]
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
        if is_generated and item != 'tmp/.gitkeep':
            # tmp/.gitkeep 是 tmp 下唯一允许 tracked 的文件。
            failures.append(f'运行态/生成物不应进入 git tracked: {item}')
        if item.endswith(('.sqlite', '.sqlite3', '.db')):
            failures.append(f'数据库文件不应进入 git tracked: {item}')

    return failures


# 解析命令行参数并运行脚本入口。
def main() -> int:
    """返回：
    Zero 当 structure is 有效, 否则 one。
    """
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    for i, arg in enumerate(sys.argv):
        if arg == '--changed-files' and i + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[i + 1])
            break
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    root = Path.cwd()
    failures = validate(root)
    if failures:
        for item in failures:
            print(f'[FAIL] {item}')
        return 1
    print('validate_repo_structure PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
