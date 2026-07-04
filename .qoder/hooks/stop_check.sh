#!/usr/bin/env bash
# Qoder Stop：调用共享 harness stop gate 的轻量入口。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="qoder"

exec python3 "$ROOT/scripts/harness/agent_stop_check.py" --agent qoder
