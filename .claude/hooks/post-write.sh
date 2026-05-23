#!/usr/bin/env bash
# PostToolUse (Write/Edit/...): 写后记录。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# 保存 stdin 到临时文件
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

# 解析当前 session 的日志目录
export FEIPI_AGENT_LOG_DIR="$(resolve_current_log_dir "$STDIN_TMP")"

python3 -m scripts.claude_hooks.main post-write < "$STDIN_TMP"
rm -f "$STDIN_TMP"
