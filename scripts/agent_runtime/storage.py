"""负责以属主校验和原子替换持久化运行时 JSON；不负责排他锁竞争；由 Session registry、lease 与端口分配器调用。"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class StorageError(RuntimeError):
    """表示属主、文件类型、原子写入或 JSON 结构不满足 Runtime 存储契约。"""

    pass


def utc_now() -> str:
    """返回统一 UTC 时间戳，供 Registry、lease 与审计证据排序。"""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def stable_hash(value: str | bytes) -> str:
    """对文本或字节计算稳定 SHA-256，供身份键与内容指纹复用。"""
    payload = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _owned_regular(path: Path, *, missing_ok: bool) -> os.stat_result | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise StorageError(f"refusing unsafe JSON path: {path}")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise StorageError(f"JSON path is not owned by current user: {path}")
    return metadata


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    """在属主私有目录写临时文件并 fsync 后原子替换目标，拒绝符号链接目标。"""
    from scripts.agent_runtime.session.contract import ensure_private_directory

    ensure_private_directory(path.parent)
    _owned_regular(path, missing_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(
        temp,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
        os.fsync(descriptor)
        os.replace(temp, path)
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """以 no-follow 和 inode 复核读取属主普通文件；缺失时复制返回调用者默认值。"""
    metadata = _owned_regular(path, missing_ok=default is not None)
    if metadata is None:
        return dict(default or {})
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise StorageError(f"JSON path changed during open: {path}")
        with os.fdopen(descriptor, encoding="utf-8", closefd=False) as handle:
            data = json.load(handle)
    finally:
        os.close(descriptor)
    if not isinstance(data, dict):
        raise StorageError(f"JSON path must contain an object: {path}")
    return data
