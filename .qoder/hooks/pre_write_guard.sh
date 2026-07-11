#!/usr/bin/env bash
# Qoder PreToolUse(Write|Edit|MultiEdit|NotebookEdit): 复用 Codex 兼容的写入前防护入口。
# 与 Codex pre_write_guard 保持一致。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/.codex/hooks/lib/common.sh"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit 1
export FEIPI_AGENT_CLIENT="qoder"
exec "$EXEC_ROOT/.codex/hooks/pre_write_guard.sh" "$@"
