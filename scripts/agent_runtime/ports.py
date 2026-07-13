"""负责在进程持有 socket 期间分配并记录临时端口；不负责服务生命周期；由需要隔离端口的 Gate executor 调用。"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from scripts.agent_runtime.session.contract import resolve_runtime_root
from scripts.agent_runtime.storage import utc_now, write_json_atomic

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class PortAllocation:
    """持有已绑定 socket 与端口证据；关闭前端口不会被并发分配器复用。"""

    name: str
    port: int
    path: Path
    socket: socket.socket | None = None

    def close(self) -> None:
        """关闭保留 socket，将端口所有权明确交还操作系统。"""
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _root(repo_root: Path) -> Path:
    return resolve_runtime_root(repo_root) / 'ports'


def _run_id() -> str:
    return (
        os.environ.get('FEIPI_RUN_ID') or os.environ.get('FEIPI_SESSION_ID') or f'pid-{os.getpid()}'
    )


def reserve_port(repo_root: Path, name: str, *, hold_socket: bool = True) -> PortAllocation:
    """绑定回环地址的临时端口并原子记录证据，返回仍持有 socket 的分配对象。"""
    root = _root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind(('127.0.0.1', 0))
    port = int(sock.getsockname()[1])
    if not hold_socket:
        sock.close()
    run_id = _run_id()
    path = root / f'{run_id}-{name}.json'
    data: dict[str, Any] = {
        'schemaVersion': 1,
        'runId': run_id,
        'name': name,
        'host': '127.0.0.1',
        'port': port,
        'pid': os.getpid(),
        'allocatedAt': utc_now(),
    }
    write_json_atomic(path, data)
    return PortAllocation(name=name, port=port, path=path, socket=sock if hold_socket else None)
