#!/usr/bin/env bash
# Codex Stop hook 的轻量入口，调用共享 harness stop gate。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export FEIPI_AGENT_CLIENT="${FEIPI_AGENT_CLIENT:-codex}"

exec python3 "$ROOT/scripts/harness/agent_stop_check.py" --agent codex
