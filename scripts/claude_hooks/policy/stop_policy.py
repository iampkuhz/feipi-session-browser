from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from ..evidence import read_changed_files, utc_now
from ..paths import RepoPaths
from .quality_policy import command_for_target


# 01. Stop 检查结果
@dataclass
class StopCheckResult:
    passed: bool
    status: str
    change_id: str
    required_targets: list[str] = field(default_factory=list)
    blocking_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# 02. 时间解析
def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


# 03. Summary 文件定位
def _summary_candidates(paths: RepoPaths, change_id: str, target: str) -> list[Path]:
    base = paths.quality_dir / change_id
    return [
        base / f"quality-gate-summary.{target}.json",
        base / "quality-gate-summary.json",
    ]


# 04. Summary 读取
def _read_summary(paths: RepoPaths, change_id: str, target: str) -> tuple[dict[str, Any] | None, Path | None]:
    for path in _summary_candidates(paths, change_id, target):
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data, path
        except Exception:
            return None, path
    return None, None


# 05. required gate 判断
def _has_skipped_required(summary: dict[str, Any]) -> list[str]:
    gates = summary.get("requiredGates") or {}
    if not isinstance(gates, dict):
        return ["requiredGates 字段缺失或不是对象。"]
    skipped = []
    for name, status in gates.items():
        if str(status).upper() == "SKIPPED":
            skipped.append(f"{name}=SKIPPED")
    return skipped


# 06. 需要 gate 的最近 change 汇总
def _latest_required_records(paths: RepoPaths) -> tuple[str | None, dict[str, list[dict[str, Any]]]]:
    rows = [r for r in read_changed_files(paths) if r.get("requiresQualityGate") and r.get("qualityTarget")]
    if not rows:
        return None, {}
    # 以最后一条 required 记录的 changeId 作为本轮 Stop 检查目标。
    change_id = str(rows[-1].get("changeId") or "")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if str(row.get("changeId") or "") == change_id:
            grouped.setdefault(str(row.get("qualityTarget")), []).append(row)
    return change_id, grouped


# 07. Stop 主检查
def check_stop(paths: RepoPaths) -> StopCheckResult:
    change_id, grouped = _latest_required_records(paths)
    if not change_id:
        return StopCheckResult(True, "PASS", "", warnings=["没有发现需要 quality gate 的变更。"])

    failures: list[str] = []
    targets = sorted(grouped.keys())

    for target in targets:
        summary, summary_path = _read_summary(paths, change_id, target)
        if not summary:
            failures.append(
                f"缺少 {target} quality summary。请运行：{command_for_target(target, change_id)}"
            )
            continue

        status = str(summary.get("status") or "").upper()
        if status != "PASS":
            failures.append(
                f"{target} quality summary 状态不是 PASS：{status}。请运行：{command_for_target(target, change_id)}"
            )

        skipped = _has_skipped_required(summary)
        if skipped:
            failures.append(f"{target} 存在 required gate 被 SKIPPED：{', '.join(skipped)}")

        finished = _parse_ts(str(summary.get("finishedAt") or ""))
        latest_change = None
        for row in grouped[target]:
            ts = _parse_ts(str(row.get("ts") or ""))
            if ts and (latest_change is None or ts > latest_change):
                latest_change = ts
        if latest_change and (not finished or finished < latest_change):
            failures.append(
                f"{target} summary 早于最近相关文件变更；请重新运行：{command_for_target(target, change_id)}"
            )

    status = "PASS" if not failures else "FAIL"
    return StopCheckResult(
        passed=not failures,
        status=status,
        change_id=change_id,
        required_targets=targets,
        blocking_failures=failures,
    )


# 08. 写入 Stop 检查摘要
def write_stop_summary(paths: RepoPaths, result: StopCheckResult) -> None:
    paths.agent_log_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": 1,
        "ts": utc_now(),
        "status": result.status,
        "passed": result.passed,
        "changeId": result.change_id,
        "requiredTargets": result.required_targets,
        "blockingFailures": result.blocking_failures,
        "warnings": result.warnings,
    }
    paths.stop_summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
