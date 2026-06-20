"""说明：Multipart message content normalizer.

Provides ``normalize_message_content(text)`` to convert raw
``request_full`` / ``response_full`` strings into a typed
``list[ContentPart]``.

Design
------
- Pure, idempotent, no side effects.
- Splits input into segments at structural boundaries (fenced code
  blocks, standalone JSON) and classifies each segment.
- Empty or whitespace-only input returns a single empty ``text`` part
  (never raises).
"""

from __future__ import annotations

import json
import re
from typing import List

from .content_part import ContentPart, ContentPartType, ContextPartType, is_json, is_code_block


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def normalize_message_content(text: str) -> List[ContentPart]:
    """转换 一个 raw message string，转换为 一个 list of ContentParts.

    Parameters
    ----------
    text : str
        The raw message content (e.g. ``request_full`` or
        ``response_full`` from a session log).

    Returns
    -------
    list[ContentPart]
        Ordered, typed content parts.  Never ``None``.

    Behaviour
    ---------
    * Empty / whitespace-only input -> ``[ContentPart("text", "")]``.
    * Fenced code blocks (```) -> ``code`` part with ``language`` hint.
    * Standalone JSON objects/arrays -> ``json`` part.
    * Everything else -> ``markdown`` part (or ``text`` if empty).
    * Consecutive non-code segments separated by blank lines are split
      into separate parts to avoid mixing unrelated payloads.
    """
    if text is None:
        return [ContentPart(part_type=ContentPartType.TEXT, content="")]

    segments = _split_segments(text)

    if not segments:
        return [ContentPart(part_type=ContentPartType.TEXT, content="")]

    parts: List[ContentPart] = []
    for seg_type, seg_content in segments:
        if seg_type == "code":
            # 说明：Try to parse as fenced code block (with language hint).
            if seg_content.startswith(("```", "~~~")):
                lang, code = _parse_code_fence(seg_content)
            else:
                # 说明：Pattern-detected code without fences.
                lang, code = "", seg_content
            parts.append(ContentPart(
                part_type=ContentPartType.CODE,
                content=code,
                language=lang,
            ))
        elif seg_type == "json":
            parts.append(ContentPart(
                part_type=ContentPartType.JSON,
                content=seg_content.strip(),
            ))
        else:
            stripped = seg_content.strip()
            if stripped:
                parts.append(ContentPart(
                    part_type=ContentPartType.MARKDOWN,
                    content=stripped,
                ))

    if not parts:
        return [ContentPart(part_type=ContentPartType.TEXT, content="")]

    return parts


def normalize_context_parts(
    text: str,
    default_context_type: str = ContextPartType.UNKNOWN,
    title: str = "",
) -> List[ContentPart]:
    """转换 raw context text，转换为 enriched ContentParts，使用 context-level metadata.

    This is a higher-level wrapper around ``normalize_message_content`` that
    additionally sets:
    - ``context_type``: the structural role of each part (system_prompt,
      user_message, tool_result, etc.).
    - ``title``: human-readable label for display headers.
    - ``content_bytes`` and ``token_hint``: auto-computed size hints.

    Parameters
    ----------
    text : str
        The raw message content.
    default_context_type : str
        ContextPartType value assigned to every part (default: UNKNOWN).
        Use this when the caller knows the overall role (e.g. this is a
        user message, so all parts get USER_MESSAGE).
    title : str
        Human-readable title applied to all parts (e.g. "User Message #1").

    Returns
    -------
    list[ContentPart]
        Ordered, typed, and enriched content parts.  Never ``None``.

    Fallback
    --------
    If the input cannot be parsed into multipart structure, returns a
    single part with context_type=UNKNOWN and an empty title, with
    ``normalize_message_content`` providing content-level type detection.
    The caller can detect this by checking if all parts have
    ``context_type == UNKNOWN``.
    """
    if text is None:
        part = ContentPart(
            part_type=ContentPartType.TEXT,
            content="",
            context_type=default_context_type,
            title=title,
        )
        part.compute_metadata()
        return [part]

    parts = normalize_message_content(text)

    for part in parts:
        part.context_type = default_context_type
        if title:
            part.title = title
        part.compute_metadata()

    return parts


