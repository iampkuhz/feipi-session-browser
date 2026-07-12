"""统一 Stop runtime：typed 七阶段管道及其证据、恢复与报告组件。

不负责平台 Hook wrapper 配置；由 Hook 或 Stop runtime 调用。"""

from .entry import main, read_stdin_once, run_stop
from .evidence import GitEvidenceError, collect_git_evidence
from .recovery import FileLock

__all__ = [
    'FileLock',
    'GitEvidenceError',
    'collect_git_evidence',
    'main',
    'read_stdin_once',
    'run_stop',
]
