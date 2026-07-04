"""构建 quality gate 运行结果的 JSON artifact。"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# 定义 PASS 常量配置。
PASS = 'PASS'
FAIL = 'FAIL'
BLOCKED = 'BLOCKED'
SKIPPED = 'SKIPPED'
ALLOWED_STATUSES = {PASS, FAIL, BLOCKED, SKIPPED}


# 返回当前 UTC timestamp。
def utc_now() -> str:
    """返回：
        当前 UTC timestamp 字符串。
    """
    return datetime.now(timezone.utc).isoformat()


# 读取当前 HEAD 的短 commit hash。
def resolve_base_commit(repo_root: str = '.') -> str:
    """参数：
        repo_root: 执行 git 命令时使用的 repo root。

    返回：
        短 commit hash；git 不可用时返回空字符串。
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


# 计算 working tree dirty 状态短 hash。
def resolve_dirty_hash(repo_root: str = '.') -> str:
    """参数：
        repo_root: 执行 git 命令时使用的 repo root。

    返回：
        dirty 状态短 hash；工作区干净或 git 不可用时返回空字符串。
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

            # 使用 diff 摘要计算稳定短哈希，标识当前工作区的 dirty 状态。
            return hashlib.sha256(result.stdout.encode()).hexdigest()[:12]
        return ''
    except Exception:
        return ''


# 判断 quality artifact 是否仍在有效时间窗口内。
def is_artifact_fresh(artifact_path: str, max_age_seconds: int = 3600) -> bool:
    """参数：
        artifact_path: 路径到 artifact JSON 文件。
        max_age_seconds: 允许的最大年龄，单位为秒。

    返回：
        满足条件时返回 true，否则返回 false。
    """
    from pathlib import Path as _Path

    p = _Path(artifact_path)
    if not p.exists():
        return False
    # 用文件 mtime 计算 artifact 年龄，避免读取损坏 JSON 时影响新鲜度判断。
    age = datetime.now(timezone.utc).timestamp() - p.stat().st_mtime
    return age <= max_age_seconds


@dataclass
class GateDetail:
    """表示 GateDetail。

    属性：
        name: 名称。
        status: 状态值。
        command: 执行命令参数列表。
        exitCode: 进程退出码；未启动时为 None。
        durationMs: 运行耗时，单位为毫秒。
        output: 诊断输出文本。
    """

    name: str
    status: str
    command: list[str] = field(default_factory=list)
    exitCode: int | None = None  # noqa: N815 - Preserve JSON artifact schema.
    durationMs: int | None = None  # noqa: N815 - Preserve JSON artifact schema.
    output: str = ''


@dataclass
class QualitySummary:
    """表示 QualitySummary。

    属性：
        schemaVersion: artifact schema 版本。
        status: 状态值。
        target: 当前要运行或解析的 quality gate target 名称。
        changeId: OpenSpec change id。
        startedAt: 运行开始时间。
        finishedAt: 运行结束时间。
        requiredGates: 必需 gate 状态映射。
        blockingFailures: 阻断通过的失败消息列表。
        warnings: 警告列表。
        artifacts: 附加 artifact 路径或 metadata。
        gateDetails: 原始 gate detail 列表。
        runId: 本次运行 id。
        baseCommit: base commit 短 hash。
        dirtyHash: working tree dirty 状态 hash。
        generatedAt: artifact 生成时间。
        freshness: artifact 新鲜度状态。
        reportHash: 报告内容 hash。
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


# 计算必需 gate 的 fail-closed 总体状态。
def compute_overall(required_gates: dict[str, str]) -> tuple[str, list[str]]:
    """参数：
        required_gates: 必需 gate 名称到报告状态的映射。

    返回：
        结果 tuple。
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


# 计算 artifact 内容 hash。
def _compute_report_hash(data: dict) -> str:
    """参数：
        data: 待处理的数据对象。

    返回：
        12 位十六进制哈希前缀。
    """
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]


# 写入 quality summary 及其明细 artifact。
def write_quality_summary(
    base_dir: Path, summary: QualitySummary, target_specific: bool = True
) -> Path:
    """参数：
        base_dir: artifact 基目录；change id 附加在其下方。
        summary: 要序列化的 summary dataclass。
        target_specific: 文件名是否包含 ``summary.target`` 以支持并行 target。

    返回：
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


# 运行脚本自测试场景。
def _self_test() -> None:
    assert compute_overall({'a': 'PASS'}) == ('PASS', [])
    status, failures = compute_overall({'a': 'SKIPPED'})
    assert status == 'FAIL'
    assert failures
    status, failures = compute_overall({})
    assert status == 'BLOCKED'


if __name__ == '__main__':
    _self_test()
    print('quality_artifact self-test PASS')
