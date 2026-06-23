"""Java batch 适配器：将 scan 流程的归一化请求委托给 Java batch 进程。

本模块是 scan 流程和 JavaBatchBridge 之间的适配层。它收集 scan 发现的
会话请求，批量发送给 Java 进程，并将结果映射回 scan 可消费的格式。

不提供 Python fallback：Java 不可用时明确失败。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from session_browser.normalized.java_bridge import (
    BatchResult,
    BatchSummary,
    BridgeError,
    JavaBatchBridge,
    JavaNotAvailableError,
    ResultStatus,
    run_batch,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NormalizedBatchRequest:
    """scan 流程中的一条归一化请求。

    Attributes:
        request_id: 请求标识，用于与结果关联。
        source_id: 源标识，Java 端 SourceAdapterRegistry 使用的 ID。
            如 'CLAUDE_CODE'、'CODEX'、'QODER'。
        root_path: 会话数据根目录路径。
        session_key: scan 流程使用的 canonical session key。
    """

    request_id: str
    source_id: str
    root_path: str
    session_key: str


@dataclass(frozen=True)
class NormalizedBatchOutcome:
    """batch 执行结果的聚合。

    Attributes:
        results: 每条请求对应的 BatchResult。
        summary: Java 端的结束摘要。
        success_count: 成功写入的 artifact 数量。
        unchanged_count: 未变更的数量。
        failed_count: 失败的数量。
    """

    results: list[BatchResult]
    summary: BatchSummary
    success_count: int
    unchanged_count: int
    failed_count: int

    def result_for(self, request_id: str) -> BatchResult | None:
        """按 request_id 查找对应的结果。

        Args:
            request_id: 请求标识。

        Returns:
            匹配的 BatchResult，不存在时返回 None。
        """
        for r in self.results:
            if r.request_id == request_id:
                return r
        return None


# Python source_id 到 Java SourceAdapterRegistry sourceId 的映射。
# Java 端使用大写枚举值，如 'CLAUDE_CODE'、'CODEX'、'QODER'。
_SOURCE_ID_MAP: dict[str, str] = {
    'claude_code': 'CLAUDE_CODE',
    'codex': 'CODEX',
    'qoder': 'QODER',
}


def map_source_id(python_agent: str) -> str:
    """将 Python scan 流程的 agent 名称映射为 Java sourceId。

    Args:
        python_agent: Python 端的 agent 标识，如 'claude_code'。

    Returns:
        Java 端的 sourceId 字符串。

    Raises:
        ValueError: 不支持的 agent 名称。
    """
    java_id = _SOURCE_ID_MAP.get(python_agent)
    if java_id is None:
        raise ValueError(f'不支持的 agent: {python_agent!r}')
    return java_id


def execute_java_normalized_batch(
    requests: list[NormalizedBatchRequest],
    *,
    output_dir: Path,
    timeout_seconds: float = 300.0,
    launcher: Path | None = None,
) -> NormalizedBatchOutcome:
    """执行一次 Java batch 归一化。

    一个 scan 只调用一次，N 个请求共享一个 JVM。
    Java 不可用时抛出 JavaNotAvailableError，不提供 Python fallback。

    Args:
        requests: scan 收集的归一化请求列表。
        output_dir: Java batch 写入 artifact 的目录。
        timeout_seconds: 超时秒数。
        launcher: 可选的 launcher 路径。

    Returns:
        包含结果列表和统计的 NormalizedBatchOutcome。

    Raises:
        JavaNotAvailableError: Java launcher 不可用。
        BridgeError: 进程通信失败。
    """
    if not requests:
        return NormalizedBatchOutcome(
            results=[],
            summary=BatchSummary(),
            success_count=0,
            unchanged_count=0,
            failed_count=0,
        )

    # 将 NormalizedBatchRequest 转换为 bridge 可接受的元组
    bridge_requests = [
        (req.request_id, req.source_id, req.root_path) for req in requests
    ]

    results, summary = run_batch(
        bridge_requests,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        launcher=launcher,
    )

    success_count = sum(1 for r in results if r.status == ResultStatus.WRITTEN)
    unchanged_count = sum(
        1 for r in results if r.status == ResultStatus.UNCHANGED
    )
    failed_count = sum(
        1
        for r in results
        if r.status in (ResultStatus.FAILED, ResultStatus.RETRYABLE)
    )

    return NormalizedBatchOutcome(
        results=results,
        summary=summary,
        success_count=success_count,
        unchanged_count=unchanged_count,
        failed_count=failed_count,
    )
