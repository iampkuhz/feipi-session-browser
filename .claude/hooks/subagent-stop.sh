#!/usr/bin/env bash
# SubagentStop: 子 agent 停止校验（委托 stop.sh）。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/stop.sh"
