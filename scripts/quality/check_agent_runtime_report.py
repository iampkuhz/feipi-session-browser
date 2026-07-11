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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.agent_runtime import policy as runtime_policy  # noqa: E402
GATE_NAME = "runtimeReport"
REPORT_DIR = ROOT / "harness" / "reports"
ACTIVE_CHANGE_PATH = ROOT / "tmp" / "active_change.json"
FALLBACK_CHANGE_ID = "harden-agent-runtime-and-skills"
REQUIRED_OUTCOME_IDS = set("ABCDEFGHIJKL")


# 输出 FAIL 并返回非 0。
def fail(message: str) -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    print(f"[{GATE_NAME}] FAIL: {message}")
    return 1


# 解析 change-id，优先级: 显式参数 > tmp/active_change.json > fallback。
def resolve_change_id(explicit: str | None = None) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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



# 维护 get_protected_roots 函数行为。
def get_protected_roots() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return runtime_policy.protected_roots(ROOT)



# 获取当前 git diff 涉及的变更文件。
def get_diff_changed_files() -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
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



# 维护 is_protected 函数行为。
def is_protected(path: str, roots: list[str] | None = None) -> bool:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    return runtime_policy.is_protected_path(path, ROOT)



# 查找 report 文件，优先 harness/reports/，再查 tmp/。
def find_report(change_id: str) -> Path | None:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    candidate = REPORT_DIR / f"{change_id}.json"
    if candidate.is_file():
        return candidate
    tmp_candidate = ROOT / "tmp" / "agent-runtime-report.json"
    if tmp_candidate.is_file():
        return tmp_candidate
    return None


# 维护 _status 函数行为。
def _status(item: object) -> str:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    if isinstance(item, dict):
        return str(item.get("status", ""))
    return ""


# 维护 validate_report_content 函数行为。
def validate_report_content(
    report: dict,
    protected_in_diff: list[str],
) -> list[str]:
    """参数：
        report: 运行报告 JSON 对象。
        protected_in_diff: 当前 diff 中的受保护路径。

    返回：
        runtime report validation 错误列表。
    """
    errors: list[str] = []

    required_fields = [
        "change_id",
        "created_at",
        "agent_platform",
        "subagents",
        "changed_files",
        "expected_outcomes",
        "effect_checks",
        "gate_escape_rate",
        "concurrency_matrix",
        "gates",
        "skipped_count",
        "blocked_items",
        "risks",
        "notes",
    ]
    for field in required_fields:
        if field not in report:
            errors.append(f"report 缺少必填字段: {field}")

    skipped = report.get("skipped_count", -1)
    if skipped != 0:
        errors.append(f"skipped_count 应为 0，实际为 {skipped}")

    outcomes = report.get("expected_outcomes", [])
    if not isinstance(outcomes, list):
        errors.append("expected_outcomes 必须是数组")
        outcomes = []
    outcome_ids = {
        str(item.get("id", ""))
        for item in outcomes
        if isinstance(item, dict) and item.get("id")
    }
    missing_outcomes = sorted(REQUIRED_OUTCOME_IDS - outcome_ids)
    if missing_outcomes:
        errors.append(f"expected_outcomes 缺少 A-L outcome: {missing_outcomes}")
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            errors.append("expected_outcomes 包含非对象条目")
            continue
        if outcome.get("required") is True and outcome.get("status") != "PASS":
            errors.append(
                f"required outcome {outcome.get('id', '?')} "
                f"状态必须为 PASS，实际为 {outcome.get('status', '?')}"
            )

    effect_checks = report.get("effect_checks", [])
    if not isinstance(effect_checks, list):
        errors.append("effect_checks 必须是数组")
        effect_checks = []
    for check in effect_checks:
        if _status(check) != "PASS":
            cid = check.get("id", "?") if isinstance(check, dict) else "?"
            errors.append(f"effect_check {cid} 状态必须为 PASS，实际为 {_status(check) or '?'}")

    escape = report.get("gate_escape_rate", {})
    if not isinstance(escape, dict):
        errors.append("gate_escape_rate 必须是对象")
        escape = {}
    threshold = escape.get("threshold")
    escape_rate = escape.get("escape_rate")
    escape_status = str(escape.get("status") or "").upper()
    if escape_status == "NOT_RUN":
        escape_rate = 0
    if threshold != 0 and threshold != 0.0:
        errors.append(f"gate_escape_rate.threshold 必须为 0，实际为 {threshold}")
    if not isinstance(escape_rate, (int, float)) or not isinstance(threshold, (int, float)):
        errors.append("gate_escape_rate.escape_rate/threshold 必须是数字")
    elif escape_rate > threshold:
        errors.append(
            f"gate_escape_rate.escape_rate({escape_rate}) 超过 threshold({threshold})"
        )

    concurrency = report.get("concurrency_matrix", [])
    if not isinstance(concurrency, list):
        errors.append("concurrency_matrix 必须是数组")
        concurrency = []
    for row in concurrency:
        if _status(row) != "PASS":
            rid = row.get("id", "?") if isinstance(row, dict) else "?"
            errors.append(
                f"concurrency_matrix {rid} 状态必须为 PASS，实际为 {_status(row) or '?'}"
            )

    gates = report.get("gates", [])
    if not isinstance(gates, list):
        errors.append("gates 必须是数组")
        gates = []
    blocked_items = report.get("blocked_items", [])
    final_status = report.get("status")
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("gates 包含非对象条目")
            continue
        if gate.get("status") == "NOT_RUN":
            if not blocked_items:
                errors.append(
                    f"gate {gate.get('name', '?')} 状态为 NOT_RUN "
                    f"但 blocked_items 为空，需要说明原因"
                )
            if final_status == "PASS":
                errors.append(
                    f"gate {gate.get('name', '?')} 状态为 NOT_RUN，final status 不能为 PASS"
                )

    report_changed = report.get("changed_files", [])
    if not isinstance(report_changed, list):
        errors.append("changed_files 必须是数组")
        report_changed = []
    missing_changed = [f for f in protected_in_diff if f not in report_changed]
    if missing_changed:
        errors.append(
            f"changed_files 未包含当前 diff 的 protected path\n"
            f"  missing: {missing_changed[:5]}\n"
            f"  report changed_files: {report_changed[:5]}"
        )

    return errors



