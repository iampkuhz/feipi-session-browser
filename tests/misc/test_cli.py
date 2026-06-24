"""CLI 模块验证测试。

serve/stop/scan 已切换至 Java launcher，Python CLI 仅保留
configure_logging 和 main 提示函数。
"""

import pytest


class TestPythonCliRetired:
    """Python CLI 生产命令已退休验证。"""

    def test_main_has_no_serve_command(self):
        """CLI main 函数不包含 serve 子命令。"""
        import inspect
        from session_browser.cli import main
        source = inspect.getsource(main)
        assert 'cmd_serve' not in source, 'CLI main 不应包含 cmd_serve'

    def test_main_has_no_stop_command(self):
        """CLI main 函数不包含 stop 子命令。"""
        import inspect
        from session_browser.cli import main
        source = inspect.getsource(main)
        assert 'cmd_stop' not in source, 'CLI main 不应包含 cmd_stop'

    def test_main_has_no_create_server_import(self):
        """CLI 模块不导入 create_server。"""
        import inspect
        import session_browser.cli as cli
        source = inspect.getsource(cli)
        assert 'create_server' not in source, 'CLI 模块不应引用 create_server'

    def test_configure_logging_still_available(self):
        """configure_logging 仍然可用。"""
        from session_browser.cli import configure_logging
        assert callable(configure_logging)

    def test_main_exits_with_error(self):
        """main() 提示 Java launcher 接管并以非零退出。"""
        from session_browser.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
