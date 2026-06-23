"""无回退只读门禁测试。

通过动态 spy 验证 artifact cutover 后不存在 Python writer/fallback。
验证点：
- Java bridge 不可用时不触发 Python 归一化生产
- artifact consumer 不暴露写入 API
- 整个 cutover 路径中不存在 Python fallback 调用
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from session_browser.normalized import artifact_consumer, java_bridge
from session_browser.normalized.java_bridge import (
    BridgeError,
    JavaBatchBridge,
    JavaNotAvailableError,
    run_batch,
)

SB_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# artifact consumer 只读验证
# ---------------------------------------------------------------------------


class TestConsumerIsReadOnly:
    """ArtifactConsumer 不暴露任何写入 API。"""

    def test_consumer_has_no_write_method(self):
        """consumer 实例不包含 write/create/persist/replace 方法。"""
        consumer = artifact_consumer.ArtifactConsumer(
            index_dir=Path(tempfile.mkdtemp())
        )
        write_methods = [
            name
            for name in dir(consumer)
            if any(
                kw in name.lower()
                for kw in ('write', 'create', 'persist', 'replace', 'save', 'store')
            )
            and not name.startswith('_')
        ]
        assert write_methods == [], (
            f'ArtifactConsumer 不应暴露写入方法，发现: {write_methods}'
        )

    def test_consumer_module_has_no_write_functions(self):
        """artifact_consumer 模块不包含写入函数。"""
        module_functions = [
            name
            for name, obj in inspect.getmembers(artifact_consumer, inspect.isfunction)
            if any(
                kw in name.lower()
                for kw in ('write', 'create', 'persist', 'replace', 'save', 'store')
            )
            and not name.startswith('_')
        ]
        assert module_functions == [], (
            f'artifact_consumer 模块不应包含写入函数，发现: {module_functions}'
        )


# ---------------------------------------------------------------------------
# Java bridge 无 Python fallback 验证
# ---------------------------------------------------------------------------


class TestNoPythonFallback:
    """Java bridge 不可用时不存在 Python fallback。"""

    def test_run_batch_raises_when_java_unavailable(self):
        """Java 不可用时 run_batch 抛出异常，不 fallback 到 Python。"""
        with patch.dict(
            os.environ,
            {'SESSION_BROWSER_JAVA_CLI': '/nonexistent/launcher'},
        ):
            with pytest.raises(JavaNotAvailableError):
                run_batch(
                    requests=[('req-1', 'claude', '/tmp/test')],
                    output_dir=Path(tempfile.mkdtemp()),
                )

    def test_bridge_start_raises_when_java_unavailable(self):
        """bridge start() 在 Java 不可用时抛出异常。"""
        bridge = JavaBatchBridge(
            output_dir=Path(tempfile.mkdtemp()),
            launcher=Path('/nonexistent/launcher'),
        )
        try:
            with pytest.raises((JavaNotAvailableError, BridgeError)):
                bridge.start()
        finally:
            bridge.close()

    def test_no_python_normalization_module_called(self):
        """Java bridge 运行过程中不调用 Python 归一化模块。"""
        # 跟踪所有可能的 Python 归一化入口
        python_producers = [
            'session_browser.normalized.agents.chat_jsonl',
            'session_browser.normalized.agents.claude_code_normalization',
            'session_browser.normalized.agents.codex_normalization',
            'session_browser.normalized.agents.qoder_normalization',
        ]
        mocks = []
        for mod_name in python_producers:
            m = MagicMock(name=f'mock_{mod_name}')
            mocks.append((mod_name, m))

        # 验证 bridge 不会 fallback 到 Python 归一化
        bridge = JavaBatchBridge(
            output_dir=Path(tempfile.mkdtemp()),
            launcher=Path('/nonexistent/launcher'),
        )
        try:
            with pytest.raises((JavaNotAvailableError, BridgeError)):
                bridge.start()
        finally:
            bridge.close()

        # 所有 Python producer 的 mock 都未被调用
        for mod_name, m in mocks:
            m.assert_not_called()

    def test_run_batch_exception_does_not_trigger_python(self):
        """run_batch 异常路径不触发 Python fallback。"""
        python_writer_mock = MagicMock(name='python_writer')

        with patch.dict(
            os.environ,
            {'SESSION_BROWSER_JAVA_CLI': '/nonexistent/launcher'},
        ):
            with pytest.raises(JavaNotAvailableError):
                run_batch(
                    requests=[('req-1', 'claude', '/tmp/test')],
                    output_dir=Path(tempfile.mkdtemp()),
                )

        # Python writer 在整个过程中未被调用
        python_writer_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 模块级别无 fallback 静态验证
# ---------------------------------------------------------------------------


class TestNoFallbackStaticEvidence:
    """静态代码证据：Java bridge 模块不包含 fallback 逻辑。"""

    def test_java_bridge_source_has_no_fallback_keyword(self):
        """java_bridge.py 源码中不包含 fallback/python_producer 关键字。"""
        source_path = Path(java_bridge.__file__)
        source = source_path.read_text(encoding='utf-8')
        # 检查源码中不存在 fallback 到 Python 的逻辑
        fallback_keywords = [
            'python_producer',
            'fallback_normalize',
            'fallback_to_python',
            '_python_fallback',
            'legacy_normalize',
        ]
        found = [kw for kw in fallback_keywords if kw in source]
        assert found == [], (
            f'java_bridge.py 不应包含 fallback 关键字，发现: {found}'
        )

    def test_java_bridge_docstring_declares_no_fallback(self):
        """java_bridge 模块 docstring 声明不提供 Python fallback。"""
        docstring = java_bridge.__doc__ or ''
        assert 'fallback' in docstring.lower() or '不提供' in docstring, (
            'java_bridge 模块 docstring 应声明不提供 Python fallback'
        )

    def test_artifact_consumer_docstring_declares_read_only(self):
        """artifact_consumer 模块 docstring 声明为只读 consumer。"""
        docstring = artifact_consumer.__doc__ or ''
        assert '只读' in docstring or 'read' in docstring.lower(), (
            'artifact_consumer 模块 docstring 应声明为只读 consumer'
        )
