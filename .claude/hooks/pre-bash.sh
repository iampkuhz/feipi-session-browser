#!/usr/bin/env bash
# PreToolUse (Bash): Bash 命令策略检查。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit $EXIT_WARN
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

# 保存 stdin 到临时文件，后续 Python 模块需要读取
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true

# 固定路径：确保 agent 日志目录存在
mkdir -p "$ROOT/tmp/agent_logs/current"

python3 -m scripts.claude_hooks.main pre-bash < "$STDIN_TMP"
rm -f "$STDIN_TMP"
