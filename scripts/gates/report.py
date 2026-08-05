"""定义 typed Gate 状态、稳定摘要与有界诊断报告。

不负责产品业务处理；由 Gate CLI 或 Stop pipeline 调用。"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

PASS = 'PASS'
NOT_PASS = 'NOT_PASS'
FAIL = 'FAIL'
BLOCKED = 'BLOCKED'
ALLOWED_STATUSES = {PASS, FAIL, BLOCKED}
DIAGNOSTIC_MAX_CHARS = 1600
DIAGNOSTIC_MAX_LINES = 16
FAILED_GATE_REPORT_LIMIT = 8
_DIAGNOSTIC_PRIORITY_RE = re.compile(
    r'(?i)(fail|error|exception|traceback|blocked|timeout|timed out|warning|'
    r'assert|missing|not found|denied|invalid|\bE\d{3,4}\b)'
)
_FILE_REFERENCE_RE = re.compile(
    r'(?<![\w.-])((?:[\w.-]+/)+[\w.-]+\.(?:py|sh|java|kt|js|ts|tsx|json|ya?ml|md|css|html)'
    r'(?::\d+(?::\d+)?)?)'
)


def utc_now() -> str:
    """返回当前 UTC 时间戳。"""
    return datetime.now(UTC).isoformat()


def resolve_base_commit(repo_root: str = '.') -> str:
    """读取当前 HEAD 的短 commit hash；Git 不可用时返回空字符串。"""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ''
    except Exception:
        return ''


def resolve_dirty_hash(repo_root: str = '.') -> str:
    """计算工作树 dirty 状态短 hash；无变化或 Git 不可用时返回空字符串。"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--shortstat'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            import hashlib

            # 使用 diff 摘要计算稳定短哈希，标识当前工作区的 dirty 状态。
            return hashlib.sha256(result.stdout.encode()).hexdigest()[:12]
        return ''
    except Exception:
        return ''


def is_artifact_fresh(artifact_path: str, max_age_seconds: int = 3600) -> bool:
    """判断 quality artifact 是否仍在有效时间窗口内。"""
    from pathlib import Path as _Path

    p = _Path(artifact_path)
    if not p.exists():
        return False
    # 用文件 mtime 计算 artifact 年龄，避免读取损坏 JSON 时影响新鲜度判断。
    age = datetime.now(UTC).timestamp() - p.stat().st_mtime
    return age <= max_age_seconds


