"""Source adapter helpers for reading local agent session data.

Scanner and route code call this module to discover and normalize records.
It keeps raw parsing behavior unchanged.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# ─── Interval merging (shared,使用 Claude) ──────────────────────────────


def _merge_intervals(intervals: list[tuple[int, int]], max_gap_ms: int = 300_000) -> int:
    """_merge_intervals function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        intervals: Input value supplied by the caller for this pipeline step.
        max_gap_ms: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not intervals:
        return 0
    intervals = [(s, e) for s, e in intervals if (e - s) <= max_gap_ms]
    if not intervals:
        return 0
    intervals.sort()
    merged = [intervals[0]]
    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return sum(e - s for s, e in merged)


# 说明:─── Token estimation (Qoder does not log usage) ──────────────────────────
#
# Qoder 估算固定走 byte-level 启发式,避免 tiktoken encode 的额外开销.
# tiktoken 不在此模块引入,留给非 qoder provider 或未来精确模式使用.

# Max text length to scan,用于 token estimation (32KB). Beyond this, text is
# truncated,在之前 counting to keep estimation fast.
_ESTIMATE_TEXT_CAP = 32 * 1024


def _cap_text(s: str) -> str:
    """_cap_text function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        s: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not s:
        return ''
    byte_len = len(s.encode('utf-8'))
    if byte_len <= _ESTIMATE_TEXT_CAP:
        return s
    # 截断 by characters to stay under cap.
    avg_bytes = byte_len / len(s)
    safe_chars = int(_ESTIMATE_TEXT_CAP / avg_bytes)
    truncated = s[:safe_chars]
    while len(truncated.encode('utf-8')) > _ESTIMATE_TEXT_CAP and len(truncated) > 0:
        truncated = truncated[:-100]
    return truncated


def _count_tokens(s: str) -> int:
    """_count_tokens function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        s: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    capped = _cap_text(s or '')
    return max(1, int(len(capped.encode('utf-8')) / 3.5))


def normalize_timestamp(ts: Any) -> str:
    """normalize_timestamp function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        ts: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not ts:
        return ''
    dt = None
    if isinstance(ts, (int, float)):
        # Detect millisecond timestamps (> 1e12) 和 convert to seconds
        actual_ts = ts / 1000 if ts > 1e12 else ts
        dt = datetime.fromtimestamp(actual_ts, tz=timezone.utc).astimezone()
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone()
        except (ValueError, TypeError):
            return ''
    if dt is None:
        return ''
    return dt.isoformat()


def _ts_ms_to_iso(ts_ms: int | float) -> str:
    """_ts_ms_to_iso function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        ts_ms: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not ts_ms:
        return ''
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).astimezone()
    return dt.isoformat()


def _scan_project_dirs(project_dir: Path) -> list[str]:
    """_scan_project_dirs function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        project_dir: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return []


def _assistant_message_key(ev: dict) -> str:
    """_assistant_message_key function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        ev: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    msg = ev.get('message', {})
    if isinstance(msg, dict) and msg.get('id'):
        return str(msg['id'])
    return str(ev.get('uuid') or ev.get('parentUuid') or id(ev))


def _merge_usage_dicts(usages: list[dict]) -> dict:
    """_merge_usage_dicts function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        usages: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not usages:
        return {}

    numeric_keys = {
        'input_tokens',
        'output_tokens',
        'cache_read_input_tokens',
        'cache_creation_input_tokens',
    }
    cache_keys = ('cache_read_input_tokens', 'cache_creation_input_tokens')

    def usage_int(usage: dict, key: str) -> int:
        """usage_int function used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            usage: Input value supplied by the caller for this pipeline step.
            key: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        value = usage.get(key, 0)
        if isinstance(value, (int, float)):
            return int(value)
        return 0

    def score(index_and_usage: tuple[int, dict]) -> tuple[int, int, int, int]:
        """Score function used by the session browser pipeline.

        The active parsing or normalization flow calls this entry point.
        It preserves the existing domain behavior and return shape.

        Args:
            index_and_usage: Input value supplied by the caller for this pipeline step.

        Returns:
            Existing return value produced by this parser or domain helper.
        """
        index, usage = index_and_usage
        output_present = 1 if usage_int(usage, 'output_tokens') > 0 else 0
        cache_field_count = sum(1 for key in cache_keys if key in usage)
        token_total = sum(usage_int(usage, key) for key in numeric_keys)
        return (output_present, cache_field_count, token_total, index)

    _, best_usage = max(enumerate(usages), key=score)
    merged = dict(best_usage)
    max_input = max((usage_int(u, 'input_tokens') for u in usages), default=0)
    if max_input > 0:
        merged['input_tokens'] = max_input
    return merged


