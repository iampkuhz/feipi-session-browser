#!/usr/bin/env bash
# Shared helpers for project Claude Code hooks.

EXIT_OK=0
EXIT_WARN=1
EXIT_BLOCK=2
EXIT_SKIP=3

HOOK_DRY_RUN="${HOOK_DRY_RUN:-1}"

hook_log() {
  local level="$1"
  shift
  echo "[hook:$(basename "${BASH_SOURCE[1]:-unknown}")] [$level] $*" >&2
}

repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
  printf '%s\n' "$script_dir"
}
