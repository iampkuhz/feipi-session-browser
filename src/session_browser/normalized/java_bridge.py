"""Java 进程桥：通过 stdin/stdout NDJSON 协议调用 Java batch 生产 normalized artifact。

一个 scan 只启动一个 JVM。bridge 不提供 Python fallback：Java 不可用时必须明确失败。
stdout 每行严格可解析，非 NDJSON 行视为 protocol fatal。
"""

from __future__ import annotations

import enum
import json
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Java batch 协议版本，必须与 NormalizedBatchCommand.PROTOCOL_VERSION 一致。
_PROTOCOL_VERSION = '1.0'
_PROTOCOL_NAME = 'normalized-batch'


class BridgeError(Exception):
    """bridge 不可恢复错误的基类。"""


class JavaNotAvailableError(BridgeError):
    """Java launcher 不存在或无法启动。"""


class ProtocolFatalError(BridgeError):
    """stdout 出现不可解析的行，协议中断。"""


class BridgeTimeoutError(BridgeError):
    """Java 进程超时。"""


class BridgeCancelledError(BridgeError):
    """bridge 被外部取消。"""


class ResultStatus(enum.Enum):
    """Java batch 单条结果的分类状态。"""

    WRITTEN = 'WRITTEN'
    UNCHANGED = 'UNCHANGED'
    RETRYABLE = 'RETRYABLE'
    FAILED = 'FAILED'
    PROTOCOL_FATAL = 'PROTOCOL_FATAL'


@dataclass(frozen=True)
class BatchResult:
    """单条 Java batch 结果。

    Attributes:
        request_id: 请求标识，与发送时的 id 对应。
        status: 结果分类。
        session_key: 会话标识，成功时有值。
        artifact_path: 生成的 artifact 路径，WRITTEN 时有值。
        content_hash: data 文件 SHA-256，WRITTEN 时有值。
        error: 错误消息，FAILED/RETRYABLE 时有值。
    """

    request_id: str
    status: ResultStatus
    session_key: str = ''
    artifact_path: str = ''
    content_hash: str = ''
    error: str = ''


@dataclass(frozen=True)
class BatchSummary:
    """Java batch 结束摘要。

    Attributes:
        total: 已处理的请求总数。
        written: 成功写入的数量。
        unchanged: 未变更的数量。
        failed: 失败的数量。
    """

    total: int = 0
    written: int = 0
    unchanged: int = 0
    failed: int = 0


@dataclass
class _BatchRequest:
    """待发送给 Java 的单条请求。

    Attributes:
        request_id: 请求标识。
        source_id: 源标识，如 'claude'、'codex'、'qoder'。
        root_path: 会话数据根目录路径。
    """

    request_id: str
    source_id: str
    root_path: str


def resolve_java_launcher() -> Path:
    """定位 Java app-cli 启动脚本。

    按以下优先级查找：
    1. 环境变量 ``SESSION_BROWSER_JAVA_CLI`` 指定的路径
    2. 仓库内 ``java/app-cli/build/install/app-cli/bin/app-cli``
    3. PATH 中的 ``session-browser-java``

    Returns:
        可执行的 launcher 路径。

    Raises:
        JavaNotAvailableError: 找不到可用的 launcher。
    """
    import os

    # 1. 显式环境变量
    env_path = os.environ.get('SESSION_BROWSER_JAVA_CLI', '').strip()
    if env_path:
        p = Path(env_path)
        if p.is_file() and os.access(p, os.X_OK):
            return p
        raise JavaNotAvailableError(
            f'SESSION_BROWSER_JAVA_CLI 指向不可用路径: {env_path}'
        )

    # 2. 仓库内 installDist 产物
    repo_root = _find_repo_root()
    if repo_root is not None:
        install_script = (
            repo_root
            / 'java'
            / 'app-cli'
            / 'build'
            / 'install'
            / 'app-cli'
            / 'bin'
            / 'app-cli'
        )
        if install_script.is_file() and os.access(install_script, os.X_OK):
            return install_script

    # 3. PATH 查找
    import shutil

    system_path = shutil.which('session-browser-java')
    if system_path:
        return Path(system_path)

    raise JavaNotAvailableError(
        'Java launcher 不可用。请运行 ./gradlew :java:app-cli:installDist '
        '或设置 SESSION_BROWSER_JAVA_CLI 环境变量'
    )


def _find_repo_root() -> Path | None:
    """从当前文件位置向上查找仓库根目录。

    Returns:
        包含 ``java/app-cli`` 的目录，找不到时返回 ``None``。
    """
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / 'java' / 'app-cli').is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


