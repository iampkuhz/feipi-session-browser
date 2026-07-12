#!/usr/bin/env bash
set -euo pipefail
# claude subagent-start Hook 调用此包装器；它只将标准输入委托给共享 runtime，不实现事件策略。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/scripts/harness/hook-common.sh"
run_python_hook claude subagent-start "$ROOT"
