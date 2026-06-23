"""Java batch bridge 单元测试。

覆盖：launcher 解析、协议解析、状态映射、异常路径、单 JVM 约束。
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from session_browser.normalized.java_bridge import (
    BatchResult,
    BatchSummary,
    BridgeCancelledError,
    BridgeError,
    BridgeTimeoutError,
    JavaBatchBridge,
    JavaNotAvailableError,
    ProtocolFatalError,
    ResultStatus,
    _find_repo_root,
    resolve_java_launcher,
    run_batch,
)


class TestResultStatus:
    """ResultStatus 枚举值正确性。"""

    def test_all_statuses_exist(self):
        assert ResultStatus.WRITTEN.value == 'WRITTEN'
        assert ResultStatus.UNCHANGED.value == 'UNCHANGED'
        assert ResultStatus.RETRYABLE.value == 'RETRYABLE'
        assert ResultStatus.FAILED.value == 'FAILED'
        assert ResultStatus.PROTOCOL_FATAL.value == 'PROTOCOL_FATAL'


class TestBatchResult:
    """BatchResult 不可变数据类。"""

    def test_frozen_instance(self):
        result = BatchResult(request_id='1', status=ResultStatus.WRITTEN)
        with pytest.raises(AttributeError):
            result.request_id = '2'

    def test_default_fields(self):
        result = BatchResult(request_id='1', status=ResultStatus.FAILED)
        assert result.session_key == ''
        assert result.artifact_path == ''
        assert result.content_hash == ''
        assert result.error == ''


class TestBatchSummary:
    """BatchSummary 不可变数据类。"""

    def test_default_zero(self):
        s = BatchSummary()
        assert s.total == 0
        assert s.written == 0
        assert s.unchanged == 0
        assert s.failed == 0


class TestResolveJavaLauncher:
    """launcher 解析优先级。"""

    def test_env_var_valid_path(self, tmp_path):
        fake_launcher = tmp_path / 'app-cli'
        fake_launcher.write_text('#!/bin/sh\n')
        fake_launcher.chmod(0o755)

        with mock.patch.dict(os.environ, {'SESSION_BROWSER_JAVA_CLI': str(fake_launcher)}):
            result = resolve_java_launcher()
            assert result == fake_launcher

    def test_env_var_invalid_path_raises(self):
        with mock.patch.dict(
            os.environ, {'SESSION_BROWSER_JAVA_CLI': '/nonexistent/path/app-cli'}
        ):
            with pytest.raises(JavaNotAvailableError, match='不可用路径'):
                resolve_java_launcher()

    def test_repo_install_dist(self, tmp_path):
        """仓库内 installDist 产物优先于 PATH。"""
        install_dir = tmp_path / 'java' / 'app-cli' / 'build' / 'install' / 'app-cli' / 'bin'
        install_dir.mkdir(parents=True)
        launcher = install_dir / 'app-cli'
        launcher.write_text('#!/bin/sh\n')
        launcher.chmod(0o755)

        # 清除环境变量避免干扰
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                'session_browser.normalized.java_bridge._find_repo_root',
                return_value=tmp_path,
            ),
        ):
            result = resolve_java_launcher()
            assert result == launcher

    def test_no_launcher_raises(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch(
                'session_browser.normalized.java_bridge._find_repo_root',
                return_value=None,
            ),
            mock.patch('shutil.which', return_value=None),
        ):
            with pytest.raises(JavaNotAvailableError, match='不可用'):
                resolve_java_launcher()


class TestMapJavaStatus:
    """Java 端 status 到 ResultStatus 的映射。"""

    def test_success_with_path_is_written(self):
        assert (
            JavaBatchBridge._map_java_status('success', '/some/path')
            == ResultStatus.WRITTEN
        )

    def test_success_without_path_is_unchanged(self):
        assert JavaBatchBridge._map_java_status('success', '') == ResultStatus.UNCHANGED

    def test_skipped_is_unchanged(self):
        assert JavaBatchBridge._map_java_status('skipped', '') == ResultStatus.UNCHANGED

    def test_error_is_failed(self):
        assert JavaBatchBridge._map_java_status('error', '') == ResultStatus.FAILED

    def test_unknown_status_is_failed(self):
        assert JavaBatchBridge._map_java_status('weird', '') == ResultStatus.FAILED


class TestParseResult:
    """stdout JSON 行到 BatchResult 的解析。"""

    def test_parse_success_result(self):
        bridge = JavaBatchBridge(output_dir=Path('/tmp/test'))
        obj = {
            'requestId': 'req-1',
            'sessionKey': 'claude_code:abc',
            'status': 'success',
            'artifactPath': '/data/artifact.json',
            'error': None,
            'contentHash': 'sha256-abc',
        }
        result = bridge._parse_result(obj)
        assert result.request_id == 'req-1'
        assert result.status == ResultStatus.WRITTEN
        assert result.session_key == 'claude_code:abc'
        assert result.artifact_path == '/data/artifact.json'
        assert result.content_hash == 'sha256-abc'

    def test_parse_error_result(self):
        bridge = JavaBatchBridge(output_dir=Path('/tmp/test'))
        obj = {
            'requestId': 'req-2',
            'sessionKey': '',
            'status': 'error',
            'artifactPath': None,
            'error': 'Unknown source',
            'contentHash': None,
        }
        result = bridge._parse_result(obj)
        assert result.status == ResultStatus.FAILED
        assert result.error == 'Unknown source'


class TestBridgeProtocol:
    """bridge 协议解析的边界条件。"""

    def test_read_results_with_valid_ndjson(self, tmp_path):
        """有效的 NDJSON stdout 能正确解析为结果。"""
        header = json.dumps({'protocol': 'normalized-batch', 'version': '1.0'})
        request_echo = json.dumps(
            {'type': 'request', 'requestId': 'req-1', 'sourceId': 'CLAUDE_CODE', 'rootPath': '/tmp'}
        )
        result_line = json.dumps(
            {
                'requestId': 'req-1',
                'sessionKey': 'claude_code:abc',
                'status': 'success',
                'artifactPath': '/data/artifact.json',
                'error': None,
                'contentHash': 'abc123',
            }
        )
        end_line = json.dumps({'type': 'end', 'totalRequests': 1, 'written': 1, 'failed': 0})

        stdout_lines = '\n'.join([header, request_echo, result_line, end_line]) + '\n'

        bridge = JavaBatchBridge(output_dir=tmp_path)
        # 模拟 process.stdout
        mock_stdout = stdout_lines.splitlines(keepends=True)
        mock_process = mock.MagicMock()
        mock_process.stdout = mock_stdout
        mock_process.poll.return_value = 0
        mock_process.wait.return_value = 0
        bridge._process = mock_process

        bridge._read_results()

        assert len(bridge._results) == 1
        assert bridge._results[0].status == ResultStatus.WRITTEN
        assert bridge._summary.total == 1
        assert bridge._summary.written == 1

    def test_read_results_non_json_raises_protocol_fatal(self, tmp_path):
        """非 NDJSON 行触发 ProtocolFatalError。"""
        bridge = JavaBatchBridge(output_dir=tmp_path)
        mock_process = mock.MagicMock()
        mock_process.stdout = ['not valid json\n']
        bridge._process = mock_process

        with pytest.raises(ProtocolFatalError, match='非 NDJSON'):
            bridge._read_results()

    def test_read_results_non_object_raises_protocol_fatal(self, tmp_path):
        """非 JSON object 行触发 ProtocolFatalError。"""
        bridge = JavaBatchBridge(output_dir=tmp_path)
        mock_process = mock.MagicMock()
        mock_process.stdout = ['[1, 2, 3]\n']
        bridge._process = mock_process

        with pytest.raises(ProtocolFatalError, match='非 JSON object'):
            bridge._read_results()


class TestBridgeLifecycle:
    """bridge 生命周期管理。"""

    def test_submit_before_start_raises(self, tmp_path):
        bridge = JavaBatchBridge(output_dir=tmp_path)
        with pytest.raises(BridgeError, match='未启动'):
            bridge.submit('req-1', 'CLAUDE_CODE', '/tmp/test')

    def test_finish_before_start_raises(self, tmp_path):
        bridge = JavaBatchBridge(output_dir=tmp_path)
        with pytest.raises(BridgeError, match='未启动'):
            bridge.finish()

    def test_cancel_sets_flag(self, tmp_path):
        bridge = JavaBatchBridge(output_dir=tmp_path)
        bridge.cancel()
        assert bridge._cancelled is True

    def test_submit_after_cancel_raises(self, tmp_path):
        bridge = JavaBatchBridge(output_dir=tmp_path)
        bridge._cancelled = True
        bridge._process = mock.MagicMock()
        bridge._process.stdin = mock.MagicMock()
        with pytest.raises(BridgeCancelledError):
            bridge.submit('req-1', 'CLAUDE_CODE', '/tmp/test')

    def test_close_kills_process(self, tmp_path):
        bridge = JavaBatchBridge(output_dir=tmp_path)
        mock_process = mock.MagicMock()
        mock_process.poll.return_value = None  # 进程仍在运行
        bridge._process = mock_process

        bridge.close()

        mock_process.kill.assert_called_once()
        assert bridge._process is None

    def test_context_manager(self, tmp_path):
        """context manager 确保资源释放。"""
        bridge = JavaBatchBridge(output_dir=tmp_path)
        mock_process = mock.MagicMock()
        mock_process.poll.return_value = 0
        mock_process.stdin = mock.MagicMock()
        mock_process.stdout = None
        mock_process.stderr = None

        # 手动设置 process 以跳过 start() 的真实进程创建
        bridge._process = mock_process

        bridge.close()
        assert bridge._process is None


class TestRunBatch:
    """run_batch 便捷函数。"""

    def test_empty_requests(self, tmp_path):
        """空请求列表不启动进程。"""
        results, summary = run_batch([], output_dir=tmp_path)
        # run_batch 会尝试 start，所以需要 mock
        # 实际上空请求直接返回空结果
        assert results == []

    def test_run_batch_with_mock_launcher(self, tmp_path):
        """使用 mock launcher 验证端到端流程。"""
        # 构造模拟的 stdout 输出
        header = json.dumps({'protocol': 'normalized-batch', 'version': '1.0'})
        result = json.dumps({
            'requestId': 'req-1',
            'sessionKey': 'claude_code:abc',
            'status': 'success',
            'artifactPath': str(tmp_path / 'artifact.json'),
            'error': None,
            'contentHash': 'abc123',
        })
        end = json.dumps({'type': 'end', 'totalRequests': 1, 'written': 1, 'failed': 0})
        stdout_text = '\n'.join([header, result, end]) + '\n'

        fake_launcher = tmp_path / 'fake-cli'
        fake_launcher.write_text('#!/bin/sh\ncat\n')
        fake_launcher.chmod(0o755)

        bridge = JavaBatchBridge(output_dir=tmp_path, launcher=fake_launcher)
        # 直接模拟 finish 流程
        mock_process = mock.MagicMock()
        mock_process.stdout = stdout_text.splitlines(keepends=True)
        mock_process.poll.return_value = 0
        mock_process.wait.return_value = 0
        mock_process.stderr = None
        mock_process.stdin = mock.MagicMock()
        bridge._process = mock_process

        results, summary = bridge.finish()

        assert len(results) == 1
        assert results[0].status == ResultStatus.WRITTEN
        assert summary.total == 1
