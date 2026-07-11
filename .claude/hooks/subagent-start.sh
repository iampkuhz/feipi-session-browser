#!/usr/bin/env bash
# SubagentStart: 子 agent 启动记录。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
EXEC_ROOT="$(hook_exec_root "$ROOT")"
cd "$EXEC_ROOT" || exit $EXIT_WARN
export PYTHONPATH="${EXEC_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="claude"

# 保存 stdin 到临时文件
STDIN_TMP="$(mktemp)"
cat > "$STDIN_TMP" 2>/dev/null || true


python3 -m scripts.claude_hooks.main subagent-start < "$STDIN_TMP"
rm -f "$STDIN_TMP"