# 显式校验 run-scoped runtime report；调用方必须传入所有运行上下文。
def validate_runtime_report(
    *,
    run_id: str,
    client: str,
    session_id: str,
    change_id: str,
    worktree_root: Path,
    changed_files: list[str],
    report_path: Path,
) -> list[str]:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    errors: list[str] = []
    if not run_id:
        errors.append("run_id is required for run-scoped runtime report")
    if not client:
        errors.append("client is required for run-scoped runtime report")
    if not session_id:
        errors.append("session_id is required for run-scoped runtime report")
    if not change_id:
        errors.append("change_id is required for run-scoped runtime report")
    if not Path(worktree_root).exists():
        errors.append(f"worktree_root does not exist: {worktree_root}")
    try:
        report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"report JSON 解析失败: {report_path} — {exc}"]

    if str(report.get("run_id") or report.get("runId") or "") != run_id:
        errors.append("report run_id does not match explicit run_id")
    if str(report.get("client") or report.get("agent_platform") or "") != client:
        errors.append("report client does not match explicit client")
    if str(report.get("session_id") or report.get("sessionId") or "") != session_id:
        errors.append("report session_id does not match explicit session_id")
    if str(report.get("change_id") or report.get("changeId") or "") != change_id:
        errors.append("report change_id does not match explicit change_id")

    protected_in_run = [path for path in changed_files if is_protected(path)]
    errors.extend(validate_report_content(report, protected_in_run))
    report_changed = report.get("changed_files", [])
    if not isinstance(report_changed, list):
        report_changed = []
    if set(report_changed) != set(changed_files):
        errors.append("report changed_files must exactly match explicit run changed_files")
    return errors

# 执行 runtime report 一致性检查。
def main() -> int:
    """参数：
        *args: 当前函数使用的输入参数。

    返回：
        当前函数计算或校验结果。
    """
    parser = argparse.ArgumentParser(description="检查 agent runtime report 一致性。")
    parser.add_argument("--change-id", default=None, help="OpenSpec change 标识")
    parser.add_argument("--run-id", default=None, help="显式 run id；启用 run-scoped 校验")
    parser.add_argument("--client", default=None, help="显式 agent client")
    parser.add_argument("--session-id", default=None, help="显式 session id")
    parser.add_argument("--worktree-root", default=None, help="显式 worktree root")
    parser.add_argument("--changed-files", default=None, help="JSON array；显式 run changed files")
    parser.add_argument("--report-path", default=None, help="显式 run-scoped report path")
    args = parser.parse_args()

    if args.run_id or args.report_path:
        if not all([args.run_id, args.client, args.session_id, args.change_id, args.worktree_root, args.changed_files, args.report_path]):
            return fail("run-scoped runtime report requires --run-id --client --session-id --change-id --worktree-root --changed-files --report-path")
        try:
            changed_files = json.loads(args.changed_files)
        except json.JSONDecodeError as exc:
            return fail(f"--changed-files JSON 解析失败: {exc}")
        if not isinstance(changed_files, list) or not all(isinstance(item, str) for item in changed_files):
            return fail("--changed-files 必须是 string array")
        errors = validate_runtime_report(
            run_id=args.run_id,
            client=args.client,
            session_id=args.session_id,
            change_id=args.change_id,
            worktree_root=Path(args.worktree_root),
            changed_files=changed_files,
            report_path=Path(args.report_path),
        )
        if errors:
            for error in errors:
                print(f"[{GATE_NAME}] FAIL: {error}")
            return 1
        print(f"[{GATE_NAME}] PASS — run-scoped report 有效: {args.report_path}")
        return 0

    print(f"[{GATE_NAME}] legacy warning: legacy runtime report mode; not multi-primary safe", file=sys.stderr)
    change_id = resolve_change_id(args.change_id)
    protected_roots = get_protected_roots()

    if not protected_roots:
        print(f"[{GATE_NAME}] PASS: 无 protected_roots 配置，跳过检查")
        return 0

    diff_files = get_diff_changed_files()
    protected_in_diff = [f for f in diff_files if is_protected(f)]

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

    errors = validate_report_content(report, protected_in_diff)

    if errors:
        for e in errors:
            print(f"[{GATE_NAME}] FAIL: {e}")
        return 1

    try:
        display_path = report_path.relative_to(ROOT)
    except ValueError:
        display_path = report_path
    print(f"[{GATE_NAME}] PASS — report 有效: {display_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
