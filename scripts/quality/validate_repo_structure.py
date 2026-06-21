#!/usr/bin/env python3
"""Validate installed hook, quality, spec, and runtime-data structure.

This deterministic repo health gate is triggered by required quality runs and
workflow/harness changes. It fails when required entry points are missing, when
runtime/generated paths are tracked by git, or when database files enter source
control. A git query failure is tolerated as an empty tracked-file list so direct
local structure checks remain usable outside a git checkout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure repo root on sys.path when run directly.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# 01. Required paths
REQUIRED_PATHS = [
    '.claude/settings.json',
    '.claude/hooks/stop.sh',
    'scripts/claude_hooks/main.py',
    'scripts/claude_hooks/hook_io.py',
    'scripts/claude_hooks/classify.py',
    'scripts/claude_hooks/evidence.py',
    'scripts/quality/run_quality_gate.py',
    'scripts/quality/quality_targets.py',
    'scripts/quality/quality_artifact.py',
    'scripts/quality/validate_acceptance_contracts.py',
    'scripts/harness/agent_stop_check.py',
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


# 02. Runtime paths that must not be tracked by git
GENERATED_PREFIXES = [
    'tmp/agent_logs/',
    '.agent/',
    'data/',
    'output/',
    '.venv/',
    '.pytest_cache/',
]


# 03. git tracked check
def git_tracked_files(root: Path) -> list[str]:
    """Return git-tracked files under the repository root.

    Args:
        root: Repository root used as the git working directory.

    Returns:
        Tracked file paths relative to `root`. If git is unavailable or the
        directory is not a checkout, returns an empty list.
    """
    try:
        out = subprocess.check_output(
            ['git', 'ls-files'], cwd=root, text=True, stderr=subprocess.DEVNULL
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return []


# 04. Main validation
def validate(root: Path) -> list[str]:
    """Validate required paths and forbidden tracked runtime artifacts.

    Args:
        root: Repository root to inspect.

    Returns:
        Blocking failure messages. An empty list means the repo structure gate passes.
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
            # tmp/.gitkeep is the only allowed tracked file under tmp.
            failures.append(f'运行态/生成物不应进入 git tracked: {item}')
        if item.endswith(('.sqlite', '.sqlite3', '.db')):
            failures.append(f'数据库文件不应进入 git tracked: {item}')

    return failures


# 05. CLI
def main() -> int:
    """Run the repository structure quality gate from the command line.

    Returns:
        Zero when the structure is valid, otherwise one.
    """
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
