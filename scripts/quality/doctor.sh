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
check_file .claude/settings.json
check_file .claude/hooks/pre-bash.sh
check_file .claude/hooks/pre-write.sh
check_file .claude/hooks/post-write.sh
check_file .claude/hooks/stop.sh
check_file .claude/commands/diagnose-ui-gate.md
check_file scripts/dev/session-browser.sh
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
check_dir scripts/dev

if [[ -f .claude/settings.json ]]; then
  python3 -m json.tool .claude/settings.json >/dev/null || {
    echo "[FAIL] invalid JSON: .claude/settings.json" >&2
    fail=1
  }
fi

if python3 -c "import yaml; yaml.safe_load(open('openspec/config.yaml'))" 2>/dev/null; then
  echo "[PASS] openspec/config.yaml is valid YAML"
else
  echo "[FAIL] openspec/config.yaml is not valid YAML" >&2
  fail=1
fi

for script in scripts/dev/session-browser.sh .claude/hooks/*.sh scripts/quality/doctor.sh; do
  [[ -f "$script" ]] || continue
  bash -n "$script" || fail=1
done

python3 -m compileall -q src || fail=1

# Check that personal/ephemeral files and dirs do NOT exist on disk.
local_files=(.claude/settings.local.json .mcp.json .env)
local_dirs=(data output .venv .pytest_cache prompts)
for f in "${local_files[@]}"; do
  if [[ -e "$f" ]]; then
    echo "[FAIL] personal file should not exist: $f" >&2
    fail=1
  else
    echo "[PASS] personal file absent: $f"
  fi
done
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
