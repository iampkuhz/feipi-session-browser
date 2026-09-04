"""负责导出 Gate Evidence 阶段公开入口；不负责渲染或执行。

由 CLI 在整次运行完成后调用。"""

from scripts.gates.evidence.receipt_store import RunReceipt, store_run_receipt

__all__ = ('RunReceipt', 'store_run_receipt')
