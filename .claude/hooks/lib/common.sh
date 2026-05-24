#!/usr/bin/env bash
# Shared helpers for project Claude Code hooks.

EXIT_OK=0
EXIT_WARN=1
EXIT_BLOCK=2
EXIT_SKIP=3

HOOK_DRY_RUN="${HOOK_DRY_RUN:-1}"

# 固定路径常量
AGENT_LOG_DIR_REL="tmp/agent_logs/current"
QUALITY_DIR_REL="tmp/quality"

# 01. hook_log: 打印 hook 日志到 stderr。
hook_log() {
  local level="$1"
  shift
  echo "[hook:$(basename "${BASH_SOURCE[1]:-unknown}")] [$level] $*" >&2
}

# 02. repo_root: 定位仓库根目录。
repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
  printf '%s\n' "$script_dir"
}

# 03. extract_session_id: 从 stdin JSON 中提取 sessionId。
# 用法：SESSION_ID="$(extract_session_id "$STDIN_TMP")"
# stdin 已经被保存到临时文件，此函数只读取文件。
extract_session_id() {
  local stdin_file="$1"
  if [[ ! -f "$stdin_file" ]]; then
    return
  fi
  python3 -c "
import json
try:
    data = json.loads(open('${stdin_file}').read())
    sid = data.get('session_id', data.get('sessionId', ''))
    if sid:
        print(sid)
except:
    pass
" 2>/dev/null || true
}

# 04. ensure_base_dirs: 确保基础日志目录存在。
ensure_base_dirs() {
  mkdir -p "tmp/agent_logs/current"
  mkdir -p "tmp/quality"
}
