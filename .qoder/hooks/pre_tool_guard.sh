#!/usr/bin/env bash
# Qoder PreToolUse(Bash): thin wrapper around Codex-compatible command guards.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
exec "$ROOT/.codex/hooks/pre_tool_guard.sh" "$@"