def detect_multipart_messages(text: str) -> List[ContentPart]:
    """Attempt to parse *text* as 一个 JSON messages array 和 return typed parts.

    If *text* looks like a JSON array of API-style messages (each with
    ``role`` and ``content``), this function extracts each message as a
    separate ContentPart with:
    - ``context_type`` derived from the message role (user, assistant, system, tool).
    - ``title`` set to a human-readable label (e.g. "System Prompt", "User Message").
    - ``content`` set to the message content (stringified if complex).

    If *text* is not a valid JSON messages array, falls back to a single
    UNKNOWN part (the caller should detect this and use raw display).

    Parameters
    ----------
    text : str
        Raw request context string that may contain a JSON messages array.

    Returns
    -------
    list[ContentPart]
        Parsed multipart parts, or a single UNKNOWN part on failure.
    """
    if not text or not text.strip():
        return []

    stripped = text.strip()
    if not stripped.startswith("["):
        return []

    try:
        messages = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return []

    if not isinstance(messages, list) or len(messages) == 0:
        return []

    # Validate: each message should have at least 一个 "role" key.
    if not all(isinstance(m, dict) and "role" in m for m in messages):
        return []

    parts: List[ContentPart] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # Complex content: flatten list of content blocks，转换为 一个 string.
        if isinstance(content, list):
            pieces = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        pieces.append(block.get("text", ""))
                    elif block_type == "tool_result":
                        pieces.append(
                            f"[Tool Result: {block.get('tool_use_id', 'unknown')}]\n"
                            f"{block.get('content', '')}"
                        )
                    elif block_type == "tool_use":
                        pieces.append(
                            f"[Tool Use: {block.get('name', 'unknown')}]\n"
                            f"{json.dumps(block.get('input', {}), indent=2)}"
                        )
                    elif block_type == "image":
                        pieces.append(
                            f"[Image: {block.get('source', {}).get('media_type', 'unknown')}]"
                        )
                    else:
                        pieces.append(json.dumps(block, indent=2))
                else:
                    pieces.append(str(block))
            content = "\n\n".join(pieces)
        elif not isinstance(content, str):
            content = json.dumps(content, indent=2)

        # 映射 role to context_type 和 title.
        ctx_type, part_title = _role_to_context_type(role, i)

        part = ContentPart(
            part_type=detect_content_type(content),
            content=content,
            context_type=ctx_type,
            title=part_title,
        )
        part.compute_metadata()
        parts.append(part)

    return parts


def _role_to_context_type(role: str, index: int) -> tuple[str, str]:
    """映射 一个 API message role to (context_type, human-readable title)."""
    role_lower = role.lower()
    if role_lower == "system":
        return ContextPartType.SYSTEM_PROMPT, "System Prompt"
    elif role_lower == "user":
        return ContextPartType.USER_MESSAGE, f"User Message #{index + 1}"
    elif role_lower == "assistant":
        return ContextPartType.ASSISTANT_MESSAGE, f"Assistant Message #{index + 1}"
    elif role_lower == "tool":
        return ContextPartType.TOOL_RESULT, f"Tool Result #{index + 1}"
    else:
        return ContextPartType.UNKNOWN, f"Message #{index + 1} ({role})"


# 说明：Import here to avoid circular import at module level.
def detect_content_type(payload: str, filename_hint: str = "") -> str:
    """说明：Delegate to content_part.detect_content_type."""
    from .content_part import detect_content_type as _detect
    return _detect(payload, filename_hint)


# ---------------------------------------------------------------------------
# 说明：Internal — segment splitting
# ---------------------------------------------------------------------------