def _normalize_qoder_provider_usage(records: list[dict]) -> None:
    """_normalize_qoder_provider_usage function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        records: Input value supplied by the caller for this pipeline step.
    """
    usages: list[dict] = []
    for rec in records:
        usage = rec.get('usage')
        usages.append(usage if isinstance(usage, dict) else {})

    for idx, usage in enumerate(usages):
        if not usage or 'input_tokens' not in usage:
            continue

        raw_input_total = int(usage.get('input_tokens', 0) or 0)
        cache_read = int(usage.get('cache_read_input_tokens', 0) or 0)
        raw_cache_write = int(usage.get('cache_creation_input_tokens', 0) or 0)

        # 保留 provider_reported cache_write,不做跨 call 推断
        cache_write = raw_cache_write

        # 跨 call 推断(仅用于 diagnostic,不污染 provider 字段)
        inferred_cache_write = 0
        inferred = False
        if raw_cache_write <= 0 and idx + 1 < len(usages):
            next_cache_read = int(usages[idx + 1].get('cache_read_input_tokens', 0) or 0)
            if next_cache_read > cache_read:
                inferred_cache_write = next_cache_read - cache_read
                inferred = True

        # 保存原始 input marker
        usage['qoder_input_tokens_total'] = raw_input_total
        usage['input_tokens'] = raw_input_total
        usage['cache_read_input_tokens'] = cache_read
        # 保留 provider_reported cache_write,不覆盖
        usage['cache_creation_input_tokens'] = cache_write

        # 跨 call 推断写入单独字段(diagnostic only)
        if inferred:
            usage['qoder_cache_write_inferred_tokens'] = inferred_cache_write
            usage['qoder_cache_write_inferred'] = True
            usage['qoder_cache_write_inference_note'] = (
                'derived from next cache_read delta; not provider_reported'
            )


def _extract_qoder_model(record: dict) -> str | None:
    """_extract_qoder_model function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        record: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    for key in ('model', 'top_level_model', 'metadata_model', 'raw_model'):
        value = record.get(key, '')
        if value:
            return value
    return None


def _assistant_records(events: list[dict]) -> list[dict]:
    """_assistant_records function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        events: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    records: dict[str, dict] = {}
    order: list[str] = []

    for ev in events:
        if ev.get('type') != 'assistant':
            continue
        msg = ev.get('message', {})
        if not isinstance(msg, dict):
            continue

        key = _assistant_message_key(ev)
        if key not in records:
            records[key] = {
                'id': key,
                'timestamp': ev.get('timestamp', ''),
                'model': msg.get('model', ''),
                'top_level_model': ev.get('model', ''),
                'metadata_model': (ev.get('metadata') or {}).get('model', ''),
                'raw_model': '',
                'text_parts': [],
                'tool_calls': [],
                'content_blocks': [],
                'usage_rows': [],
                'stop_reason': '',
                'row_count': 0,
            }
            order.append(key)

        rec = records[key]
        rec['row_count'] += 1
        if ev.get('timestamp'):
            rec['timestamp'] = ev.get('timestamp', '')
        if msg.get('model'):
            rec['model'] = msg.get('model', '')
        if ev.get('model'):
            rec['top_level_model'] = ev.get('model', '')
        metadata_model = (ev.get('metadata') or {}).get('model', '')
        if metadata_model:
            rec['metadata_model'] = metadata_model
        if msg.get('stop_reason'):
            rec['stop_reason'] = msg.get('stop_reason', '')

        usage = msg.get('usage')
        if isinstance(usage, dict):
            rec['usage_rows'].append(usage)

        content = msg.get('content', [])
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get('type') == 'text':
                    text = item.get('text', '')
                    if text:
                        rec['text_parts'].append(text)
                    rec['content_blocks'].append({'type': 'text', 'content': text})
                elif item.get('type') == 'thinking':
                    thinking = item.get('thinking', '')
                    if thinking:
                        rec['text_parts'].append(thinking)
                    rec['content_blocks'].append({'type': 'thinking', 'content': thinking})
                elif item.get('type') == 'tool_use':
                    tool_block = {
                        'id': item.get('id', ''),
                        'name': item.get('name', ''),
                        'parameters': item.get('input', {}),
                    }
                    rec['tool_calls'].append(tool_block)
                    rec['content_blocks'].append({'type': 'tool_use', **tool_block})
                # Priority 4: look,用于 explicit model field in request/response content
                if isinstance(item, dict) and item.get('model'):
                    rec['raw_model'] = item.get('model', '')

    merged_records = []
    for key in order:
        rec = records[key]
        rec['usage'] = _merge_usage_dicts(rec.pop('usage_rows'))
        merged_records.append(rec)
    _normalize_qoder_provider_usage(merged_records)
    return merged_records


