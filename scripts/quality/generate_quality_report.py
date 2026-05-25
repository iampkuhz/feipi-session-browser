#!/usr/bin/env python3
"""quality-report.md 生成器。

读取 quality gate summary JSON，生成人类可读的 Markdown 报告。

用法:
    python3 scripts/quality/generate_quality_report.py --target session-detail --change-id fix-xyz
    python3 scripts/quality/generate_quality_report.py --summary-file tmp/quality/test/quality-gate-summary.session-detail.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def load_summary(summary_path: Path) -> dict:
    """加载 quality gate summary JSON。"""
    text = summary_path.read_text(encoding="utf-8")
    return json.loads(text)


def format_duration(ms: int | None) -> str:
    """格式化毫秒为可读字符串。"""
    if ms is None:
        return "N/A"
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def status_badge(status: str) -> str:
    """生成状态徽章文本。"""
    s = str(status).upper()
    if s == "PASS":
        return "PASS"
    elif s == "FAIL":
        return "FAIL"
    elif s == "BLOCKED":
        return "BLOCKED"
    elif s == "SKIPPED":
        return "SKIPPED"
    return status


def generate_report(data: dict) -> str:
    """根据 summary JSON 生成 Markdown 报告。"""
    lines: list[str] = []

    # Header
    target = data.get("target", "unknown")
    change_id = data.get("changeId", "unknown")
    status = data.get("status", "UNKNOWN")
    schema_version = data.get("schemaVersion", 0)

    lines.append(f"# Quality Report: {target}")
    lines.append("")
    lines.append(f"| 字段 | 值 |")
    lines.append(f"|---|---|")
    lines.append(f"| 状态 | **{status_badge(status)}** |")
    lines.append(f"| Change ID | `{change_id}` |")
    lines.append(f"| Schema Version | {schema_version} |")

    started = data.get("startedAt", "")
    finished = data.get("finishedAt", "")
    if started:
        lines.append(f"| 开始时间 | {started} |")
    if finished:
        lines.append(f"| 完成时间 | {finished} |")
        try:
            t_start = datetime.fromisoformat(started)
            t_end = datetime.fromisoformat(finished)
            delta = t_end - t_start
            total_ms = int(delta.total_seconds() * 1000)
            lines.append(f"| 耗时 | {format_duration(total_ms)} |")
        except (ValueError, TypeError):
            pass

    lines.append("")

    # Gate Results
    required_gates = data.get("requiredGates", {})
    gate_details = data.get("gateDetails", [])

    if gate_details:
        lines.append("## Gate 结果")
        lines.append("")
        lines.append("| Gate | 状态 | 耗时 | 退出码 |")
        lines.append("|---|---|---|---|")

        for detail in gate_details:
            name = detail.get("name", "unknown")
            g_status = status_badge(detail.get("status", "UNKNOWN"))
            duration = format_duration(detail.get("durationMs"))
            exit_code = detail.get("exitCode", "N/A")
            lines.append(f"| {name} | {g_status} | {duration} | {exit_code} |")

        lines.append("")

    # Blocking Failures
    blocking = data.get("blockingFailures", [])
    if blocking:
        lines.append("## 阻断失败")
        lines.append("")
        for item in blocking:
            lines.append(f"- {item}")
        lines.append("")

    # Warnings
    warnings = data.get("warnings", [])
    if warnings:
        lines.append("## 警告")
        lines.append("")
        for item in warnings:
            lines.append(f"- {item}")
        lines.append("")

    # Gate Output Details (only for failed gates)
    failed_details = [d for d in gate_details if str(d.get("status", "")).upper() in {"FAIL", "BLOCKED"}]
    if failed_details:
        lines.append("## 失败详情")
        lines.append("")
        for detail in failed_details:
            name = detail.get("name", "unknown")
            g_status = status_badge(detail.get("status", "UNKNOWN"))
            output = detail.get("output", "")
            lines.append(f"### {name} ({g_status})")
            lines.append("")
            if output:
                # Truncate long output
                if len(output) > 2000:
                    output = output[:2000] + "\n...(truncated)"
                lines.append("```")
                lines.append(output)
                lines.append("```")
                lines.append("")

    # Artifacts
    artifacts = data.get("artifacts", {})
    if artifacts:
        lines.append("## Artifacts")
        lines.append("")
        for key, value in artifacts.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"由 generate_quality_report.py 自动生成 | {datetime.now(timezone.utc).isoformat()}")
    lines.append("")

    return "\n".join(lines)


def find_latest_summary(target: str, change_id: str, out_dir: Path) -> Path | None:
    """在质量输出目录中查找最新的 summary JSON。"""
    base = out_dir / change_id
    if not base.exists():
        return None

    # Try target-specific first
    target_file = base / f"quality-gate-summary.{target}.json"
    if target_file.exists():
        return target_file

    # Fall back to default
    default_file = base / "quality-gate-summary.json"
    if default_file.exists():
        return default_file

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="quality-report.md 生成器")
    parser.add_argument("--target", default=None, help="Quality target (e.g., session-detail)")
    parser.add_argument("--change-id", default=None, help="Change ID")
    parser.add_argument("--summary-file", default=None, help="Direct path to summary JSON")
    parser.add_argument("--out-dir", default="tmp/quality", help="Quality artifact directory")
    parser.add_argument("--output", default=None, help="Output markdown path (default: auto)")
    args = parser.parse_args()

    summary_path: Path | None = None

    if args.summary_file:
        summary_path = Path(args.summary_file)
    elif args.target and args.change_id:
        out_dir = REPO_ROOT / args.out_dir
        summary_path = find_latest_summary(args.target, args.change_id, out_dir)
    else:
        print("ERROR: 需要 --summary-file 或 (--target + --change-id)")
        return 1

    if not summary_path or not summary_path.exists():
        print(f"ERROR: summary 文件不存在: {summary_path}")
        return 1

    data = load_summary(summary_path)
    report = generate_report(data)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        change_id = data.get("changeId", "unknown")
        target = data.get("target", "unknown")
        out_dir = REPO_ROOT / args.out_dir / change_id
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"quality-report.{target}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"quality report: {output_path}")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
