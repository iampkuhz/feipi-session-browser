#!/usr/bin/env bash
# Stop: warn about local-only files and common generated artifacts.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN

FAIL=0

if git status --short -- .claude/settings.local.json .mcp.json .env data output .venv .pytest_cache 2>/dev/null | grep -q .; then
  hook_log "WARN" "local-only files or generated artifacts appear in git status"
  git status --short -- .claude/settings.local.json .mcp.json .env data output .venv .pytest_cache >&2 || true
  FAIL=1
fi

if [[ -f .agent/task-ledger.md ]] && ! grep -q '|.*ID.*任务.*状态' .agent/task-ledger.md 2>/dev/null; then
  hook_log "WARN" ".agent/task-ledger.md table header not found"
  FAIL=1
fi

[[ $FAIL -ne 0 ]] && exit $EXIT_WARN
exit $EXIT_OK
