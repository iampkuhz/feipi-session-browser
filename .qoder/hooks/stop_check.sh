#!/usr/bin/env bash
set -euo pipefail
# 本 Stop 包装器只委托统一生产入口 scripts/harness/stop_entry.py 执行，不包含业务逻辑。
# 传递给 stop_entry 的 agent 参数为 --agent qoder，保持平台标识一致。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/scripts/harness/hook-common.sh"
run_stop_hook qoder "$ROOT"
