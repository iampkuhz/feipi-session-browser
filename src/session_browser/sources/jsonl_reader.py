"""Source adapter helpers for reading local agent session data.

Scanner and route code call this module to discover and normalize records.
It keeps raw parsing behavior unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# 说明:─── Severity & Issue enums ──────────────────────────────────────────────


class ParseSeverity(Enum):
    """ParseSeverity contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        INFO: Public contract field or enum value.
        WARNING: Public contract field or enum value.
        ERROR: Public contract field or enum value.
    """

    INFO = auto()
    WARNING = auto()
    ERROR = auto()


class ParseIssue(Enum):
    """ParseIssue contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        BAD_JSON: Public contract field or enum value.
        NON_OBJECT_SKIPPED: Public contract field or enum value.
        CONCATENATED_OBJECTS: Public contract field or enum value.
    """

    # 说明:Format-level problems
    BAD_JSON = 'BAD_JSON'  # 说明:Unparseable JSON
    NON_OBJECT_SKIPPED = 'NON_OBJECT_SKIPPED'  # 说明:Valid JSON but not a dict
    CONCATENATED_OBJECTS = 'CONCATENATED_OBJECTS'  # 说明:Split ``}{`` boundary detected


# 说明:─── Data classes ────────────────────────────────────────────────────────


@dataclass
class ParseIssueItem:
    """ParseIssueItem contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        issue: Public contract field or enum value.
        severity: Public contract field or enum value.
        line_no: Public contract field or enum value.
        detail: Public contract field or enum value.
        preview: Public contract field or enum value.
    """

    issue: ParseIssue
    severity: ParseSeverity
    line_no: int
    detail: str = ''
    preview: str = ''


@dataclass
class JsonlDiagnostics:
    """JsonlDiagnostics contract used by the session browser pipeline.

    Callers create or import this class to carry normalized domain state while
    preserving existing parsing invariants.

    Attributes:
        issues: Public contract field or enum value.
        total_lines: Public contract field or enum value.
        non_empty_lines: Public contract field or enum value.
        events_parsed: Public contract field or enum value.
        events_skipped: Public contract field or enum value.
    """

    issues: list[ParseIssueItem] = field(default_factory=list)
    total_lines: int = 0
    non_empty_lines: int = 0
    events_parsed: int = 0
    events_skipped: int = 0

    @property
    def warning_count(self) -> int:
        """warning_count method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return sum(1 for i in self.issues if i.severity == ParseSeverity.WARNING)

    @property
    def error_count(self) -> int:
        """error_count method used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        return sum(1 for i in self.issues if i.severity == ParseSeverity.ERROR)


# 说明:─── Internal helpers ────────────────────────────────────────────────────


def _brace_chars_outside_strings(text: str) -> str:
    """_brace_chars_outside_strings function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        text: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string and ch in '{}[]':
            result.append(ch)
    return ''.join(result)


def _split_at_depth0(text: str) -> list[str]:
    """_split_at_depth0 function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        text: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    parts: list[str] = []
    current_start = 0
    depth = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and i + 1 < len(text) and text[i + 1] == '{':
                candidate = text[current_start : i + 1].strip()
                if candidate:
                    parts.append(candidate)
                current_start = i + 1

    if current_start == 0:
        return [text]

    tail = text[current_start:].strip()
    if tail:
        parts.append(tail)
    return parts if parts else [text]


def _try_parse_json(
    text: str,
    line_no: int,
    events: list[dict],
    skipped: list[tuple[int, str, str]],
) -> None:
    """_try_parse_json function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        text: Input value supplied by the caller for this pipeline step.
        line_no: Input value supplied by the caller for this pipeline step.
        events: Input value supplied by the caller for this pipeline step.
        skipped: Input value supplied by the caller for this pipeline step.
    """
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            events.append(obj)
        else:
            skipped.append((line_no, type(obj).__name__, repr(text[:120])))
        return
    except json.JSONDecodeError:
        pass

    # 拆分 at top-level ``}{`` boundaries.
    parts = _split_at_depth0(text)
    if len(parts) > 1:
        for part in parts:
            try:
                obj = json.loads(part)
                if isinstance(obj, dict):
                    events.append(obj)
                else:
                    skipped.append((line_no, type(obj).__name__, repr(part[:120])))
            except json.JSONDecodeError:
                skipped.append((line_no, 'BAD_JSON', repr(part[:120])))
    else:
        skipped.append((line_no, 'BAD_JSON', repr(text[:120])))


# 说明:─── Public API ──────────────────────────────────────────────────────────


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    """_iter_lines function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        path: Input value supplied by the caller for this pipeline step.

    Yields:
        Items produced in source order for the caller to consume lazily.
    """
    with path.open(encoding='utf-8') as fh:
        for line_no, raw_line in enumerate(fh, 1):
            stripped = raw_line.rstrip()
            if stripped:
                yield line_no, stripped


def _build_diagnostics(
    diagnostics: JsonlDiagnostics,
    skipped: list[tuple[int, str, str]],
    events: list[dict],
) -> JsonlDiagnostics:
    """_build_diagnostics function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        diagnostics: Input value supplied by the caller for this pipeline step.
        skipped: Input value supplied by the caller for this pipeline step.
        events: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    diagnostics.events_parsed = len(events)
    diagnostics.events_skipped = len(skipped)

    for line_no, type_name, preview in skipped:
        if type_name == 'BAD_JSON':
            diagnostics.issues.append(
                ParseIssueItem(
                    issue=ParseIssue.BAD_JSON,
                    severity=ParseSeverity.ERROR,
                    line_no=line_no,
                    detail=f'Unparseable JSON at line {line_no}',
                    preview=preview,
                )
            )
        else:
            diagnostics.issues.append(
                ParseIssueItem(
                    issue=ParseIssue.NON_OBJECT_SKIPPED,
                    severity=ParseSeverity.WARNING,
                    line_no=line_no,
                    detail=f'Non-dict JSON value skipped: {type_name}',
                    preview=preview,
                )
            )

    return diagnostics


def parse_jsonl_events(
    path: Path | str,
    verbose: bool = False,
) -> tuple[list[dict], JsonlDiagnostics]:
    """parse_jsonl_events function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        path: Input value supplied by the caller for this pipeline step.
        verbose: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if isinstance(path, str):
        path = Path(path)

    events: list[dict] = []
    skipped: list[tuple[int, str, str]] = []
    current_lines: list[str] = []
    depth = 0

    diagnostics = JsonlDiagnostics()
    line_no = 0  # 说明:Initialize to handle empty files without UnboundLocalError

    for line_no, stripped in _iter_lines(path):
        diagnostics.non_empty_lines += 1

        for ch in _brace_chars_outside_strings(stripped):
            if ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1

        current_lines.append(stripped)

        if depth == 0:
            full = '\n'.join(current_lines).strip()
            current_lines = []
            _try_parse_json(full, line_no, events, skipped)

    diagnostics.total_lines = line_no  # 说明:last line_no seen
    _build_diagnostics(diagnostics, skipped, events)

    if verbose and skipped:
        print(f'  [jsonl_reader] {path.name}: {len(skipped)} non-dict JSON item(s) skipped:')
        for line_no, type_name, preview in skipped:
            print(f'    L{line_no} [{type_name}] {preview}')

    return events, diagnostics
