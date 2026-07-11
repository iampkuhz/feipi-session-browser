#!/usr/bin/env bash
# Codex Stop hook 的轻量入口，调用共享 harness stop runner。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(repo_root)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"
STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
cat > "$STDIN_TMP" 2>/dev/null || true
EXEC_ROOT="$(hook_exec_root_from_payload "$ROOT" "$STDIN_TMP" "$FEIPI_AGENT_CLIENT")"
export FEIPI_HOOK_EXEC_ROOT="$EXEC_ROOT"
cd "$EXEC_ROOT" || exit 1
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec python3 "$EXEC_ROOT/scripts/harness/stop_entry.py" --agent codex < "$STDIN_TMP"
