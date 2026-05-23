#!/usr/bin/env bash
# 01. 严格模式：hook 入口只做分发，不承载业务逻辑。
set -uo pipefail

# 02. 读取事件名：由 settings.json 传入，例如 pre-bash / post-write / stop。
EVENT_NAME="${1:-unknown}"

# 03. 定位仓库根目录：优先使用 git，其次从当前脚本位置回退。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v git >/dev/null 2>&1; then
  REPO_ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null || true)"
else
  REPO_ROOT=""
fi
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

# 04. 设置 Python 环境：允许 namespace package 形式导入 scripts.claude_hooks。
cd "${REPO_ROOT}" || exit 0
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_LOG_DIR="${FEIPI_AGENT_LOG_DIR:-tmp/agent_log}"

# 05. 分发 Hook 事件：stdin 原样交给 Python runtime 解析。
python3 -m scripts.claude_hooks.main "${EVENT_NAME}"
STATUS=$?

# 06. Exit code 透传：Claude Code 使用非 0 识别阻塞；2 表示明确 policy block。
exit "${STATUS}"
