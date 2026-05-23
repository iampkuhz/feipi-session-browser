#!/usr/bin/env bash
# SubagentStop: 子 agent 停止校验（复用 Stop 脚本逻辑）。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/stop.sh"
