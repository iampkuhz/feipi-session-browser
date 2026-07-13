#!/usr/bin/env python3
"""生成 agent runtime report JSON，符合 harness/agent-runtime-report.schema.json。

不负责产品业务处理；由 harness 命令行或受控收口流程调用。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_NAME = "writeAgentRuntimeReport"


# 解析 --gate 参数，格式 name=status:command。
def parse_gate(raw: str) -> dict:
    """参数：
        raw: 原始 gate 字符串。

    返回：
        gate 字典。
    """
    eq_idx = raw.find("=")
    if eq_idx < 0:
        print(
            f"[{GATE_NAME}] FAIL: --gate 格式错误(缺少 '='): {raw}，期望格式: name=status:command",
            file=sys.stderr,
        )
        raise SystemExit(1)
    name = raw[:eq_idx]
    rest = raw[eq_idx + 1 :]
    colon_idx = rest.find(":")
    if colon_idx < 0:
        print(
            f"[{GATE_NAME}] FAIL: --gate 格式错误(缺少 ':'): {raw}，期望格式: name=status:command",
            file=sys.stderr,
        )
        raise SystemExit(1)
    status = rest[:colon_idx]
    command = rest[colon_idx + 1 :]
    if status not in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
        print(
            f"[{GATE_NAME}] FAIL: --gate status 无效: {status}，"
            "允许值: PASS, FAIL, BLOCKED, NOT_RUN",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return {
        "name": name,
        "command": command,
        "status": status,
        "skipped_count": 0,
        "evidence": f"{name}={status}",
    }


# 生成 report JSON 并写入指定路径。
def main() -> int:
    """返回：
    进程退出码。
    """
    parser = argparse.ArgumentParser(
        description="生成 agent runtime report JSON。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "gate 格式: name=status:command\n"
            "  name        gate 标识\n"
            "  status      PASS | FAIL | BLOCKED | NOT_RUN\n"
            "  command     关联的检查命令"
        ),
    )
    parser.add_argument("--change-id", required=True, help="OpenSpec change 标识")
    parser.add_argument("--agent-platform", required=True, help="agent 平台(claude/codex/qoder)")
    parser.add_argument("--changed-file", action="append", default=[], help="变更文件(可重复)")
    parser.add_argument(
        "--gate",
        action="append",
        default=[],
        help="gate 记录，格式: name=status:command(可重复)",
    )
    parser.add_argument("--blocked", action="append", default=[], help="blocked 项(可重复)")
    parser.add_argument("--risk", action="append", default=[], help="风险项(可重复)")
    parser.add_argument(
        "--output",
        default=None,
        help="输出路径(默认: harness/reports/<change-id>.json)",
    )

    args = parser.parse_args()

    if args.output is None:
        args.output = str(ROOT / "harness" / "reports" / f"{args.change_id}.json")

    gates = [parse_gate(g) for g in args.gate]

    total_skipped = sum(g.get("skipped_count", 0) for g in gates)

    report = {
        "change_id": args.change_id,
        "created_at": datetime.now(UTC).isoformat(),
        "agent_platform": args.agent_platform,
        "subagents": [],
        "changed_files": list(args.changed_file),
        "gates": gates,
        "skipped_count": total_skipped,
        "blocked_items": list(args.blocked),
        "risks": list(args.risk),
        "notes": [],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"[{GATE_NAME}] PASS: report 已写入 {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