def _extract_user_text(ev: dict) -> str:
    """_extract_user_text function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        ev: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    # 跳过 meta events (internal commands like /login, /model)
    if ev.get('isMeta') is True:
        return ''
    msg = ev.get('message', {})
    if not isinstance(msg, dict):
        return ''
    content = msg.get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                text = item.get('text', '')
                # 说明:Filter out system caveats
                if text and 'Caveat: The messages below were generated' not in text:
                    parts.append(text)
        return '\n'.join(p for p in parts if p)
    return ''


def _summarize_text(text: str, max_len: int = 80) -> str:
    """_summarize_text function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        text: Input value supplied by the caller for this pipeline step.
        max_len: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text).strip()
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return ''
    sentence_match = re.match(r'^(.+?[.!?])\s', text)
    if sentence_match:
        first_sentence = sentence_match.group(1).strip()
        if len(first_sentence) <= max_len:
            return first_sentence
        return first_sentence[: max_len - 1] + '…'
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + '…'


def _extract_readable_title(raw_content: str) -> str:
    """_extract_readable_title function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        raw_content: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if not raw_content:
        return ''
    content = raw_content.strip()
    cmd_match = re.search(r'<command-message>([^<]+)</command-message>', content)
    if cmd_match:
        cmd_name = cmd_match.group(1).strip()
        args_match = re.search(r'<command-args>(.+?)</command-args>', content, re.DOTALL)
        if args_match:
            args_text = args_match.group(1).strip()
            intent = _summarize_text(args_text)
            if intent:
                return f'{cmd_name} · {intent}'
        after_cmd = content[cmd_match.end() :].strip()
        if after_cmd:
            intent = _summarize_text(after_cmd)
            if intent:
                return f'{cmd_name} · {intent}'
        return cmd_name
    return _summarize_text(content)


def _stringify_tool_result(result_content: Any) -> str:
    """_stringify_tool_result function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        result_content: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    if result_content is None:
        return ''
    if isinstance(result_content, str):
        return result_content
    if isinstance(result_content, list):
        parts = []
        for item in result_content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    parts.append(item.get('text', ''))
                elif 'content' in item:
                    parts.append(str(item.get('content', '')))
            else:
                parts.append(str(item))
        return '\n'.join(p for p in parts if p)
    if isinstance(result_content, dict):
        return json.dumps(result_content, ensure_ascii=False)
    return str(result_content)