@dataclass
class GateDetail:
    """保存 `GateDetail` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

    name: str
    status: str
    command: list[str] = field(default_factory=list)
    exitCode: int | None = None  # noqa: N815 - Preserve JSON artifact schema.
    durationMs: int | None = None  # noqa: N815 - Preserve JSON artifact schema.
    output: str = ''
    executionState: str = 'EXECUTED'  # noqa: N815 - Preserve JSON artifact schema.
    groupId: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    rerunCommand: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    taskOutcomes: dict[str, str] = field(default_factory=dict)  # noqa: N815
    taskFailureReasons: dict[str, str] = field(default_factory=dict)  # noqa: N815
    mode: str = ''
    targetSeconds: int | None = None  # noqa: N815
    timingState: str = ''  # noqa: N815
    reason: str = ''

    def __post_init__(self) -> None:
        """保证每个执行失败明细都有可机器处理的原因码。"""

        if self.status == FAIL and not self.reason:
            self.reason = 'outcome-unknown'


@dataclass
class QualitySummary:
    """保存 `QualitySummary` 的结构化契约数据；字段由所属运行阶段构造并由后续报告读取。"""

    schemaVersion: int  # noqa: N815 - Preserve JSON artifact schema.
    status: str
    mode: str
    changeId: str  # noqa: N815 - Preserve JSON artifact schema.
    startedAt: str  # noqa: N815 - Preserve JSON artifact schema.
    finishedAt: str  # noqa: N815 - Preserve JSON artifact schema.
    gateResults: dict[str, str]  # noqa: N815 - Preserve JSON artifact schema.
    selector: str | None = None
    selectorValue: str | None = None  # noqa: N815 - Preserve JSON artifact schema.
    notPassReasons: list[str] = field(default_factory=list)  # noqa: N815 - Preserve schema.
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    gateDetails: list[dict[str, Any]] = field(default_factory=list)  # noqa: N815 - Preserve schema.
    # 运行身份与执行计划字段沿用既有 JSON schema 的 camelCase 命名。
    runId: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    baseCommit: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    dirtyHash: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    generatedAt: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    freshness: str = ''
    # 报告内容哈希：用于验证 artifact 完整性，防止篡改。
    reportHash: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    planId: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    planFingerprint: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    commandGroups: list[dict[str, Any]] = field(default_factory=list)  # noqa: N815
    processCounts: dict[str, int] = field(default_factory=dict)  # noqa: N815
    gateStates: dict[str, str] = field(default_factory=dict)  # noqa: N815


def concise_diagnostic(
    output: str,
    *,
    max_chars: int = DIAGNOSTIC_MAX_CHARS,
    max_lines: int = DIAGNOSTIC_MAX_LINES,
) -> str:
    """生成优先保留错误行且受字符数与行数限制的诊断摘要。"""
    raw_lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not raw_lines:
        return '(no gate output; inspect the artifact or rerun the command)'

    lines: list[str] = []
    seen: set[str] = set()
    for line in raw_lines:
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)

    priority = [index for index, line in enumerate(lines) if _DIAGNOSTIC_PRIORITY_RE.search(line)]
    selected = priority[:max_lines]
    if len(selected) < max_lines:
        for index in range(max(0, len(lines) - max_lines), len(lines)):
            if index not in selected:
                selected.append(index)
            if len(selected) >= max_lines:
                break
    selected.sort()

    excerpt = '\n'.join(lines[index] for index in selected)
    truncated = len(selected) < len(lines) or len(excerpt) > max_chars
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max(0, max_chars - 1)].rstrip() + '…'
    if truncated:
        excerpt += (
            '\n[diagnostic truncated; additional captured output is in the gate detail artifact]'
        )
    return excerpt


def _coerce_detail(detail: GateDetail | dict[str, Any]) -> GateDetail:
    """把序列化字典或现有对象规范化为 GateDetail。"""
    if isinstance(detail, GateDetail):
        return detail
    raw_command = detail.get('command') or []
    return GateDetail(
        name=str(detail.get('name', 'unknown')),
        status=str(detail.get('status', FAIL)),
        command=[str(part) for part in raw_command] if isinstance(raw_command, list) else [],
        exitCode=detail.get('exitCode') if isinstance(detail.get('exitCode'), int) else None,
        durationMs=(
            detail.get('durationMs') if isinstance(detail.get('durationMs'), int) else None
        ),
        output=str(detail.get('output', '') or ''),
        executionState=str(detail.get('executionState', 'EXECUTED')),
        groupId=str(detail.get('groupId', '')),
        rerunCommand=str(detail.get('rerunCommand', '')),
        taskOutcomes={
            str(key): str(value) for key, value in dict(detail.get('taskOutcomes') or {}).items()
        },
        taskFailureReasons={
            str(key): str(value)
            for key, value in dict(detail.get('taskFailureReasons') or {}).items()
        },
        mode=str(detail.get('mode', '')),
        targetSeconds=(
            detail.get('targetSeconds') if isinstance(detail.get('targetSeconds'), int) else None
        ),
        timingState=str(detail.get('timingState', '')),
        reason=str(detail.get('reason', '')),
    )


def _affected_files(output: str, limit: int = 8) -> list[str]:
    """从诊断输出提取数量受限且去重的受影响文件。"""
    files: list[str] = []
    for match in _FILE_REFERENCE_RE.finditer(output):
        value = match.group(1)
        if value not in files:
            files.append(value)
        if len(files) >= limit:
            break
    return files


def format_quality_report(
    summary: QualitySummary | dict[str, Any], artifact_path: str | Path
) -> str:
    """格式化质量结果；成功为单行，失败为有界可操作报告。"""
    if isinstance(summary, dict):
        status = str(summary.get('status', NOT_PASS)).upper()
        mode = str(summary.get('mode', 'unknown'))
        selector = summary.get('selector')
        selector_value = summary.get('selectorValue')
        raw_results = summary.get('gateResults') or {}
        results = dict(raw_results) if isinstance(raw_results, dict) else {}
        raw_details = summary.get('gateDetails') or []
        details = (
            [_coerce_detail(detail) for detail in raw_details if isinstance(detail, dict)]
            if isinstance(raw_details, list)
            else []
        )
        raw_reasons = summary.get('notPassReasons') or []
        reasons = list(raw_reasons) if isinstance(raw_reasons, list) else []
    else:
        status = summary.status.upper()
        mode = summary.mode
        selector = summary.selector
        selector_value = summary.selectorValue
        results = summary.gateResults
        details = [_coerce_detail(detail) for detail in summary.gateDetails]
        reasons = summary.notPassReasons

    passed = sum(str(value).upper() == PASS for value in results.values())
    artifact = str(artifact_path)
    selection = f'{selector}:{selector_value}' if selector and selector_value else 'automatic'
    headline = (
        f'QUALITY_GATE_RESULT status={status} mode={mode} selector={selection} '
        f'passed={passed}/{len(results)} artifact={artifact}'
    )
    if status == PASS:
        return headline

    failed_details = [detail for detail in details if detail.status.upper() != PASS]
    if not failed_details:
        reason = concise_diagnostic('\n'.join(str(item) for item in reasons))
        return f'{headline}\nFAILED_GATES:\n- gate=unknown status={status}\n  error={reason}'

    lines = [headline, 'FAILED_GATES:']
    for detail in failed_details[:FAILED_GATE_REPORT_LIMIT]:
        gate_status = detail.status.upper()
        rendered_command = ''
        reason_suffix = f' reason={detail.reason}' if detail.reason else ''
        lines.append(
            f'- gate={detail.name} status={gate_status} exit_code={detail.exitCode}{reason_suffix}'
        )
        if detail.command:
            rendered_command = shlex.join(str(part) for part in detail.command)
            lines.append(f'  command={rendered_command}')
        files = _affected_files(detail.output)
        if files:
            lines.append(f'  affected_files={", ".join(files)}')
        lines.append('  error_summary:')
        lines.extend(f'    {line}' for line in concise_diagnostic(detail.output).splitlines())
        if gate_status == BLOCKED:
            suffix = f' Then rerun: {rendered_command}' if rendered_command else ''
            lines.append(f'  fix_hint=Fix the repository issue.{suffix}')
        elif gate_status == FAIL:
            suffix = f' Then rerun: {rendered_command}' if rendered_command else ''
            lines.append(
                '  fix_hint=Restore the missing runtime, input, dependency, or environment.'
                + suffix
            )
    omitted = len(failed_details) - FAILED_GATE_REPORT_LIMIT
    if omitted > 0:
        lines.append(f'... omitted_failed_gates={omitted}; inspect artifact for complete details')
    return '\n'.join(lines)


def compute_overall(gate_results: dict[str, str]) -> tuple[str, list[str]]:
    """把三态 Gate 明细归约为唯一对外 PASS/NOT_PASS。"""
    failures: list[str] = []
    if not gate_results:
        return NOT_PASS, ['gateResults is empty; cannot default to PASS.']

    for name, status in gate_results.items():
        normalized = str(status).upper()
        if normalized not in ALLOWED_STATUSES:
            failures.append(f'{name} has invalid status: {status}')
        elif normalized in {FAIL, BLOCKED}:
            failures.append(f'{name}={normalized}')

    return (PASS, []) if not failures else (NOT_PASS, failures)


def _compute_report_hash(data: dict) -> str:
    """计算 artifact 内容的 12 位稳定 hash。"""
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]


def write_quality_summary(
    base_dir: Path,
    summary: QualitySummary,
    selection_specific: bool = True,
) -> Path:
    """写入 quality summary artifact，并返回 JSON 路径。"""
    out_dir = base_dir / summary.changeId
    out_dir.mkdir(parents=True, exist_ok=True)

    label = summary.selectorValue or summary.mode
    filename = (
        f'quality-gate-summary.{label}.json' if selection_specific else 'quality-gate-summary.json'
    )
    summary_path = out_dir / filename

    # 先计算 reportHash（基于不含 reportHash 的字典），再写入完整 artifact。
    summary_dict = asdict(summary)
    summary_dict['reportHash'] = _compute_report_hash(summary_dict)
    summary.reportHash = summary_dict['reportHash']

    summary_path.write_text(
        json.dumps(summary_dict, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )

    details = out_dir / (
        f'gate-details.{label}.json' if selection_specific else 'gate-details.json'
    )
    details.write_text(
        json.dumps(summary.gateDetails, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    return summary_path


def build_summary(
    mode: str,
    change_id: str,
    started_at: str,
    details: list[GateDetail],
    *,
    selector: str | None = None,
    selector_value: str | None = None,
    not_triggered_gates: list[str] | None = None,
    repo_root: Path | None = None,
    execution_metadata: dict[str, Any] | None = None,
) -> QualitySummary:
    """由 executor 明细构造无并发元数据的 schema v4 Gate 运行摘要。"""
    required = {detail.name: detail.status for detail in details}
    status, failures = compute_overall(required)
    warning_failures = [
        f'{detail.name}: warning after trigger'
        for detail in details
        if 'warning after trigger' in (detail.output or '')
    ]
    base_commit = resolve_base_commit(str(repo_root)) if repo_root else ''
    dirty_hash = resolve_dirty_hash(str(repo_root)) if repo_root else ''
    metadata = execution_metadata or {}
    finished_at = utc_now()
    return QualitySummary(
        schemaVersion=4,
        status=status,
        mode=mode,
        changeId=change_id,
        startedAt=started_at,
        finishedAt=finished_at,
        gateResults=required,
        selector=selector,
        selectorValue=selector_value,
        notPassReasons=failures,
        warnings=warning_failures,
        artifacts={
            'notTriggeredGates': not_triggered_gates or [],
            'inputAuditReason': str(metadata.get('inputAuditReason', '')),
        },
        gateDetails=[asdict(detail) for detail in details],
        runId=(
            f'{change_id}-{mode}-{selector or "automatic"}-'
            f'{selector_value or "all-matched"}-{started_at}'
        ),
        baseCommit=base_commit,
        dirtyHash=dirty_hash,
        generatedAt=finished_at,
        freshness='0s',
        planId=str(metadata.get('planId', '')),
        planFingerprint=str(metadata.get('planFingerprint', '')),
        commandGroups=list(metadata.get('commandGroups', [])),
        processCounts=dict(metadata.get('processCounts', {})),
        gateStates={
            **{
                detail.name: (
                    detail.executionState
                    if detail.executionState in {'EXECUTED', 'NOT_TRIGGERED', 'FAILED', 'BLOCKED'}
                    else ('EXECUTED' if detail.status == PASS else detail.status)
                )
                for detail in details
            },
            **dict.fromkeys(not_triggered_gates or [], 'NOT_TRIGGERED'),
        },
    )
