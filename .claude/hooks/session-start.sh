#!/usr/bin/env bash
# SessionStart: 创建本 session 的独立日志目录，并记录 session ID 供 Stop hook 使用。
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

# 构建 per-session 日志目录：tmp/agent_logs/MMDD_<session_id>/
# 多个 agent 实例同时运行时，各自写入独立目录，互不干扰。
if [[ -n "$SESSION_ID" ]]; then
  # 从 sessionId 提取短 ID（UUID 的前 8 位），避免路径过长
  SHORT_SID="${SESSION_ID%%-*}"
  DATE_PART="$(date +%m%d)"
  FEIPI_AGENT_LOG_DIR="tmp/agent_logs/${DATE_PART}_${SHORT_SID}"
else
  # 无法获取 session ID 时，使用 adhoc 目录
  DATE_PART="$(date +%m%d)"
  FEIPI_AGENT_LOG_DIR="tmp/agent_logs/${DATE_PART}_adhoc"
fi

# 创建目录并导出环境变量，后续所有 hook 共享此路径
mkdir -p "${FEIPI_AGENT_LOG_DIR}"
export FEIPI_AGENT_LOG_DIR

# 记录 session ID 到文件，供 stop.sh 等非 stdin hook 查询
echo "$SESSION_ID" > "${FEIPI_AGENT_LOG_DIR}/session-id.txt"

# 调用 Python hook 逻辑
python3 -m scripts.claude_hooks.main session-start < "$STDIN_TMP"
rm -f "$STDIN_TMP"
