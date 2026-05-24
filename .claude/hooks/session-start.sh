#!/usr/bin/env bash
# SessionStart: 创建 session 日志目录，并记录 session ID 供 Stop hook 使用。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

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

# 固定路径：agent 日志目录
AGENT_LOG_DIR="$ROOT/tmp/agent_logs/current"

# 创建目录
mkdir -p "${AGENT_LOG_DIR}"

# 记录 session ID 到文件，供 stop.sh 等非 stdin hook 查询
if [[ -n "$SESSION_ID" ]]; then
  echo "$SESSION_ID" > "${AGENT_LOG_DIR}/session-id.txt"
fi

# 调用 Python hook 逻辑
python3 -m scripts.claude_hooks.main session-start < "$STDIN_TMP"
rm -f "$STDIN_TMP"
