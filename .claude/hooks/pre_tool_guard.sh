#!/usr/bin/env bash
# PreToolUse(Bash): block destructive commands before they run.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

INPUT="${CLAUDE_TOOL_INPUT:-${CC_TOOL_INPUT:-${1:-}}}"

declare -a BLOCK_PATTERNS=(
  'rm[[:space:]]+-rf[[:space:]]+/'
  'git[[:space:]]+reset[[:space:]]+--hard'
  'git[[:space:]]+clean[[:space:]]+-fdx'
  'chmod[[:space:]]+-R[[:space:]]+777[[:space:]]+/'
  'dd[[:space:]]+if=.+of=/dev/'
)

for pattern in "${BLOCK_PATTERNS[@]}"; do
  if echo "$INPUT" | grep -qE "$pattern"; then
    hook_log "BLOCK" "blocked dangerous command pattern: $pattern"
    exit $EXIT_BLOCK
  fi
done

exit $EXIT_OK
