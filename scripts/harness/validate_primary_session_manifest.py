#!/usr/bin/env python3
"""校验 primary session 机器可读契约清单。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.harness.primary_session import (  # noqa: E402
    MANIFEST_PATH,
    PrimarySessionValidationError,
    validate_manifest_file,
)


# 运行 primary session 清单校验命令。
def main(argv: list[str] | None = None) -> int:
    """参数：
        argv: 可选命令行参数列表。

    返回：
        进程退出码。
    """
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
    raise SystemExit(main())
