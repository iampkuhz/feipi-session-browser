"""serve/stop 所有权守卫：验证 Python Web 生产路径不可达。

WEB-110 cutover 后，serve/stop 由 Java launcher 接管。
本模块验证 Python 侧不再具有 serve/stop 生产能力。
"""

from __future__ import annotations

import inspect


class TestPythonWebProductionUnreachable:
    """Python Web 生产路径不可达验证。"""

    def test_cli_does_not_import_create_server(self):
        """CLI 模块不导入 create_server。"""
        import session_browser.cli as cli
        source = inspect.getsource(cli)
        assert 'create_server' not in source, (
            'CLI 模块不应引用 create_server；serve 已由 Java launcher 接管'
        )

    def test_cli_has_no_cmd_serve(self):
        """CLI 模块不包含 cmd_serve 函数。"""
        import session_browser.cli as cli
        assert not hasattr(cli, 'cmd_serve'), (
            'cmd_serve 不应存在于 CLI 模块；serve 已由 Java launcher 接管'
        )

    def test_cli_has_no_cmd_stop(self):
        """CLI 模块不包含 cmd_stop 函数。"""
        import session_browser.cli as cli
        assert not hasattr(cli, 'cmd_stop'), (
            'cmd_stop 不应存在于 CLI 模块；stop 已由 Java launcher 接管'
        )

    def test_cli_has_no_process_killing_helpers(self):
        """CLI 模块不包含进程终止辅助函数（已随 serve/stop 移除）。"""
        import session_browser.cli as cli
        for func_name in ('_is_orphan', '_find_pids_on_port', '_kill_process'):
            assert not hasattr(cli, func_name), (
                f'{func_name} 不应存在于 CLI 模块；'
                '进程管理已由 Java launcher 接管'
            )

    def test_python_main_exits_with_error(self):
        """python -m session_browser 以非零退出码结束并提示 Java launcher。"""
        import sys
        from session_browser.cli import main
        try:
            main()
        except SystemExit as exc:
            assert exc.code == 1, 'main() 应以 exit code 1 退出'
        else:
            raise AssertionError('main() 应抛出 SystemExit')

    def test_create_server_marked_deprecated(self):
        """create_server 函数文档标记为 deprecated。"""
        from session_browser.web.routes import create_server
        docstring = create_server.__doc__ or ''
        assert 'deprecated' in docstring.lower() or 'WEB-110' in docstring, (
            'create_server 应标记为 deprecated（WEB-110）'
        )
