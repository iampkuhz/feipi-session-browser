#!/usr/bin/env bash
# Release candidate 创建脚本 —— 非交互式生成发布 tag 并验证前置条件。
#
# 功能：
# 1. 验证 VERSION 文件存在且格式合法
# 2. 验证工作区干净（无未提交改动）
# 3. 验证当前分支与远程同步
# 4. 创建 release tag 并输出 candidate 元数据
#
# 用法：
#   scripts/release/create-release-candidate.sh [--dry-run]
#
# 参数：
#   --dry-run  只验证不创建 tag
set -euo pipefail

DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "未知参数: $1" >&2
            echo "用法: $0 [--dry-run]" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

echo "===== Release Candidate 创建 ====="
echo ""

# ============================================================
# 阶段 1：验证 VERSION 文件
# ============================================================
echo "--- 阶段 1：验证 VERSION 文件 ---"

VERSION_FILE="VERSION"
if [[ ! -f "$VERSION_FILE" ]]; then
    echo "FAIL: VERSION 文件不存在" >&2
    exit 1
fi

VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [[ -z "$VERSION" ]]; then
    echo "FAIL: VERSION 文件为空" >&2
    exit 1
fi

# 验证版本格式：X.Y 或 X.Y.Z，可选 -rc.N / -alpha.N / -beta.N 后缀
if [[ ! "$VERSION" =~ ^([0-9]+\.[0-9]+(-[A-Za-z0-9._-]+)?|[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9._-]+)?)$ ]]; then
    echo "FAIL: VERSION 格式非法: $VERSION" >&2
    echo "期望格式: X.Y 或 X.Y.Z，例如 0.4 或 0.4.1-rc.1" >&2
    exit 1
fi

echo "  版本: $VERSION"
echo "  TAG:  v$VERSION"
echo ""

# ============================================================
# 阶段 2：验证工作区干净
# ============================================================
echo "--- 阶段 2：验证工作区状态 ---"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "FAIL: 工作区包含未提交改动：" >&2
    git status --porcelain >&2
    echo ""
    echo "请先提交或暂存所有改动后再创建 release candidate。" >&2
    exit 1
fi

echo "  PASS: 工作区干净"
echo ""

# ============================================================
# 阶段 3：验证 tag 不存在
# ============================================================
echo "--- 阶段 3：验证 tag 唯一性 ---"

TAG="v$VERSION"
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "FAIL: tag $TAG 已存在" >&2
    echo "请使用 git tag -d $TAG 删除后重试，或更新 VERSION 文件。" >&2
    exit 1
fi

echo "  PASS: tag $TAG 不存在"
echo ""

# ============================================================
# 阶段 4：验证 Gradle 构建
# ============================================================
echo "--- 阶段 4：验证构建 ---"

if ! ./gradlew check --no-daemon --quiet 2>&1; then
    echo "FAIL: ./gradlew check 失败" >&2
    exit 1
fi

echo "  PASS: ./gradlew check 通过"
echo ""

# ============================================================
# 阶段 5：创建 tag
# ============================================================
echo "--- 阶段 5：创建 release tag ---"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  DRY-RUN: 跳过 tag 创建"
    echo ""
    echo "===== Candidate 元数据 ====="
    echo "版本: $VERSION"
    echo "Tag: $TAG"
    echo "Commit: $(git rev-parse --short=12 HEAD)"
    echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
    echo "模式: dry-run"
else
    git tag -a "$TAG" -m "Release v$VERSION"
    echo "  PASS: tag $TAG 已创建"
    echo ""
    echo "===== Candidate 元数据 ====="
    echo "版本: $VERSION"
    echo "Tag: $TAG"
    echo "Commit: $(git rev-parse --short=12 HEAD)"
    echo "Branch: $(git rev-parse --abbrev-ref HEAD)"
    echo "模式: release"
    echo ""
    echo "下一步: git push origin $TAG"
fi
