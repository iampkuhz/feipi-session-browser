#!/usr/bin/env bash
# 定义 EXIT_OK 常量配置。
EXIT_OK=0
EXIT_WARN=1
EXIT_BLOCK=2

# hook_log: 打印 hook 日志到 stderr。
# 用法：hook_log "LEVEL" "message"
hook_log() {
  local level="$1"
  shift
  echo "[hook:$(basename "${BASH_SOURCE[1]:-unknown}")] [$level] $*" >&2
}
