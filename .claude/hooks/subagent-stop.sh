#!/usr/bin/env bash
# SubagentStop: 子 agent 停止校验（委托 stop.sh）。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
exec "$SCRIPT_DIR/stop.sh"
