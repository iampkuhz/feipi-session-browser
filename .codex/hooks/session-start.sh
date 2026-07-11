#!/usr/bin/env bash
# Codex 会话开始：记录激活和延迟绑定证据。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(repo_root)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit 1
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="codex"
exec python3 -m scripts.claude_hooks.main session-start
