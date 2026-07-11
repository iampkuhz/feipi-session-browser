#!/usr/bin/env bash
# SessionStart: 创建 session 日志目录，并记录 session ID 供 Stop hook 使用。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit $EXIT_WARN
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="claude"

# 从 stdin 提取 sessionId
# Claude Code hook 传入的 JSON 包含 sessionId 字段
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

SESSION_ID="$(python3 -c "
import json
try:
    data = json.loads(open('$STDIN_TMP').read())
    print(data.get('session_id', data.get('sessionId', '')))
except:
    print('')
" 2>/dev/null)"


# 调用 Python hook 逻辑
python3 -m scripts.claude_hooks.main session-start < "$STDIN_TMP"
rm -f "$STDIN_TMP"
