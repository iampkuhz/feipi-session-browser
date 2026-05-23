#!/usr/bin/env bash
# PreToolUse (Bash): Bash 命令策略检查。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# 保存 stdin 到临时文件，后续 Python 模块和 log_dir 解析都需要
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

# 解析当前 session 的日志目录（per-session 隔离）
export FEIPI_AGENT_LOG_DIR="$(resolve_current_log_dir "$STDIN_TMP")"

python3 -m scripts.claude_hooks.main pre-bash < "$STDIN_TMP"
rm -f "$STDIN_TMP"
