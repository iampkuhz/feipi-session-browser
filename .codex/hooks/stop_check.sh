#!/usr/bin/env bash
# Codex Stop hook 的轻量入口，调用共享 harness stop gate。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit 1
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"

python3 "$EXEC_ROOT/scripts/harness/agent_stop_check.py" --agent codex || exit $?
python3 "$EXEC_ROOT/scripts/quality/check_agent_runtime_report.py" || exit $?
