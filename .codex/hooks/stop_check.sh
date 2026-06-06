#!/usr/bin/env bash
# Codex Stop: thin wrapper around the shared harness stop gate.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT" || exit 1
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec python3 "$ROOT/scripts/harness/agent_stop_check.py" --agent codex
