"""Codex prompt text splitter for normalized source units.

该模块只处理 Codex prompt 中可确定的 wrapper 和 tag 边界. 它在 normalized
Codex parser 读取 request/response 文本片段时触发, 不做自然语言分类, 也不跨越
当前 text part 推断来源.
"""

from __future__ import annotations

import re

from session_browser.normalized.agents.codex_parts.source_units import (
    CodexSourceUnitDraft,
    text_unit,
)

_PROJECT_FILES = ('AGENTS.md', '.codex/AGENTS.md', 'CLAUDE.md', '.claude/CLAUDE.md')
_PROJECT_RE = re.compile(
    r'^# (?P<file>AGENTS\.md|\.codex/AGENTS\.md|CLAUDE\.md|\.claude/CLAUDE\.md) '
    r'instructions for (?P<root>[^\n]+)\n\n<INSTRUCTIONS>[\s\S]*</INSTRUCTIONS>\s*$'
)

_TAG_RULES: tuple[tuple[str, str, str], ...] = (
    ('skills_instructions', 'skills_instructions_block', 'skill_definitions'),
    ('plugins_instructions', 'plugins_instructions_block', 'skill_definitions'),
    ('permissions instructions', 'permissions_block', 'runtime_context'),
    ('app-context', 'app_context_block', 'runtime_context'),
    ('collaboration_mode', 'collaboration_mode_block', 'runtime_context'),
    ('environment_context', 'environment_context_block', 'runtime_context'),
    ('subagent_notification', 'subagent_notification', 'tool_results'),
    ('INSTRUCTIONS', 'visible_instructions_block', 'system_instructions'),
)


def split_codex_prompt_text(  # noqa: PLR0913
    *,
    text: str,
    origin_path: str,
    timestamp: str,
    event_order: int,
    direction: str = 'request',
    part_index: int = 0,
    default_candidate: str | None = 'system_instructions',
    default_unit_type: str = 'prompt_plain_text',
    priority: int = 60,
) -> list[CodexSourceUnitDraft]:
    """Split one Codex prompt text part into normalized source-unit drafts.

    触发点是 Codex normalized parser 遍历单个 prompt text part 时. 边界仅限当前
    text 值内的 project-instruction wrapper 和已知 XML-like tags. 未匹配文本只按
    caller 提供的默认 candidate 归类.

    Args:
        text: 当前 prompt text 的原始字符串.
        origin_path: 产生该 text part 的 session 文件或虚拟来源.
        timestamp: 继承自事件的时间戳.
        event_order: 当前事件在 session 中的稳定顺序.
        direction: request 或 response 方向.
        part_index: 当前 text part 在事件内的稳定序号.
        default_candidate: 未匹配片段使用的默认 attribution candidate.
        default_unit_type: 未匹配片段使用的 source unit 类型.
        priority: source unit 去重时使用的优先级.

    Returns:
        按出现顺序生成的 Codex source-unit drafts.
    """
    value = str(text or '')
    if not value.strip():
        return []

    project_match = _PROJECT_RE.fullmatch(value)
    if project_match:
        file_name = project_match.group('file')
        root = project_match.group('root').strip()
        locator = _project_locator(root, file_name)
        return [
            text_unit(
                origin_path=origin_path,
                canonical_source_locator=locator,
                unit_type='project_instruction_bundle',
                candidate='system_instructions',
                direction=direction,
                text=value,
                timestamp=timestamp,
                event_order=event_order,
                part_index=part_index,
                byte_range=(0, len(value.encode('utf-8'))),
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
                byte_range=(0, len(value.encode('utf-8'))),
                label=default_unit_type,
                priority=priority - 1,
            )
        ]
    return []


def _find_known_blocks(text: str) -> list[tuple[int, int, str, str]]:
    """Find known tagged blocks inside a single Codex text part.

    Args:
        text: Text part to scan for known tags.

    Returns:
        Sorted spans with unit_type and candidate metadata.
    """
    matches: list[tuple[int, int, str, str]] = []
    for tag, unit_type, candidate in _TAG_RULES:
        pattern = re.compile(rf'<{re.escape(tag)}>.*?</{re.escape(tag)}>', re.DOTALL)
        for match in pattern.finditer(text):
            start, end = match.span()
            if _overlaps(start, end, [(m[0], m[1]) for m in matches]):
                continue
            matches.append((start, end, unit_type, candidate))
    return sorted(matches, key=lambda item: item[0])


def _remaining_chunks(text: str, consumed: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    """Return unconsumed text spans after known blocks are removed.

    Args:
        text: Original text part.
        consumed: Character spans already assigned to known blocks.

    Returns:
        Unconsumed character spans and their text chunks.
    """
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
    """Report whether a candidate span overlaps any existing span.

    Args:
        start: Candidate start character offset.
        end: Candidate end character offset.
        ranges: Existing character ranges.

    Returns:
        True when the candidate range overlaps an existing range.
    """
    return any(start < old_end and end > old_start for old_start, old_end in ranges)


def _char_to_byte_range(text: str, start: int, end: int) -> tuple[int, int]:
    """Convert character offsets into UTF-8 byte offsets.

    Args:
        text: Source text used for offset conversion.
        start: Start character offset.
        end: End character offset.

    Returns:
        Start and end UTF-8 byte offsets.
    """
    return (len(text[:start].encode('utf-8')), len(text[:end].encode('utf-8')))


def _project_locator(root: str, file_name: str) -> str:
    """Build a stable locator for project-level instruction wrappers.

    Args:
        root: Project root captured from the wrapper heading.
        file_name: Instruction file name captured from the wrapper heading.

    Returns:
        Canonical locator for the project instruction source.
    """
    if not root:
        return file_name
    return f'{root.rstrip("/")}/{file_name}'
