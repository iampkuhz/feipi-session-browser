#!/usr/bin/env bash
# Qoder PostToolUse(Bash)：复用 Codex 兼容的 Bash evidence 入口。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
export FEIPI_AGENT_CLIENT="qoder"
exec "$ROOT/.codex/hooks/post_bash_guard.sh" "$@"
