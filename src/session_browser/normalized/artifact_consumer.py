"""只读 artifact consumer：统一验证 canonical path、meta、hash、schema/version 和 freshness。

本模块是 Python 侧对 normalized artifact 的唯一读取入口。
写入路径完全由 Java bridge 处理，consumer 不暴露任何 write/replace/create API。
验证只在跨进程/持久化边界执行，内部不重复计算。
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from session_browser.normalized.constants import NORMALIZED_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Typed 状态
# ---------------------------------------------------------------------------

class ArtifactStatus(enum.Enum):
    """Artifact 完整性分类状态。

    Consumer 在跨进程/持久化边界使用这些状态来描述 artifact 的完整性。
    内部读取不重复计算，状态判定只在边界验证时发生。
    """

    # artifact 文件或 sidecar meta 不存在
    MISSING = 'missing'
    # sidecar meta 与当前 source 不匹配（stale freshness）
    STALE = 'stale'
    # content hash 与 meta 中记录的不匹配
    CORRUPT = 'corrupt'
    # artifact 文件存在但内容为空或不完整
    INCOMPLETE = 'incomplete'
    # schema_version 不被当前 consumer 支持
    UNSUPPORTED_VERSION = 'unsupported_version'
    # artifact 完整且当前
    OK = 'ok'


# consumer 支持的 schema version 集合。当前只有一个版本。
_SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({NORMALIZED_SCHEMA_VERSION})

# 当前 generator version，与 artifacts.py 中的值保持一致。
_CURRENT_GENERATOR_VERSION = 'normalized-session-artifact.v6'

# artifact type 标识。
_ARTIFACT_TYPE = 'normalized_session_json'

# source mtime 比较容差。
_MTIME_TOLERANCE_SECONDS = 1e-6


# ---------------------------------------------------------------------------
# 验证结果
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactValidationResult:
    """跨进程/持久化边界的 artifact 验证结果。

    Attributes:
        status: 完整性分类状态。
        path: artifact canonical path（可能不存在）。
        meta_path: sidecar meta 路径。
        content_hash: 计算得到的 SHA-256，仅在 status 为 OK 时非空。
        schema_version: artifact 中记录的 schema version。
        detail: 人类可读的附加说明。
    """

    status: ArtifactStatus
    path: Path
    meta_path: Path
    content_hash: str = ''
    schema_version: str = ''
    detail: str = ''


# ---------------------------------------------------------------------------
# 只读 Consumer
# ---------------------------------------------------------------------------

class ArtifactConsumer:
    """Canonical artifact 只读 consumer。

    本类只暴露读取和验证 API，不提供任何写入、替换或创建操作。
    写入路径完全由 Java bridge (java_bridge.py) 处理。

    Usage::

        consumer = ArtifactConsumer(index_dir=Path('/path/to/index'))
        result = consumer.validate_artifact(
            session_key='claude_code:abc-123',
            source_path='/path/to/source.jsonl',
            source_mtime=1234567890.0,
        )
        if result.status == ArtifactStatus.OK:
            data = consumer.read_artifact(result.path)
    """

    def __init__(self, *, index_dir: Path) -> None:
        """初始化 consumer 配置。

        Args:
            index_dir: SQLite index 和 artifact tree 的根目录。
        """
        self._index_dir = Path(index_dir)

    # ---- 读取 API ----

    def read_artifact(self, path: str | Path) -> dict[str, Any]:
        """读取一个 normalized session JSON artifact。

        只解码 JSON object，不验证语义 schema，不修改 artifact。
        调用方应在读取前已通过 validate_artifact 确认状态为 OK。

        Args:
            path: normalized JSON artifact 的文件系统路径。

        Returns:
            解码后的 JSON object。

        Raises:
            ValueError: JSON 负载不是 object。
            FileNotFoundError: 文件不存在。
        """
        artifact_path = Path(path)
        with artifact_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError('normalized artifact 必须包含 JSON object')
        return data

    def read_artifact_safe(self, path: str | Path) -> dict[str, Any] | None:
        """安全读取 artifact，出错时返回 None 而非抛出异常。

        Args:
            path: normalized JSON artifact 的文件系统路径。

        Returns:
            解码后的 JSON object，或出错时返回 None。
        """
        try:
            return self.read_artifact(path)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def read_meta(self, artifact_path: str | Path) -> dict[str, Any]:
        """读取 artifact 的 sidecar metadata。

        Args:
            artifact_path: JSON artifact 路径。

        Returns:
            metadata object，缺失或无效时返回空 dict。
        """
        meta_path = _derive_meta_path(artifact_path)
        if not meta_path.exists():
            return {}
        try:
            with meta_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # ---- 路径 API ----

    def resolve_canonical_path(
        self,
        *,
        agent: str,
        session_id: str,
    ) -> Path:
        """计算 deterministic artifact canonical path。

        不执行任何 I/O，只根据 agent 和 session_id 计算路径。
        隐藏绝对用户路径，返回相对于 index_dir 的结构化路径。

        Args:
            agent: source adapter 名称。
            session_id: provider-local session 标识符。

        Returns:
            canonical artifact path。
        """
        safe_agent = _safe_path_component(agent)
        safe_session_id = _safe_path_component(session_id)
        return (
            self._index_dir
            / 'artifacts'
            / 'normalized-sessions'
            / safe_agent
            / f'{safe_session_id}.json'
        )

    # ---- 验证 API ----

    def validate_artifact(
        self,
        *,
        session_key: str,
        source_path: str,
        source_mtime: float,
    ) -> ArtifactValidationResult:
        """在跨进程/持久化边界验证 artifact 完整性。

        统一验证 canonical path、meta、hash、schema/version 和 freshness。
        内部不重复计算：只在边界调用时执行完整验证。

        Args:
            session_key: canonical ``agent:session_id`` key。
            source_path: source transcript 路径。
            source_mtime: source transcript 修改时间。

        Returns:
            验证结果，status 为 OK 时表示 artifact 完整且当前。
        """
        agent, session_id = _split_session_key(session_key)
        if not agent or not session_id:
            path = self._index_dir / 'artifacts' / 'normalized-sessions' / '_invalid_' / 'invalid.json'
            return ArtifactValidationResult(
                status=ArtifactStatus.MISSING,
                path=path,
                meta_path=_derive_meta_path(path),
                detail='无效的 session_key 格式',
            )

        path = self.resolve_canonical_path(agent=agent, session_id=session_id)
        meta_path = _derive_meta_path(path)

        # 检查文件存在性
        if not path.exists():
            return ArtifactValidationResult(
                status=ArtifactStatus.MISSING,
                path=path,
                meta_path=meta_path,
                detail='artifact 文件不存在',
            )

        # 检查 artifact 内容完整性
        try:
            with path.open('r', encoding='utf-8') as f:
                raw = f.read()
        except OSError:
            return ArtifactValidationResult(
                status=ArtifactStatus.CORRUPT,
                path=path,
                meta_path=meta_path,
                detail='无法读取 artifact 文件',
            )

        if not raw.strip():
            return ArtifactValidationResult(
                status=ArtifactStatus.INCOMPLETE,
                path=path,
                meta_path=meta_path,
                detail='artifact 文件内容为空',
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ArtifactValidationResult(
                status=ArtifactStatus.CORRUPT,
                path=path,
                meta_path=meta_path,
                detail='artifact JSON 解析失败',
            )

        if not isinstance(data, dict):
            return ArtifactValidationResult(
                status=ArtifactStatus.CORRUPT,
                path=path,
                meta_path=meta_path,
                detail='artifact 顶层不是 JSON object',
            )

        # 检查 schema version
        schema_version = str(data.get('schema_version') or '')
        if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            return ArtifactValidationResult(
                status=ArtifactStatus.UNSUPPORTED_VERSION,
                path=path,
                meta_path=meta_path,
                schema_version=schema_version,
                detail=f'不支持的 schema version: {schema_version}',
            )

        # 读取并验证 meta
        meta = self.read_meta(path)
        if not meta:
            return ArtifactValidationResult(
                status=ArtifactStatus.STALE,
                path=path,
                meta_path=meta_path,
                schema_version=schema_version,
                detail='sidecar meta 缺失或不可读',
            )

        # 验证 meta 字段一致性
        if not _meta_matches(
            meta,
            source_path=source_path,
            source_mtime=source_mtime,
        ):
            return ArtifactValidationResult(
                status=ArtifactStatus.STALE,
                path=path,
                meta_path=meta_path,
                schema_version=schema_version,
                detail='sidecar meta 与 source 不匹配',
            )

        # 验证 size 一致性
        recorded_size = int(meta.get('size_bytes') or 0)
        actual_size = path.stat().st_size
        if recorded_size != actual_size:
            return ArtifactValidationResult(
                status=ArtifactStatus.CORRUPT,
                path=path,
                meta_path=meta_path,
                schema_version=schema_version,
                detail=f'size 不匹配: meta={recorded_size}, actual={actual_size}',
            )

        # 计算并验证 content hash
        content_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        recorded_hash = str(meta.get('content_hash') or '')
        if recorded_hash and recorded_hash != content_hash:
            return ArtifactValidationResult(
                status=ArtifactStatus.CORRUPT,
                path=path,
                meta_path=meta_path,
                content_hash=content_hash,
                schema_version=schema_version,
                detail='content hash 不匹配',
            )

        return ArtifactValidationResult(
            status=ArtifactStatus.OK,
            path=path,
            meta_path=meta_path,
            content_hash=content_hash,
            schema_version=schema_version,
        )

    def find_current_artifact(
        self,
        *,
        session_key: str,
        source_path: str,
        source_mtime: float,
    ) -> Path | None:
        """查找当前有效的 normalized artifact，不写入任何状态。

        这是 validate_artifact 的便捷封装，只返回路径或 None。

        Args:
            session_key: canonical ``agent:session_id`` key。
            source_path: source transcript 路径。
            source_mtime: source transcript 修改时间。

        Returns:
            状态为 OK 的 artifact 路径，否则返回 None。
        """
        result = self.validate_artifact(
            session_key=session_key,
            source_path=source_path,
            source_mtime=source_mtime,
        )
        if result.status == ArtifactStatus.OK:
            return result.path
        return None

    # ---- 旧版本处理 ----

    def classify_legacy_artifact(
        self,
        path: str | Path,
    ) -> ArtifactStatus:
        """分类旧版本 artifact 的处理策略。

        不自动回退 Python 生产。调用方根据返回状态决定
        discard 或标记为需要迁移。

        Args:
            path: 待分类的 artifact 路径。

        Returns:
            分类状态。旧版本返回 UNSUPPORTED_VERSION，
            缺失返回 MISSING，损坏返回 CORRUPT。
        """
        artifact_path = Path(path)
        if not artifact_path.exists():
            return ArtifactStatus.MISSING

        try:
            with artifact_path.open('r', encoding='utf-8') as f:
                raw = f.read()
        except OSError:
            return ArtifactStatus.CORRUPT

        if not raw.strip():
            return ArtifactStatus.INCOMPLETE

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ArtifactStatus.CORRUPT

        if not isinstance(data, dict):
            return ArtifactStatus.CORRUPT

        schema_version = str(data.get('schema_version') or '')
        if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
            return ArtifactStatus.UNSUPPORTED_VERSION

        return ArtifactStatus.OK

    def should_discard_legacy(self, path: str | Path) -> bool:
        """判断旧版本 artifact 是否应被丢弃。

        不自动执行删除，只返回决策建议。
        不支持的版本和损坏的 artifact 应被丢弃。

        Args:
            path: 待判断的 artifact 路径。

        Returns:
            True 表示应丢弃，False 表示可保留或状态未知。
        """
        status = self.classify_legacy_artifact(path)
        return status in (
            ArtifactStatus.UNSUPPORTED_VERSION,
            ArtifactStatus.CORRUPT,
            ArtifactStatus.INCOMPLETE,
        )


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _derive_meta_path(artifact_path: str | Path) -> Path:
    """推导 artifact 的 sidecar meta 路径。

    Args:
        artifact_path: JSON artifact 路径。

    Returns:
        ``.json.meta.json`` 后缀的 sidecar 路径。
    """
    p = Path(artifact_path)
    return p.with_suffix(p.suffix + '.meta.json')


def _split_session_key(session_key: str) -> tuple[str, str]:
    """将 canonical session key 拆分为 (agent, session_id)。

    Args:
        session_key: 格式为 ``agent:session_id`` 的 key。

    Returns:
        ``(agent, session_id)``，格式错误时返回 ``('', '')``。
    """
    if ':' not in session_key:
        return '', ''
    agent, session_id = session_key.split(':', 1)
    return agent, session_id


def _safe_path_component(value: str) -> str:
    """将标识符清理为安全的 path component。

    Args:
        value: 原始 provider 标识符。

    Returns:
        路径安全的 component，最长 180 字符。
    """
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value or 'unknown')).strip('._-')
    return (safe or 'unknown')[:180]


def _meta_matches(
    meta: dict[str, Any],
    *,
    source_path: str,
    source_mtime: float,
) -> bool:
    """检查 sidecar meta 是否与 source transcript 匹配。

    验证 artifact_type、generator_version、source_path、source_mtime
    和 source_size 的一致性。

    Args:
        meta: 解码后的 sidecar meta。
        source_path: 期望的 source transcript 路径。
        source_mtime: 期望的 source transcript 修改时间。

    Returns:
        True 表示 meta 与 source 一致。
    """
    expected = {
        'artifact_type': _ARTIFACT_TYPE,
        'generator_version': _CURRENT_GENERATOR_VERSION,
        'schema_version': NORMALIZED_SCHEMA_VERSION,
        'source_path': source_path,
    }
    if not meta or any(meta.get(k) != v for k, v in expected.items()):
        return False

    try:
        if (
            abs(float(meta.get('source_mtime') or 0) - float(source_mtime or 0))
            > _MTIME_TOLERANCE_SECONDS
        ):
            return False
    except (TypeError, ValueError):
        return False

    if source_path:
        source = Path(source_path)
        if not source.exists():
            return False
        if int(meta.get('source_size') or 0) != source.stat().st_size:
            return False

    return True
