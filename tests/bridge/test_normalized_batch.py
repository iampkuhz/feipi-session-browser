"""Java normalized batch 适配器单元测试。

覆盖：source_id 映射、空请求、batch 结果聚合。
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from session_browser.normalized.java_bridge import (
    BatchResult,
    BatchSummary,
    ResultStatus,
)
from session_browser.normalized.normalized_batch import (
    NormalizedBatchOutcome,
    NormalizedBatchRequest,
    execute_java_normalized_batch,
    map_source_id,
)


class TestMapSourceId:
    """Python agent 到 Java sourceId 映射。"""

    def test_claude_code(self):
        assert map_source_id('claude_code') == 'CLAUDE_CODE'

    def test_codex(self):
        assert map_source_id('codex') == 'CODEX'

    def test_qoder(self):
        assert map_source_id('qoder') == 'QODER'

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match='不支持'):
            map_source_id('unknown_agent')


class TestNormalizedBatchRequest:
    """请求数据类。"""

    def test_frozen(self):
        req = NormalizedBatchRequest(
            request_id='1',
            source_id='CLAUDE_CODE',
            root_path='/tmp',
            session_key='claude_code:abc',
        )
        with pytest.raises(AttributeError):
            req.request_id = '2'


class TestNormalizedBatchOutcome:
    """结果聚合数据类。"""

    def test_result_for_found(self):
        results = [
            BatchResult(request_id='1', status=ResultStatus.WRITTEN),
            BatchResult(request_id='2', status=ResultStatus.FAILED),
        ]
        outcome = NormalizedBatchOutcome(
            results=results,
            summary=BatchSummary(),
            success_count=1,
            unchanged_count=0,
            failed_count=1,
        )
        assert outcome.result_for('1').status == ResultStatus.WRITTEN
        assert outcome.result_for('2').status == ResultStatus.FAILED

    def test_result_for_not_found(self):
        outcome = NormalizedBatchOutcome(
            results=[],
            summary=BatchSummary(),
            success_count=0,
            unchanged_count=0,
            failed_count=0,
        )
        assert outcome.result_for('nonexistent') is None


class TestExecuteJavaNormalizedBatch:
    """batch 执行集成测试。"""

    def test_empty_requests_returns_empty(self, tmp_path):
        """空请求列表不启动 Java 进程。"""
        outcome = execute_java_normalized_batch(
            [],
            output_dir=tmp_path,
        )
        assert outcome.results == []
        assert outcome.success_count == 0
        assert outcome.unchanged_count == 0
        assert outcome.failed_count == 0

    def test_batch_result_aggregation(self, tmp_path):
        """结果统计正确聚合。"""
        mock_results = [
            BatchResult(
                request_id='1',
                status=ResultStatus.WRITTEN,
                session_key='claude_code:abc',
                artifact_path='/data/1.json',
            ),
            BatchResult(
                request_id='2',
                status=ResultStatus.UNCHANGED,
                session_key='claude_code:def',
            ),
            BatchResult(
                request_id='3',
                status=ResultStatus.FAILED,
                error='some error',
            ),
        ]
        mock_summary = BatchSummary(total=3, written=1, unchanged=1, failed=1)

        with mock.patch(
            'session_browser.normalized.normalized_batch.run_batch',
            return_value=(mock_results, mock_summary),
        ):
            requests = [
                NormalizedBatchRequest('1', 'CLAUDE_CODE', '/tmp/a', 'claude_code:abc'),
                NormalizedBatchRequest('2', 'CLAUDE_CODE', '/tmp/b', 'claude_code:def'),
                NormalizedBatchRequest('3', 'CLAUDE_CODE', '/tmp/c', 'claude_code:ghi'),
            ]
            outcome = execute_java_normalized_batch(
                requests,
                output_dir=tmp_path,
            )

        assert outcome.success_count == 1
        assert outcome.unchanged_count == 1
        assert outcome.failed_count == 1
        assert len(outcome.results) == 3

    def test_bridge_error_propagates(self, tmp_path):
        """bridge 错误不吞没，直接向上抛出。"""
        from session_browser.normalized.java_bridge import JavaNotAvailableError

        with mock.patch(
            'session_browser.normalized.normalized_batch.run_batch',
            side_effect=JavaNotAvailableError('Java 不可用'),
        ):
            requests = [
                NormalizedBatchRequest('1', 'CLAUDE_CODE', '/tmp/a', 'claude_code:abc'),
            ]
            with pytest.raises(JavaNotAvailableError, match='不可用'):
                execute_java_normalized_batch(requests, output_dir=tmp_path)
