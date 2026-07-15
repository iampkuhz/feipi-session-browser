"""负责导出停止阶段的 Git 证据；不负责变更生命周期编排；由共享钩子入口调用。"""

from .evidence import GitEvidenceError, collect_git_evidence

__all__ = [
    'GitEvidenceError',
    'collect_git_evidence',
]