class JavaBatchBridge:
    """管理一个 JVM 进程的批量归一化 bridge。

    一个 scan 只创建一个实例，通过同一进程处理所有请求。
    不提供 Python fallback：Java 不可用时抛出异常。

    Usage::

        bridge = JavaBatchBridge(output_dir=Path('/path/to/output'))
        try:
            bridge.start()
            for req_id, source_id, root_path in requests:
                bridge.submit(req_id, source_id, root_path)
            results, summary = bridge.finish()
        finally:
            bridge.close()
    """

    def __init__(
        self,
        *,
        output_dir: Path,
        timeout_seconds: float = 300.0,
        launcher: Path | None = None,
    ) -> None:
        """初始化 bridge 配置。

        Args:
            output_dir: Java batch 写入 artifact 的目录。
            timeout_seconds: 单个请求的超时秒数。
            launcher: 可选的 launcher 路径，为 None 时自动解析。
        """
        self._output_dir = output_dir
        self._timeout_seconds = timeout_seconds
        self._launcher = launcher
        self._process: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._results: list[BatchResult] = []
        self._summary: BatchSummary = BatchSummary()
        self._header_sent = False
        self._pending_count = 0
        self._cancelled = False
        self._protocol_broken = False

    @property
    def is_started(self) -> bool:
        """进程是否已启动。"""
        return self._process is not None

    def start(self) -> None:
        """启动 Java 进程。

        Raises:
            JavaNotAvailableError: launcher 不可用。
            BridgeError: 进程启动失败。
        """
        if self._process is not None:
            return
        if self._launcher is None:
            self._launcher = resolve_java_launcher()

        cmd = [
            str(self._launcher),
            'normalized-batch',
            '--output-dir',
            str(self._output_dir),
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
            )
        except FileNotFoundError as e:
            raise JavaNotAvailableError(f'Java launcher 启动失败: {e}') from e
        except OSError as e:
            raise BridgeError(f'Java 进程启动失败: {e}') from e

        # 异步 drain stderr，避免 pipe buffer 满阻塞
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            daemon=True,
        )
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        """异步读取 stderr 并记录为日志。"""
        if self._process is None or self._process.stderr is None:
            return
        try:
            for line in self._process.stderr:
                stripped = line.rstrip('\n')
                self._stderr_lines.append(stripped)
                logger.debug('java-batch stderr: %s', stripped)
        except (OSError, ValueError):
            pass

    def submit(self, request_id: str, source_id: str, root_path: str) -> None:
        """向 Java 进程提交一条归一化请求。

        Args:
            request_id: 请求标识。
            source_id: 源标识，如 'claude'、'codex'、'qoder'。
            root_path: 会话数据根目录路径。

        Raises:
            BridgeError: 进程未启动或协议已中断。
        """
        if self._cancelled:
            raise BridgeCancelledError('bridge 已被取消')
        if self._process is None:
            raise BridgeError('Java 进程未启动，请先调用 start()')
        if self._protocol_broken:
            raise ProtocolFatalError('协议已中断，无法继续提交')
        if self._process.stdin is None:
            raise BridgeError('stdin 不可用')

        # 首条请求前发送协议头（当前 Java 端不需要显式 header，
        # 但保留用于未来协议扩展）
        line = json.dumps(
            {
                'requestId': request_id,
                'sourceId': source_id,
                'rootPath': root_path,
            },
            ensure_ascii=False,
        )
        try:
            self._process.stdin.write(line + '\n')
            self._process.stdin.flush()
        except BrokenPipeError as e:
            self._protocol_broken = True
            raise BridgeError(f'Java stdin broken: {e}') from e
        except OSError as e:
            self._protocol_broken = True
            raise BridgeError(f'Java stdin 写入失败: {e}') from e

        self._pending_count += 1

    def finish(self) -> tuple[list[BatchResult], BatchSummary]:
        """关闭 stdin，读取所有结果并等待进程退出。

        Returns:
            ``(results, summary)`` 结果列表和摘要。

        Raises:
            ProtocolFatalError: stdout 出现不可解析的行。
            BridgeTimeoutError: 进程超时。
        """
        if self._cancelled:
            raise BridgeCancelledError('bridge 已被取消')
        if self._process is None:
            raise BridgeError('Java 进程未启动')
        if self._protocol_broken:
            raise ProtocolFatalError('协议已中断')

        # 关闭 stdin 通知 Java 端输入结束
        if self._process.stdin is not None:
            try:
                self._process.stdin.close()
            except OSError:
                pass

        # 读取 stdout 所有行
        if self._process.stdout is not None:
            self._read_results()

        # 等待进程退出
        try:
            exit_code = self._process.wait(timeout=self._timeout_seconds)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)
            raise BridgeTimeoutError(
                f'Java 进程超时 ({self._timeout_seconds}s)'
            )

        if exit_code != 0 and not self._results:
            raise BridgeError(
                f'Java 进程异常退出 (exit={exit_code})，无结果输出'
            )

        # 等待 stderr drain 完成
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=5)

        return self._results, self._summary

    def _read_results(self) -> None:
        """从 stdout 逐行读取 NDJSON 结果。

        Raises:
            ProtocolFatalError: 非 NDJSON 行或未知协议类型。
        """
        if self._process is None or self._process.stdout is None:
            return

        header_seen = False
        for line in self._process.stdout:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as e:
                self._protocol_broken = True
                raise ProtocolFatalError(
                    f'stdout 非 NDJSON 行: {stripped[:200]!r}: {e}'
                ) from e

            if not isinstance(obj, dict):
                self._protocol_broken = True
                raise ProtocolFatalError(
                    f'stdout 非 JSON object: {stripped[:200]!r}'
                )

            line_type = obj.get('type') or obj.get('protocol')

            # 协议版本头
            if line_type == 'protocol' or (
                obj.get('protocol') == _PROTOCOL_NAME
            ):
                version = obj.get('version', '')
                if version != _PROTOCOL_VERSION:
                    logger.warning(
                        'Java batch 协议版本不匹配: 期望 %s, 收到 %s',
                        _PROTOCOL_VERSION,
                        version,
                    )
                header_seen = True
                continue

            # 请求回显
            if line_type == 'request':
                continue

            # 候选项结果
            if line_type is None and 'requestId' in obj:
                result = self._parse_result(obj)
                self._results.append(result)
                continue

            # 结束摘要
            if line_type == 'end':
                self._summary = BatchSummary(
                    total=obj.get('totalRequests', 0),
                    written=obj.get('written', 0),
                    unchanged=obj.get('unchanged', 0),
                    failed=obj.get('failed', 0),
                )
                continue

            # BatchOutputRecord（无 type 字段但有 status 字段）
            if 'status' in obj and 'requestId' in obj:
                result = self._parse_result(obj)
                self._results.append(result)
                continue

            # 未知行类型
            logger.debug('忽略未知协议行: %s', stripped[:200])

    def _parse_result(self, obj: dict[str, Any]) -> BatchResult:
        """将 Java BatchOutputRecord JSON 解析为 typed result。

        Args:
            obj: 从 stdout 读取的 JSON object。

        Returns:
            分类后的 BatchResult。
        """
        request_id = str(obj.get('requestId', ''))
        session_key = str(obj.get('sessionKey', ''))
        java_status = str(obj.get('status', ''))
        artifact_path = str(obj.get('artifactPath', '') or '')
        error = str(obj.get('error', '') or '')
        content_hash = str(obj.get('contentHash', '') or '')

        status = self._map_java_status(java_status, artifact_path)

        return BatchResult(
            request_id=request_id,
            status=status,
            session_key=session_key,
            artifact_path=artifact_path,
            content_hash=content_hash,
            error=error,
        )

    @staticmethod
    def _map_java_status(java_status: str, artifact_path: str) -> ResultStatus:
        """将 Java 端 status 字符串映射为 typed ResultStatus。

        Java 端使用 'success'、'error'、'skipped' 三种状态。
        bridge 将其映射为更细粒度的 WRITTEN/UNCHANGED/RETRYABLE/FAILED。

        Args:
            java_status: Java BatchOutputRecord 的 status 字段。
            artifact_path: artifact 路径，用于区分 WRITTEN 和 UNCHANGED。

        Returns:
            分类后的 ResultStatus。
        """
        if java_status == 'success' and artifact_path:
            return ResultStatus.WRITTEN
        if java_status == 'success' and not artifact_path:
            return ResultStatus.UNCHANGED
        if java_status == 'skipped':
            return ResultStatus.UNCHANGED
        if java_status == 'error':
            return ResultStatus.FAILED
        # 未知状态默认为 FAILED
        return ResultStatus.FAILED

    def cancel(self) -> None:
        """取消 bridge，终止 Java 进程。"""
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.kill()
            except OSError:
                pass

    def close(self) -> None:
        """确保 Java 进程已终止并释放资源。"""
        if self._process is not None:
            try:
                if self._process.poll() is None:
                    self._process.kill()
                    self._process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                # 关闭所有 pipe
                for pipe in (
                    self._process.stdin,
                    self._process.stdout,
                    self._process.stderr,
                ):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except OSError:
                            pass
                self._process = None

    def __enter__(self) -> JavaBatchBridge:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def run_batch(
    requests: list[tuple[str, str, str]],
    *,
    output_dir: Path,
    timeout_seconds: float = 300.0,
    launcher: Path | None = None,
) -> tuple[list[BatchResult], BatchSummary]:
    """一次性运行 Java batch 的便捷函数。

    一个 scan 调用一次，N 个请求共享一个 JVM。

    Args:
        requests: ``(request_id, source_id, root_path)`` 元组列表。
        output_dir: Java batch 写入 artifact 的目录。
        timeout_seconds: 超时秒数。
        launcher: 可选的 launcher 路径。

    Returns:
        ``(results, summary)`` 结果列表和摘要。

    Raises:
        JavaNotAvailableError: Java launcher 不可用（不提供 fallback）。
        ProtocolFatalError: stdout 协议中断。
        BridgeTimeoutError: 超时。
    """
    bridge = JavaBatchBridge(
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        launcher=launcher,
    )
    try:
        bridge.start()
        for request_id, source_id, root_path in requests:
            bridge.submit(request_id, source_id, root_path)
        return bridge.finish()
    except Exception:
        bridge.cancel()
        raise
    finally:
        bridge.close()
