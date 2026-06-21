"""Extract tool-result evidence from the current session event stream.

Session attribution collectors call this module after raw event loading. It
accepts event dictionaries from the session stream and returns Evidence rows for
tool results without reading files, network resources, or global state.
"""

from __future__ import annotations

import re

from session_browser.attribution.collectors.session.event_stream_reader import (
    TOOL_RESULT,
    filter_events_by_type,
)
from session_browser.attribution.core.models import ContentRef, Evidence


def extract_tool_results(
    events: list[dict],
    call_id: str,
    preceding_only: bool = True,
    evidence_counter: int = 0,
) -> list[Evidence]:
    """Extract tool-result events into current-session Evidence rows.

    The session evidence collector calls this after filtering or loading the
    event stream for an LLM call. The current implementation preserves legacy
    behavior by converting all tool-result events in the provided list.

    Args:
        events: Session event dictionaries containing content/result fields and
            optional line metadata.
        call_id: LLM call identifier supplied by the caller; retained for API
            compatibility and not used to filter the current event list.
        preceding_only: Legacy flag indicating whether callers intended only
            preceding tool results; filtering is expected to happen upstream.
        evidence_counter: Offset used to keep generated Evidence identifiers
            stable when this collector is composed with other collectors.

    Returns:
        Evidence rows in the same order as matching tool-result events.
    """
    tool_events = filter_events_by_type(events, TOOL_RESULT)
    results = []

    for idx, ev in enumerate(tool_events):
        result_text = ev.get('content', ev.get('result', '')) or ''
        tool_use_id = ev.get('tool_use_id', ev.get('id', ''))

        content_str = str(result_text)
        preview = content_str[:200]

        results.append(
            Evidence(
                evidence_id=f'session_tool_result_{evidence_counter + idx}',
                scope='current_session',
                kind='tool_result',
                source_event_id=ev.get('id', ''),
                content_ref=ContentRef(
                    kind='session_event',
                    pointer=f'line_{ev.get("_line", idx)}',
                    preview=preview,
                    can_load_full=True,
                ),
                text_preview=preview,
                precision='extracted',
                confidence=0.9,
                source_path=tool_use_id,
            )
        )

    return results


def _extract_tool_name(text: str) -> str:
    """Infer a display tool name from raw tool-result text.

    Tool-result extraction keeps this helper for callers that lack structured
    metadata. It has no side effects and falls back to a bounded first token.

    Args:
        text: Raw tool-result text or an empty string.

    Returns:
        Parsed tool name, the first text token truncated to 30 characters, or
        ``unknown`` when no usable text exists.
    """
    if not text:
        return 'unknown'

    m = re.search(r'(?:Tool|tool)[\s_]*(?:Call|Result|Output)?[:\s]+(\w+)', text)
    if m:
        return m.group(1)
    first = text.split(maxsplit=1)[0] if text.split() else 'unknown'
    return first[:30]
