#!/usr/bin/env bash
# Release candidate 创建脚本 —— 非交互式生成发布 tag 并验证前置条件。
#
# 功能：
# 1. 验证 VERSION 文件存在且格式合法
# 2. 验证工作区干净（无未提交改动）
# 3. 验证本地 tag 不存在；不检查远程同步状态
# 4. 创建 release tag 并输出 candidate 元数据
#
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "用法: $0 <verify|create>" >&2
    exit 2
fi
ACTION="$1"
case "$ACTION" in
    verify|create) ;;
    *)
        echo "无效动作: $ACTION" >&2
        echo "用法: $0 <verify|create>" >&2
        exit 2
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "===== Release Candidate 创建 ====="
echo ""

# 阶段 1：验证 VERSION 文件
echo "--- 阶段 1：验证 VERSION 文件 ---"

VERSION_FILE="java/gradle/VERSION"
if [[ ! -f "$VERSION_FILE" ]]; then
    echo "FAIL: VERSION 文件不存在" >&2
    exit 1
fi

VERSION="$(cat "$VERSION_FILE")"
# 接受现有发布约定的 X.Y / X.Y.Z 及预发布后缀，不在此推导或改写版本。
if [[ ! "$VERSION" =~ ^([0-9]+\.[0-9]+(-[A-Za-z0-9._-]+)?|[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9._-]+)?)$ || "$VERSION" == *..* ]]; then
    echo "FAIL: VERSION 格式非法: $VERSION" >&2
    echo "期望格式: X.Y 或 X.Y.Z，例如 0.4 或 0.4.1-rc.1" >&2
    exit 1
fi

echo "  版本: $VERSION"
echo "  TAG:  v$VERSION"
echo ""

# 阶段 2：验证工作区干净
echo "--- 阶段 2：验证工作区状态 ---"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "FAIL: 工作区包含未提交改动：" >&2
    git status --porcelain >&2
    echo ""
    echo "请先提交所有改动；仅暂存仍不是干净工作区。" >&2
    exit 1
fi

echo "  PASS: 工作区干净"
echo ""

# 阶段 3：验证 tag 不存在
echo "--- 阶段 3：验证 tag 唯一性 ---"

TAG="v$VERSION"
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "FAIL: tag $TAG 已存在" >&2
    echo "请核对现有 tag 或更新 VERSION；本脚本不会删除 tag。" >&2
    exit 1
fi

echo "  PASS: tag $TAG 不存在"
echo ""

if [[ "$ACTION" == "create" ]]; then
    git tag -a "$TAG" -m "Release v$VERSION"
    echo "  PASS: 本地 tag $TAG 已创建；尚未推送或发布"
else
    echo "  PASS: 本地前置验证完成；未运行远端 Gate"
fi

printf '版本: %s\nTag: %s\nCommit: %s\n动作: %s\n' \
    "$VERSION" "$TAG" "$(git rev-parse --short=12 HEAD)" "$ACTION"
