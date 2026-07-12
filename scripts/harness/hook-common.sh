#!/usr/bin/env bash
# 三个平台共享的极薄 hook shell helper；业务逻辑统一交给 Python 入口。
set -euo pipefail

# 直接执行共享 Python hook 入口，保持包装器不复制业务逻辑。
run_python_hook() {
  local client="$1" event="$2" root="$3"
  export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
  export FEIPI_AGENT_CLIENT="$client"
  cd "$root"
  export PYTHONPATH="${root}${PYTHONPATH:+:${PYTHONPATH}}"
  exec python3 -m scripts.agent_runtime.hook_entry "$event"
}

# 标准输入不落盘、不解析，直接转发给共享 Stop 入口。
run_stop_hook() {
  local client="$1" root="$2"
  export FEIPI_HOOK_CWD="${FEIPI_HOOK_CWD:-$PWD}"
  export FEIPI_AGENT_CLIENT="$client"
  cd "$root"
  export PYTHONPATH="${root}${PYTHONPATH:+:${PYTHONPATH}}"
  exec python3 "$root/scripts/harness/stop_entry.py" --agent "$client"
}
