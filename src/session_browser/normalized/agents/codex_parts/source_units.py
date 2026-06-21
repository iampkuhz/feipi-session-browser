"""Codex normalized source unit helpers.

Source unit 是 Codex 归因链路的 normalized 边界: 这里记录可见来源, 统一
candidate 和稳定去重键. 调用点是 Codex normalized parser 产出 text 或 payload
片段时, 边界不跨 call 推断, mapping 层再决定它们如何解释 accounting fields.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

_BYTE_RANGE_ITEM_COUNT = 2


@dataclass(frozen=True)
class CodexSourceUnitDraft:
    """Codex source unit draft before call-scoped hydration.

    该草稿是 parser 与 catalog/call-scoped 输出之间的边界对象. 它在发现一个
    Codex text 或 payload 来源片段时创建, 不负责解释 accounting 字段.

    Attributes:
        origin_path: 原始 session 文件或虚拟来源路径.
        canonical_source_locator: 用于跨 call/catalog 去重的规范来源定位符.
        unit_type: 来源片段的 normalized 类型.
        candidate: 兼容 attribution_candidates 的候选分组.
        direction: request 或 response 方向.
        event_order: 事件在 session 内的稳定顺序.
        part_index: 片段在事件内的稳定顺序.
        byte_range: 片段在原始文本或稳定 payload 表示中的 UTF-8 byte 范围.
        text: 文本 source unit 的原文.
        payload: 结构化 source unit 的 JSON-safe payload.
        timestamp: 继承自事件的时间戳.
        label: 展示用标签.
        priority: 同 call 去重时的优先级.
        sub_source: 更细的子来源标记.
        source_candidate: 上游来源候选名称.
        diagnostics: parser 附带的诊断信息.
    """

    origin_path: str
    canonical_source_locator: str
    unit_type: str
    candidate: str
    direction: str
    event_order: int
    part_index: int = 0
    byte_range: tuple[int, int] = (0, 0)
    text: str = ''
    payload: Any = None
    timestamp: str = ''
    label: str = ''
    priority: int = 50
    sub_source: str = ''
    source_candidate: str = ''
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def text_unit(  # noqa: PLR0913
    *,
    origin_path: str,
    unit_type: str,
    candidate: str,
    direction: str,
    text: str,
    timestamp: str,
    event_order: int,
    part_index: int = 0,
    byte_range: tuple[int, int] | None = None,
    canonical_source_locator: str = '',
    label: str = '',
    priority: int = 50,
    sub_source: str = '',
    source_candidate: str = '',
) -> CodexSourceUnitDraft:
    """Create a Codex text source-unit draft.

    触发点是 parser 已经定位到明确文本边界时. 函数只补齐默认 locator 和 byte
    range, 不拆分文本, 不改写 candidate.

    Args:
        origin_path: 原始 session 文件或虚拟来源路径.
        unit_type: normalized source unit 类型.
        candidate: 兼容 attribution_candidates 的候选分组.
        direction: request 或 response 方向.
        text: 文本片段原文.
        timestamp: 继承自事件的时间戳.
        event_order: 事件在 session 内的稳定顺序.
        part_index: 片段在事件内的稳定顺序.
        byte_range: 可选 UTF-8 byte 范围. 缺省时覆盖完整 text.
        canonical_source_locator: 可选规范来源定位符.
        label: 可选展示标签.
        priority: 同 call 去重时的优先级.
        sub_source: 可选子来源标记.
        source_candidate: 可选上游来源候选名称.

    Returns:
        尚未绑定 call_id 的 Codex source-unit draft.
    """
    text_value = str(text or '')
    if byte_range is None:
        byte_range = (0, len(text_value.encode('utf-8')))
    return CodexSourceUnitDraft(
        origin_path=origin_path,
        canonical_source_locator=canonical_source_locator or origin_path,
        unit_type=unit_type,
        candidate=candidate,
        direction=direction,
        event_order=event_order,
        part_index=part_index,
        byte_range=byte_range,
        text=text_value,
        timestamp=timestamp,
        label=label or unit_type,
        priority=priority,
        sub_source=sub_source,
        source_candidate=source_candidate,
    )


def payload_unit(  # noqa: PLR0913
    *,
    origin_path: str,
    unit_type: str,
    candidate: str,
    direction: str,
    payload: object,
    timestamp: str,
    event_order: int,
    part_index: int = 0,
    canonical_source_locator: str = '',
    label: str = '',
    priority: int = 50,
    text: str = '',
    sub_source: str = '',
    source_candidate: str = '',
) -> CodexSourceUnitDraft:
    """Create a Codex payload source-unit draft.

    触发点是 parser 已经定位到结构化 payload 边界时. 函数以稳定 JSON 文本计算
    byte range, 但保留 JSON-safe payload 供后续展示和 catalog 使用.

    Args:
        origin_path: 原始 session 文件或虚拟来源路径.
        unit_type: normalized source unit 类型.
        candidate: 兼容 attribution_candidates 的候选分组.
        direction: request 或 response 方向.
        payload: 结构化 payload 值.
        timestamp: 继承自事件的时间戳.
        event_order: 事件在 session 内的稳定顺序.
        part_index: 片段在事件内的稳定顺序.
        canonical_source_locator: 可选规范来源定位符.
        label: 可选展示标签.
        priority: 同 call 去重时的优先级.
        text: 可选 preview 或伴随文本.
        sub_source: 可选子来源标记.
        source_candidate: 可选上游来源候选名称.

    Returns:
        尚未绑定 call_id 的 Codex source-unit draft.
    """
    payload_text = _stable_payload_text(payload)
    return CodexSourceUnitDraft(
        origin_path=origin_path,
        canonical_source_locator=canonical_source_locator or origin_path,
        unit_type=unit_type,
        candidate=candidate,
        direction=direction,
        event_order=event_order,
        part_index=part_index,
        byte_range=(0, len(payload_text.encode('utf-8'))),
        text=text,
        payload=_json_safe(payload),
        timestamp=timestamp,
        label=label or unit_type,
        priority=priority,
        sub_source=sub_source,
        source_candidate=source_candidate,
    )


def finalize_source_units(call_id: str, drafts: list[CodexSourceUnitDraft]) -> list[dict[str, Any]]:
    """Hydrate Codex drafts into call-scoped source_units.

    Args:
        call_id: 当前 call 的稳定标识.
        drafts: parser 在当前 call 中收集的 source-unit drafts.

    Returns:
        已绑定 call_id, 已按 dedupe_key 和 priority 去重的 source_units.
    """
    prepared = [_draft_to_unit(call_id, idx, draft) for idx, draft in enumerate(drafts)]
    by_key: dict[str, dict[str, Any]] = {}
    for unit in prepared:
        key = unit['dedupe_key']
        existing = by_key.get(key)
        if existing is None or _dedupe_rank(unit) > _dedupe_rank(existing):
            by_key[key] = unit
    return sorted(
        by_key.values(),
        key=lambda item: (
            int(item.get('event_order') or 0),
            int(item.get('part_index') or 0),
            item.get('unit_type', ''),
        ),
    )


def source_units_to_candidates(
    source_units: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Derive legacy-compatible attribution_candidates from source_units.

    Args:
        source_units: 已绑定 call_id 的 normalized source_units.

    Returns:
        按 direction 和 candidate 分组的 attribution candidate items.
    """
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {'request': {}, 'response': {}}
    for unit in source_units:
        direction = str(unit.get('direction') or '')
        if direction not in grouped:
            continue
        candidate = str(unit.get('candidate') or '')
        if not candidate:
            continue
        grouped[direction].setdefault(candidate, []).append(_candidate_item_from_unit(unit))
    return {side: {k: v for k, v in values.items() if v} for side, values in grouped.items()}


