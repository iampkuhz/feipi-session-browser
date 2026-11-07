#!/usr/bin/env bash
# 职责：复用唯一原生归档与候选验收；不执行数据迁移、备份或回滚。
# 入口：接受 verify-candidate 的全部参数，必须显式提供预期来源身份。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/release_pipeline_helpers.py" verify-candidate "$@"
echo "not-claimed: 跨版本升级、回滚、迁移及同版本备份恢复均未执行。"
