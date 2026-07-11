#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/.codex/hooks/lib/common.sh"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
export FEIPI_AGENT_CLIENT="qoder"
STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
cat > "$STDIN_TMP" 2>/dev/null || true
EXEC_ROOT="$(hook_exec_root_from_payload "$ROOT" "$STDIN_TMP" "$FEIPI_AGENT_CLIENT")"
export FEIPI_HOOK_EXEC_ROOT="$EXEC_ROOT"
cd "$EXEC_ROOT"
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 "$EXEC_ROOT/scripts/harness/stop_entry.py" --agent qoder "$@" < "$STDIN_TMP"
