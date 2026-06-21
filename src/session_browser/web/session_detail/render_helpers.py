"""说明:Session detail rendering helpers.

Extracted from routes.py: content block rendering, HTML escaping, and
local-time formatting. These are pure functions used by the view model
builder and the handler's payload API endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime

from session_browser.web.template_env import (
    _format_compact_token,
    _shorten_path,
)


def _html_escape(text: str) -> str:
    """转义 HTML special characters.

    Args:
        text: Text to escape.

    Returns:
        HTML-escaped text.
    """
    text = str(text or '')
    return (
        text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    )


def _to_local_time_hms(iso_str: str) -> str:
    """转换 UTC ISO8601 timestamp to local-time HH:MM:SS only.

    Args:
        iso_str: ISO8601 timestamp string.

    Returns:
        Local time formatted as ``HH:MM:SS``.
    """
    if not iso_str:
        return ''

    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        local_dt = dt.astimezone()
        return local_dt.strftime('%H:%M:%S')
    except (ValueError, TypeError):
        return str(iso_str)[-8:]


def _build_tool_command_summary(tool_name: str, params: dict) -> str:  # noqa: PLR0911,PLR0912,PLR0915
    """构建 一个 short command/summary string,用于 一个 tool call.

    Args:
        tool_name: Tool name from the interaction payload.
        params: Tool parameter dictionary.

    Returns:
        HTML-safe summary string; callers may still escape before rendering.

    For Read/Write/Edit tools: show file path.
    For Bash: show first 120 chars of the command.
    For Grep: show pattern + path/glob.
    For Glob: show pattern.
    For LS: show path.
    For MCP: show server/tool + key args.
    For Agent: show agent_type/agent_id.
    For unknown tools: show compact JSON key subset of parameters.

    """
    name = (tool_name or '').strip()
    if params is None:
        params = {}

    # 说明:── File tools: show file_path ──────────────────────────────
    if name in ('Read', 'Write', 'Edit'):
        return str(params.get('file_path', '') or params.get('path', ''))

    # 说明:── Bash: first 120 chars of command ────────────────────────
    if name == 'Bash':
        cmd = params.get('command', '')
        if cmd:
            cmd = str(cmd).strip()
            return cmd[:120] + ('...' if len(cmd) > 120 else '')
        return name

    # 说明:── Grep: pattern + path/glob ───────────────────────────────
    if name == 'Grep':
        parts = []
        pattern = params.get('pattern', '')
        if pattern:
            parts.append(f'"{pattern}"')
        path = params.get('paths', '')
        if path:
            if isinstance(path, list):
                path = ', '.join(str(p) for p in path[:3])
            parts.append(str(path))
        glob_p = params.get('glob', '')
        if glob_p:
            parts.append(f'--glob {glob_p}')
        return ' '.join(parts) if parts else name

    # 说明:── Glob: show pattern ──────────────────────────────────────
    if name == 'Glob':
        pattern = params.get('pattern', '')
        if pattern:
            return str(pattern)
        return name

    # 说明:── LS: show path ───────────────────────────────────────────
    if name == 'LS':
        path = params.get('path', '')
        if path:
            return str(path)
        return name

    # 说明:── MCP: show server/tool + key args ────────────────────────
    if name == 'MCP' or name.lower().startswith('mcp'):
        parts = []
        server = params.get('server', '')
        tool = params.get('tool', '')
        if server:
            parts.append(str(server))
        if tool:
            parts.append(str(tool))
        # Add 一个 few key args
        for key in ('query', 'input', 'text', 'url', 'path'):
            val = params.get(key, '')
            if val:
                val_str = str(val)
                parts.append(val_str[:60])
                break
        return '/'.join(parts) if parts else name

    # 说明:── Agent: show agent_type ──────────────────────────────────
    if name == 'Agent':
        agent_type = params.get('agent_type', '')
        if agent_type:
            return str(agent_type)
        return name

    # 说明:── Unknown: compact JSON key subset ────────────────────────
    # 说明:Show up to 3 key=value pairs (values truncated to 40 chars)
    if params:
        parts = []
        for key in list(params.keys())[:3]:
            val = params[key]
            if isinstance(val, (dict, list)):
                try:
                    val_str = json.dumps(val, ensure_ascii=False)[:40]
                except Exception:
                    val_str = str(val)[:40]
            else:
                val_str = str(val)[:40]
            parts.append(f'{key}={val_str}')
        summary = ' '.join(parts)
        if summary:
            return summary

    return name


def _render_response_content_blocks(
    content_blocks: list[dict] | None = None,
    response_text: str = '',
    tool_calls: list | None = None,
    max_blocks: int = 20,
) -> str:  # noqa: PLR0912,PLR0915
    """为 response payload 生成 HTML 内容块..

    Args:
        content_blocks: Structured response content blocks in API order.
        response_text: Legacy plain response text fallback.
        tool_calls: Legacy tool call fallback.
        max_blocks: Maximum number of blocks to render.

    Returns:
        HTML for response content cards.

    优先按 API 原始顺序渲染 text、thinking、tool_use;content_blocks 缺省时
    使用 response_text 和 tool_calls 作为不可用处理.
    """
    blocks = []
    block_index = 0

    if content_blocks:
        # 按 API 原始顺序渲染结构化 blocks.
        for block in content_blocks:
            if block_index >= max_blocks:
                break
            block_type = block.get('type', '')
            block_index += 1

            if block_type == 'text':
                content = block.get('content', '')
                if not content or not content.strip():
                    block_index -= 1
                    continue
                char_count = len(content.encode('utf-8'))
                preview = content[:500]
                blocks.append(
                    f'<article class="sd-content-block sd-content-block--text">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">text</span>'
                    f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                    f'</div>'
                    f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                    f'</article>'
                )

            elif block_type == 'thinking':
                content = block.get('content', '')
                if not content or not content.strip():
                    block_index -= 1
                    continue
                char_count = len(content.encode('utf-8'))
                preview = content[:500]
                blocks.append(
                    f'<article class="sd-content-block sd-content-block--thinking">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">thinking</span>'
                    f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                    f'</div>'
                    f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                    f'</article>'
                )

            elif block_type == 'tool_use':
                tool_id = (block.get('id', '') or '')[:12]
                tool_name = block.get('name', 'unknown')
                params = block.get('parameters', {}) or {}

                grid_rows = []
                grid_rows.append(f'<div class="key">name</div><div>{_html_escape(tool_name)}</div>')
                if params.get('file_path'):
                    file_path = _html_escape(_shorten_path(str(params['file_path'])))
                    grid_rows.append(
                        f'<div class="key">file_path</div><div>{file_path}</div>'
                    )
                if params.get('command'):
                    command = _html_escape(_shorten_path(str(params['command']))[:200])
                    grid_rows.append(
                        f'<div class="key">command</div><div>{command}</div>'
                    )
                # Unified command summary,用于 所有 tool types
                cmd_summary = _build_tool_command_summary(tool_name, params)
                if cmd_summary and cmd_summary != tool_name:
                    summary = _html_escape(_shorten_path(str(cmd_summary))[:200])
                    grid_rows.append(
                        f'<div class="key">summary</div><div>{summary}</div>'
                    )

                try:
                    raw_json = json.dumps(params, ensure_ascii=False, indent=2)[:500]
                except Exception:
                    raw_json = '{}'

                blocks.append(
                    f'<article class="sd-content-block sd-content-block--tool">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">tool_use · {_html_escape(tool_name)}</span>'
                    f'<span class="sd-block-meta">{_html_escape(tool_id)}</span>'
                    f'</div>'
                    f'<div class="sd-block-body">'
                    f'<div class="sd-tool-input-grid">{"".join(grid_rows)}</div>'
                    f'<div class="sd-json-inline">{_html_escape(raw_json)}</div>'
                    f'</div>'
                    f'</article>'
                )
    else:
        # 说明:Legacy fallback: text then tool_uses (no interleaving)
        if response_text and response_text.strip():
            block_index += 1
            char_count = len(response_text.encode('utf-8'))
            preview = response_text[:500]
            blocks.append(
                f'<article class="sd-content-block sd-content-block--text">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">text</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

        if tool_calls:
            for tc in tool_calls:
                if block_index >= max_blocks:
                    break
                block_index += 1
                tool_id = getattr(tc, 'tool_use_id', '')[:12] or ''
                tool_name = getattr(tc, 'name', 'unknown')
                params = getattr(tc, 'parameters', {}) or {}

                grid_rows = []
                grid_rows.append(f'<div class="key">name</div><div>{_html_escape(tool_name)}</div>')
                if params.get('file_path'):
                    file_path = _html_escape(_shorten_path(str(params['file_path'])))
                    grid_rows.append(
                        f'<div class="key">file_path</div><div>{file_path}</div>'
                    )
                if params.get('command'):
                    command = _html_escape(_shorten_path(str(params['command']))[:200])
                    grid_rows.append(
                        f'<div class="key">command</div><div>{command}</div>'
                    )
                # Unified command summary,用于 所有 tool types
                cmd_summary = _build_tool_command_summary(tool_name, params)
                if cmd_summary and cmd_summary != tool_name:
                    summary = _html_escape(_shorten_path(str(cmd_summary))[:200])
                    grid_rows.append(
                        f'<div class="key">summary</div><div>{summary}</div>'
                    )

                try:
                    raw_json = json.dumps(params, ensure_ascii=False, indent=2)[:500]
                except Exception:
                    raw_json = '{}'

                blocks.append(
                    f'<article class="sd-content-block sd-content-block--tool">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">tool_use · {_html_escape(tool_name)}</span>'
                    f'<span class="sd-block-meta">{_html_escape(tool_id)}</span>'
                    f'</div>'
                    f'<div class="sd-block-body">'
                    f'<div class="sd-tool-input-grid">{"".join(grid_rows)}</div>'
                    f'<div class="sd-json-inline">{_html_escape(raw_json)}</div>'
                    f'</div>'
                    f'</article>'
                )

    if not blocks:
        return '<div class="sd-payload-warning">Response 内容为空</div>'

    return f'<div class="sd-payload-block-list">{"".join(blocks)}</div>'


def _render_context_content_blocks(content_blocks: list[dict], max_blocks: int = 30) -> str:
    """说明:Render context (request) content as structured block cards.

    Args:
        content_blocks: Blocks returned by ``normalize_llm_content()``.
        max_blocks: Maximum number of blocks to render.

    Returns:
        HTML for context content cards.

    Takes blocks from normalize_llm_content() which parses request_full text
    into typed blocks: tool_result, file_code, file_markdown, plain_text, unknown.
    Each block becomes a styled card matching the response payload design.
    """
    cards = []
    block_index = 0

    for block in content_blocks:
        if block_index >= max_blocks:
            break

        kind = block.get('kind', 'unknown')
        title = block.get('title', '')
        subtitle = block.get('subtitle', '')
        content = block.get('content', '')

        if not content or not content.strip():
            continue

        block_index += 1

        # 说明:normalize_llm_content returns plain_text/file_* kinds;
        # 说明:tool results are identified by title prefix "Tool Result:"
        is_tool_result = title.startswith('Tool Result:')
        is_file = kind in ('file_code', 'file_markdown')

        if is_tool_result:
            char_count = len(content.encode('utf-8'))
            preview = content[:500]
            tool_id_display = title.replace('Tool Result: ', '')[:30]
            cards.append(
                f'<article class="sd-content-block sd-content-block--tool-result">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">tool_result</span>'
                f'<span class="sd-block-meta">{_html_escape(tool_id_display)}</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

        elif is_file:
            char_count = len(content.encode('utf-8'))
            preview = content[:500]
            file_display = title.replace('File: ', '') if title else 'file'
            lang = block.get('language', '')
            lang_display = f' · {lang}' if lang else ''
            cards.append(
                f'<article class="sd-content-block sd-content-block--file">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">file{lang_display}</span>'
                f'<span class="sd-block-meta" title="{_html_escape(file_display)}">'
                f'{_html_escape(file_display[:60])}</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

        else:
            # plain_text 或 unknown
            char_count = len(content.encode('utf-8'))
            preview = content[:500]
            block_title = title if title else (subtitle if subtitle else 'text')
            cards.append(
                f'<article class="sd-content-block sd-content-block--context-text">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">{_html_escape(block_title)}</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

    if not cards:
        return '<div class="sd-payload-warning">Context 内容为空</div>'

    return f'<div class="sd-payload-block-list">{"".join(cards)}</div>'
