"""文件锁：互斥 acquire、fencing token 与 stale owner reclaim。"""

from __future__ import annotations

import json
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.harness.primary_session import ensure_private_directory
from scripts.harness.resource_lock import _pid_start_time, process_is_alive

from ._io import utc_now


@dataclass
class FileLock:
    """基于文件系统的排他锁，支持 stale owner 回收。"""

    path: Path
    owner: dict[str, Any]
    acquired: bool = False
    fencing_token: str = ''
    reclaimed_owner: dict[str, Any] = field(default_factory=dict)

    # 不跟随符号链接且不接受所有者变更地读取锁负载。
    def _read_payload(self) -> dict[str, Any]:
        """参数：
            当前函数没有输入参数。

        返回：
            当前函数的计算结果。
        """
        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            return {}
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return {}
        if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
            return {}
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0),
            )
        except OSError:
            return {}
        try:
            opened = os.fstat(descriptor)
            if opened.st_ino != metadata.st_ino or opened.st_dev != metadata.st_dev:
                return {}
            raw = os.read(descriptor, 64 * 1024)
        finally:
            os.close(descriptor)
        try:
            data = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # 尝试获取锁。
    def acquire(self) -> bool:
        """参数：
            当前函数没有输入参数。

        返回：
            当前函数的计算结果。
        """
        self._remove_stale()
        ensure_private_directory(self.path.parent)
        payload = dict(self.owner)
        self.fencing_token = uuid.uuid4().hex
        payload.update({
            'schemaVersion': 1,
            'pid': os.getpid(),
            'processStartTime': _pid_start_time(os.getpid()),
            'fencingToken': self.fencing_token,
            'createdAt': utc_now(),
            'heartbeatAt': utc_now(),
        })
        try:
            fd = os.open(
                str(self.path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0),
                0o600,
            )
        except FileExistsError:
            return False
        except OSError:
            return False
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        self.acquired = True
        return True

    # 释放锁（需 fencing token 匹配）。
    def release(self) -> bool:
        """参数：
            当前函数没有输入参数。

        返回：
            当前函数的计算结果。
        """
        if not self.acquired:
            return False
        released = False
        try:
            data = self._read_payload()
            if not isinstance(data, dict) or data.get('fencingToken') != self.fencing_token:
                return False
            for field_name in ('runId', 'sessionId', 'worktreeId'):
                if str(data.get(field_name) or '') != str(self.owner.get(field_name) or ''):
                    return False
            self.path.unlink()
            released = True
        except FileNotFoundError:
            pass
        finally:
            self.acquired = False
            self.fencing_token = ''
        return released

    # 回收已死亡 owner 的锁。
    def _remove_stale(self) -> None:
        data = self._read_payload()
        if not isinstance(data, dict) or not data:
            return
        for field_name in ('runId', 'sessionId', 'worktreeId'):
            expected = str(self.owner.get(field_name) or '')
            if not expected or str(data.get(field_name) or '') != expected:
                return
        pid = data.get('pid')
        started = str(data.get('processStartTime') or '')
        token = str(data.get('fencingToken') or '')
        if not isinstance(pid, int) or pid <= 0 or not started or not token:
            return
        if process_is_alive(pid, started):
            return
        try:
            metadata = self.path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                return
            if hasattr(os, 'geteuid') and metadata.st_uid != os.geteuid():
                return
            if time.time() - metadata.st_mtime <= 0:
                return
            self.path.unlink()
            self.reclaimed_owner = data
        except OSError:
            return
