#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/.codex/hooks/lib/common.sh"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT"
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="qoder"
exec python3 -m scripts.claude_hooks.main post-bash "$@"
