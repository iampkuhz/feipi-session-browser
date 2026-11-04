#!/usr/bin/env bash
# 职责：生成或严格验证发行归档清单；不构建、不发布。
# 入口：generate-checksums.sh <dist-dir> [--verify]，兼容系统旧版 Bash。
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 || ( $# -eq 2 && "$2" != "--verify" ) ]]; then
    echo "用法: $0 <dist-dir> [--verify]" >&2
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$SCRIPT_DIR/release_pipeline_helpers.py" checksums --dist-dir "$@"
