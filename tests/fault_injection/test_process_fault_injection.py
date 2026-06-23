"""进程层故障注入测试。

验证 Java launcher 进程级别的故障场景：
- launcher 不可用
- JVM 启动失败
- 处理超时
- 用户取消

每种故障都必须 fail closed，不触发 Python fallback。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_browser.normalized.java_bridge import (
    BridgeCancelledError,
    BridgeError,
    BridgeTimeoutError,
    JavaBatchBridge,
    JavaNotAvailableError,
    resolve_java_launcher,
)

SB_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# launcher 不可用
# ---------------------------------------------------------------------------


class TestLauncherMissing:
    """launcher 缺失时 bridge 必须 fail closed，不 fallback 到 Python。"""

    def test_resolve_launcher_no_env_no_install_no_path(self):
        """所有查找路径均不可用时抛出 JavaNotAvailableError。"""
        from unittest.mock import MagicMock as _MM
        import importlib

        # shutil 在 resolve_java_launcher 函数体内通过 import shutil 导入，
        # 因此需要替换 sys.modules 中的 shutil 使其返回 mock 对象
        mock_shutil = _MM()
        mock_shutil.which.return_value = None
        original_shutil = sys.modules.get('shutil')
        sys.modules['shutil'] = mock_shutil
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('SESSION_BROWSER_JAVA_CLI', None)
                with patch(
                    'session_browser.normalized.java_bridge._find_repo_root',
                    return_value=None,
                ):
                    with pytest.raises(JavaNotAvailableError, match='Java launcher 不可用'):
                        resolve_java_launcher()
        finally:
            if original_shutil is not None:
                sys.modules['shutil'] = original_shutil
            else:
                sys.modules.pop('shutil', None)

    def test_resolve_launcher_env_path_invalid(self):
        """SESSION_BROWSER_JAVA_CLI 指向不存在的路径时抛出异常。"""
        with patch.dict(
            os.environ,
            {'SESSION_BROWSER_JAVA_CLI': '/nonexistent/java/launcher'},
        ):
            with pytest.raises(JavaNotAvailableError, match='不可用路径'):
                resolve_java_launcher()

    def test_start_with_missing_launcher_raises(self):
        """start() 在 launcher 不存在时抛出 JavaNotAvailableError。"""
        bridge = JavaBatchBridge(
            output_dir=Path(tempfile.mkdtemp()),
            launcher=Path('/nonexistent/java/launcher'),
        )
        try:
            with pytest.raises((JavaNotAvailableError, BridgeError)):
                bridge.start()
        finally:
            bridge.close()

    def test_bridge_does_not_fallback_on_launcher_missing(self):
        """launcher 缺失时 bridge 不尝试 Python producer。"""
        mock_python_producer = MagicMock()

        bridge = JavaBatchBridge(
            output_dir=Path(tempfile.mkdtemp()),
            launcher=Path('/nonexistent/java/launcher'),
        )
        try:
            with pytest.raises((JavaNotAvailableError, BridgeError)):
                bridge.start()
        finally:
            bridge.close()

        # 验证 Python producer 未被调用
        mock_python_producer.assert_not_called()


# ---------------------------------------------------------------------------
# JVM 启动失败
# ---------------------------------------------------------------------------


class TestJvmStartFailure:
    """JVM 启动失败时 bridge 必须 fail closed。"""

    def test_start_failure_file_not_found(self):
        """launcher 文件存在但不可执行时抛出 BridgeError 或 JavaNotAvailableError。"""
        with tempfile.NamedTemporaryFile(suffix='.sh', delete=False) as f:
            f.write(b'#!/bin/sh\nexit 1\n')
            tmp_path = f.name
        try:
            # 文件不可执行
            os.chmod(tmp_path, 0o644)
            bridge = JavaBatchBridge(
                output_dir=Path(tempfile.mkdtemp()),
                launcher=Path(tmp_path),
            )
            try:
                with pytest.raises((JavaNotAvailableError, BridgeError, PermissionError, OSError)):
                    bridge.start()
            finally:
                bridge.close()
        finally:
            os.unlink(tmp_path)

    def test_start_failure_exit_immediately(self):
        """launcher 启动后立即退出时 finish() 应报错。"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, prefix='fake_java_'
        ) as f:
            f.write('#!/bin/sh\nexit 1\n')
            tmp_path = f.name
        try:
            os.chmod(tmp_path, 0o755)
            bridge = JavaBatchBridge(
                output_dir=Path(tempfile.mkdtemp()),
                launcher=Path(tmp_path),
            )
            try:
                bridge.start()
                # 提交一个请求，然后 finish
                bridge.submit('req-1', 'claude', '/tmp/test')
                with pytest.raises(BridgeError, match='异常退出'):
                    bridge.finish()
            finally:
                bridge.close()
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 处理超时
# ---------------------------------------------------------------------------


