"""命令行入口：已退休至 Java launcher。

serve/stop/scan 命令已由 Java launcher 接管。
本模块仅保留 ``configure_logging`` 供测试和内部工具使用。
通过 ``python -m session_browser`` 调用时提示用户改用 Java launcher。
"""

from __future__ import annotations

import logging
import sys

from session_browser.config import (
    SESSION_BROWSER_LOG_LEVEL,
    SESSION_BROWSER_VERSION,
)

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


def main() -> None:
    """提示用户 serve/stop/scan 已由 Java launcher 接管。

    console 脚本和 ``python -m session_browser`` 调用此函数。
    所有生产命令（serve、stop、scan）已切换至 Java launcher。
    """
    print(
        'session-browser: serve/stop/scan 已由 Java launcher 接管。',
        file=sys.stderr,
    )
    print(
        '请使用：./scripts/session-browser.sh <serve|stop|scan> [options]',
        file=sys.stderr,
    )
    print(
        f'当前版本: {SESSION_BROWSER_VERSION}',
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == '__main__':
    main()
