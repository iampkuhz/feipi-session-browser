#!/usr/bin/env bash
# SessionStart: 初始化会话上下文，并记录 session ID 供 Stop hook 判断本 session 是否有文件修改。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_LOG_DIR="${FEIPI_AGENT_LOG_DIR:-tmp/agent_log}"

# 从 stdin 提取 sessionId 并保存到文件，供 stop.sh 查询。
# stdin 必须保留，因为后续 python3 -m scripts.claude_hooks.main 也需要读取。
# 方案：先拷贝到临时文件，然后两方都从中读取。
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

SESSION_ID="$(python3 -c "
import json, sys
try:
    data = json.loads(open('$STDIN_TMP').read())
    print(data.get('session_id', data.get('sessionId', '')))
except:
    print('')
" 2>/dev/null)"
if [[ -n "$SESSION_ID" ]]; then
  echo "$SESSION_ID" > "${FEIPI_AGENT_LOG_DIR}/session-id.txt"
fi

# 将 stdin 恢复给后续 Python 模块。
python3 -m scripts.claude_hooks.main session-start < "$STDIN_TMP"
rm -f "$STDIN_TMP"
