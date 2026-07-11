"""Run-scoped localhost port allocation records."""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.harness.primary_session import resolve_runtime_root


# 维护 utc now 函数行为。
def _utc_now() -> str:
    """参数：
        当前函数不接收参数。

    返回：
        UTC 时间字符串。
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class PortAllocation:
    name: str
    port: int
    path: Path
    socket: socket.socket | None = None

    # 维护 close 函数行为。
    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


# 维护 root 路径。
def _root(repo_root: Path) -> Path:
    """参数：
        repo_root: 仓库根目录。

    返回：
        shared runtime root 下的 ports 目录。
    """
    return resolve_runtime_root(repo_root) / "ports"


# 维护 run id 解析。
def _run_id() -> str:
    """参数：
        当前函数不接收参数。

    返回：
        当前 run id 或进程级 fallback id。
    """
    return os.environ.get("FEIPI_RUN_ID") or os.environ.get("FEIPI_SESSION_ID") or f"pid-{os.getpid()}"


# 维护 reserve port 函数行为。
def reserve_port(repo_root: Path, name: str, *, hold_socket: bool = True) -> PortAllocation:
    """参数：
        repo_root: 仓库根目录。
        name: 端口用途名称。
        hold_socket: 是否保留 socket 直到调用方启动服务前释放。

    返回：
        run-scoped 端口分配记录。
    """
    root = _root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    if not hold_socket:
        sock.close()
    run_id = _run_id()
    path = root / f"{run_id}-{name}.json"
    data: dict[str, Any] = {"schemaVersion": 1, "runId": run_id, "name": name, "host": "127.0.0.1", "port": port, "pid": os.getpid(), "allocatedAt": _utc_now()}
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return PortAllocation(name=name, port=port, path=path, socket=sock if hold_socket else None)


# 维护端口可用性检查。
def assert_port_available(port: int) -> bool:
    """参数：
        port: 待检查端口号。

    返回：
        本机 localhost 可 bind 时返回 true。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        sock.close()
    return True
