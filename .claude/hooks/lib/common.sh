#!/usr/bin/env bash
# Shared helpers for project Claude Code hooks.

EXIT_OK=0
EXIT_WARN=1
EXIT_BLOCK=2
EXIT_SKIP=3

HOOK_DRY_RUN="${HOOK_DRY_RUN:-1}"

# 基础日志目录（所有 session 的父目录）
FEIPI_AGENT_LOGS_BASE="${FEIPI_AGENT_LOGS_BASE:-tmp/agent_logs}"

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
# 用法：SESSION_ID="$(extract_session_id)"
# stdin 会被消费，调用方需要先将 stdin 保存到临时文件再传。
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

# 04. build_session_log_dir: 根据 sessionId 构建 per-session 日志目录路径。
# 格式：tmp/agent_logs/MMDD_<short_session_id>/
# 多个 agent 实例同时运行时，各自有独立目录，互不干扰。
# 返回值：输出目录路径到 stdout，并在 FEIPI_AGENT_LOG_DIR 环境变量中设置。
build_session_log_dir() {
  local session_id="${1:-}"
  local base="${FEIPI_AGENT_LOGS_BASE:-tmp/agent_logs}"
  local date_part short_sid log_dir

  date_part="$(date +%m%d)"

  if [[ -n "$session_id" ]]; then
    # 提取 UUID 前 8 位作为短 ID
    short_sid="${session_id%%-*}"
    log_dir="${base}/${date_part}_${short_sid}"
  else
    # 无 session ID 时使用 adhoc 目录
    log_dir="${base}/${date_part}_adhoc"
  fi

  mkdir -p "$log_dir"
  printf '%s\n' "$log_dir"
}

# 05. resolve_current_log_dir: 解析当前 session 的日志目录。
# 优先从环境变量 FEIPI_AGENT_LOG_DIR 读取（如果 session-start.sh 已设置）。
# 否则从 stdin 临时文件中提取 sessionId 并构建目录路径。
# 如果文件不存在则自动创建。
# 用法：resolve_current_log_dir "$STDIN_TMP"
resolve_current_log_dir() {
  local stdin_file="${1:-}"

  # 已设置环境变量，直接使用
  if [[ -n "${FEIPI_AGENT_LOG_DIR:-}" ]] && [[ -d "${FEIPI_AGENT_LOG_DIR}" ]]; then
    printf '%s\n' "${FEIPI_AGENT_LOG_DIR}"
    return
  fi

  # 从 stdin 提取 sessionId
  local session_id=""
  if [[ -n "$stdin_file" ]] && [[ -f "$stdin_file" ]]; then
    session_id="$(extract_session_id "$stdin_file")"
  fi

  local log_dir
  log_dir="$(build_session_log_dir "$session_id")"

  # 写入 session-id.txt 文件，供其他脚本查询
  if [[ -n "$session_id" ]]; then
    echo "$session_id" > "${log_dir}/session-id.txt"
  fi

  export FEIPI_AGENT_LOG_DIR="$log_dir"
  printf '%s\n' "$log_dir"
}