def draft_to_catalog_unit(draft: CodexSourceUnitDraft) -> dict[str, Any]:
    """Convert one Codex draft into a call-independent catalog entry.

    Args:
        draft: 尚未绑定 call_id 的 source-unit draft.

    Returns:
        可跨 call 复用的 catalog entry.
    """
    normalized_content = _normalized_content(draft)
    content_hash = hashlib.sha256(normalized_content.encode('utf-8')).hexdigest()
    start, end = draft.byte_range
    unit_key_basis = '|'.join(
        (
            draft.canonical_source_locator,
            draft.unit_type,
            draft.candidate,
            draft.direction,
            str(draft.event_order),
            str(draft.part_index),
            str(start),
            str(end),
            content_hash,
        )
    )
    unit: dict[str, Any] = {
        'unit_key': hashlib.sha256(unit_key_basis.encode('utf-8')).hexdigest(),
        'origin_path': draft.origin_path,
        'canonical_source_locator': draft.canonical_source_locator,
        'unit_type': draft.unit_type,
        'candidate': draft.candidate,
        'direction': draft.direction,
        'event_order': draft.event_order,
        'part_index': draft.part_index,
        'byte_range': [start, end],
        'content_hash': content_hash,
        'timestamp': draft.timestamp,
        'label': draft.label or draft.unit_type,
        'priority': draft.priority,
        'preview': _preview(draft.text if draft.text else normalized_content),
    }
    if draft.text:
        unit['text'] = draft.text
    if draft.payload not in (None, ''):
        unit['payload'] = _json_safe(draft.payload)
    if draft.sub_source:
        unit['sub_source'] = draft.sub_source
    if draft.source_candidate:
        unit['source_candidate'] = draft.source_candidate
    if draft.diagnostics:
        unit['diagnostics'] = list(draft.diagnostics)
    return unit


