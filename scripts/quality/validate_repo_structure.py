#!/usr/bin/env python3
"""Deterministic repo health gate: validate that hook/quality/spec structure is properly installed."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

# Ensure repo root on sys.path when run directly.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# 01. 必需路径
REQUIRED_PATHS = [
    ".claude/settings.json",
    ".claude/hooks/stop.sh",
    "scripts/claude_hooks/main.py",
    "scripts/claude_hooks/hook_io.py",
    "scripts/claude_hooks/classify.py",
    "scripts/claude_hooks/evidence.py",
    "scripts/quality/run_quality_gate.py",
    "scripts/quality/quality_targets.py",
    "scripts/quality/quality_artifact.py",
    "scripts/quality/validate_acceptance_contracts.py",
    "scripts/harness/agent_stop_check.py",
    "harness/README.md",
    "harness/agent-runtime.md",
    "docs/acceptance-contracts/README.md",
    ".codex/hooks/stop_check.sh",
    ".qoder/hooks/stop_check.sh",
    "tmp/.gitkeep",
]


# 02. 不应被 git 跟踪的运行态路径
GENERATED_PREFIXES = [
    "tmp/agent_logs/",
    ".agent/",
    "data/",
    "output/",
    ".venv/",
    ".pytest_cache/",
]


# 03. git tracked 检查
def git_tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=root, text=True, stderr=subprocess.DEVNULL)
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return []


# 04. 主校验
def validate(root: Path) -> list[str]:
    failures: list[str] = []

    for rel in REQUIRED_PATHS:
        if not (root / rel).exists():
            failures.append(f"缺少必需路径：{rel}")

    tracked = git_tracked_files(root)
    for item in tracked:
        if any(item == p.rstrip("/") or item.startswith(p) for p in GENERATED_PREFIXES):
            # tmp/.gitkeep 允许被 tracked；tmp/agent_logs 不允许。
            if item != "tmp/.gitkeep":
                failures.append(f"运行态/生成物不应进入 git tracked：{item}")
        if item.endswith((".sqlite", ".sqlite3", ".db")):
            failures.append(f"数据库文件不应进入 git tracked：{item}")

    return failures


# 05. CLI
def main() -> int:
    root = Path.cwd()
    failures = validate(root)
    if failures:
        for item in failures:
            print(f"[FAIL] {item}")
        return 1
    print("validate_repo_structure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