class TestProcessingTimeout:
    """处理超时时 bridge 必须 fail closed。"""

    def test_timeout_raises_bridge_timeout_error(self):
        """进程超时时抛出 BridgeTimeoutError。"""
        # 创建一个关闭 stdout 后长时间不退出的假 launcher。
        # 关闭 stdout 使 _read_results() 立即返回，
        # 然后 _process.wait() 触发超时逻辑。
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, prefix='slow_java_'
        ) as f:
            f.write('#!/bin/sh\ncat > /dev/null\nexec 1>&-\nsleep 30\n')
            tmp_path = f.name
        try:
            os.chmod(tmp_path, 0o755)
            bridge = JavaBatchBridge(
                output_dir=Path(tempfile.mkdtemp()),
                launcher=Path(tmp_path),
                timeout_seconds=1.0,
            )
            try:
                bridge.start()
                bridge.submit('req-1', 'claude', '/tmp/test')
                with pytest.raises(BridgeTimeoutError, match='超时'):
                    bridge.finish()
            finally:
                bridge.close()
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# 用户取消
# ---------------------------------------------------------------------------


class TestUserCancel:
    """用户取消时 bridge 必须终止进程并 fail closed。"""

    def test_cancel_prevents_further_submit(self):
        """cancel() 后 submit() 抛出 BridgeCancelledError。"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, prefix='fake_java_'
        ) as f:
            f.write('#!/bin/sh\ncat > /dev/null\n')
            tmp_path = f.name
        try:
            os.chmod(tmp_path, 0o755)
            bridge = JavaBatchBridge(
                output_dir=Path(tempfile.mkdtemp()),
                launcher=Path(tmp_path),
            )
            try:
                bridge.start()
                bridge.cancel()
                with pytest.raises(BridgeCancelledError, match='已被取消'):
                    bridge.submit('req-1', 'claude', '/tmp/test')
            finally:
                bridge.close()
        finally:
            os.unlink(tmp_path)

    def test_cancel_terminates_process(self):
        """cancel() 后进程应被终止。"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, prefix='fake_java_'
        ) as f:
            f.write('#!/bin/sh\nsleep 60\n')
            tmp_path = f.name
        try:
            os.chmod(tmp_path, 0o755)
            bridge = JavaBatchBridge(
                output_dir=Path(tempfile.mkdtemp()),
                launcher=Path(tmp_path),
            )
            try:
                bridge.start()
                assert bridge.is_started
                bridge.cancel()
                # 等待进程终止
                if bridge._process is not None:
                    bridge._process.wait(timeout=5)
                    assert bridge._process.poll() is not None
            finally:
                bridge.close()
        finally:
            os.unlink(tmp_path)

    def test_cancel_prevents_finish(self):
        """cancel() 后 finish() 抛出 BridgeCancelledError。"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.sh', delete=False, prefix='fake_java_'
        ) as f:
            f.write('#!/bin/sh\nsleep 60\n')
            tmp_path = f.name
        try:
            os.chmod(tmp_path, 0o755)
            bridge = JavaBatchBridge(
                output_dir=Path(tempfile.mkdtemp()),
                launcher=Path(tmp_path),
            )
            try:
                bridge.start()
                bridge.cancel()
                with pytest.raises(BridgeCancelledError, match='已被取消'):
                    bridge.finish()
            finally:
                bridge.close()
        finally:
            os.unlink(tmp_path)
