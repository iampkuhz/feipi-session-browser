#!/usr/bin/env bash
# 定义 EXIT_OK 常量配置。
EXIT_OK=0
EXIT_WARN=1
EXIT_BLOCK=2
EXIT_SKIP=3

HOOK_DRY_RUN="${HOOK_DRY_RUN:-1}"
# 写入 hook 日志。

hook_log() {
  local level="$1"
  shift
  echo "[hook:$(basename "${BASH_SOURCE[1]:-unknown}")] [$level] $*" >&2
}
# 解析 repo root。

repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
  printf '%s\n' "$script_dir"
}
