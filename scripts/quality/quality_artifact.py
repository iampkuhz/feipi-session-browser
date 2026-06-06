from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


# 01. 常量
PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
SKIPPED = "SKIPPED"
ALLOWED_STATUSES = {PASS, FAIL, BLOCKED, SKIPPED}


# 02. 时间
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# 03. Gate detail
@dataclass
class GateDetail:
    name: str
    status: str
    command: list[str] = field(default_factory=list)
    exitCode: int | None = None
    durationMs: int | None = None
    output: str = ""


# 04. Summary 构造
@dataclass
class QualitySummary:
    schemaVersion: int
    status: str
    target: str
    changeId: str
    startedAt: str
    finishedAt: str
    requiredGates: dict[str, str]
    blockingFailures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    gateDetails: list[dict[str, Any]] = field(default_factory=list)


# 05. overall 状态计算
def compute_overall(required_gates: dict[str, str]) -> tuple[str, list[str]]:
    failures: list[str] = []
    if not required_gates:
        return BLOCKED, ["requiredGates 为空，不能默认 PASS。"]

    for name, status in required_gates.items():
        normalized = str(status).upper()
        if normalized not in ALLOWED_STATUSES:
            failures.append(f"{name} 状态非法：{status}")
        elif normalized == SKIPPED:
            failures.append(f"{name} 是 required gate，不能 SKIPPED。")
        elif normalized in {FAIL, BLOCKED}:
            failures.append(f"{name}={normalized}")

    return (PASS, []) if not failures else (FAIL, failures)


# 06. 写入 artifact
def write_quality_summary(base_dir: Path, summary: QualitySummary, target_specific: bool = True) -> Path:
    out_dir = base_dir / summary.changeId
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"quality-gate-summary.{summary.target}.json" if target_specific else "quality-gate-summary.json"
    summary_path = out_dir / filename
    summary_path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    details = out_dir / (f"gate-details.{summary.target}.json" if target_specific else "gate-details.json")
    details.write_text(json.dumps(summary.gateDetails, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary_path


# 07. 自测试
def _self_test() -> None:
    assert compute_overall({"a": "PASS"}) == ("PASS", [])
    status, failures = compute_overall({"a": "SKIPPED"})
    assert status == "FAIL"
    assert failures
    status, failures = compute_overall({})
    assert status == "BLOCKED"


if __name__ == "__main__":
    _self_test()
    print("quality_artifact self-test PASS")
