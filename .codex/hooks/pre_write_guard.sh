#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit|NotebookEdit): 写入前拦截受保护路径。
# 与 Qoder pre_write_guard 保持一致。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1

# 如果没有 stdin（hook payload），只做轻量检查并 PASS，不误杀。
STDIN_TMP="$(mktemp)"
trap 'rm -f "$STDIN_TMP"' EXIT
if ! cat > "$STDIN_TMP" 2>/dev/null; then
  exit 0
fi
if [[ ! -s "$STDIN_TMP" ]]; then
  exit 0
fi

# 尝试从 stdin JSON 中提取写入目标路径。
TARGET_PATH=""
TARGET_PATH="$(python3 - "$STDIN_TMP" <<'PY' 2>/dev/null || true
import json
import sys

try:
    data = json.loads(open(sys.argv[1], encoding='utf-8').read())
except Exception:
    data = {}
tool_input = data.get('tool_input') or data.get('toolInput') or {}
if isinstance(tool_input, dict):
    path = tool_input.get('file_path') or tool_input.get('path') or ''
    print(path)
else:
    print('')
PY
)"

# 如果没有提取到路径，退化为检查是否有活跃 OpenSpec change。
if [[ -z "$TARGET_PATH" ]]; then
  if [[ -f "scripts/hooks/guard_openspec_change.py" ]]; then
    python3 scripts/hooks/guard_openspec_change.py
    exit $?
  fi
  exit 0
fi

# 检查写入目标是否在受保护根下。
PROTECTED_ROOTS=(
  ".claude/"
  ".codex/"
  ".qoder/"
  ".agents/"
  "skills/"
  "harness/"
  "scripts/"
  "openspec/"
  "AGENTS.md"
  "CLAUDE.md"
)

for protected in "${PROTECTED_ROOTS[@]}"; do
  protected_base="${protected%/}"
  case "$TARGET_PATH" in
    "$protected"|"$protected/"*|"$protected_base"|"$protected_base/"*)
      # 写入目标在受保护路径下，检查是否有活跃 OpenSpec change。
      if [[ -f "scripts/hooks/guard_openspec_change.py" ]]; then
        python3 scripts/hooks/guard_openspec_change.py
        exit $?
      fi
      # 没有 guard 脚本时，检查是否有活跃变更。
      if [[ ! -d "openspec/changes" ]]; then
        echo "[pre_write_guard] FAIL: 写入受保护路径 $protected_base 但 openspec/changes/ 不存在" >&2
        exit 2
      fi
      has_active=0
      for d in openspec/changes/*/; do
        [[ -d "$d" ]] || continue
        [[ "$(basename "$d")" == "archive" ]] && continue
        has_active=1
        break
      done
      if [[ $has_active -eq 0 ]]; then
        echo "[pre_write_guard] FAIL: 写入受保护路径 $protected_base 但无活跃 OpenSpec change" >&2
        exit 2
      fi
      exit 0
      ;;
  esac
done

# 写入目标不在受保护路径下，放行。
exit 0
