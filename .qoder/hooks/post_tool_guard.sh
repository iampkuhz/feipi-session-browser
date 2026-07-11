#!/usr/bin/env bash
# Qoder PostToolUse(Edit/Write)：复用共享 changed-file evidence 入口。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/.codex/hooks/lib/common.sh"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit 1
export FEIPI_AGENT_CLIENT="qoder"
exec "$EXEC_ROOT/.codex/hooks/post_tool_guard.sh" "$@"
