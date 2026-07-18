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

# 记录一项通过的检查结果。
pass_check() {
  local message="$1"
  pass_count=$((pass_count + 1))
  if [[ $VERBOSE -eq 1 ]]; then
    echo "[PASS] $message"
  fi
}

# 记录一项失败的检查结果。
fail_check() {
  local message="$1"
  failure_count=$((failure_count + 1))
  fail=1
  echo "[FAIL] $message" >&2
}

# 记录一项警告检查结果。
warn_check() {
  local message="$1"
  warning_count=$((warning_count + 1))
  echo "[WARN] $message" >&2
}

# 执行检查命令并记录结果。
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

# 通过共享 resolver 解析项目 Python executable。
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

# 检查文件。
check_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    pass_check "file exists: $file"
  else
    fail_check "missing file: $file"
  fi
}

# 检查dir。
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
check_file .claude/settings.json
check_file .codex/hooks.json
check_file .qoder/settings.json
check_file scripts/harness/hook_dispatch.py
check_file harness/manifest.yaml
check_file docs/agent-runtime.md
check_file scripts/harness/change.py
check_file scripts/agent_runtime/hook_entry.py
check_file scripts/agent_runtime/change/controller.py
check_file scripts/agent_runtime/change/model.py
check_file scripts/agent_runtime/change/store.py
check_file scripts/agent_runtime/change/runtime.py
check_file scripts/agent_runtime/change/candidate.py
check_file scripts/agent_runtime/change/fixture.py
check_file scripts/agent_runtime/change/protocol.py
check_file scripts/agent_runtime/stop/evidence.py
check_dir tests
check_dir scripts/agent_runtime

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

if [[ -f .claude/settings.json && -n "$PYTHON" ]]; then
  run_check "valid JSON: .claude/settings.json" \
    "$PYTHON" -m json.tool .claude/settings.json
fi

run_check "valid shell syntax: scripts/session-browser.sh" bash -n scripts/session-browser.sh

if [[ -n "$PYTHON" ]]; then
  run_check "Python source compiles" "$PYTHON" -m compileall -q src
  checks=(
    repository.language-policy
    agent.codex-policy
    agent.runtime-manifest
    agent.hook-parity
    repository.no-committed-local-paths
    agent.permission-policy
    agent.policy-size
    agent.rules-sync
    agent.runtime-isolation
    agent.runtime-worktree
    repository.gate-bypass
    agent.protected-roots
    agent.qoder-parity
    agent.hook-payload
    agent.subagent-handoff
    agent.skill-registry
    agent.entry-parity
    repository.no-real-session-fixtures
    security.secret-like-content
    web.css-ownership
  )
  for check in "${checks[@]}"; do
    run_check "quality check: $check" "$PYTHON" -m scripts.checks "$check"
  done
fi

# 检查个人文件和临时目录是否不存在于磁盘。
# 必须使用 `test ! -e`，因为 `.gitignore` 会隐藏 git status 结果。
local_files=(.mcp.json .env)
# 注意：不检查 `.pytest_cache`，因为它是 pytest 正常副作用。
# doctor 本身也可能通过产品测试触发 pytest。
local_dirs=(data output)
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
for d in "${local_dirs[@]}"; do
  if [[ -d "$d" ]]; then
    fail_check "ephemeral dir should not exist: $d"
  else
    pass_check "ephemeral dir absent: $d"
  fi
done

# OpenSpec runtime state 不应被 Git 追踪
openspec_tracked=$(git ls-files openspec/active_change.json openspec/changes 2>/dev/null || true)
if [[ -n "$openspec_tracked" ]]; then
  fail_check "OpenSpec runtime state 不应被 Git 追踪: $openspec_tracked"
else
  pass_check "OpenSpec runtime state 未被 Git 追踪"
fi

# openspec/changes/ 应存在，不存在时自动创建
if [[ ! -d "openspec/changes" ]]; then
  mkdir -p openspec/changes
  warn_check "openspec/changes/ 不存在，已自动创建"
else
  pass_check "openspec/changes/ 目录存在"
fi

# active_change.json 不存在是正常状态
if [[ -f "openspec/active_change.json" ]]; then
  pass_check "openspec/active_change.json 存在（本地 runtime state）"
else
  pass_check "openspec/active_change.json 不存在（正常状态）"
fi

if [[ $fail -ne 0 ]]; then
  echo "DOCTOR_RESULT status=FAIL passed=$pass_count failed=$failure_count warnings=$warning_count" >&2
  exit 1
fi

echo "DOCTOR_RESULT status=PASS passed=$pass_count failed=0 warnings=$warning_count"
