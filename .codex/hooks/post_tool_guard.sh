#!/usr/bin/env bash
# PostToolUse(Edit/Write): lightweight syntax checks for edited files.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

MODIFIED_FILE="${CLAUDE_FILE_PATH:-${CC_FILE_PATH:-${1:-}}}"
[[ -z "$MODIFIED_FILE" ]] && exit $EXIT_SKIP

case "$MODIFIED_FILE" in
  */.claude/settings.local.json|*/.mcp.json)
    hook_log "WARN" "personal local config was modified: $MODIFIED_FILE"
    [[ "$HOOK_DRY_RUN" == "1" ]] && exit $EXIT_WARN
    exit $EXIT_BLOCK
    ;;
  *.sh)
    if [[ -f "$MODIFIED_FILE" ]]; then
      bash -n "$MODIFIED_FILE" || {
        hook_log "WARN" "shell syntax check failed: $MODIFIED_FILE"
        [[ "$HOOK_DRY_RUN" == "1" ]] && exit $EXIT_WARN
        exit $EXIT_BLOCK
      }
    fi
    ;;
  *.json)
    if [[ -f "$MODIFIED_FILE" ]]; then
      python3 -m json.tool "$MODIFIED_FILE" >/dev/null || {
        hook_log "WARN" "json syntax check failed: $MODIFIED_FILE"
        [[ "$HOOK_DRY_RUN" == "1" ]] && exit $EXIT_WARN
        exit $EXIT_BLOCK
      }
    fi
    ;;
esac

exit $EXIT_OK
