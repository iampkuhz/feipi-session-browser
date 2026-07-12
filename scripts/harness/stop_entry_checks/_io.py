"""共享 I/O 工具：原子写入、时间戳。"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.harness.primary_session import ensure_private_directory


def utc_now() -> str:
    """返回当前 UTC 时间的 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    """以原子替换方式写入仅当前用户可访问的 JSON 文档。"""
    ensure_private_directory(path.parent)
    try:
        existing = path.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
            raise RuntimeError(f'refusing unsafe Stop state target: {path}')
        if hasattr(os, 'geteuid') and existing.st_uid != os.geteuid():
            raise RuntimeError(f'Stop state is not owned by current user: {path}')
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp')
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        payload = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()
        with os.fdopen(descriptor, 'wb', closefd=False) as handle:
            handle.write(payload)
            handle.flush()
        os.fsync(descriptor)
        os.replace(temporary, path)
    finally:
        os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
