"""负责定义 Session registry 与 writer lease 的公共失败类型；不负责捕获或降级错误；由 Runtime 服务和 CLI adapter 调用。"""

from scripts.agent_runtime.storage import StorageError as SessionctlError


class WriterLeaseConflictError(SessionctlError):
    """表示同一 checkout 已有其他活动 writer，当前运行只能保持只读。"""

    pass


class WriterLeaseFencedError(SessionctlError):
    """表示缓存 epoch 或 fencing token 已失效，当前运行不得继续修改或释放 lease。"""

    pass
