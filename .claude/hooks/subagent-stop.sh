#!/usr/bin/env bash
set -euo pipefail
# claude subagent-stop Hook 调用此包装器；它只将标准输入委托给共享 runtime，不实现事件策略。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
exec "$SCRIPT_DIR/stop.sh"
