#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit|NotebookEdit): 写入前拦截受保护路径。
# 与 Qoder pre_write_guard 保持一致。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit 1

STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
if ! cat > "$STDIN_TMP" 2>/dev/null; then
  exit 0
fi
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"
python3 -m scripts.claude_hooks.main pre-write < "$STDIN_TMP"
