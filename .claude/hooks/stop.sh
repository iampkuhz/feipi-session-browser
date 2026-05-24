#!/usr/bin/env bash
# Stop: 区分只读会话与有写操作会话的质量门禁校验。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# 保存 stdin 供后续 Python 脚本读取（Claude hook 传入的 JSON 包含 sessionId）。
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

# 固定路径：agent 日志与 quality artifact
AGENT_LOG_DIR="$ROOT/tmp/agent_logs/current"
QUALITY_DIR="$ROOT/tmp/quality"
mkdir -p "$AGENT_LOG_DIR" "$QUALITY_DIR"

STOP_SUMMARY="${AGENT_LOG_DIR}/stop-check-summary.json"
WARN=0
BLOCK=0

# ---- 步骤 1：判断是否只读会话 ----
# 依据：changed-files.jsonl 中是否有当前 session 的 Write/Edit 记录。
# changed-files.jsonl 由 post-write hook 写入，每条记录带 sessionId。
# 这是最可靠的判断 —— 覆盖 Claude 所有写操作（Write/Edit/MultiEdit/NotebookEdit），
# 不受 git dirty state 干扰，也不受跨 session 历史数据影响。

write_session_script="${ROOT}/scripts/claude_hooks/policy/write_session_check.py"
if [[ -f "$write_session_script" ]]; then
  SESSION_CHECK="$(python3 "$write_session_script" < "$STDIN_TMP" 2>/dev/null || echo "unknown")"
else
  SESSION_CHECK="unknown"
fi

if [[ "$SESSION_CHECK" == "no_changes" ]]; then
  hook_log "INFO" "本次无文件修改（当前 session 无 Write/Edit 记录），跳过质量门禁校验"

  python3 -c "
import json
from pathlib import Path
from datetime import datetime, timezone
agent_log_dir = Path('${AGENT_LOG_DIR}')
summary_path = agent_log_dir / 'stop-check-summary.json'
d = {
    'schemaVersion': 1,
    'ts': datetime.now(timezone.utc).isoformat(),
    'readOnly': True,
    'status': 'PASS',
    'changeId': '',
    'requiredTargets': [],
    'blockingFailures': [],
    'warnings': [],
}
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
"
  rm -f "$STDIN_TMP"
  exit $EXIT_OK
fi

# ---- 步骤 2：有写操作会话 —— 完整质量门禁校验 ----
if [[ "$SESSION_CHECK" == "unknown" ]]; then
  hook_log "WARN" "无法获取 session ID，保守地假设有文件变更，执行完整质量门禁校验"
else
  hook_log "INFO" "检测到本 session 有文件修改，执行完整质量门禁校验"
fi

# 2a. OpenSpec 变更完整性
python3 "$ROOT/scripts/agent_hooks/stop_validate_change.py" >&2
HOOK_EXIT=$?
if [[ $HOOK_EXIT -ne 0 ]]; then
  hook_log "BLOCK" "stop_validate_change.py 校验失败 (exit=$HOOK_EXIT)"
  BLOCK=1
fi

# 2b. 自动运行 required quality gates（包含 session-detail）
python3 "$ROOT/scripts/quality/run_required_quality_gates.py" --include-session-detail >&2
RG_EXIT=$?
if [[ $RG_EXIT -ne 0 ]]; then
  hook_log "BLOCK" "run_required_quality_gates.py 运行失败 (exit=$RG_EXIT)"
  BLOCK=1
fi

# 2c. UI 质量门禁校验（session-detail artifact  freshness + PASS）
python3 "$ROOT/scripts/hooks/stop_quality_gate.py" >&2
QG_EXIT=$?
if [[ $QG_EXIT -ne 0 ]]; then
  hook_log "BLOCK" "stop_quality_gate.py 校验失败 (exit=$QG_EXIT)"
  BLOCK=1
fi

# 2d. 非 session-detail quality targets artifact 校验
python3 "$ROOT/scripts/quality/stop_check_targets.py" >&2
ST_EXIT=$?
if [[ $ST_EXIT -ne 0 ]]; then
  hook_log "BLOCK" "stop_check_targets.py 校验失败 (exit=$ST_EXIT)"
  BLOCK=1
fi

# 2e. task-ledger 检查
if [[ -f tmp/task-ledger.md ]] && ! grep -q '|.*ID.*任务.*状态' tmp/task-ledger.md 2>/dev/null; then
  hook_log "WARN" "tmp/task-ledger.md 表头格式不正确"
  WARN=1
fi

# 2f. 写入 write-session summary
python3 -c "
import json, os
from pathlib import Path
from datetime import datetime, timezone
agent_log_dir = Path('${AGENT_LOG_DIR}')
summary_path = agent_log_dir / 'stop-check-summary.json'
block = int(os.environ.get('STOP_BLOCK', '0'))
d = {
    'schemaVersion': 1,
    'ts': datetime.now(timezone.utc).isoformat(),
    'readOnly': False,
    'status': 'FAIL' if block else 'PASS',
    'changeId': '',
    'requiredTargets': [],
    'blockingFailures': [],
    'warnings': [],
}
summary_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
"

rm -f "$STDIN_TMP"
[[ $BLOCK -ne 0 ]] && exit $EXIT_BLOCK
[[ $WARN -ne 0 ]] && exit $EXIT_WARN
exit $EXIT_OK
