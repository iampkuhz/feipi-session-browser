#!/usr/bin/env bash
# Stop: warn about local-only files and common generated artifacts.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN

WARN=0
BLOCK=0

if git status --short -- .claude/settings.local.json .mcp.json .env data output .venv .pytest_cache 2>/dev/null | grep -q .; then
  hook_log "WARN" "local-only files or generated artifacts appear in git status"
  git status --short -- .claude/settings.local.json .mcp.json .env data output .venv .pytest_cache >&2 || true
  WARN=1
fi

if [[ -f .agent/task-ledger.md ]] && ! grep -q '|.*ID.*任务.*状态' .agent/task-ledger.md 2>/dev/null; then
  hook_log "WARN" ".agent/task-ledger.md table header not found"
  WARN=1
fi

# Validate OpenSpec change completeness for protected edits.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT" || exit $EXIT_WARN

python3 "$ROOT/scripts/agent_hooks/stop_validate_change.py" >&2
HOOK_EXIT=$?
if [[ $HOOK_EXIT -ne 0 ]]; then
  hook_log "BLOCK" "stop_validate_change.py blocked stop (exit=$HOOK_EXIT)"
  BLOCK=1
fi

# Quality gate artifact enforcement for UI changes.
python3 "$ROOT/scripts/hooks/stop_quality_gate.py" >&2
QG_EXIT=$?
if [[ $QG_EXIT -ne 0 ]]; then
  hook_log "BLOCK" "stop_quality_gate.py blocked stop (exit=$QG_EXIT)"
  BLOCK=1
fi

[[ $BLOCK -ne 0 ]] && exit $EXIT_BLOCK
[[ $WARN -ne 0 ]] && exit $EXIT_WARN
exit $EXIT_OK
