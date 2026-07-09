#!/usr/bin/env python3
"""检查 agent runtime report 存在性和一致性。

当当前 diff 涉及 protected paths 时，必须存在有效的 runtime report。
当 diff 不涉及 protected paths 时，直接 PASS(避免阻塞普通非 agent 任务)。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_NAME = "runtimeReport"
MANIFEST_PATH = ROOT / "harness" / "agent-runtime.manifest.yaml"
REPORT_DIR = ROOT / "harness" / "reports"
ACTIVE_CHANGE_PATH = ROOT / "tmp" / "active_change.json"
FALLBACK_CHANGE_ID = "harden-agent-runtime-and-skills"


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        message: 用户可读错误信息。

    返回：
        进程退出码。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 解析 change-id，优先级: 显式参数 > tmp/active_change.json > fallback。
def resolve_change_id(explicit: str | None = None) -> str:
    """参数：
        explicit: 命令行显式指定的 change-id。

    返回：
        解析后的 change-id。
    """
    if explicit:
        return explicit
    if ACTIVE_CHANGE_PATH.is_file():
        try:
            data = json.loads(ACTIVE_CHANGE_PATH.read_text(encoding="utf-8"))
            cid = data.get("change_id") or data.get("changeId") or ""
            if cid:
                return cid
        except (json.JSONDecodeError, OSError):
            pass
    return FALLBACK_CHANGE_ID


# 从 manifest 读取 protected_roots。
def get_protected_roots() -> list[str]:
    """返回：
        protected root 前缀列表。
    """
    if not MANIFEST_PATH.is_file():
        return []
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    roots: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("protected_roots:"):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("- "):
                roots.append(stripped[2:].strip())
            elif stripped and not stripped.startswith("#"):
                break
    return roots


# 获取当前 git diff 涉及的变更文件。
def get_diff_changed_files() -> list[str]:
    """返回：
        变更文件路径列表。
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.SubprocessError, OSError):
        pass

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
    except (subprocess.SubprocessError, OSError):
        pass

    return []


# 判断路径是否属于 protected root。
def is_protected(path: str, roots: list[str]) -> bool:
    """参数：
        path: 待检查路径。
        roots: protected root 前缀列表。

    返回：
        是否受保护。
    """
    for root in roots:
        root_clean = root.strip("/")
        if path.startswith(root_clean + "/") or path == root_clean:
            return True
    return False


# 查找 report 文件，优先 harness/reports/，再查 tmp/。
def find_report(change_id: str) -> Path | None:
    """参数：
        change_id: OpenSpec change 标识。

    返回：
        report 路径；不存在时返回 None。
    """
    candidate = REPORT_DIR / f"{change_id}.json"
    if candidate.is_file():
        return candidate
    tmp_candidate = ROOT / "tmp" / "agent-runtime-report.json"
    if tmp_candidate.is_file():
        return tmp_candidate
    return None


# 执行 runtime report 一致性检查。
def main() -> int:
    """返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description="检查 agent runtime report 一致性。")
    parser.add_argument("--change-id", default=None, help="OpenSpec change 标识")
    args = parser.parse_args()

    change_id = resolve_change_id(args.change_id)
    protected_roots = get_protected_roots()

    if not protected_roots:
        print(f"[{GATE_NAME}] PASS: 无 protected_roots 配置，跳过检查")
        return 0

    diff_files = get_diff_changed_files()
    protected_in_diff = [f for f in diff_files if is_protected(f, protected_roots)]

    if not protected_in_diff:
        print(f"[{GATE_NAME}] PASS: diff 无 protected paths，跳过检查")
        return 0

    report_path = find_report(change_id)
    if report_path is None:
        return fail(
            f"diff 涉及 protected paths 但未找到 runtime report\n"
            f"  expected: harness/reports/{change_id}.json 或 tmp/agent-runtime-report.json\n"
            f"  change-id: {change_id}\n"
            f"  protected files in diff: {protected_in_diff[:5]}"
        )

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return fail(f"report JSON 解析失败: {report_path} — {e}")

    errors: list[str] = []

    skipped = report.get("skipped_count", -1)
    if skipped != 0:
        errors.append(f"skipped_count 应为 0，实际为 {skipped}")

    gates = report.get("gates", [])
    blocked_items = report.get("blocked_items", [])
    for gate in gates:
        if gate.get("status") == "NOT_RUN" and not blocked_items:
            errors.append(
                f"gate {gate.get('name', '?')} 状态为 NOT_RUN "
                f"但 blocked_items 为空，需要说明原因"
            )

    report_changed = report.get("changed_files", [])
    has_protected = any(
        is_protected(f, protected_roots) for f in report_changed
    )
    if not has_protected:
        errors.append(
            f"changed_files 未包含任何 protected path\n"
            f"  report changed_files: {report_changed[:5]}\n"
            f"  diff protected paths: {protected_in_diff[:5]}"
        )

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    print(f"[{GATE_NAME}] PASS — report 有效: {report_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
