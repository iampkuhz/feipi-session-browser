#!/usr/bin/env python3
"""本模块负责校验 primary session 机器可读契约清单及其触发范围。

不负责修复被检查对象；由 Gate executor 或维护者命令行调用。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.checks._trigger import parse_changed_files, skip_if_not_triggered  # noqa: E402
from scripts.harness.primary_session import (  # noqa: E402
    MANIFEST_PATH,
    PrimarySessionValidationError,
    validate_manifest_file,
)

# 声明本脚本的触发模式：只有匹配的文件变更时才运行本检查。
TRIGGER_PATTERNS = [
    'data/**',
    'scripts/checks/check_primary_session_manifest.py',
]


def main(argv: list[str] | None = None) -> int:
    """校验默认或显式指定的清单，并返回稳定的命令行退出码。"""
    args = argv if argv is not None else sys.argv[1:]
    manifest = Path(args[0]) if args else ROOT / MANIFEST_PATH
    if not manifest.is_absolute():
        manifest = ROOT / manifest
    try:
        validate_manifest_file(manifest)
    except PrimarySessionValidationError as exc:
        print(f"[primarySessionManifest] FAIL: {exc}")
        return 1
    print("[primarySessionManifest] PASS")
    return 0


if __name__ == "__main__":
    # 自感知跳过：当变更文件不匹配触发模式时直接 SKIP。
    changed_files = None
    for i, arg in enumerate(sys.argv):
        if arg == '--changed-files' and i + 1 < len(sys.argv):
            changed_files = parse_changed_files(sys.argv[i + 1])
            break
    skip_if_not_triggered(changed_files, TRIGGER_PATTERNS)

    raise SystemExit(main([]))
