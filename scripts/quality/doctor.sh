#!/usr/bin/env bash
# Project doctor for feipi-session-browser.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
VENV_DIR="${SESSION_BROWSER_VENV_DIR:-$ROOT/.venv}"

python_is_compatible() {
  local candidate="$1"
  "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

python_bin() {
  if [[ -n "${SESSION_BROWSER_PYTHON:-}" ]]; then
    if python_is_compatible "$SESSION_BROWSER_PYTHON"; then
      printf '%s\n' "$SESSION_BROWSER_PYTHON"
      return 0
    fi
    echo "[FAIL] SESSION_BROWSER_PYTHON 不可执行或低于 Python 3.10：$SESSION_BROWSER_PYTHON" >&2
    return 1
  fi
  if [[ -x "$VENV_DIR/bin/python" ]] && python_is_compatible "$VENV_DIR/bin/python"; then
    printf '%s\n' "$VENV_DIR/bin/python"
    return 0
  fi
  if command -v python >/dev/null 2>&1 && python_is_compatible python; then
    printf 'python\n'
    return 0
  fi
  if command -v python3 >/dev/null 2>&1 && python_is_compatible python3; then
    printf 'python3\n'
    return 0
  fi
  echo "[FAIL] 未找到可用 Python 解释器（需要 Python >= 3.10）。" >&2
  return 1
}

PYTHON="$(python_bin)" || PYTHON=""

fail=0

check_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    echo "[PASS] file exists: $file"
  else
    echo "[FAIL] missing file: $file" >&2
    fail=1
  fi
}

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
check_file .claude/settings.json
check_file .claude/hooks/pre-bash.sh
check_file .claude/hooks/pre-write.sh
check_file .claude/hooks/post-write.sh
check_file .claude/hooks/stop.sh
check_file .claude/commands/diagnose-ui-gate.md
check_file scripts/session-browser.sh
check_file requirements.txt
check_file requirements-dev.txt
check_file requirements.lock
check_file requirements-dev.lock
check_file harness/README.md
check_dir src/session_browser
check_dir tests
check_dir openspec/specs
check_dir openspec/changes
check_dir openspec/schemas
check_dir openspec/templates
check_dir scripts/openspec
check_dir scripts/agent_hooks
check_dir scripts/quality

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

if [[ -n "$PYTHON" ]] && "$PYTHON" -c "import yaml; yaml.safe_load(open('openspec/config.yaml'))" 2>/dev/null; then
  echo "[PASS] openspec/config.yaml is valid YAML"
else
  echo "[FAIL] openspec/config.yaml is not valid YAML" >&2
  fail=1
fi

for script in scripts/session-browser.sh .claude/hooks/*.sh scripts/quality/doctor.sh; do
  [[ -f "$script" ]] || continue
  bash -n "$script" || fail=1
done

if [[ -n "$PYTHON" ]]; then
  "$PYTHON" -m compileall -q src || fail=1
fi

# Check that personal/ephemeral files and dirs do NOT exist on disk.
local_files=(.mcp.json .env)
local_dirs=(data output prompts)
for f in "${local_files[@]}"; do
  if [[ -e "$f" ]]; then
    echo "[FAIL] personal file should not exist: $f" >&2
    fail=1
  else
    echo "[PASS] personal file absent: $f"
  fi
done
# settings.local.json is a normal user config that should be kept locally;
# warn but do not block the doctor gate.
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

if [[ $fail -ne 0 ]]; then
  echo "[FAIL] doctor found issues" >&2
  exit 1
fi

echo "[PASS] doctor completed"
