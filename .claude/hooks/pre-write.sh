#!/usr/bin/env bash
# PreToolUse (Write/Edit/...): 写路径策略检查。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_LOG_DIR="${FEIPI_AGENT_LOG_DIR:-tmp/agent_log}"

python3 -m scripts.claude_hooks.main pre-write
