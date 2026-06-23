"""命令行入口：服务和本地会话索引管理。

Usage:
    python -m session_browser serve       # 启动 Web 服务
    python -m session_browser serve --port 18999
    python -m session_browser stop        # 停止 Web 服务

Scan 命令已退休，由 Java launcher 接管。
本模块保留 serve/stop 子命令，连接 SQLite 索引提供只读查询。
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from typing import TYPE_CHECKING, TextIO

from session_browser.config import (
    SERVER_HOST,
    SERVER_PORT,
    SESSION_BROWSER_LOG_LEVEL,
    SESSION_BROWSER_VERSION,
)
from session_browser.web.routes import create_server

logger = logging.getLogger('session_browser')


def configure_logging(level: str | None = None) -> None:
    """配置进程级日志。

    Args:
        level: 可选的日志级别名称。省略时使用 ``SESSION_BROWSER_LOG_LEVEL``
            或 ``INFO``。

    Side Effects:
        重新配置根日志记录器，捕获警告到日志，并降低嘈杂的第三方日志。
    """
    raw_level = (level or SESSION_BROWSER_LOG_LEVEL or 'INFO').upper()
    log_level = getattr(logging, raw_level, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True,
    )
    logging.captureWarnings(True)
    for noisy_logger in ('markdown_it', 'PIL'):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    logger.debug('日志已配置，级别: %s', logging.getLevelName(log_level))


def _run_command(
    cmd: list[str],
    *,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """运行短时辅助命令并在超时时清理进程组。

    Args:
        cmd: 可执行文件和参数。
        timeout: 最大等待秒数。

    Returns:
        已完成的进程，包含捕获的文本 stdout 和 stderr。

    Raises:
        subprocess.TimeoutExpired: 在 SIGTERM/SIGKILL 清理后抛出。
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.communicate(timeout=3)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        raise subprocess.TimeoutExpired(
            cmd,
            timeout,
            output=exc.output,
            stderr=exc.stderr,
        ) from exc

    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _is_orphan(pid: int) -> bool:
    """判断进程是否看起来已孤立（父 PID 为 1）。

    Args:
        pid: 在请求的服务端口上发现的进程 ID。

    Returns:
        ``ps`` 报告 PPID 为 1 时返回 ``True``。
    """
    try:
        result = subprocess.run(
            ['ps', '-o', 'ppid=', '-p', str(pid)],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            ppid = int(result.stdout.strip())
            return ppid == 1
    except (ValueError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return False


def _find_pids_on_port(port: int) -> list[int]:
    """查找监听指定 TCP 端口的进程。

    Args:
        port: ``serve`` 或 ``stop`` 请求的本地端口。

    Returns:
        ``lsof`` 报告的整数 PID 列表。
    """
    pids = []
    try:
        result = _run_command(['lsof', '-ti', f':{port}'], timeout=5)
        for raw_line in result.stdout.strip().splitlines():
            line = raw_line.strip()
            if line:
                with suppress(ValueError):
                    pids.append(int(line))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return pids


def _kill_process(pid: int) -> bool:
    """以优雅和强制信号终止进程。

    Args:
        pid: 要终止的进程 ID。

    Returns:
        最终检查时进程已消失返回 ``True``。

    Side Effects:
        发送 SIGTERM，等待最多五秒，然后尝试 SIGKILL。
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError:
        pass

    for _ in range(5):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(1)

    try:
        os.kill(pid, signal.SIGKILL)
        time.sleep(1)
    except (ProcessLookupError, PermissionError):
        pass

    try:
        os.kill(pid, 0)
        return False
    except ProcessLookupError:
        return True


def cmd_serve(args: argparse.Namespace) -> None:
    """启动本地 Web 服务。

    Python scan 已退休；服务仅以只读方式连接 Java 创建的 SQLite 索引。

    Args:
        args: 解析的 ``serve`` 命名空间。``--host`` 和 ``--port`` 选择绑定目标，
            ``--allow-empty`` 允许空索引启动，``--force`` 强制终止冲突。

    Side Effects:
        可能终止孤立或冲突的端口占用进程，日志记录配置路径，
        并阻塞在 HTTP 服务中直到被中断。
    """
    port = args.port or SERVER_PORT
    host = args.host or SERVER_HOST
    force = getattr(args, 'force', False)

    existing_pids = _find_pids_on_port(port)
    if existing_pids:
        pid_list = ', '.join(str(p) for p in existing_pids)
        orphans = [p for p in existing_pids if _is_orphan(p)]
        if orphans:
            orphan_list = ', '.join(str(p) for p in orphans)
            logger.warning(
                '端口 %s 上的孤立进程: pids=%s (PPID=1, 可能是 fixture 服务)',
                port,
                orphan_list,
            )
            for pid in orphans:
                if _kill_process(pid):
                    logger.warning('已终止孤立进程 pid=%s', pid)
                else:
                    logger.error('终止孤立进程失败 pid=%s', pid)
            time.sleep(1)
            existing_pids = [p for p in existing_pids if p not in orphans]

        if existing_pids:
            pid_list = ', '.join(str(p) for p in existing_pids)
            logger.warning(
                '已有进程在监听: host=%s port=%s pids=%s',
                host,
                port,
                pid_list,
            )
            if force:
                logger.warning('--force: 自动终止现有服务')
            else:
                try:
                    answer = input('Kill it and restart? [y/N]: ').strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = 'n'
            if force or answer in ('y', 'yes'):
                for pid in existing_pids:
                    if _kill_process(pid):
                        logger.warning('已终止服务进程 pid=%s', pid)
                    else:
                        logger.error('终止服务进程失败 pid=%s', pid)
                time.sleep(1)
            else:
                print('Aborted.')
                sys.exit(0)

    from session_browser.config import (  # noqa: PLC0415
        CLAUDE_DATA_DIR,
        CODEX_DATA_DIR,
        INDEX_DIR,
        QODER_DATA_DIR,
    )

    logger.info(
        '数据路径: index=%s claude=%s codex=%s qoder=%s',
        INDEX_DIR,
        CLAUDE_DATA_DIR,
        CODEX_DATA_DIR,
        QODER_DATA_DIR,
    )

    server = create_server(host=host, port=port)
    logger.info(
        '启动 session-browser: url=http://%s:%s version=%s log_level=%s',
        host,
        port,
        SESSION_BROWSER_VERSION,
        logging.getLevelName(logging.getLogger().getEffectiveLevel()),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info('收到 KeyboardInterrupt，正在关闭')
        server.shutdown()
    except Exception:
        logger.exception('服务致命错误')
        raise


def cmd_stop(args: argparse.Namespace) -> None:
    """停止监听指定端口的运行中服务进程。

    Args:
        args: 包含要检查端口的 ``stop`` 命名空间。

    Side Effects:
        调用 ``lsof`` 发现监听者，向每个 PID 发送 SIGTERM，
        打印状态消息，``lsof`` 缺失或超时时以 ``1`` 退出。
    """
    port = args.port or SERVER_PORT

    try:
        result = _run_command(
            ['lsof', '-ti', f':{port}'],
            timeout=5,
        )
    except FileNotFoundError:
        print("Error: 'lsof' not found. Stop the server manually.")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(f'Error: 在端口 {port} 上搜索进程超时。')
        sys.exit(1)

    pids = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    if not pids:
        print(f'端口 {port} 上未找到进程。服务可能未运行。')
        return

    for pid in pids:
        try:
            print(f'正在停止进程 {pid}（端口 {port}）...')
            os.kill(int(pid), signal.SIGTERM)
            print(f'进程 {pid} 已停止。')
        except ProcessLookupError:
            print(f'进程 {pid} 已退出。')
        except PermissionError:
            print(f'进程 {pid} 权限被拒绝。尝试: kill {pid}')


def main() -> None:
    """解析 CLI 参数并分派到所选子命令。

    console 脚本和 ``python -m session_browser`` 调用此函数。
    scan 子命令已退休，由 Java launcher 接管。
    """
    parser = argparse.ArgumentParser(
        prog='session-browser',
        description='本地 agent 会话浏览器和分析器',
    )
    parser.add_argument(
        '--version', action='version', version=f'%(prog)s {SESSION_BROWSER_VERSION}'
    )
    sub = parser.add_subparsers(dest='command')

    serve_p = sub.add_parser('serve', help='启动本地 Web 服务')
    serve_p.add_argument(
        '--host', default=SERVER_HOST, help=f'绑定地址（默认: {SERVER_HOST}）'
    )
    serve_p.add_argument(
        '--port', type=int, default=SERVER_PORT, help=f'端口（默认: {SERVER_PORT}）'
    )
    serve_p.add_argument(
        '--allow-empty', action='store_true', help='允许空索引启动'
    )
    serve_p.add_argument(
        '--no-scan', action='store_true', help='已废弃；保留以兼容'
    )
    serve_p.add_argument(
        '--startup-scan',
        action='store_true',
        help='已废弃；保留以兼容',
    )
    serve_p.add_argument(
        '--force', '-f', action='store_true', help='不提示直接终止端口上的现有服务'
    )
    serve_p.add_argument(
        '--log-level',
        default=SESSION_BROWSER_LOG_LEVEL,
        help=f'日志级别（默认: {SESSION_BROWSER_LOG_LEVEL}）',
    )

    stop_p = sub.add_parser('stop', help='停止运行中的 Web 服务')
    stop_p.add_argument(
        '--port', type=int, default=SERVER_PORT, help=f'要停止的端口（默认: {SERVER_PORT}）'
    )

    args = parser.parse_args()
    configure_logging(getattr(args, 'log_level', None))

    if args.command == 'serve':
        cmd_serve(args)
    elif args.command == 'stop':
        cmd_stop(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
