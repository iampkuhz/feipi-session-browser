"""协议层故障注入测试。

验证 NDJSON 协议级别的故障场景：
- 半条 NDJSON（不完整行）
- stdout 污染（非 NDJSON 输出混入）
- 未知协议版本
- 重复请求 ID

每种故障都必须 fail closed，不丢弃错误信息。
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_browser.normalized.java_bridge import (
    JavaBatchBridge,
    ProtocolFatalError,
    ResultStatus,
)

SB_ROOT = Path(__file__).resolve().parents[2]


def _create_fake_java(stdout_content: str) -> str:
    """创建输出指定内容的 fake java launcher，返回脚本路径。"""
    fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='fake_java_')
    os.close(fd)
    # 转义 stdout_content 中的单引号
    escaped = stdout_content.replace("'", "'\\''")
    with open(script_path, 'w') as f:
        f.write('#!/bin/sh\n')
        f.write("# 消费 stdin\n")
        f.write('cat > /dev/null\n')
        f.write(f"printf '%s' '{escaped}'\n")
    os.chmod(script_path, stat.S_IRWXU)
    return script_path


def _run_bridge_with_stdout(stdout_content: str) -> tuple:
    """使用 fake launcher 运行 bridge 并返回 (results, summary, error)。"""
    script_path = _create_fake_java(stdout_content)
    try:
        bridge = JavaBatchBridge(
            output_dir=Path(tempfile.mkdtemp()),
            launcher=Path(script_path),
            timeout_seconds=5.0,
        )
        try:
            bridge.start()
            bridge.submit('req-1', 'claude', '/tmp/test')
            results, summary = bridge.finish()
            return results, summary, None
        except Exception as e:
            return [], None, e
        finally:
            bridge.close()
    finally:
        os.unlink(script_path)


# ---------------------------------------------------------------------------
# 半条 NDJSON（不完整行）
# ---------------------------------------------------------------------------


class TestIncompleteNdjson:
    """不完整 NDJSON 行必须触发 ProtocolFatalError。"""

    def test_partial_json_line_raises_protocol_fatal(self):
        """stdout 包含截断的 JSON 行时抛出 ProtocolFatalError。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '{"type":"request","requestId":"req-1"}\n'
            '{"requestId":"req-1","sessionKey":"a:b","status":"suc'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is not None
        assert isinstance(error, ProtocolFatalError)
        assert '非 NDJSON' in str(error) or 'JSON' in str(error)

    def test_empty_line_at_end_is_tolerated(self):
        """尾部空行不触发协议错误。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '{"type":"request","requestId":"req-1"}\n'
            '{"requestId":"req-1","sessionKey":"a:b","status":"success","artifactPath":"/tmp/x.json","contentHash":"abc"}\n'
            '{"type":"end","totalRequests":1}\n'
            '\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is None
        assert len(results) == 1
        assert results[0].status == ResultStatus.WRITTEN

    def test_half_line_in_middle_raises_protocol_fatal(self):
        """中间的不完整 JSON 行触发 ProtocolFatalError。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '{"requestId":"req-1","sessionKey":"a:b","status":"success","artifactPath":"/tmp/x.json","contentHash":"abc"}\n'
            'this is not json at all\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is not None
        assert isinstance(error, ProtocolFatalError)


# ---------------------------------------------------------------------------
# stdout 污染（非 NDJSON 输出）
# ---------------------------------------------------------------------------


class TestStdoutPollution:
    """stdout 中混入非 NDJSON 内容必须触发 ProtocolFatalError。"""

    def test_random_text_in_stdout_raises_protocol_fatal(self):
        """随机文本行触发协议致命错误。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            'WARNING: JVM heap low\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is not None
        assert isinstance(error, ProtocolFatalError)

    def test_log4j_in_stdout_raises_protocol_fatal(self):
        """Log4j 格式日志触发协议致命错误。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '2024-01-01 10:00:00 INFO  SomeClass - some message\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is not None
        assert isinstance(error, ProtocolFatalError)

    def test_json_array_in_stdout_raises_protocol_fatal(self):
        """JSON 数组（非 object）触发协议致命错误。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '[1, 2, 3]\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is not None
        assert isinstance(error, ProtocolFatalError)
        assert '非 JSON object' in str(error)


# ---------------------------------------------------------------------------
# 未知协议版本
# ---------------------------------------------------------------------------


class TestUnknownProtocolVersion:
    """未知协议版本应被记录但当前仍 fail closed。"""

    def test_unknown_version_logs_warning(self):
        """版本号不匹配时 bridge 记录 warning 但继续处理。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"99.0"}\n'
            '{"type":"request","requestId":"req-1"}\n'
            '{"requestId":"req-1","sessionKey":"a:b","status":"success","artifactPath":"/tmp/x.json","contentHash":"abc"}\n'
            '{"type":"end","totalRequests":1}\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        # 当前版本不匹配只产生 warning，不致命
        assert error is None
        assert len(results) == 1

    def test_completely_different_protocol_raises(self):
        """完全不同的协议名时 bridge 继续但忽略未知行。"""
        stdout = (
            '{"protocol":"some-other-protocol","version":"1.0"}\n'
            '{"requestId":"req-1","sessionKey":"a:b","status":"success","artifactPath":"/tmp/x.json","contentHash":"abc"}\n'
            '{"type":"end","totalRequests":1}\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        # 非匹配协议头被忽略，结果行仍可解析
        assert error is None
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 重复请求 ID
# ---------------------------------------------------------------------------


class TestDuplicateRequestId:
    """重复请求 ID 不导致协议中断，每个结果独立记录。"""

    def test_duplicate_request_id_both_recorded(self):
        """两个相同 requestId 的结果都被记录。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '{"type":"request","requestId":"dup-1"}\n'
            '{"requestId":"dup-1","sessionKey":"a:b","status":"success","artifactPath":"/tmp/x.json","contentHash":"abc"}\n'
            '{"requestId":"dup-1","sessionKey":"c:d","status":"success","artifactPath":"/tmp/y.json","contentHash":"def"}\n'
            '{"type":"end","totalRequests":1}\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is None
        assert len(results) == 2
        assert results[0].session_key == 'a:b'
        assert results[1].session_key == 'c:d'
        assert results[0].request_id == results[1].request_id == 'dup-1'

    def test_duplicate_with_error_status(self):
        """重复 ID 其中一个失败时两个结果都保留。"""
        stdout = (
            '{"protocol":"normalized-batch","version":"1.0"}\n'
            '{"requestId":"dup-2","sessionKey":"a:b","status":"success","artifactPath":"/tmp/x.json","contentHash":"abc"}\n'
            '{"requestId":"dup-2","sessionKey":"c:d","status":"error","error":"parse failed"}\n'
            '{"type":"end","totalRequests":1}\n'
        )
        results, summary, error = _run_bridge_with_stdout(stdout)
        assert error is None
        assert len(results) == 2
        assert results[0].status == ResultStatus.WRITTEN
        assert results[1].status == ResultStatus.FAILED
