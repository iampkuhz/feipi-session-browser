#!/usr/bin/env bash
# Project doctor for feipi-session-browser.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

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
check_file README.md
check_file pyproject.toml
check_file requirements.txt
check_file requirements-dev.txt
check_file scripts/session-browser.sh
check_file docs/governance/tool-usage.md
check_file .claude/settings.json
# Hook entry scripts — each hook type has its own shell script.
check_file .claude/hooks/stop.sh
check_file .claude/hooks/session-start.sh
check_file .claude/hooks/subagent-start.sh
check_file .claude/hooks/pre-bash.sh
check_file .claude/hooks/pre-write.sh
check_file .claude/hooks/post-write.sh
check_file .claude/hooks/tool-failure.sh
check_file .claude/hooks/subagent-stop.sh
check_file .claude/hooks/config-change.sh
check_file .claude/hooks/lib/common.sh
# Legacy helpers kept for reference.
check_file .claude/hooks/pre_tool_guard.sh
check_file .claude/hooks/post_tool_guard.sh
check_file harness/manifest.yaml
check_dir src/session_browser
check_dir tests
check_dir scripts/claude_hooks

if [[ -f .claude/settings.json ]]; then
  python3 -m json.tool .claude/settings.json >/dev/null || {
    echo "[FAIL] invalid JSON: .claude/settings.json" >&2
    fail=1
  }
fi

for script in scripts/session-browser.sh .claude/hooks/*.sh; do
  [[ -f "$script" ]] || continue
  bash -n "$script" || fail=1
done

python3 -m compileall -q src || fail=1

# CSS ownership validation
# session-detail-timeline.css is a known deprecated file that triggers a
# forbidden_filename warning — that one is expected and allowed until it
# is fully removed from the repo.
css_output="$(python3 scripts/validate_css_ownership.py 2>&1)" || true
css_total="$(echo "$css_output" | grep 'Total:' | sed 's/.*Total: \([0-9]*\).*/\1/' || echo 0)"
css_expected=1  # only the deprecated timeline file is allowed
if [[ "$css_total" -gt "$css_expected" ]]; then
  echo "[FAIL] CSS ownership violations: $css_total (expected $css_expected or fewer)" >&2
  echo "$css_output" >&2
  fail=1
else
  echo "[PASS] CSS ownership validation (${css_total} known warning)"
fi

# Check that personal/ephemeral files and dirs do NOT exist on disk.
# Must use `test ! -e` (not git status) because .gitignore hides them.
local_files=(.mcp.json .env)
# Note: .pytest_cache is NOT checked here because it is a normal side-effect
# of running pytest (which doctor itself triggers via product tests).
local_dirs=(data output .venv)
for f in "${local_files[@]}"; do
  if [[ -e "$f" ]]; then
    echo "[FAIL] personal file should not exist: $f" >&2
    fail=1
  else
    echo "[PASS] personal file absent: $f"
  fi
done
# settings.local.json is a normal user config that should be kept locally;
# just warn but don't block quality gate.
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