def _tool_result_looks_failed(result_content: Any, tool_name: str = '') -> bool:
    """_tool_result_looks_failed function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        result_content: Input value supplied by the caller for this pipeline step.
        tool_name: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    text = _stringify_tool_result(result_content).lower()
    if not text:
        return False

    # 说明:For Read/Write/Edit/Glob/Grep/LS tools, detect file-level errors
    if tool_name in ('Read', 'Write', 'Edit', 'Glob', 'Grep', 'LS'):
        first_line = text.split('\n', 1)[0].strip()
        return bool(
            first_line.startswith(
                (
                    'file does not exist',
                    'permission denied',
                    'no such file',
                    'directory not found',
                    'path not found',
                    'cannot read',
                    'not a directory',
                    'too many levels of symbolic links',
                    'input/output error',
                    'is a directory',
                )
            )
        )

    # 说明:── Tool runtime error markers (anchored at line start) ─────
    # These indicate 该 tool could not execute, not that it ran and
    # produced 一个 error result.
    line_markers = [
        'api error',
        'tool_use_error',
        'key_model_access_denied',
        'rate limit exceeded',
        'user rejected',
        'request cancelled',
        'permission denied',  # 说明:bash: ./deploy.sh: Permission denied
        'fatal:',  # 说明:git errors: fatal: not a git repository
    ]
    for marker in line_markers:
        if text.startswith(marker):
            return True
        for line in text.split('\n'):
            stripped = line.strip().lstrip('$# ').strip()
            if stripped.startswith(marker):
                return True
            # Also match,在之后 shell error prefix: "bash: cmd: ..."
            parts = stripped.split(': ')
            if len(parts) > 1:
                last_part = parts[-1].strip()
                if last_part.startswith(marker):
                    return True

    # ── "command not found" at line start or,在之后 shell prefix ──
    if re.search(r'(?:^|\n)\s*command not found', text, re.MULTILINE):
        return True
    for line in text.split('\n'):
        stripped = line.strip()
        m = re.match(r'^(?:ba)?sh:\s+.*:\s+command not found', stripped)
        if m:
            return True

    # 说明:── "timeout" at line start ──────────────────────────────────
    return bool(re.search(r'(?:^|\n)\s*timeout\b', text, re.MULTILINE))


def _extract_event_text(ev: dict) -> tuple[str, str]:
    """_extract_event_text function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        ev: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    typ = ev.get('type')
    msg = ev.get('message') or {}
    content = msg.get('content')

    if typ == 'user':
        if ev.get('isMeta') is True:
            return None, ''
        if isinstance(content, str):
            return 'user_prompt', content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    text = item.get('text', '')
                    if text and 'Caveat: The messages below were generated' not in text:
                        parts.append(text)
            if parts:
                return 'user_prompt', '\n'.join(parts)
            # 说明:tool_result content goes back as input on next turn
            tr_parts = []
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'tool_result':
                    tr_parts.append(str(item.get('content', '')))
            if tr_parts:
                return 'tool_result', '\n'.join(tr_parts)

    if typ == 'assistant' and isinstance(content, list):
        text_parts = []
        tool_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    tool_parts.append(json.dumps(item, ensure_ascii=False))
        if tool_parts and not text_parts:
            return 'assistant_tool_call', '\n'.join(tool_parts)
        if text_parts or tool_parts:
            return 'assistant_text', '\n'.join(text_parts + tool_parts)

    return None, ''


def _estimate_tokens_from_events(events: list[dict]):
    """_estimate_tokens_from_events function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        events: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    # 说明:First pass: check whether any event already carries usage dict
    has_real_usage = False
    for ev in events:
        if ev.get('type') == 'assistant':
            usage = (ev.get('message') or {}).get('usage')
            if isinstance(usage, dict) and usage.get('input_tokens'):
                has_real_usage = True
                break

    if has_real_usage:
        return 0, 0, False

    visible_context_tokens = 0
    estimated_input = 0
    estimated_output = 0
    seen_keys: set[str] = set()

    for ev in events:
        cat, text = _extract_event_text(ev)
        if not cat:
            continue

        tok = _count_tokens(text)

        if cat.startswith('assistant'):
            key = _assistant_message_key(ev)
            if key not in seen_keys:
                # 说明:First fragment: capture visible context as input
                seen_keys.add(key)
                estimated_input += visible_context_tokens
                estimated_output += tok
            else:
                # 说明:Subsequent fragments: accumulate output only
                estimated_output += tok

        visible_context_tokens += tok

    return estimated_input, estimated_output, True
