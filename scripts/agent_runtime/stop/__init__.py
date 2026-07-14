"""负责旧 Stop package 的证据导出；不负责加载 controller，由兼容入口调用。"""

from .evidence import GitEvidenceError, collect_git_evidence

__all__ = [
    'GitEvidenceError',
    'collect_git_evidence',
]
