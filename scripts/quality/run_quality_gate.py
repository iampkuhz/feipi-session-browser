#!/usr/bin/env python3
"""Deterministic quality gate runner.

按指定 target 运行质量门禁检查，并写入结构化 summary artifact。

用法:
    python3 scripts/quality/run_quality_gate.py --target session-detail --change-id fix-xyz
    python3 scripts/quality/run_quality_gate.py --target hook-runtime --change-id hook-runtime-selftest
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import time
import shutil

# 确保 repo_root 在 sys.path 中，使 `scripts.*` 导入在直接运行时可用。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.quality.quality_artifact import (
    GateDetail,
    QualitySummary,
    compute_overall,
    utc_now,
    write_quality_summary,
    PASS,
    FAIL,
    BLOCKED,
)
from scripts.quality.quality_targets import required_gates_for_target, applicable_gates_for_target, validate_target


# 01. 命令执行工具
def run_cmd(name: str, cmd: list[str], cwd: Path, required: bool = True) -> GateDetail:
    started = time.time()
    if not cmd or shutil.which(cmd[0]) is None:
        status = BLOCKED if required else FAIL
        return GateDetail(name=name, status=status, command=cmd, durationMs=0, output=f"命令不存在：{cmd[0] if cmd else '<empty>'}")

    # Playwright 测试在并行化后应在 20s 内完成，120s 足够
    timeout = 120 if cmd[:2] == ["npx", "playwright"] else 300

    try:
        proc = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        duration = int((time.time() - started) * 1000)
        output = (proc.stdout or "").strip()
        if len(output) > 4000:
            output = output[-4000:]
        return GateDetail(
            name=name,
            status=PASS if proc.returncode == 0 else FAIL,
            command=cmd,
            exitCode=proc.returncode,
            durationMs=duration,
            output=output,
        )
    except subprocess.TimeoutExpired as exc:
        return GateDetail(name=name, status=FAIL, command=cmd, durationMs=int((time.time() - started) * 1000), output=f"超时：{exc}")


# 02. gate 命令映射
def gate_command(gate: str, repo_root: Path, target: str) -> list[str]:
    if gate == "settingsJson":
        return ["python3", "-m", "json.tool", ".claude/settings.json"]
    if gate == "bashSyntax":
        shell_files = [
            ".claude/hooks/stop.sh",
            "scripts/harness/doctor.sh",
        ]
        existing = [f for f in shell_files if (repo_root / f).exists()]
        return ["bash", "-n", *existing] if existing else []
    if gate == "pythonCompile":
        paths = ["scripts/claude_hooks", "scripts/quality"]
        if target == "python-src":
            paths = ["src"]
        if target == "harness":
            paths = ["scripts/harness", "scripts/quality"]
        if target == "index":
            paths = ["src/session_browser/index", "scripts/quality/check_index_integrity.py"]
        return ["python3", "-m", "compileall", "-q", *paths]
    if gate == "hookSelfTest":
        return ["python3", "-m", "scripts.claude_hooks.main", "--self-test"]
    if gate == "templateContract":
        return ["python3", "scripts/quality/template_contract_check.py"]
    if gate == "staticCssContract":
        return ["python3", "scripts/quality/static_contract_check.py"]
    if gate == "cssOwnership":
        return ["python3", "scripts/quality/check_css_ownership.py"]
    if gate == "browserLayout":
        if (repo_root / "tests" / "playwright").exists() and (repo_root / "playwright.config.js").exists() and (repo_root / "node_modules").exists():
            return ["npx", "playwright", "test", "session-detail-layout", "shell-states"]
        return []
    if gate == "browserInteraction":
        if (repo_root / "tests" / "playwright").exists() and (repo_root / "playwright.config.js").exists() and (repo_root / "node_modules").exists():
            return ["npx", "playwright", "test", "session-detail.spec.js", "sessions-list.spec.js", "--grep-invert", "100 轮"]
        return []
    if gate == "pytest":
        test_candidates = {
            "session-detail": ["tests/ui/test_web_template_contract.py", "tests/ui/test_web_static_contract.py"],
            "python-src": ["tests"],
            "hook-runtime": [
                "tests/hooks/test_claude_hooks_hook_io.py",
                "tests/hooks/test_claude_hooks_classify.py",
                "tests/hooks/test_claude_hooks_bash_policy.py",
                "tests/hooks/test_claude_hooks_file_policy.py",
                "tests/hooks/test_claude_hooks_evidence.py",
                "tests/quality/test_quality_artifact.py",
            ],
            "index": ["tests/index/"],
        }
        items = [x for x in test_candidates.get(target, ["tests"]) if (repo_root / x).exists()]
        return ["pytest", "-q", *items] if items else []
    if gate == "doctor":
        return ["bash", "scripts/harness/doctor.sh"]
    if gate == "repoStructure":
        return ["python3", "scripts/quality/validate_repo_structure.py"]
    if gate == "harnessStructure":
        return ["python3", "scripts/harness/validate_harness_structure.py"]
    if gate == "openspecLayout":
        return ["python3", "scripts/harness/validate_openspec_layout.py"]
    if gate == "repoSlimming":
        return ["python3", "scripts/quality/repo_slimming_contract_check.py"]
    if gate == "indexIntegrity":
        return ["python3", "scripts/quality/check_index_integrity.py"]
    if gate == "rawInnerhtml":
        return ["python3", "scripts/quality/check_raw_innerhtml.py", "--check"]
    if gate == "layoutInlineStyle":
        return ["python3", "scripts/quality/check_layout_inline_style.py", "--check"]
    return []


# 03. target 执行
def run_target(repo_root: Path, target: str, changed_files: list[str] | None = None) -> list[GateDetail]:
    details: list[GateDetail] = []
    for gate in applicable_gates_for_target(target, changed_files):
        cmd = gate_command(gate, repo_root, target)
        if not cmd:
            details.append(GateDetail(name=gate, status=BLOCKED, command=[], output=f"required gate {gate} 没有可执行命令或依赖缺失。"))
            continue
        details.append(run_cmd(gate, cmd, repo_root, required=True))
    return details


# 04. summary 生成
def build_summary(target: str, change_id: str, started_at: str, details: list[GateDetail]) -> QualitySummary:
    required = {detail.name: detail.status for detail in details}
    status, failures = compute_overall(required)
    return QualitySummary(
        schemaVersion=3,
        status=status,
        target=target,
        changeId=change_id,
        startedAt=started_at,
        finishedAt=utc_now(),
        requiredGates=required,
        blockingFailures=failures,
        warnings=[],
        artifacts={},
        gateDetails=[detail.__dict__ for detail in details],
    )


# 05. CLI
def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic quality gate runner")
    parser.add_argument("--target", required=True, choices=["session-detail", "python-src", "hook-runtime", "harness", "index"])
    parser.add_argument("--change-id", required=True)
    parser.add_argument("--out", default="tmp/quality",
                        help="Quality artifact directory. Default: tmp/quality")
    parser.add_argument("--changed-files", default=None,
                        help="JSON array of changed file paths, or 'auto' to read from changed-files.jsonl")
    args = parser.parse_args()

    repo_root = Path.cwd()
    validate_target(args.target)
    started_at = utc_now()

    # 解析输出目录：默认 tmp/quality
    out_dir = Path(args.out)

    # 解析 changed files
    changed_files: list[str] | None = None
    if args.changed_files == "auto":
        changed_files = _read_changed_files(repo_root)
    elif args.changed_files:
        import json
        changed_files = json.loads(args.changed_files)

    details = run_target(repo_root, args.target, changed_files)
    summary = build_summary(args.target, args.change_id, started_at, details)
    out = write_quality_summary(repo_root / out_dir, summary, target_specific=True)
    print(f"quality summary: {out}")
    print(f"status: {summary.status}")
    return 0 if summary.status == PASS else 1


def _read_changed_files(repo_root: Path) -> list[str]:
    """从固定路径 tmp/agent_logs/current/changed-files.jsonl 读取文件列表。"""
    changed_file = repo_root / "tmp" / "agent_logs" / "current" / "changed-files.jsonl"
    if not changed_file.exists():
        return []

    session_id_file = repo_root / "tmp" / "agent_logs" / "current" / "session-id.txt"
    session_id = None
    if session_id_file.exists():
        session_id = session_id_file.read_text().strip() or None

    files: list[str] = []
    for line in changed_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            import json
            record = json.loads(line)
            if session_id and record.get("sessionId") != session_id:
                continue
            f = record.get("file") or record.get("file_path")
            if f:
                files.append(f)
        except (json.JSONDecodeError, Exception):
            continue
    return files


if __name__ == "__main__":
    raise SystemExit(main())
