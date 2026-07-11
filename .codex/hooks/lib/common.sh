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

# hook_exec_root_from_payload：Stop hook 读取 stdin 后，根据 session assignment 解析执行根。
# 当 active project 仍是 base checkout，但 stdin session 已绑定 worktree 时，确保后续 Stop gate
# 和 runtime report gate 都在 assigned worktree 中执行。
hook_exec_root_from_payload() {
  local fallback_root="${1:-}"
  local stdin_file="${2:-}"
  local client="${3:-${FEIPI_AGENT_CLIENT:-}}"
  local direct_root=""

  direct_root="$(hook_exec_root "$fallback_root")"
  if [[ "$direct_root" != "$fallback_root" ]]; then
    printf '%s\n' "$direct_root"
    return 0
  fi
  python3 - "$fallback_root" "${stdin_file:-}" "$client" "$direct_root" <<'PYHOOK'
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

fallback_root = Path(sys.argv[1]).resolve()
stdin_file = Path(sys.argv[2])
client_arg = sys.argv[3]
direct_root = Path(sys.argv[4]).resolve()

SAFE_SEGMENT_RE = re.compile(r'[^A-Za-z0-9._-]+')
MAX_SEGMENT_LENGTH = 80


def sanitize(value: str | None, fallback: str = 'unknown') -> str:
    raw = str(value or '').strip() or fallback
    cleaned = SAFE_SEGMENT_RE.sub('-', raw).strip('.-_/') or fallback
    if cleaned in {'.', '..'}:
        cleaned = fallback
    if cleaned == raw and len(cleaned) <= MAX_SEGMENT_LENGTH and '/' not in cleaned:
        return cleaned
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]
    prefix = cleaned[: max(1, MAX_SEGMENT_LENGTH - 13)].rstrip('.-')
    return f'{prefix}-{digest}'


def git_common(root: Path) -> Path | None:
    try:
        raw = subprocess.check_output(
            ['git', '-C', str(root), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None
    return Path(raw).resolve() if raw else None


def output(path: Path) -> None:
    print(str(path.resolve()))

try:
    payload = json.loads(stdin_file.read_text(encoding='utf-8')) if str(stdin_file) else {}
    if not isinstance(payload, dict):
        payload = {}
except Exception:
    payload = {}

session_id = str(payload.get('session_id') or payload.get('sessionId') or '')
client = str(client_arg or payload.get('agent_client') or payload.get('agentClient') or payload.get('client') or '')
common = git_common(fallback_root)
if common is None or not client:
    output(direct_root)
    raise SystemExit(0)


def assigned_from_marker(marker: Path) -> Path | None:
    try:
        marker_data = json.loads(marker.read_text(encoding='utf-8'))
        assigned = Path(str(marker_data.get('worktreePath') or '')).expanduser().resolve()
    except Exception:
        return None
    if not assigned.is_dir():
        return None
    if not (assigned / 'scripts' / 'harness' / 'stop_entry.py').is_file():
        return None
    assigned_common = git_common(assigned)
    if assigned_common != common:
        return None
    return assigned

marker_dir = common / 'feipi-agent-runtime' / 'worktrees' / sanitize(client)
markers: list[Path]
if session_id:
    markers = [marker_dir / f'{sanitize(session_id)}.json']
else:
    try:
        markers = sorted(marker_dir.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
    except Exception:
        markers = []

for marker in markers:
    assigned = assigned_from_marker(marker)
    if assigned is not None:
        output(assigned)
        raise SystemExit(0)
output(direct_root)
PYHOOK
}
