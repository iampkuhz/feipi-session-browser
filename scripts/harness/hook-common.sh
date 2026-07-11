#!/usr/bin/env bash
# 三个平台共享的极薄 hook shell helper；业务逻辑统一交给 Python 入口。
set -euo pipefail

EXIT_OK=0
EXIT_WARN=1
EXIT_BLOCK=2

#
# 输出带统一前缀的 hook 日志。
hook_log() {
  local level="$1"; shift || true
  printf '[feipi-hook:%s] %s\n' "$level" "$*" >&2
}

# 定位当前 Git 仓库根；失败时回退到 helper 所在仓库。
repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || {
    local source_path="${BASH_SOURCE[0]}"
    local dir
    dir="$(cd "$(dirname "$source_path")/../.." && pwd)"
    printf '%s\n' "$dir"
  }
}

# 根据载荷之外的当前目录提示解析可信执行根。
hook_exec_root() {
  local root="${1:-$(repo_root)}"
  local hint="${FEIPI_HOOK_CWD:-$PWD}"
  git -C "$hint" rev-parse --show-toplevel 2>/dev/null || printf '%s\n' "$root"
}

# 从标准输入载荷、运行记录和会话绑定解析执行根。
hook_exec_root_from_payload() {
  local root="$1"
  local stdin_file="$2"
  local client="${3:-${FEIPI_AGENT_CLIENT:-unknown}}"
  python3 - "$root" "$stdin_file" "$client" <<'PY'
import json, os, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
stdin_file = Path(sys.argv[2])
client = sys.argv[3]
try:
    data = json.loads(stdin_file.read_text(encoding='utf-8') or '{}')
except Exception:
    data = {}
run_id = data.get('run_id') or data.get('runId') or os.environ.get('FEIPI_RUN_ID','')
session = data.get('session_id') or data.get('sessionId') or os.environ.get('FEIPI_SESSION_ID','')
cwd = data.get('cwd') or data.get('workingDirectory') or os.environ.get('FEIPI_HOOK_CWD') or os.getcwd()

def git_root(path):
    try:
        out = subprocess.check_output(['git','-C',str(path),'rev-parse','--show-toplevel'], text=True, stderr=subprocess.DEVNULL).strip()
        return Path(out).resolve()
    except Exception:
        return None

def runtime_root(repo):
    override = os.environ.get('FEIPI_AGENT_RUNTIME_ROOT','').strip()
    if override:
        return Path(override).expanduser().resolve()
    try:
        common = subprocess.check_output(['git','-C',str(repo),'rev-parse','--git-common-dir'], text=True, stderr=subprocess.DEVNULL).strip()
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = repo / common_path
        return common_path.resolve() / 'feipi-agent-runtime'
    except Exception:
        return repo / '.git' / 'feipi-agent-runtime'
repo = git_root(cwd) or git_root(root) or root
runs = runtime_root(repo) / 'runs'
record = None
if run_id:
    p = runs / f'{run_id}.json'
    if p.exists():
        try: record = json.loads(p.read_text(encoding='utf-8'))
        except Exception: record = None
if record is None and session:
    index = runs / 'index.json'
    ids = []
    try: ids = json.loads(index.read_text(encoding='utf-8')).get('runs', [])
    except Exception: ids = []
    if not ids and runs.is_dir(): ids = [p.stem for p in runs.glob('*.json') if p.name != 'index.json']
    for rid in ids:
        try: item = json.loads((runs / f'{rid}.json').read_text(encoding='utf-8'))
        except Exception: continue
        if item.get('client') == client and item.get('sessionId') == session:
            record = item; break
if record and record.get('worktreeRoot'):
    wt = Path(str(record['worktreeRoot'])).resolve()
    if wt.exists():
        print(wt)
        raise SystemExit(0)
print(repo)
PY
}

# 直接执行共享 Python hook 入口，保持包装器不复制业务逻辑。
run_python_hook() {
  local client="$1" event="$2" root="$3"
  export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
  export FEIPI_AGENT_CLIENT="$client"
  local exec_root
  exec_root="$(hook_exec_root "$root")"
  cd "$exec_root"
  export PYTHONPATH="${exec_root}${PYTHONPATH:+:${PYTHONPATH}}"
  exec python3 -m scripts.claude_hooks.main "$event"
}

# 只读取一次标准输入后执行共享 Stop 入口。
run_stop_hook() {
  local client="$1" root="$2"
  export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
  export FEIPI_AGENT_CLIENT="$client"
  local stdin_tmp
  stdin_tmp="$(mktemp)"
  trap 'rm -f "$stdin_tmp"' EXIT
  cat > "$stdin_tmp" 2>/dev/null || true
  local exec_root
  exec_root="$(hook_exec_root_from_payload "$root" "$stdin_tmp" "$client")"
  export FEIPI_HOOK_EXEC_ROOT="$exec_root"
  cd "$exec_root"
  export PYTHONPATH="${exec_root}${PYTHONPATH:+:${PYTHONPATH}}"
  exec python3 "$exec_root/scripts/harness/stop_entry.py" --agent "$client" < "$stdin_tmp"
}
