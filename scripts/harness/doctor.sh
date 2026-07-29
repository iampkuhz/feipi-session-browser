#!/usr/bin/env bash
# feipi-session-browser 项目环境体检脚本。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VENV_DIR="${SESSION_BROWSER_VENV_DIR:-$ROOT/.local/python/venv}"
if [[ "$VENV_DIR" != /* ]]; then
  VENV_DIR="$ROOT/$VENV_DIR"
fi
fail=0
pass_count=0
failure_count=0
warning_count=0
VERBOSE=0

case "${1:-}" in
  "") ;;
  --verbose|-v) VERBOSE=1 ;;
  --help|-h)
    echo "Usage: bash scripts/harness/doctor.sh [--verbose]"
    exit 0
    ;;
  *)
    echo "[FAIL] unknown argument: $1" >&2
    echo "Usage: bash scripts/harness/doctor.sh [--verbose]" >&2
    exit 2
    ;;
esac

# 三类记录函数集中维护计数与稳定输出格式，避免检查分支各自拼装结果。
pass_check() {
  local message="$1"
  pass_count=$((pass_count + 1))
  if [[ $VERBOSE -eq 1 ]]; then
    echo "[PASS] $message"
  fi
}

fail_check() {
  local message="$1"
  failure_count=$((failure_count + 1))
  fail=1
  echo "[FAIL] $message" >&2
}

warn_check() {
  local message="$1"
  warning_count=$((warning_count + 1))
  echo "[WARN] $message" >&2
}

# 子检查输出有界截断，防止 doctor 失败时用下游长日志淹没首要诊断。
run_check() {
  local label="$1"
  shift
  local output
  if output="$("$@" 2>&1)"; then
    pass_check "$label"
    if [[ $VERBOSE -eq 1 && -n "$output" ]]; then
      printf '%s\n' "$output"
    fi
  else
    local rc=$?
    fail_check "$label (exit=$rc)"
    if [[ -n "$output" ]]; then
      local line_count
      line_count="$(printf '%s\n' "$output" | wc -l | tr -d ' ')"
      if [[ "$line_count" -gt 40 ]]; then
        echo "[diagnostic truncated: showing last 40 of $line_count lines]" >&2
      fi
      printf '%s\n' "$output" | tail -n 40 | tail -c 8000 >&2
      printf '\n' >&2
    fi
  fi
}

# 这里只选择能启动共享 resolver 的 bootstrap Python；最终项目解释器仍由 python_env.py 判定。
python_bin() {
  local resolver=""
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    resolver="$VENV_DIR/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    resolver="python3"
  elif command -v python >/dev/null 2>&1; then
    resolver="python"
  else
    echo "[FAIL] 未找到可运行 resolver 的 Python executable。" >&2
    return 1
  fi
  "$resolver" scripts/harness/python_env.py resolve
}

PYTHON="$(python_bin)" || PYTHON=""

check_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    pass_check "file exists: $file"
  else
    fail_check "missing file: $file"
  fi
}

check_dir() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    pass_check "dir exists: $dir"
  else
    fail_check "missing dir: $dir"
  fi
}

check_file AGENTS.md
check_file CLAUDE.md
check_file README.md
check_file pyproject.toml
check_file uv.lock
check_file scripts/session-browser.sh
check_file harness/agent-policy.manifest.yaml
check_file harness/skill-registry.yaml
check_file scripts/harness/validate_harness_structure.py
check_file scripts/openspec/validate_layout.py
check_dir tests
check_dir skills
check_dir openspec/specs

if [[ -n "$PYTHON" ]]; then
  pass_check "python interpreter: $PYTHON"
  run_check "python environment report" "$PYTHON" scripts/harness/python_env.py report
  run_check "test dependencies installed" \
    "$PYTHON" scripts/harness/python_env.py check-installed --profile test
else
  fail_check "no compatible Python interpreter"
fi

if command -v uv >/dev/null 2>&1; then
  run_check "uv lock is current" uv lock --check
else
  fail_check "uv is required for the Python dependency lock"
fi

run_check "valid shell syntax: scripts/session-browser.sh" bash -n scripts/session-browser.sh

if [[ -n "$PYTHON" ]]; then
  run_check "harness structure" "$PYTHON" scripts/harness/validate_harness_structure.py
  run_check "OpenSpec layout" "$PYTHON" scripts/openspec/validate_layout.py
fi

# 检查个人文件和临时目录是否不存在于磁盘。
# 必须使用 `test ! -e`，因为 `.gitignore` 会隐藏 git status 结果。
local_files=(.mcp.json .env)
for f in "${local_files[@]}"; do
  if [[ -e "$f" ]]; then
    fail_check "personal file should not exist: $f"
  else
    pass_check "personal file absent: $f"
  fi
done
# `settings.local.json` 是应保留在本地的用户配置。
# 这里只告警，不阻断 quality gate。
if [[ -e ".claude/settings.local.json" ]]; then
  warn_check "personal config present: .claude/settings.local.json (gitignored, allowed)"
fi

# OpenSpec runtime state 属于会话数据；一旦被追踪就阻断，避免个人运行状态进入仓库。
openspec_tracked=$(git ls-files openspec/active_change.json openspec/changes 2>/dev/null || true)
if [[ -n "$openspec_tracked" ]]; then
  fail_check "OpenSpec runtime state 不应被 Git 追踪: $openspec_tracked"
else
  pass_check "OpenSpec runtime state 未被 Git 追踪"
fi

# 缺少本地 change 目录不阻断环境使用；doctor 只报告，不自动修复。
if [[ ! -d "openspec/changes" ]]; then
  warn_check "openspec/changes/ 不存在；需要时请显式创建 OpenSpec change"
else
  pass_check "openspec/changes/ 目录存在"
fi

if [[ $fail -ne 0 ]]; then
  echo "DOCTOR_RESULT status=FAIL passed=$pass_count failed=$failure_count warnings=$warning_count" >&2
  exit 1
fi

echo "DOCTOR_RESULT status=PASS passed=$pass_count failed=0 warnings=$warning_count"
