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

# hook_exec_root：当 FEIPI_HOOK_CWD 指向同一仓库的 linked worktree 时优先使用它。
# 这样 hook 入口可以仍位于 base checkout，但策略和 gate 在当前主 agent worktree 中执行。
hook_exec_root() {
  local fallback_root="${1:-}"
  local hook_cwd="${FEIPI_HOOK_CWD:-$PWD}"
  local candidate_root=""
  local fallback_common=""
  local candidate_common=""

  candidate_root="$(git -C "$hook_cwd" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -n "$candidate_root" && -f "$candidate_root/scripts/harness/agent_stop_check.py" ]]; then
    fallback_common="$(git -C "$fallback_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    candidate_common="$(git -C "$candidate_root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    if [[ -n "$fallback_common" && "$fallback_common" == "$candidate_common" ]]; then
      printf '%s\n' "$candidate_root"
      return 0
    fi
  fi

  printf '%s\n' "$fallback_root"
}
