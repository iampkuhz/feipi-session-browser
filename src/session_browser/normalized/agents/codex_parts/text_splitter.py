"""Codex deterministic prompt text splitter."""

from __future__ import annotations

import re

from session_browser.normalized.agents.codex_parts.source_units import CodexSourceUnitDraft, text_unit

_PROJECT_FILES = ("AGENTS.md", ".codex/AGENTS.md", "CLAUDE.md", ".claude/CLAUDE.md")
_PROJECT_RE = re.compile(
    r"^# (?P<file>AGENTS\.md|\.codex/AGENTS\.md|CLAUDE\.md|\.claude/CLAUDE\.md) instructions for (?P<root>[^\n]+)\n\n<INSTRUCTIONS>[\s\S]*</INSTRUCTIONS>\s*$"
)

_TAG_RULES: tuple[tuple[str, str, str], ...] = (
    ("skills_instructions", "skills_instructions_block", "skill_definitions"),
    ("plugins_instructions", "plugins_instructions_block", "skill_definitions"),
    ("permissions instructions", "permissions_block", "runtime_context"),
    ("app-context", "app_context_block", "runtime_context"),
    ("collaboration_mode", "collaboration_mode_block", "runtime_context"),
    ("environment_context", "environment_context_block", "runtime_context"),
    ("INSTRUCTIONS", "visible_instructions_block", "system_instructions"),
)


def split_codex_prompt_text(
    *,
    text: str,
    origin_path: str,
    timestamp: str,
    event_order: int,
    direction: str = "request",
    part_index: int = 0,
    default_candidate: str | None = "system_instructions",
    default_unit_type: str = "prompt_plain_text",
    priority: int = 60,
) -> list[CodexSourceUnitDraft]:
    """按 Codex 文档的精确 wrapper/tag 规则拆分 prompt text。

    不做自然语言分类；未匹配的剩余文本只按容器默认 candidate 归类。
    """
    value = str(text or "")
    if not value.strip():
        return []

    project_match = _PROJECT_RE.fullmatch(value)
    if project_match:
        file_name = project_match.group("file")
        root = project_match.group("root").strip()
        locator = _project_locator(root, file_name)
        return [
            text_unit(
                origin_path=origin_path,
                canonical_source_locator=locator,
                unit_type="project_instruction_bundle",
                candidate="system_instructions",
                direction=direction,
                text=value,
                timestamp=timestamp,
                event_order=event_order,
                part_index=part_index,
                byte_range=(0, len(value.encode("utf-8"))),
                label=file_name,
                priority=priority,
            )
        ]

    matches = _find_known_blocks(value)
    units: list[CodexSourceUnitDraft] = []
    consumed: list[tuple[int, int]] = []
    for start, end, unit_type, candidate in matches:
        block = value[start:end]
        units.append(
            text_unit(
                origin_path=origin_path,
                unit_type=unit_type,
                candidate=candidate,
                direction=direction,
                text=block,
                timestamp=timestamp,
                event_order=event_order,
                part_index=part_index,
                byte_range=_char_to_byte_range(value, start, end),
                label=unit_type,
                priority=priority,
            )
        )
        consumed.append((start, end))

    if default_candidate:
        for idx, (start, end, chunk) in enumerate(_remaining_chunks(value, consumed), 1):
            if not chunk.strip():
                continue
            units.append(
                text_unit(
                    origin_path=origin_path,
                    unit_type=default_unit_type,
                    candidate=default_candidate,
                    direction=direction,
                    text=chunk,
                    timestamp=timestamp,
                    event_order=event_order,
                    part_index=part_index * 1000 + idx,
                    byte_range=_char_to_byte_range(value, start, end),
                    label=default_unit_type,
                    priority=priority - 1,
                )
            )

    if units:
        return units
    if default_candidate:
        return [
            text_unit(
                origin_path=origin_path,
                unit_type=default_unit_type,
                candidate=default_candidate,
                direction=direction,
                text=value,
                timestamp=timestamp,
                event_order=event_order,
                part_index=part_index,
                byte_range=(0, len(value.encode("utf-8"))),
                label=default_unit_type,
                priority=priority - 1,
            )
        ]
    return []


def _find_known_blocks(text: str) -> list[tuple[int, int, str, str]]:
    matches: list[tuple[int, int, str, str]] = []
    for tag, unit_type, candidate in _TAG_RULES:
        pattern = re.compile(rf"<{re.escape(tag)}>.*?</{re.escape(tag)}>", re.DOTALL)
        for match in pattern.finditer(text):
            start, end = match.span()
            if _overlaps(start, end, [(m[0], m[1]) for m in matches]):
                continue
            matches.append((start, end, unit_type, candidate))
    return sorted(matches, key=lambda item: item[0])


def _remaining_chunks(text: str, consumed: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    if not consumed:
        return [(0, len(text), text)]
    chunks: list[tuple[int, int, str]] = []
    cursor = 0
    for start, end in sorted(consumed):
        if start > cursor:
            chunks.append((cursor, start, text[cursor:start]))
        cursor = max(cursor, end)
    if cursor < len(text):
        chunks.append((cursor, len(text), text[cursor:]))
    return chunks


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < old_end and end > old_start for old_start, old_end in ranges)


def _char_to_byte_range(text: str, start: int, end: int) -> tuple[int, int]:
    return (len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8")))


def _project_locator(root: str, file_name: str) -> str:
    if not root:
        return file_name
    return f"{root.rstrip('/')}/{file_name}"
