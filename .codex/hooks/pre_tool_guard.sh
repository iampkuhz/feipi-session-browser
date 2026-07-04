#!/usr/bin/env bash
# PreToolUse(Bash): 执行前拦截危险命令。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(repo_root)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"
STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
cat > "$STDIN_TMP" 2>/dev/null || true

INPUT="${CLAUDE_TOOL_INPUT:-${CC_TOOL_INPUT:-${1:-}}}"
if [[ -z "$INPUT" && -s "$STDIN_TMP" ]]; then
  INPUT="$(python3 - "$STDIN_TMP" <<'PY'
import json
import sys

try:
    data = json.loads(open(sys.argv[1], encoding='utf-8').read())
except Exception:
    data = {}
tool_input = data.get('tool_input') or data.get('toolInput') or {}
if isinstance(tool_input, dict):
    print(tool_input.get('command') or '')
else:
    print('')
PY
)"
fi

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

python3 -m scripts.claude_hooks.main pre-bash < "$STDIN_TMP" >/dev/null

exit $EXIT_OK
