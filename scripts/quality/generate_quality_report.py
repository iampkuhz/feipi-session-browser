#!/usr/bin/env python3
"""quality-report.md generator.

读取 quality gate summary JSON, 生成人类可读的 Markdown 报告。

用法:
    python3 scripts/quality/generate_quality_report.py --target session-detail --change-id fix-xyz
    python3 scripts/quality/generate_quality_report.py --summary-file \
tmp/quality/test/quality-gate-summary.session-detail.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MILLISECONDS_PER_SECOND = 1000
MAX_OUTPUT_CHARS = 2000


def load_summary(summary_path: Path) -> dict:
    """加载 quality gate summary JSON。.

    Args:
        summary_path: Input value for summary_path.

    Returns:
        Computed result.
    """
    text = summary_path.read_text(encoding='utf-8')
    return json.loads(text)


def format_duration(ms: int | None) -> str:
    """格式化毫秒为可读字符串。.

    Args:
        ms: Input value for ms.

    Returns:
        Computed result.
    """
    if ms is None:
        return 'N/A'
    if ms < MILLISECONDS_PER_SECOND:
        return f'{ms}ms'
    return f'{ms / MILLISECONDS_PER_SECOND:.1f}s'


def status_badge(status: str) -> str:
    """生成状态徽章文本。.

    Args:
        status: Input value for status.

    Returns:
        Computed result.
    """
    s = str(status).upper()
    if s == 'PASS':
        return 'PASS'
    if s == 'FAIL':
        return 'FAIL'
    if s == 'BLOCKED':
        return 'BLOCKED'
    if s == 'SKIPPED':
        return 'SKIPPED'
    return status


def _append_timing_rows(lines: list[str], data: dict) -> None:
    """Append optional timing metadata rows to a Markdown table.

    Args:
        lines: Report lines being built.
        data: Input value for data.
    """
    started = data.get('startedAt', '')
    finished = data.get('finishedAt', '')
    if started:
        lines.append(f'| 开始时间 | {started} |')
    if not finished:
        return

    lines.append(f'| 完成时间 | {finished} |')
    try:
        t_start = datetime.fromisoformat(started)
        t_end = datetime.fromisoformat(finished)
        delta = t_end - t_start
        total_ms = int(delta.total_seconds() * MILLISECONDS_PER_SECOND)
        lines.append(f'| 耗时 | {format_duration(total_ms)} |')
    except (ValueError, TypeError):
        pass


def _append_gate_details(lines: list[str], gate_details: list[dict]) -> None:
    """Append gate result table rows when details exist.

    Args:
        lines: Report lines being built.
        gate_details: Gate detail records from the summary.
    """
    if not gate_details:
        return

    lines.append('## Gate 结果')
    lines.append('')
    lines.append('| Gate | 状态 | 耗时 | 退出码 |')
    lines.append('|---|---|---|---|')

    for detail in gate_details:
        name = detail.get('name', 'unknown')
        g_status = status_badge(detail.get('status', 'UNKNOWN'))
        duration = format_duration(detail.get('durationMs'))
        exit_code = detail.get('exitCode', 'N/A')
        lines.append(f'| {name} | {g_status} | {duration} | {exit_code} |')

    lines.append('')


def _append_list_section(lines: list[str], title: str, items: list) -> None:
    """Append a bullet-list section when it has items.

    Args:
        lines: Report lines being built.
        title: Section heading.
        items: Bullet values to render.
    """
    if not items:
        return

    lines.append(f'## {title}')
    lines.append('')
    for item in items:
        lines.append(f'- {item}')
    lines.append('')


def _append_failed_outputs(lines: list[str], gate_details: list[dict]) -> None:
    """Append failed gate output snippets.

    Args:
        lines: Report lines being built.
        gate_details: Gate detail records from the summary.
    """
    failed_details = [
        d for d in gate_details if str(d.get('status', '')).upper() in {'FAIL', 'BLOCKED'}
    ]
    if not failed_details:
        return

    lines.append('## 失败详情')
    lines.append('')
    for detail in failed_details:
        name = detail.get('name', 'unknown')
        g_status = status_badge(detail.get('status', 'UNKNOWN'))
        output = detail.get('output', '')
        lines.append(f'### {name} ({g_status})')
        lines.append('')
        if output:
            if len(output) > MAX_OUTPUT_CHARS:
                output = output[:MAX_OUTPUT_CHARS] + '\n...(truncated)'
            lines.append('```')
            lines.append(output)
            lines.append('```')
            lines.append('')


def _append_artifacts(lines: list[str], artifacts: dict) -> None:
    """Append artifact links from the summary.

    Args:
        lines: Report lines being built.
        artifacts: Artifact mapping from the summary.
    """
    if not artifacts:
        return

    lines.append('## Artifacts')
    lines.append('')
    for key, value in artifacts.items():
        lines.append(f'- **{key}**: {value}')
    lines.append('')


def generate_report(data: dict) -> str:
    """根据 summary JSON 生成 Markdown 报告。.

    Args:
        data: Input value for data.

    Returns:
        Computed result.
    """
    lines: list[str] = []

    # Header
    target = data.get('target', 'unknown')
    change_id = data.get('changeId', 'unknown')
    status = data.get('status', 'UNKNOWN')
    schema_version = data.get('schemaVersion', 0)

    lines.append(f'# Quality Report: {target}')
    lines.append('')
    lines.append('| 字段 | 值 |')
    lines.append('|---|---|')
    lines.append(f'| 状态 | **{status_badge(status)}** |')
    lines.append(f'| Change ID | `{change_id}` |')
    lines.append(f'| Schema Version | {schema_version} |')
    _append_timing_rows(lines, data)

    lines.append('')

    gate_details = data.get('gateDetails', [])
    _append_gate_details(lines, gate_details)
    _append_list_section(lines, '阻断失败', data.get('blockingFailures', []))
    _append_list_section(lines, '警告', data.get('warnings', []))
    _append_failed_outputs(lines, gate_details)
    _append_artifacts(lines, data.get('artifacts', {}))

    # Footer
    lines.append('---')
    lines.append(
        f'由 generate_quality_report.py 自动生成 | {datetime.now(timezone.utc).isoformat()}'
    )
    lines.append('')

    return '\n'.join(lines)


def find_latest_summary(target: str, change_id: str, out_dir: Path) -> Path | None:
    """在质量输出目录中查找最新的 summary JSON。.

    Args:
        target: Input value for target.
        change_id: Input value for change_id.
        out_dir: Input value for out_dir.

    Returns:
        Computed result.
    """
    base = out_dir / change_id
    if not base.exists():
        return None

    # Try target-specific first
    target_file = base / f'quality-gate-summary.{target}.json'
    if target_file.exists():
        return target_file

    # Fall back to default
    default_file = base / 'quality-gate-summary.json'
    if default_file.exists():
        return default_file

    return None


def main() -> int:
    """Parse CLI arguments and generate the requested quality report.

    Returns:
        Computed result.
    """
    parser = argparse.ArgumentParser(description='quality-report.md 生成器')
    parser.add_argument('--target', default=None, help='Quality target (e.g., session-detail)')
    parser.add_argument('--change-id', default=None, help='Change ID')
    parser.add_argument('--summary-file', default=None, help='Direct path to summary JSON')
    parser.add_argument('--out-dir', default='tmp/quality', help='Quality artifact directory')
    parser.add_argument('--output', default=None, help='Output markdown path (default: auto)')
    args = parser.parse_args()

    summary_path: Path | None = None

    if args.summary_file:
        summary_path = Path(args.summary_file)
    elif args.target and args.change_id:
        out_dir = REPO_ROOT / args.out_dir
        summary_path = find_latest_summary(args.target, args.change_id, out_dir)
    else:
        print('ERROR: 需要 --summary-file 或 (--target + --change-id)')
        return 1

    if not summary_path or not summary_path.exists():
        print(f'ERROR: summary 文件不存在: {summary_path}')
        return 1

    data = load_summary(summary_path)
    report = generate_report(data)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        change_id = data.get('changeId', 'unknown')
        target = data.get('target', 'unknown')
        out_dir = REPO_ROOT / args.out_dir / change_id
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f'quality-report.{target}.md'

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding='utf-8')
    print(f'quality report: {output_path}')
    print(report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
