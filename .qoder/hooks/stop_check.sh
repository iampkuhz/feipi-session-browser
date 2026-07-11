#!/usr/bin/env bash
# Qoder Stop：调用共享 harness stop gate 的轻量入口。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/.codex/hooks/lib/common.sh"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit 1
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="qoder"

python3 "$EXEC_ROOT/scripts/harness/agent_stop_check.py" --agent qoder || exit $?
python3 "$EXEC_ROOT/scripts/quality/check_agent_runtime_report.py" || exit $?
