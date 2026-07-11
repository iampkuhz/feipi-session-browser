#!/usr/bin/env bash
# Claude Code Stop hook 的轻量入口，调用共享 harness stop gate。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
export FEIPI_AGENT_CLIENT="claude"
STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
cat > "$STDIN_TMP" 2>/dev/null || true
EXEC_ROOT="$(hook_exec_root_from_payload "$ROOT" "$STDIN_TMP" "$FEIPI_AGENT_CLIENT")"
export FEIPI_HOOK_EXEC_ROOT="$EXEC_ROOT"
cd "$EXEC_ROOT" || exit 1
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

python3 "$EXEC_ROOT/scripts/harness/agent_stop_check.py" --agent claude < "$STDIN_TMP" || exit $?
