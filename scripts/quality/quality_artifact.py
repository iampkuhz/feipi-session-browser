"""构建质量门运行结果的 JSON artifact。

artifact schema 遵循 harness 和 OpenSpec 工作流消费的门运行契约：每个 target
的 summary 记录 change id、时间戳、必需门状态、阻断失败、警告、辅助 artifact
路径和原始门详情。必需门是 fail-closed 的：空集合阻断运行，`SKIPPED` 视为
失败，无效状态报告为阻断失败而非规范化为通过。

artifact 元数据包含 run id、base commit、dirty hash、生成时间、report hash，
用于证据溯源和完整性验证。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# 01. Constants
PASS = 'PASS'
FAIL = 'FAIL'
BLOCKED = 'BLOCKED'
SKIPPED = 'SKIPPED'
ALLOWED_STATUSES = {PASS, FAIL, BLOCKED, SKIPPED}


# 02. Time
def utc_now() -> str:
    """Return the current UTC timestamp for quality artifact metadata.

    Returns:
        An ISO-8601 timestamp with timezone information.
    """
    return datetime.now(timezone.utc).isoformat()


def resolve_base_commit(repo_root: str = '.') -> str:
    """Return the current HEAD commit hash for artifact traceability.

    Args:
        repo_root: Repository root for git command execution.

    Returns:
        Short commit hash or empty string when git is unavailable.
    """
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
    """Return a short hash of the working tree dirty state.

    Args:
        repo_root: Repository root for git command execution.

    Returns:
        Short dirty hash or empty string when clean or git is unavailable.
    """
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
            return hashlib.sha256(result.stdout.encode()).hexdigest()[:12]
        return ''
    except Exception:
        return ''


def is_artifact_fresh(artifact_path: str, max_age_seconds: int = 3600) -> bool:
    """Check whether a quality artifact is still fresh enough to use as evidence.

    Args:
        artifact_path: Path to the artifact JSON file.
        max_age_seconds: Maximum acceptable age in seconds.

    Returns:
        True when the artifact exists and was generated within the freshness window.
    """
    from pathlib import Path as _Path
    p = _Path(artifact_path)
    if not p.exists():
        return False
    age = datetime.now(timezone.utc).timestamp() - p.stat().st_mtime
    return age <= max_age_seconds


# 03. Gate detail
@dataclass
class GateDetail:
    """Serializable detail for one executed quality gate.

    Attributes:
        name: Stable gate name shown in reports.
        status: Gate outcome, normally one of `PASS`, `FAIL`, `BLOCKED`, or `SKIPPED`.
        command: Command vector used to run the gate.
        exitCode: Process exit code, or `None` when execution did not start.
        durationMs: Runtime duration in milliseconds, or `None` when unavailable.
        output: Captured human-readable output for diagnostics.
    """

    name: str
    status: str
    command: list[str] = field(default_factory=list)
    exitCode: int | None = None  # noqa: N815 - Preserve JSON artifact schema.
    durationMs: int | None = None  # noqa: N815 - Preserve JSON artifact schema.
    output: str = ''


# 04. Summary construction
@dataclass
class QualitySummary:
    """Top-level quality artifact summary written by a required gate run.

    Attributes:
        schemaVersion: Integer schema version for downstream compatibility checks.
        status: Overall status computed from required gate outcomes.
        target: Quality target name, such as a changed-file slice or regression target.
        changeId: OpenSpec change id associated with the run.
        startedAt: UTC timestamp captured when the quality run started.
        finishedAt: UTC timestamp captured when the quality run finished.
        requiredGates: Mapping from required gate name to status.
        blockingFailures: Failure messages that prevent the run from passing.
        warnings: Non-blocking diagnostics retained for operators.
        artifacts: Extra artifact paths or metadata produced by the run.
        gateDetails: Raw per-gate details serialized alongside the summary.
    """

    schemaVersion: int  # noqa: N815 - Preserve JSON artifact schema.
    status: str
    target: str
    changeId: str  # noqa: N815 - Preserve JSON artifact schema.
    startedAt: str  # noqa: N815 - Preserve JSON artifact schema.
    finishedAt: str  # noqa: N815 - Preserve JSON artifact schema.
    requiredGates: dict[str, str]  # noqa: N815 - Preserve JSON artifact schema.
    blockingFailures: list[str] = field(default_factory=list)  # noqa: N815 - Preserve schema.
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
    gateDetails: list[dict[str, Any]] = field(default_factory=list)  # noqa: N815 - Preserve schema.
    # 04b. 新增 artifact 元数据字段
    runId: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    baseCommit: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    dirtyHash: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    generatedAt: str = ''  # noqa: N815 - Preserve JSON artifact schema.
    freshness: str = ''
    # 报告内容哈希：用于验证 artifact 完整性，防止篡改。
    reportHash: str = ''  # noqa: N815 - Preserve JSON artifact schema.


# 05. Overall status computation
def compute_overall(required_gates: dict[str, str]) -> tuple[str, list[str]]:
    """Compute the fail-closed overall status for required gates.

    Args:
        required_gates: Mapping from required gate name to its reported status.

    Returns:
        A tuple containing the overall status and blocking failure messages. Empty
        required gate mappings return `BLOCKED`; `SKIPPED`, `FAIL`, `BLOCKED`, and
        unknown statuses all produce blocking failures.
    """
    failures: list[str] = []
    if not required_gates:
        return BLOCKED, ['requiredGates is empty; cannot default to PASS.']

    for name, status in required_gates.items():
        normalized = str(status).upper()
        if normalized not in ALLOWED_STATUSES:
            failures.append(f'{name} has invalid status: {status}')
        elif normalized == SKIPPED:
            failures.append(f'{name} is a required gate and cannot be SKIPPED.')
        elif normalized in {FAIL, BLOCKED}:
            failures.append(f'{name}={normalized}')

    return (PASS, []) if not failures else (FAIL, failures)


# 06. Artifact writing
def _compute_report_hash(data: dict) -> str:
    """计算 artifact 内容的 SHA-256 哈希，用于完整性验证。

    Args:
        data: 序列化后的 artifact 字典（不含 reportHash 自身）。

    Returns:
        12 位十六进制哈希前缀。
    """
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]


def write_quality_summary(
    base_dir: Path, summary: QualitySummary, target_specific: bool = True
) -> Path:
    """写入 quality summary 和 detail artifact，并计算 reportHash。

    Args:
        base_dir: artifact 基目录；change id 附加在其下方。
        summary: 要序列化的 summary dataclass。
        target_specific: 文件名是否包含 ``summary.target`` 以支持并行 target。

    Returns:
        写入的 summary JSON 文件路径。
    """
    out_dir = base_dir / summary.changeId
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = (
        f'quality-gate-summary.{summary.target}.json'
        if target_specific
        else 'quality-gate-summary.json'
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
        f'gate-details.{summary.target}.json' if target_specific else 'gate-details.json'
    )
    details.write_text(
        json.dumps(summary.gateDetails, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    return summary_path


# 07. Self-test
def _self_test() -> None:
    """Run a minimal deterministic check for direct script execution."""
    assert compute_overall({'a': 'PASS'}) == ('PASS', [])
    status, failures = compute_overall({'a': 'SKIPPED'})
    assert status == 'FAIL'
    assert failures
    status, failures = compute_overall({})
    assert status == 'BLOCKED'


if __name__ == '__main__':
    _self_test()
    print('quality_artifact self-test PASS')
