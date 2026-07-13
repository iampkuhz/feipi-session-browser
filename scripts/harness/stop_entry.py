#!/usr/bin/env python3
"""跨平台 Stop 公开薄入口。

本文件只负责把 harness 导入路径和 CLI 委托给
``scripts.agent_runtime.stop.entry``；不得承载 Stop 业务、Gate 选择或报告逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证直接执行脚本时可解析仓库内唯一 runtime package。
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 仅导出 CLI/dispatcher 稳定入口，不转发内部 evidence/recovery/report API。
from scripts.agent_runtime.stop.entry import main, read_stdin_once  # noqa: E402
from scripts.agent_runtime.stop.pipeline import run_stop  # noqa: E402

# 明确公开面仅包含委托入口，防止业务重新回流到 harness。
# 业务测试应直接导入 scripts.agent_runtime.stop 对应责任模块。
# 共享 dispatcher 只需继续执行 main。
__all__ = ['main', 'read_stdin_once', 'run_stop']


# 平台 Hook 通过本文件启动；所有参数和 payload 解析仍由 entry 模块完成。
if __name__ == '__main__':
    raise SystemExit(main())
