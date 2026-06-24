"""Python scan 写路径退休验证。

本模块验证 Python scan 写路径已完全退休：
- scanners 模块不可导入
- init_schema/upsert_session 不从 indexer 导出
- CLI 没有 scan 子命令
- Python 不能创建/迁移/写 index
"""

from __future__ import annotations

import sqlite3

import pytest


class TestPythonScanWritePathRetired:
    """Python scan 写路径不可达验证。"""

    def test_scanners_module_not_importable(self):
        """scanners 模块已删除，不可导入。"""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            from session_browser.index import scanners  # noqa: F401

    def test_init_schema_not_in_indexer(self):
        """init_schema 不再从 indexer 导出。"""
        import session_browser.index.indexer as indexer
        assert not hasattr(indexer, 'init_schema'), (
            'init_schema 不应从 indexer 导出'
        )

    def test_upsert_session_not_in_indexer(self):
        """upsert_session 不再从 indexer 导出。"""
        import session_browser.index.indexer as indexer
        assert not hasattr(indexer, 'upsert_session'), (
            'upsert_session 不应从 indexer 导出'
        )

    def test_full_scan_not_in_indexer(self):
        """full_scan 不再从 indexer 导出。"""
        import session_browser.index.indexer as indexer
        assert not hasattr(indexer, 'full_scan'), (
            'full_scan 不应从 indexer 导出'
        )

    def test_incremental_scan_not_in_indexer(self):
        """incremental_scan 不再从 indexer 导出。"""
        import session_browser.index.indexer as indexer
        assert not hasattr(indexer, 'incremental_scan'), (
            'incremental_scan 不应从 indexer 导出'
        )

    def test_cli_has_no_scan_command(self):
        """CLI 没有 scan 子命令。"""
        import inspect
        from session_browser.cli import main
        # 验证 cli.py 的 main 不包含 scan 相关导入
        source = inspect.getsource(main)
        assert 'cmd_scan' not in source, 'CLI main 不应包含 cmd_scan'

    def test_cli_has_no_serve_command(self):
        """CLI 没有 serve 子命令（WEB-110 已切换至 Java）。"""
        import inspect
        from session_browser.cli import main
        source = inspect.getsource(main)
        assert 'cmd_serve' not in source, 'CLI main 不应包含 cmd_serve'

    def test_cli_has_no_stop_command(self):
        """CLI 没有 stop 子命令（WEB-110 已切换至 Java）。"""
        import inspect
        from session_browser.cli import main
        source = inspect.getsource(main)
        assert 'cmd_stop' not in source, 'CLI main 不应包含 cmd_stop'

    def test_background_scanner_not_in_cli(self):
        """CLI 模块不包含 _BackgroundScanner 类。"""
        import session_browser.cli as cli
        assert not hasattr(cli, '_BackgroundScanner'), (
            '_BackgroundScanner 不应在 cli 模块中'
        )

    def test_python_cannot_create_index_schema(self):
        """Python 无法通过 indexer API 创建 index schema。"""
        import session_browser.index.indexer as indexer
        # 确认没有 schema 创建函数
        assert not hasattr(indexer, 'init_schema')
        assert not hasattr(indexer, '_ensure_schema_exists')

    def test_query_api_still_works(self):
        """只读查询 API 仍然可用。"""
        from session_browser.index.indexer import (
            _get_connection,
            _row_to_summary,
            count_sessions,
            get_session,
            list_sessions,
        )
        # 所有查询函数应该可导入
        assert callable(_get_connection)
        assert callable(_row_to_summary)
        assert callable(count_sessions)
        assert callable(get_session)
        assert callable(list_sessions)
