#!/usr/bin/env bash
# Codex PostToolUse(Bash): 记录 session 级 Bash 变更 evidence。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(repo_root)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit $EXIT_WARN
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"

STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
cat > "$STDIN_TMP" 2>/dev/null || true

python3 -m scripts.claude_hooks.main post-bash < "$STDIN_TMP" >/dev/null 2>&1 || true

exit $EXIT_OK