# Match opening/closing fenced code blocks (```, ~~~，使用 optional language).
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*([^\s`]*)\s*$", re.MULTILINE)


def _split_segments(text: str) -> list[tuple[str, str]]:
    """拆分 *text*，转换为 (type, content) segments.

    Types: ``"code"``, ``"text"``.
    JSON detection happens in a second pass over ``"text"`` segments.
    """
    segments: list[tuple[str, str]] = []

    fences = list(_FENCE_RE.finditer(text))
    if not fences:
        return _split_text_segments(text)

    # 说明：Match paired fences (same char, >= opening length).
    pairs = _pair_fences(fences, text)
    if not pairs:
        return _split_text_segments(text)

    parts: list[tuple[str, str]] = []
    cursor = 0

    for opening, closing, lang in pairs:
        # 说明：Pre-fence text.
        if opening.start() > cursor:
            pre = text[cursor:opening.start()]
            parts.extend(_split_text_segments(pre))

        # Code block content (between opening line end 和 closing line start).
        inner_start = text.index("\n", opening.start(), closing.start()) + 1
        code = text[inner_start:closing.start()]

        # 查找 opening fence end，用于 language hint.
        open_end = text.index("\n", opening.start()) + 1

        parts.append(("code", text[opening.start():closing.end()]))
        cursor = closing.end()

    # 说明：Trailing text.
    if cursor < len(text):
        trailing = text[cursor:]
        parts.extend(_split_text_segments(trailing))

    return parts


def _pair_fences(fences, text: str) -> list:
    """Pair opening 和 closing fences greedily.

    Returns list of (opening_match, closing_match, lang).
    """
    pairs = []
    used: set[int] = set()

    i = 0
    while i < len(fences):
        if i in used:
            i += 1
            continue

        opening = fences[i]
        fence_char = opening.group(1)[0]  # ` or ~
        fence_len = len(opening.group(1))
        lang = opening.group(2)

        # 查找 matching closing fence.
        for j in range(i + 1, len(fences)):
            if j in used:
                continue
            closing = fences[j]
            c_char = closing.group(1)[0]
            c_len = len(closing.group(1))

            if c_char == fence_char and c_len >= fence_len:
                pairs.append((opening, closing, lang))
                used.add(i)
                used.add(j)
                i = j + 1
                break
        else:
            # 说明：No match — skip this opening fence.
            i += 1

    return pairs


# ---------------------------------------------------------------------------
# 说明：Internal — text segment splitting
# ---------------------------------------------------------------------------

# Two 或 more blank lines indicate 一个 segment boundary.
_MULTI_BLANK_RE = re.compile(r"\n\s*\n\s*\n")


def _split_text_segments(text: str) -> list[tuple[str, str]]:
    """拆分 plain text，转换为 sub-segments at blank-line boundaries,
    then classify each as ``"json"``, ``"code"``, or ``"text"``.
    """
    text = text.strip()
    if not text:
        return []

    # 说明：Try to extract standalone JSON blocks.
    if is_json(text):
        return [("json", text)]

    # 检查，如果 该 entire text looks like 一个 code block.
    if is_code_block(text):
        return [("code", text)]

    # 检查，用于 embedded JSON objects/arrays.
    json_candidates = _find_standalone_json(text)
    if json_candidates:
        return _assemble_with_json(text, json_candidates)

    # 拆分 on multi-blank-line boundaries.
    chunks = _MULTI_BLANK_RE.split(text)
    result = []
    for chunk in chunks:
        stripped = chunk.strip()
        if not stripped:
            continue
        if is_json(stripped):
            result.append(("json", stripped))
        elif is_code_block(stripped):
            result.append(("code", stripped))
        else:
            result.append(("text", stripped))
    return result


def _find_standalone_json(text: str) -> list[tuple[int, int]]:
    """查找 positions of standalone JSON objects/arrays in *text*.

    A JSON block is considered "standalone" if it is:
    - On its own (possibly with leading/trailing whitespace), or
    - Separated from surrounding text by blank lines.

    Returns a list of (start, end) offsets into *text*.
    """
    results = []
    for pattern, open_ch, close_ch in [
        ("object", "{", "}"),
        ("array", "[", "]"),
    ]:
        for m in re.finditer(re.escape(open_ch), text):
            start = m.start()
            # Check: either at start of text 或 on its own line (preceded by newline).
            prefix = text[:start]
            stripped_prefix = prefix.rstrip()
            if stripped_prefix and not prefix.endswith("\n"):
                # Something non-whitespace immediately precedes 该 JSON — not standalone.
                continue

            depth = 0
            in_string = False
            escape_next = False
            end = None

            for idx in range(start, len(text)):
                ch = text[idx]
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\":
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        end = idx + 1
                        break

            if end is None:
                continue

            # Check: either at end of text 或 on its own line (followed by newline).
            suffix = text[end:]
            stripped_suffix = suffix.lstrip()
            if stripped_suffix and not suffix.startswith("\n"):
                # 说明：Something non-whitespace immediately follows — not standalone.
                continue

            candidate = text[start:end]
            try:
                json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue

            results.append((start, end))

    # 去重 和 sort by position.
    results.sort(key=lambda x: x[0])
    # 说明：Remove overlapping ranges.
    deduped = []
    for start, end in results:
        if deduped and start < deduped[-1][1]:
            continue
        deduped.append((start, end))
    return deduped


def _assemble_with_json(text: str, json_ranges: list[tuple[int, int]]) -> list[tuple[str, str]]:
    """Assemble segments，来源于 *text*, extracting JSON at *json_ranges*.

    Each gap between JSON blocks becomes a ``"text"`` segment (if
    non-empty after stripping).
    """
    segments: list[tuple[str, str]] = []
    cursor = 0

    for jstart, jend in json_ranges:
        if jstart > cursor:
            gap = text[cursor:jstart].strip()
            if gap:
                segments.append(("text", gap))
        segments.append(("json", text[jstart:jend].strip()))
        cursor = jend

    if cursor < len(text):
        tail = text[cursor:].strip()
        if tail:
            segments.append(("text", tail))

    return segments


# ---------------------------------------------------------------------------
# 说明：Internal — code fence parsing
# ---------------------------------------------------------------------------

_FENCE_LANG_RE = re.compile(r"^(`{3,}|~{3,})[ \t]*([^\s`]*)")


def _parse_code_fence(block: str) -> tuple[str, str]:
    """提取 (language, code_body)，来源于 一个 fenced code block string.

    >>> _parse_code_fence("```python\\nprint(1)\\n```")
    ('python', 'print(1)')
    """
    m = _FENCE_LANG_RE.match(block)
    lang = m.group(2) if m else ""

    # Strip opening 和 closing fence lines.
    lines = block.splitlines()
    if lines:
        lines = lines[1:]  # 移除开头 fence。
    if lines and re.match(r"^`{3,}\s*$|^~{3,}\s*$", lines[-1]):
        lines = lines[:-1]  # 移除结尾 fence。

    return lang, "\n".join(lines)


# ---------------------------------------------------------------------------
# Title sanitization，用于 list views
# ---------------------------------------------------------------------------

_LIST_TITLE_MAX = 120


def sanitize_list_title(text: str, max_len: int = _LIST_TITLE_MAX) -> str:
    """Sanitize 一个 session title，用于 list-view display.

    Normalizes whitespace (newlines → space, collapses runs of whitespace,
    strips ends) and truncates to *max_len* characters with an ellipsis
    suffix when the title exceeds the limit.

    - ``None`` or ``""`` → ``""`` (caller handles "Untitled" fallback).
    - Short titles pass through unchanged (after whitespace normalization).
    - Over-long titles get truncated with ``…`` appended.
    """
    if not text:
        return ""
    text = str(text)
    # Replace 所有 whitespace runs (including newlines)，使用 一个 single space.
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    if len(text) > max_len:
        return text[:max_len].rstrip() + "…"
    return text
