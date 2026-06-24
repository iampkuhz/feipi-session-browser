#!/usr/bin/env bash
# 发行包 SHA-256 checksum 生成与验证脚本。
# 输出 MANIFEST.SHA256 包含所有发行产物的 hash、文件名和大小，
# 供 release 发布和消费者验证使用。
#
# 用法：
#   scripts/release/generate-checksums.sh <dist-dir>
#   scripts/release/generate-checksums.sh <dist-dir> --verify
#
# <dist-dir> 包含 *.zip / *.tar.gz 发行文件的目录。
# --verify  读取目录中的 MANIFEST.SHA256 并逐一校验。
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "用法: $0 <dist-dir> [--verify]" >&2
    exit 1
fi

DIST_DIR="$1"
MODE="${2:-generate}"

if [[ ! -d "$DIST_DIR" ]]; then
    echo "错误: 目录不存在: $DIST_DIR" >&2
    exit 1
fi

MANIFEST_FILE="$DIST_DIR/MANIFEST.SHA256"

# 生成 SHA-256 manifest
generate_manifest() {
    local timestamp
    timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    {
        echo "# Feipi Session Browser Distribution Manifest"
        echo "# Generated: $timestamp"
        echo "# Format: SHA256  SIZE  FILENAME"
        echo "#"
    } > "$MANIFEST_FILE"

    local count=0
    for file in "$DIST_DIR"/*.zip "$DIST_DIR"/*.tar.gz; do
        [[ -f "$file" ]] || continue
        local basename
        basename="$(basename "$file")"
        local hash
        if command -v shasum >/dev/null 2>&1; then
            hash="$(shasum -a 256 "$file" | awk '{print $1}')"
        else
            hash="$(sha256sum "$file" | awk '{print $1}')"
        fi
        local size
        size="$(wc -c < "$file" | tr -d ' ')"
        echo "$hash  $size  $basename" >> "$MANIFEST_FILE"
        count=$((count + 1))
    done

    if [[ "$count" -eq 0 ]]; then
        echo "警告: 未找到发行文件 (*.zip / *.tar.gz)" >&2
        rm -f "$MANIFEST_FILE"
        exit 1
    fi

    echo "已生成 ${MANIFEST_FILE}（${count} 个文件）"
}

# 从 MANIFEST.SHA256 验证每个文件的 checksum
verify_manifest() {
    if [[ ! -f "$MANIFEST_FILE" ]]; then
        echo "错误: manifest 不存在: $MANIFEST_FILE" >&2
        exit 1
    fi

    local failures=0
    local checked=0

    while IFS= read -r line; do
        # 跳过注释和空行
        [[ "$line" =~ ^#.*$ || -z "${line// /}" ]] && continue

        local expected_hash expected_size filename
        expected_hash="$(echo "$line" | awk '{print $1}')"
        expected_size="$(echo "$line" | awk '{print $2}')"
        filename="$(echo "$line" | awk '{print $3}')"

        local filepath="$DIST_DIR/$filename"
        if [[ ! -f "$filepath" ]]; then
            echo "缺失: $filename" >&2
            failures=$((failures + 1))
            continue
        fi

        local actual_hash
        if command -v shasum >/dev/null 2>&1; then
            actual_hash="$(shasum -a 256 "$filepath" | awk '{print $1}')"
        else
            actual_hash="$(sha256sum "$filepath" | awk '{print $1}')"
        fi

        if [[ "$actual_hash" != "$expected_hash" ]]; then
            echo "校验失败: $filename (期望 $expected_hash, 实际 $actual_hash)" >&2
            failures=$((failures + 1))
        else
            checked=$((checked + 1))
        fi
    done < "$MANIFEST_FILE"

    if [[ "$failures" -gt 0 ]]; then
        echo "验证失败: $failures 个文件不通过" >&2
        exit 1
    fi

    echo "验证通过: $checked 个文件"
}

case "$MODE" in
    --verify)
        verify_manifest
        ;;
    generate|"")
        generate_manifest
        ;;
    *)
        echo "错误: 未知参数 '$MODE'，期望 --verify 或空" >&2
        exit 1
        ;;
esac
