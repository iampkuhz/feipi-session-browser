#!/usr/bin/env bash
# Claude Code Stop hook 的轻量入口，调用共享 harness stop gate。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="claude"

python3 "$ROOT/scripts/harness/agent_stop_check.py" --agent claude || exit $?
python3 "$ROOT/scripts/quality/check_agent_runtime_report.py" || exit $?
