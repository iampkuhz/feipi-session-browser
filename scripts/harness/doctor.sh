#!/usr/bin/env bash
# feipi-session-browser 项目环境体检脚本。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VENV_DIR="${SESSION_BROWSER_VENV_DIR:-$ROOT/.venv}"
fail=0

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
    echo "[PASS] file exists: $file"
  else
    echo "[FAIL] missing file: $file" >&2
    fail=1
  fi
}

# 检查dir。
check_dir() {
  local dir="$1"
  if [[ -d "$dir" ]]; then
    echo "[PASS] dir exists: $dir"
  else
    echo "[FAIL] missing dir: $dir" >&2
    fail=1
  fi
}

check_file AGENTS.md
check_file CLAUDE.md
check_file README.md
check_file pyproject.toml
check_file requirements-dev.txt
check_file requirements-dev.lock
check_file scripts/session-browser.sh
check_file .claude/settings.json
# Hook 入口脚本：每类 hook 都有独立 shell 脚本。
check_file .claude/hooks/stop.sh
check_file .claude/hooks/session-start.sh
check_file .claude/hooks/subagent-start.sh
check_file .claude/hooks/pre-bash.sh
check_file .claude/hooks/post-bash.sh
check_file .claude/hooks/pre-write.sh
check_file .claude/hooks/post-write.sh
check_file .claude/hooks/tool-failure.sh
check_file .claude/hooks/subagent-stop.sh
check_file .claude/hooks/config-change.sh
check_file .claude/hooks/lib/common.sh
check_file .codex/hooks/pre_tool_guard.sh
check_file .codex/hooks/pre_write_guard.sh
check_file .codex/hooks/post_bash_guard.sh
check_file .codex/hooks/post_tool_guard.sh
check_file .codex/hooks/stop_check.sh
check_file .qoder/hooks/pre_tool_guard.sh
check_file .qoder/hooks/pre_write_guard.sh
check_file .qoder/hooks/post_bash_guard.sh
check_file .qoder/hooks/post_tool_guard.sh
check_file .qoder/hooks/stop_check.sh
check_file harness/manifest.yaml
check_file harness/agent-runtime.md
check_file scripts/harness/agent_stop_check.py
check_dir tests
check_dir scripts/claude_hooks

if [[ -n "$PYTHON" ]]; then
  echo "[INFO] python: $PYTHON"
  "$PYTHON" scripts/harness/python_env.py report || fail=1
  "$PYTHON" scripts/harness/python_env.py check-installed --profile test || fail=1
else
  fail=1
fi

if [[ -f .claude/settings.json && -n "$PYTHON" ]]; then
  "$PYTHON" -m json.tool .claude/settings.json >/dev/null || {
    echo "[FAIL] invalid JSON: .claude/settings.json" >&2
    fail=1
  }
fi

for script in scripts/session-browser.sh .claude/hooks/*.sh .codex/hooks/*.sh .qoder/hooks/*.sh; do
  [[ -f "$script" ]] || continue
  bash -n "$script" || fail=1
done

if [[ -n "$PYTHON" ]]; then
  "$PYTHON" -m compileall -q src || fail=1
  "$PYTHON" scripts/quality/check_language_policy.py || fail=1
  "$PYTHON" scripts/quality/check_codex_agent_policy.py || fail=1
  "$PYTHON" scripts/quality/check_agent_runtime_manifest.py || fail=1
  "$PYTHON" scripts/quality/check_agent_hook_parity.py || fail=1
fi

# CSS ownership 校验。
if [[ -n "$PYTHON" ]]; then
  css_output="$("$PYTHON" scripts/validate_css_ownership.py 2>&1)" || true
  css_total="$(echo "$css_output" | grep 'Total:' | sed 's/.*Total: \([0-9]*\).*/\1/' || echo 0)"
  if [[ "$css_total" -gt 0 ]]; then
    echo "[FAIL] CSS ownership violations: $css_total" >&2
    echo "$css_output" >&2
    fail=1
  else
    echo "[PASS] CSS ownership validation"
  fi
fi

# 检查个人文件和临时目录是否不存在于磁盘。
# 必须使用 `test ! -e`，因为 `.gitignore` 会隐藏 git status 结果。
local_files=(.mcp.json .env)
# 注意：不检查 `.pytest_cache`，因为它是 pytest 正常副作用。
# doctor 本身也可能通过产品测试触发 pytest。
local_dirs=(data output)
for f in "${local_files[@]}"; do
  if [[ -e "$f" ]]; then
    echo "[FAIL] personal file should not exist: $f" >&2
    fail=1
  else
    echo "[PASS] personal file absent: $f"
  fi
done
# `settings.local.json` 是应保留在本地的用户配置。
# 这里只告警，不阻断 quality gate。
if [[ -e ".claude/settings.local.json" ]]; then
  echo "[WARN] personal config present: .claude/settings.local.json (gitignored, allowed)"
fi
for d in "${local_dirs[@]}"; do
  if [[ -d "$d" ]]; then
    echo "[FAIL] ephemeral dir should not exist: $d" >&2
    fail=1
  else
    echo "[PASS] ephemeral dir absent: $d"
  fi
done

# OpenSpec runtime state 不应被 Git 追踪
openspec_tracked=$(git ls-files openspec/active_change.json openspec/changes 2>/dev/null)
if [[ -n "$openspec_tracked" ]]; then
  echo "[FAIL] OpenSpec runtime state 不应被 Git 追踪: $openspec_tracked" >&2
  fail=1
else
  echo "[PASS] OpenSpec runtime state 未被 Git 追踪"
fi

# openspec/changes/ 应存在，不存在时自动创建
if [[ ! -d "openspec/changes" ]]; then
  mkdir -p openspec/changes
  echo "[WARN] openspec/changes/ 不存在，已自动创建"
else
  echo "[PASS] openspec/changes/ 目录存在"
fi

# active_change.json 不存在是正常状态
if [[ -f "openspec/active_change.json" ]]; then
  echo "[PASS] openspec/active_change.json 存在（本地 runtime state）"
else
  echo "[PASS] openspec/active_change.json 不存在（正常状态）"
fi

if [[ $fail -ne 0 ]]; then
  echo "[FAIL] doctor found issues" >&2
  exit 1
fi

echo "[PASS] doctor completed"
