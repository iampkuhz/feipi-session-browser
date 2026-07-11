#!/usr/bin/env bash
# PostToolUse (Bash): 记录 Bash 命令造成的文件变更 evidence。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit $EXIT_WARN
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="claude"

STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

python3 -m scripts.claude_hooks.main post-bash < "$STDIN_TMP"
rm -f "$STDIN_TMP"
