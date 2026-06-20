"""Qoder normalized source unit 帮助函数。"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any


@dataclass(frozen=True)
class QoderSourceUnitDraft:
    """尚未绑定 call_id 的 Qoder source unit 草稿。"""

    origin_path: str
    canonical_source_locator: str
    unit_type: str
    candidate: str
    direction: str
    event_order: int
    part_index: int = 0
    byte_range: tuple[int, int] = (0, 0)
    text: str = ""
    payload: Any = None
    timestamp: str = ""
    label: str = ""
    priority: int = 50
    sub_source: str = ""
    source_candidate: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def text_unit(
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
    canonical_source_locator: str = "",
    label: str = "",
    priority: int = 50,
    sub_source: str = "",
    source_candidate: str = "",
) -> QoderSourceUnitDraft:
    """创建文本 source unit 草稿。"""
    text_value = str(text or "")
    if byte_range is None:
        byte_range = (0, len(text_value.encode("utf-8")))
    return QoderSourceUnitDraft(
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


def payload_unit(
    *,
    origin_path: str,
    unit_type: str,
    candidate: str,
    direction: str,
    payload: Any,
    timestamp: str,
    event_order: int,
    part_index: int = 0,
    canonical_source_locator: str = "",
    label: str = "",
    priority: int = 50,
    text: str = "",
    sub_source: str = "",
    source_candidate: str = "",
) -> QoderSourceUnitDraft:
    """创建结构化 payload source unit 草稿。"""
    payload_text = _stable_payload_text(payload)
    return QoderSourceUnitDraft(
        origin_path=origin_path,
        canonical_source_locator=canonical_source_locator or origin_path,
        unit_type=unit_type,
        candidate=candidate,
        direction=direction,
        payload=_json_safe(payload),
        event_order=event_order,
        part_index=part_index,
        byte_range=(0, len(payload_text.encode("utf-8"))),
        text=text,
        timestamp=timestamp,
        label=label or unit_type,
        priority=priority,
        sub_source=sub_source,
        source_candidate=source_candidate,
    )


def finalize_source_units(call_id: str, drafts: list[QoderSourceUnitDraft]) -> list[dict[str, Any]]:
    """绑定 call_id，并在单个 call 内做稳定去重。"""
    prepared = [_draft_to_unit(call_id, idx, draft) for idx, draft in enumerate(drafts)]
    by_key: dict[str, dict[str, Any]] = {}
    for unit in prepared:
        key = unit["dedupe_key"]
        existing = by_key.get(key)
        if existing is None or _dedupe_rank(unit) > _dedupe_rank(existing):
            by_key[key] = unit
    return sorted(
        by_key.values(),
        key=lambda item: (int(item.get("event_order") or 0), int(item.get("part_index") or 0), item.get("unit_type", "")),
    )


def source_units_to_candidates(source_units: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """由 source_units 派生兼容展示用 attribution_candidates。"""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {"request": {}, "response": {}}
    for unit in source_units:
        direction = str(unit.get("direction") or "")
        if direction not in grouped:
            continue
        candidate = str(unit.get("candidate") or "")
        if not candidate:
            continue
        grouped[direction].setdefault(candidate, []).append(_candidate_item_from_unit(unit))
    return {side: {k: v for k, v in values.items() if v} for side, values in grouped.items()}


def _draft_to_unit(call_id: str, index: int, draft: QoderSourceUnitDraft) -> dict[str, Any]:
    normalized_content = _normalized_content(draft)
    content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
    start, end = draft.byte_range
    safe_origin = _safe_id_part(draft.origin_path)
    source_id = f"{call_id}:{safe_origin}:{draft.event_order}:{draft.part_index}:{draft.unit_type}:{start}-{end}:{index}"
    dedupe_basis = "|".join((call_id, draft.canonical_source_locator, draft.unit_type, content_hash))
    unit: dict[str, Any] = {
        "source_id": source_id,
        "dedupe_key": hashlib.sha256(dedupe_basis.encode("utf-8")).hexdigest(),
        "origin_path": draft.origin_path,
        "canonical_source_locator": draft.canonical_source_locator,
        "unit_type": draft.unit_type,
        "candidate": draft.candidate,
        "direction": draft.direction,
        "event_order": draft.event_order,
        "part_index": draft.part_index,
        "byte_range": [start, end],
        "content_hash": content_hash,
        "timestamp": draft.timestamp,
        "label": draft.label or draft.unit_type,
        "priority": draft.priority,
        "preview": _preview(draft.text if draft.text else normalized_content),
    }
    if draft.text:
        unit["text"] = draft.text
    if draft.payload not in (None, ""):
        unit["payload"] = _json_safe(draft.payload)
    if draft.sub_source:
        unit["sub_source"] = draft.sub_source
    if draft.source_candidate:
        unit["source_candidate"] = draft.source_candidate
    if draft.diagnostics:
        unit["diagnostics"] = list(draft.diagnostics)
    return unit


def _candidate_item_from_unit(unit: dict[str, Any]) -> dict[str, Any]:
    item = {
        "source": unit.get("origin_path", ""),
        "source_id": unit.get("source_id", ""),
        "unit_type": unit.get("unit_type", ""),
        "label": unit.get("label", ""),
        "event_order": unit.get("event_order", 0),
        "timestamp": unit.get("timestamp", ""),
        "preview": unit.get("preview", ""),
    }
    if unit.get("text") is not None:
        item["text"] = unit.get("text", "")
    if "payload" in unit:
        item["payload"] = unit.get("payload")
    if unit.get("sub_source"):
        item["sub_source"] = unit.get("sub_source")
    if unit.get("source_candidate"):
        item["source_candidate"] = unit.get("source_candidate")
    return item


def _normalized_content(draft: QoderSourceUnitDraft) -> str:
    if draft.text:
        return re.sub(r"\s+", " ", draft.text).strip()
    return _stable_payload_text(draft.payload)


def _stable_payload_text(payload: Any) -> str:
    if payload in (None, ""):
        return ""
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return str(payload)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _preview(text: str, limit: int = 240) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _safe_id_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", value or "unknown")[:120]


def _dedupe_rank(unit: dict[str, Any]) -> tuple[int, int]:
    return (int(unit.get("priority") or 0), -int(unit.get("event_order") or 0))
