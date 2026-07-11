#!/usr/bin/env bash
# PostToolUse(Edit/Write): 对已编辑文件执行轻量语法检查。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(repo_root)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit $EXIT_WARN
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"
STDIN_TMP="$(mktemp)"
NORMALIZED_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP" "$NORMALIZED_TMP"' EXIT
cat > "$STDIN_TMP" 2>/dev/null || true

MODIFIED_FILE="${CLAUDE_FILE_PATH:-${CC_FILE_PATH:-${1:-}}}"
python3 - "$STDIN_TMP" "$NORMALIZED_TMP" "$MODIFIED_FILE" <<'PY' || true
import json
import os
import sys

stdin_path, out_path, fallback_path = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    raw = json.loads(open(stdin_path, encoding='utf-8').read())
    if not isinstance(raw, dict):
        raw = {}
except Exception:
    raw = {}

tool_input = raw.get('tool_input') or raw.get('toolInput') or {}
if not isinstance(tool_input, dict):
    tool_input = {}

candidate_paths = []
for key in ('file_path', 'path', 'notebook_path'):
    value = tool_input.get(key)
    if isinstance(value, str) and value:
        candidate_paths.append(value)

edits = tool_input.get('edits')
if isinstance(edits, list):
    for item in edits:
        if not isinstance(item, dict):
            continue
        for key in ('file_path', 'path', 'notebook_path'):
            value = item.get(key)
            if isinstance(value, str) and value:
                candidate_paths.append(value)

path = fallback_path or (candidate_paths[0] if candidate_paths else '')

payload = {
    'session_id': raw.get('session_id') or raw.get('sessionId') or '',
    'agent_id': raw.get('agent_id') or raw.get('agentId') or '',
    'agent_type': raw.get('agent_type') or raw.get('agentType') or '',
    'agent_client': raw.get('agent_client') or raw.get('agentClient') or os.environ.get('FEIPI_AGENT_CLIENT') or 'codex',
    'tool_name': raw.get('tool_name') or raw.get('toolName') or 'CodexPostToolUse',
    'tool_use_id': raw.get('tool_use_id') or raw.get('toolUseId') or '',
    'tool_input': dict(tool_input),
}
if path and not any(payload['tool_input'].get(k) for k in ('file_path', 'path', 'notebook_path')):
    payload['tool_input']['file_path'] = path
if path or candidate_paths:
    open(out_path, 'w', encoding='utf-8').write(json.dumps(payload, ensure_ascii=False))
PY
if [[ -z "$MODIFIED_FILE" && -s "$NORMALIZED_TMP" ]]; then
  MODIFIED_FILE="$(python3 - "$NORMALIZED_TMP" <<'PY'
import json
import sys

try:
    data = json.loads(open(sys.argv[1], encoding='utf-8').read())
except Exception:
    data = {}
tool_input = data.get('tool_input') or {}
for key in ('file_path', 'path', 'notebook_path'):
    value = tool_input.get(key)
    if isinstance(value, str) and value:
        print(value)
        break
PY
)"
fi

if [[ -z "$MODIFIED_FILE" ]]; then
  exit $EXIT_SKIP
fi

if [[ -s "$NORMALIZED_TMP" ]]; then
  python3 -m scripts.claude_hooks.main post-write < "$NORMALIZED_TMP" >/dev/null 2>&1 || true
fi

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
