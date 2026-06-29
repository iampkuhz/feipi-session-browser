#!/usr/bin/env bash
# Qoder PostToolUse(Edit/Write): thin wrapper around shared changed-file evidence.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
exec "$ROOT/.codex/hooks/post_tool_guard.sh" "$@"