def hydrate_source_units(
    call_id: str,
    catalog_units: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Hydrate catalog entries into legacy call-scoped source_units.

    Args:
        call_id: 当前 call 的稳定标识.
        catalog_units: call-independent catalog entries.

    Returns:
        已绑定 call_id, 已按 dedupe_key 和 priority 去重的 source_units.
    """
    prepared = [
        _catalog_unit_to_call_unit(call_id, idx, unit) for idx, unit in enumerate(catalog_units)
    ]
    by_key: dict[str, dict[str, Any]] = {}
    for unit in prepared:
        key = unit['dedupe_key']
        existing = by_key.get(key)
        if existing is None or _dedupe_rank(unit) > _dedupe_rank(existing):
            by_key[key] = unit
    return sorted(
        by_key.values(),
        key=lambda item: (
            int(item.get('event_order') or 0),
            int(item.get('part_index') or 0),
            item.get('unit_type', ''),
        ),
    )


def _draft_to_unit(call_id: str, index: int, draft: CodexSourceUnitDraft) -> dict[str, Any]:
    """Build a call-scoped Codex source unit from a draft.

    Args:
        call_id: Stable call identifier.
        index: Draft position within the prepared call list.
        draft: Codex source-unit draft.

    Returns:
        Call-scoped source unit dictionary.
    """
    normalized_content = _normalized_content(draft)
    content_hash = hashlib.sha256(normalized_content.encode('utf-8')).hexdigest()
    start, end = draft.byte_range
    safe_origin = _safe_id_part(draft.origin_path)
    source_id = (
        f'{call_id}:{safe_origin}:{draft.event_order}:'
        f'{draft.part_index}:{draft.unit_type}:{start}-{end}:{index}'
    )
    dedupe_basis = '|'.join(
        (call_id, draft.canonical_source_locator, draft.unit_type, content_hash)
    )
    unit: dict[str, Any] = {
        'source_id': source_id,
        'dedupe_key': hashlib.sha256(dedupe_basis.encode('utf-8')).hexdigest(),
        'origin_path': draft.origin_path,
        'canonical_source_locator': draft.canonical_source_locator,
        'unit_type': draft.unit_type,
        'candidate': draft.candidate,
        'direction': draft.direction,
        'event_order': draft.event_order,
        'part_index': draft.part_index,
        'byte_range': [start, end],
        'content_hash': content_hash,
        'timestamp': draft.timestamp,
        'label': draft.label or draft.unit_type,
        'priority': draft.priority,
        'preview': _preview(draft.text if draft.text else normalized_content),
    }
    if draft.text:
        unit['text'] = draft.text
    if draft.payload not in (None, ''):
        unit['payload'] = _json_safe(draft.payload)
    if draft.sub_source:
        unit['sub_source'] = draft.sub_source
    if draft.source_candidate:
        unit['source_candidate'] = draft.source_candidate
    if draft.diagnostics:
        unit['diagnostics'] = list(draft.diagnostics)
    return unit


def _catalog_unit_to_call_unit(
    call_id: str, index: int, catalog_unit: dict[str, Any]
) -> dict[str, Any]:
    """Build a call-scoped Codex source unit from a catalog entry.

    Args:
        call_id: Stable call identifier.
        index: Catalog entry position within the prepared call list.
        catalog_unit: Call-independent catalog entry.

    Returns:
        Call-scoped source unit dictionary.
    """
    start, end = _byte_range(catalog_unit.get('byte_range'))
    safe_origin = _safe_id_part(str(catalog_unit.get('origin_path') or ''))
    unit_type = str(catalog_unit.get('unit_type') or '')
    event_order = int(catalog_unit.get('event_order') or 0)
    part_index = int(catalog_unit.get('part_index') or 0)
    content_hash = str(catalog_unit.get('content_hash') or '')
    canonical_source_locator = str(catalog_unit.get('canonical_source_locator') or '')
    source_id = (
        f'{call_id}:{safe_origin}:{event_order}:{part_index}:{unit_type}:{start}-{end}:{index}'
    )
    dedupe_basis = '|'.join((call_id, canonical_source_locator, unit_type, content_hash))
    unit: dict[str, Any] = {
        'source_id': source_id,
        'dedupe_key': hashlib.sha256(dedupe_basis.encode('utf-8')).hexdigest(),
        'origin_path': str(catalog_unit.get('origin_path') or ''),
        'canonical_source_locator': canonical_source_locator,
        'unit_type': unit_type,
        'candidate': str(catalog_unit.get('candidate') or ''),
        'direction': str(catalog_unit.get('direction') or ''),
        'event_order': event_order,
        'part_index': part_index,
        'byte_range': [start, end],
        'content_hash': content_hash,
        'timestamp': str(catalog_unit.get('timestamp') or ''),
        'label': str(catalog_unit.get('label') or unit_type),
        'priority': int(catalog_unit.get('priority') or 0),
        'preview': str(catalog_unit.get('preview') or ''),
    }
    if catalog_unit.get('text') is not None:
        unit['text'] = catalog_unit.get('text', '')
    if 'payload' in catalog_unit:
        unit['payload'] = catalog_unit.get('payload')
    if catalog_unit.get('sub_source'):
        unit['sub_source'] = catalog_unit.get('sub_source')
    if catalog_unit.get('source_candidate'):
        unit['source_candidate'] = catalog_unit.get('source_candidate')
    if catalog_unit.get('diagnostics'):
        unit['diagnostics'] = list(catalog_unit.get('diagnostics') or [])
    return unit


def _candidate_item_from_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Convert one source unit into a legacy candidate item.

    Args:
        unit: Source unit dictionary.

    Returns:
        Candidate item dictionary for legacy attribution output.
    """
    item = {
        'source': unit.get('origin_path', ''),
        'source_id': unit.get('source_id', ''),
        'unit_type': unit.get('unit_type', ''),
        'label': unit.get('label', ''),
        'event_order': unit.get('event_order', 0),
        'timestamp': unit.get('timestamp', ''),
        'preview': unit.get('preview', ''),
    }
    if unit.get('text') is not None:
        item['text'] = unit.get('text', '')
    if 'payload' in unit:
        item['payload'] = unit.get('payload')
    if unit.get('sub_source'):
        item['sub_source'] = unit.get('sub_source')
    if unit.get('source_candidate'):
        item['source_candidate'] = unit.get('source_candidate')
    return item


def _normalized_content(draft: CodexSourceUnitDraft) -> str:
    """Return the stable content string used for hashing a Codex draft.

    Args:
        draft: Codex source-unit draft.

    Returns:
        Whitespace-normalized text or stable payload text.
    """
    if draft.text:
        return re.sub(r'\s+', ' ', draft.text).strip()
    return _stable_payload_text(draft.payload)


def _stable_payload_text(payload: object) -> str:
    """Serialize payload into stable text for hashing and byte ranges.

    Args:
        payload: Payload value to serialize.

    Returns:
        Stable JSON text, string fallback, or an empty string.
    """
    if payload in (None, ''):
        return ''
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    except TypeError:
        return str(payload)


def _json_safe(value: object) -> object:
    """Return JSON-serializable data or a string fallback.

    Args:
        value: Value that may not be JSON serializable.

    Returns:
        Original value when JSON serializable, otherwise its string form.
    """
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _preview(text: str, limit: int = 240) -> str:
    """Return a compact whitespace-normalized preview.

    Args:
        text: Text used to build the preview.
        limit: Maximum preview length.

    Returns:
        Whitespace-normalized preview text.
    """
    value = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + '...'


def _safe_id_part(value: str) -> str:
    """Sanitize a value so it can be embedded in source_id.

    Args:
        value: Raw identifier segment.

    Returns:
        Safe identifier segment capped to the supported length.
    """
    return re.sub(r'[^A-Za-z0-9_.:-]+', '-', value or 'unknown')[:120]


def _dedupe_rank(unit: dict[str, Any]) -> tuple[int, int]:
    """Return priority tuple used when duplicate source units collide.

    Args:
        unit: Source unit dictionary with priority and event_order fields.

    Returns:
        Ranking tuple for duplicate resolution.
    """
    return (int(unit.get('priority') or 0), -int(unit.get('event_order') or 0))


def _byte_range(value: object) -> tuple[int, int]:
    """Normalize catalog byte_range values into a two-integer tuple.

    Args:
        value: Raw byte_range value from a catalog entry.

    Returns:
        Start and end offsets, or zeros when invalid.
    """
    if isinstance(value, (list, tuple)) and len(value) == _BYTE_RANGE_ITEM_COUNT:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return (0, 0)
    return (0, 0)
