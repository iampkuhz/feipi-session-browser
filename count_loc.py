#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统计仓库代码行数，默认跳过常见非代码文件、依赖目录、构建产物、缓存目录。

用法：
  python3 count_loc.py /path/to/repo
  python3 count_loc.py .
"""

from __future__ import annotations

import argparse
from pathlib import Path
from collections import defaultdict


# 跳过的目录名
SKIP_DIRS = {
    ".git",
    ".github",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
    ".pnpm-store",
    "site-packages",
}


# 跳过的文件名
SKIP_FILENAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
    "Cargo.lock",
}


# 跳过的扩展名：常见非代码、二进制、数据、图片、文档、锁文件等
SKIP_EXTS = {
    # 文档
    ".md",
    ".mdx",
    ".txt",
    ".rst",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",

    # 图片 / 字体 / 媒体
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",

    # 数据 / 生成物
    ".jsonl",
    ".csv",
    ".tsv",
    ".sqlite",
    ".db",
    ".log",
    ".lock",

    # 压缩包
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".rar",
    ".7z",

    # Python / Node 构建产物
    ".pyc",
    ".pyo",
    ".so",
    ".dylib",
    ".dll",
}


# 只统计这些代码扩展名；避免把未知类型误算进去
CODE_EXTS = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".vue",
    ".svelte",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".sh",
    ".bash",
    ".zsh",
    ".fish",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".sql",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".kts",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".sol",
}


def should_skip_file(path: Path) -> bool:
    if path.name in SKIP_FILENAMES:
        return True

    if path.suffix.lower() in SKIP_EXTS:
        return True

    if path.suffix.lower() not in CODE_EXTS:
        return True

    return False


def count_lines(path: Path) -> tuple[int, int]:
    """
    返回：
      total_lines: 总行数
      code_lines: 非空、非纯注释行数的粗略统计

    注意：
      code_lines 是粗略值，只处理常见单行注释。
    """
    total_lines = 0
    code_lines = 0

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                total_lines += 1
                stripped = line.strip()

                if not stripped:
                    continue

                # 粗略跳过常见单行注释
                if stripped.startswith(("#", "//", "--")):
                    continue

                code_lines += 1
    except Exception as e:
        print(f"[WARN] 读取失败，已跳过: {path} ({e})")

    return total_lines, code_lines


def scan_repo(root: Path) -> None:
    total_files = 0
    total_lines = 0
    total_code_lines = 0

    by_ext = defaultdict(lambda: {"files": 0, "lines": 0, "code_lines": 0})

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(root)

        # 跳过任意一级目录命中 SKIP_DIRS 的文件
        if any(part in SKIP_DIRS for part in rel.parts):
            continue

        if should_skip_file(path):
            continue

        lines, code_lines = count_lines(path)

        total_files += 1
        total_lines += lines
        total_code_lines += code_lines

        ext = path.suffix.lower() or "[no_ext]"
        by_ext[ext]["files"] += 1
        by_ext[ext]["lines"] += lines
        by_ext[ext]["code_lines"] += code_lines

    print("\n=== 仓库代码行数统计 ===")
    print(f"仓库路径: {root}")
    print(f"代码文件数: {total_files}")
    print(f"总行数: {total_lines}")
    print(f"粗略代码行数: {total_code_lines}")

    print("\n=== 按扩展名统计 ===")
    print(f"{'扩展名':<10} {'文件数':>8} {'总行数':>12} {'粗略代码行数':>14}")
    print("-" * 50)

    for ext, stat in sorted(by_ext.items(), key=lambda x: x[1]["lines"], reverse=True):
        print(
            f"{ext:<10} "
            f"{stat['files']:>8} "
            f"{stat['lines']:>12} "
            f"{stat['code_lines']:>14}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="统计仓库代码行数")
    parser.add_argument("repo", help="仓库路径，例如 . 或 /path/to/repo")
    args = parser.parse_args()

    root = Path(args.repo).resolve()

    if not root.exists():
        raise SystemExit(f"路径不存在: {root}")

    if not root.is_dir():
        raise SystemExit(f"不是目录: {root}")

    scan_repo(root)


if __name__ == "__main__":
    main()
