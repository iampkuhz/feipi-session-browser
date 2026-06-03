#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
按单个文件统计代码行数，并按粗略代码行数从高到低排序。
跳过常见非代码文件、依赖目录、构建产物、缓存目录。
"""

from pathlib import Path
from collections import namedtuple
import argparse

# 需跳过的目录
SKIP_DIRS = {
    ".git", ".github", ".idea", ".vscode", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", "node_modules", "dist", "build",
    "target", "coverage", ".next", ".nuxt", ".turbo", ".cache",
}

# 需跳过的文件扩展名
SKIP_EXTS = {
    ".md", ".mdx", ".txt", ".rst", ".pdf", ".doc", ".docx",
    ".ppt", ".pptx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".mp4", ".mov", ".mp3", ".wav", ".ttf", ".otf", ".woff", ".woff2",
    ".jsonl", ".csv", ".tsv", ".sqlite", ".db", ".log", ".lock",
    ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
    ".pyc", ".pyo", ".so", ".dylib", ".dll",
}

# 统计的代码文件扩展名
CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".vue", ".svelte", ".html", ".css", ".scss", ".sass", ".less",
    ".sh", ".bash", ".zsh", ".fish",
    ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".sql", ".rs", ".go", ".java", ".kt", ".kts", ".c", ".h",
    ".cpp", ".hpp", ".cc", ".cs", ".rb", ".php", ".swift", ".sol",
}


def should_skip_file(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    if path.suffix.lower() in SKIP_EXTS:
        return True
    if path.suffix.lower() not in CODE_EXTS:
        return True
    return False


def count_lines(path: Path) -> int:
    """
    返回粗略代码行数：非空、非单行注释
    """
    code_lines = 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith(("#", "//", "--")):
                    continue
                code_lines += 1
    except Exception as e:
        print(f"[WARN] 跳过文件 {path}: {e}")
    return code_lines


def scan_repo(root: Path):
    FileStat = namedtuple("FileStat", ["path", "lines"])
    stats = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip_file(path):
            continue

        code_lines = count_lines(path)
        stats.append(FileStat(path=path.relative_to(root), lines=code_lines))

    # 按代码行数排序，从高到低
    stats.sort(key=lambda x: x.lines, reverse=True)

    print(f"{'代码行数':>8}  {'文件路径'}")
    print("-" * 60)
    for stat in stats:
        print(f"{stat.lines:8}  {stat.path}")


def main():
    parser = argparse.ArgumentParser(description="按文件统计代码行数，并按行数排序")
    parser.add_argument("repo", help="仓库路径，例如 . 或 /path/to/repo")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"路径不存在或不是目录: {root}")

    scan_repo(root)


if __name__ == "__main__":
    main()
