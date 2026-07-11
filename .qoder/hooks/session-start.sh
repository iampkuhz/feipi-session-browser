#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT/.codex/hooks/lib/common.sh"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT"
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="qoder"

STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
cat > "$STDIN_TMP"

SESSION_ID="$(python3 - "$STDIN_TMP" <<'PY'
import json, sys
try:
    data = json.loads(open(sys.argv[1], encoding='utf-8').read() or '{}')
except Exception:
    data = {}
print(data.get('session_id') or data.get('sessionId') or '')
PY
)"

if [[ -n "${FEIPI_RUN_ID:-}" && -n "$SESSION_ID" ]]; then
  python3 "$EXEC_ROOT/scripts/harness/sessionctl.py" bind-session \
    --run-id "$FEIPI_RUN_ID" \
    --session-id "$SESSION_ID" \
    --client qoder \
    --cwd "$EXEC_ROOT" >/dev/null
else
  python3 - "$EXEC_ROOT" "$SESSION_ID" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
session = sys.argv[2] or 'unknown'
path = root / 'tmp' / 'agent_logs' / 'qoder' / session / 'read-only-unbound.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({
    'schemaVersion': 1,
    'client': 'qoder',
    'sessionId': session,
    'status': 'read-only-unbound',
    'reason': 'FEIPI_RUN_ID or session_id missing; Qoder is not writable-ready without launcher binding'
}, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
PY
fi

exec python3 -m scripts.claude_hooks.main session-start "$@" < "$STDIN_TMP"
