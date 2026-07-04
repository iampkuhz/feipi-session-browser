#!/usr/bin/env bash
# Qoder PreToolUse(Bash)：复用 Codex 兼容的命令防护入口。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
export FEIPI_AGENT_CLIENT="qoder"
exec "$ROOT/.codex/hooks/pre_tool_guard.sh" "$@"
