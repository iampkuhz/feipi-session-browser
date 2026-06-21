"""LLM content block 归一化和 HTML 渲染..

Extracted from template_env.py to isolate LLM block rendering concerns.
Provides:
- normalize_llm_content(): split raw LLM text into structured blocks
- render_llm_blocks_html(): render blocks as HTML cards
- _content_parts_to_blocks(): bridge ContentPart to viewer dicts
- _parts_mode_from_raw(): raw string -> viewer-compatible dicts
"""

from __future__ import annotations

import html
import re

from session_browser.domain.content_part import ContentPart
from session_browser.domain.normalizer import normalize_message_content
from session_browser.web.renderers.markdown import render_markdown

# 说明:─── LLM content block normalization patterns ───────────────────────

_TOOL_RESULT_RE = re.compile(r'^(Tool result for (?:toolu_\S+|[^:]+):)\s*$', re.MULTILINE)
_FILE_MARKER_RE = re.compile(r'^#\s+([\w\-]+\.\w+)\s*$', re.MULTILINE)
_LINE_NUM_RE = re.compile(r'^\d+\t', re.MULTILINE)
_MIN_GUTTER_LINES = 3
_MIN_SPLIT_PARTS = 3
_TOOL_SPLIT_PARTS = 2


# 说明:─── Line number helpers ─────────────────────────────────────────────


def _detect_line_number_gutter(text: str) -> bool:
    """返回 True,如果 text looks like it has UI-added line numbers.

    Args:
        text: Text to inspect for a tab-separated line-number gutter.

    Returns:
        ``True`` when most lines start with ``N<TAB>``.
    """
    lines = text.splitlines()
    if len(lines) < _MIN_GUTTER_LINES:
        return False
    matched = sum(1 for line in lines if _LINE_NUM_RE.match(line))
    return matched > len(lines) * 0.6


def _strip_line_number_gutter(text: str) -> str:
    r"""Remove leading 'N\\t',来源于 each line,当 line numbers are detected.

    Args:
        text: Text that may contain a line-number gutter.

    Returns:
        Text without line-number prefixes when detected.
    """
    if not _detect_line_number_gutter(text):
        return text
    return re.sub(r'^\d+\t', '', text, flags=re.MULTILINE)


# 说明:─── Language inference ──────────────────────────────────────────────


def _infer_code_language(filename_hint: str = '', content: str = '') -> str | None:
    """推断 code block language,来源于 filename 或 content.

    Args:
        filename_hint: Optional filename used to infer the language from the extension.
        content: Optional code content used for lightweight language detection.

    Returns:
        Language identifier, or ``None`` when unknown.
    """
    filename_hint = (filename_hint or '').lower()
    lang_map = {
        '.py': 'python',
        '.ts': 'typescript',
        '.tsx': 'tsx',
        '.js': 'javascript',
        '.jsx': 'jsx',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.json': 'json',
        '.sh': 'bash',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.rb': 'ruby',
        '.rs': 'rust',
        '.go': 'go',
        '.java': 'java',
        '.cpp': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.php': 'php',
        '.html': 'html',
        '.css': 'css',
        '.scss': 'scss',
        '.sql': 'sql',
        '.xml': 'xml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'ini',
        '.conf': 'ini',
        '.env': 'bash',
        '.Dockerfile': 'dockerfile',
        'Dockerfile': 'dockerfile',
        '.makefile': 'makefile',
        'Makefile': 'makefile',
        '.proto': 'protobuf',
        '.graphql': 'graphql',
    }
    for ext, lang in lang_map.items():
        if filename_hint.endswith(ext):
            return lang
    stripped = content.lstrip()
    if stripped.startswith(('def ', 'class ', 'from ', 'async def ')) or (
        stripped.startswith('import ') and not stripped.startswith('import {')
    ):
        return 'python'
    if stripped.startswith(('const ', 'let ', 'var ', 'function ', 'export ', 'import {')):
        return 'typescript'
    return None


# 说明:─── Block builders ──────────────────────────────────────────────────


def _make_plain_block(text: str, title: str = '') -> dict:
    """创建 一个 plain text block.

    Args:
        text: Block content.
        title: Optional block title.

    Returns:
        Viewer-compatible block dictionary.
    """
    if not text:
        return {
            'kind': 'unknown',
            'title': title,
            'subtitle': '',
            'language': '',
            'content': text,
            'raw': text,
        }
    lang = _infer_code_language(content=text)
    return {
        'kind': 'plain_text',
        'title': title,
        'subtitle': '',
        'language': lang or '',
        'content': text,
        'raw': text,
    }


def _make_block_from_content(text: str, title: str = '') -> dict:
    """创建 一个 block, trying to detect,如果 it's code 或 markdown.

    Args:
        text: Block content.
        title: Optional block title.

    Returns:
        Viewer-compatible block dictionary.
    """
    lang = _infer_code_language(content=text)
    if lang:
        return {
            'kind': 'file_code',
            'title': title,
            'subtitle': '',
            'language': lang,
            'content': text,
            'raw': text,
        }
    return {
        'kind': 'plain_text',
        'title': title,
        'subtitle': '',
        'language': '',
        'content': text,
        'raw': text,
    }


# 说明:─── File marker detection ───────────────────────────────────────────


def _detect_file_marker(text: str) -> str | None:
    """检查,如果 text starts,使用 一个 file-like heading like '# AGENTS.md'.

    Args:
        text: Text to inspect for a file heading.

    Returns:
        Detected filename, or ``None`` when no marker exists.
    """
    first_lines = text.split('\n')[:5]
    for line in first_lines:
        stripped = line.strip()
        m = re.match(r'^#\s+([\w\-\./]+\.\w+)\s*$', stripped)
        if m:
            return m.group(1)
    return None


def _try_split_files(text: str) -> list[dict]:
    """说明:Try to split text by file heading markers.

    Args:
        text: Text to split into file-marked blocks.

    Returns:
        List of blocks if split succeeds, empty list otherwise.
    """
    file_header_re = re.compile(
        r'^(#\s+[\w\-\./]+\.(?:md|markdown|txt|py|ts|tsx|js|jsx|json|yaml|yml|sh|bash|rb|rs|go|java|cpp|c|css|html|xml|toml|ini|cfg|conf|sql|graphql|proto))\s*$',
        re.MULTILINE,
    )

    parts = file_header_re.split(text)
    if len(parts) < _MIN_SPLIT_PARTS:
        return []

    blocks = []
    i = 0
    if parts[0].strip():
        blocks.append(_make_plain_block(parts[0].strip(), 'Message content'))
        i = 0
    else:
        i = 0

    while i + 1 < len(parts):
        header = parts[i + 1]
        content = parts[i + 2] if i + 2 < len(parts) else ''
        filename = re.sub(r'^#\s+', '', header).strip()

        content_stripped = content.strip()
        if not content_stripped:
            i += 2
            continue

        content_with_heading = f'# {filename}\n{content_stripped}'

        lang = _infer_code_language(filename, content_with_heading)
        if lang:
            blocks.append(
                {
                    'kind': 'file_code',
                    'title': f'File: {filename}',
                    'subtitle': '',
                    'language': lang,
                    'content': content_with_heading,
                    'raw': content_with_heading,
                }
            )
        else:
            blocks.append(
                {
                    'kind': 'file_markdown',
                    'title': f'File: {filename}',
                    'subtitle': '',
                    'language': '',
                    'content': content_with_heading,
                    'raw': content_with_heading,
                }
            )
        i += 2

    return blocks if blocks else []


# 说明:─── LLM content normalization ───────────────────────────────────────


def normalize_llm_content(input: str) -> list[dict]:  # noqa: A002,PLR0912
    """拆分 raw LLM request/response string,转换为 structured content blocks.

    Args:
        input: Raw LLM request or response string.

    Returns:
        List of dicts with keys: kind, title, subtitle, language, content, and raw.
    """
    if not input:
        return []

    text = input

    has_line_numbers = _detect_line_number_gutter(text)
    clean_text = _strip_line_number_gutter(text) if has_line_numbers else text

    blocks: list[dict] = []

    tool_parts = _TOOL_RESULT_RE.split(clean_text)

    if len(tool_parts) > _TOOL_SPLIT_PARTS:
        pre_text = tool_parts[0].strip()
        if pre_text:
            blocks.append(_make_plain_block(pre_text, 'Message preamble'))

        i = 1
        while i + 1 < len(tool_parts):
            tool_id_match = tool_parts[i]
            content_part = tool_parts[i + 1].strip()
            tool_id = tool_id_match.replace('Tool result for ', '').rstrip(':')

            file_blocks = _try_split_files(content_part)
            if file_blocks:
                first = file_blocks[0]
                first['title'] = f'Tool Result: {tool_id}' + (
                    f' - {first["title"]}' if first.get('title') else ''
                )
                blocks.extend(file_blocks)
            elif content_part:
                blocks.append(_make_block_from_content(content_part, f'Tool Result: {tool_id}'))

            i += 2

        if len(tool_parts) % 2 == 0:
            trailing = tool_parts[-1].strip()
            if trailing:
                blocks.append(_make_plain_block(trailing, 'Trailing text'))
    else:
        file_blocks = _try_split_files(clean_text)
        if file_blocks and len(file_blocks) > 1:
            blocks.extend(file_blocks)
        elif clean_text:
            file_hint = _detect_file_marker(clean_text)
            if file_hint:
                lang = _infer_code_language(file_hint, clean_text)
                if lang:
                    blocks.append(
                        {
                            'kind': 'file_code',
                            'title': f'File: {file_hint}',
                            'subtitle': '',
                            'language': lang,
                            'content': clean_text,
                            'raw': text,
                        }
                    )
                else:
                    blocks.append(
                        {
                            'kind': 'file_markdown',
                            'title': f'File: {file_hint}',
                            'subtitle': '',
                            'language': '',
                            'content': clean_text,
                            'raw': text,
                        }
                    )
            else:
                blocks.append(
                    {
                        'kind': 'plain_text',
                        'title': '',
                        'subtitle': '',
                        'language': '',
                        'content': clean_text,
                        'raw': text,
                    }
                )

    if not blocks:
        blocks.append(
            {
                'kind': 'unknown',
                'title': '',
                'subtitle': '',
                'language': '',
                'content': text,
                'raw': text,
            }
        )

    return blocks


# 说明:─── HTML escape ─────────────────────────────────────────────────────


def _html_escape(text: str) -> str:
    """转义 HTML entities.

    Args:
        text: Text to escape.

    Returns:
        HTML-escaped text.
    """
    return html.escape(text)


# 说明:─── Render LLM blocks as HTML ───────────────────────────────────────


def render_llm_blocks_html(input: str | list[dict]) -> str:  # noqa: A002
    """Accept 一个 raw string 或 pre-normalized blocks, render as HTML cards.

    Args:
        input: Raw LLM text or pre-normalized block dictionaries.

    Returns:
        Rendered HTML for LLM blocks.

    When given a string (the common template case), normalizes it into
    content blocks first.  When given a list[dict], renders directly.
    """
    if isinstance(input, str):
        blocks = normalize_llm_content(input)
    elif isinstance(input, list):
        blocks = input
    else:
        blocks = []

    if not blocks:
        return '<p class="text-muted">(No content available)</p>'

    parts = []
    for block in blocks:
        kind = block.get('kind', 'unknown')
        title = block.get('title', '')
        subtitle = block.get('subtitle', '')
        language = block.get('language', '')
        content = block.get('content', '')

        header_parts = []
        if title:
            header_parts.append(_html_escape(title))
        if subtitle:
            header_parts.append(_html_escape(subtitle))
        if language and kind == 'file_code':
            header_parts.append(f'<code class="block-lang-tag">{_html_escape(language)}</code>')

        header_html = ''
        if header_parts:
            header_html = '<div class="llm-block__header">' + ' '.join(header_parts) + '</div>'

        if kind == 'file_code':
            lang_attr = f' class="language-{_html_escape(language)}"' if language else ''
            content_html = f'<pre><code{lang_attr}>{_html_escape(content)}</code></pre>'
        elif kind in {'file_markdown', 'plain_text'}:
            content_html = render_markdown(content)
        else:
            content_html = render_markdown(content)

        parts.append(
            f'<div class="llm-block">{header_html}'
            f'<div class="llm-block__content">{content_html}</div></div>'
        )

    return '\n'.join(parts)


# 说明:─── Content parts bridge ────────────────────────────────────────────


def _content_parts_to_blocks(parts: list) -> list[dict]:
    """转换 [ContentPart, ...] to 该 dict format 该 viewer template expects.

    Args:
        parts: ContentPart objects, dictionaries, or fallback values.

    Returns:
        Viewer-compatible block dictionaries.

    Maps ContentPart fields:
    - part_type -> kind
    - content -> content
    - language -> language
    - context_type -> context_type (I-08)
    - title -> title (I-08)
    """
    blocks = []
    for part in parts:
        if isinstance(part, ContentPart):
            block = {
                'kind': part.part_type,
                'content': part.content,
                'language': part.language or '',
                'title': getattr(part, 'title', '') or '',
                'context_type': getattr(part, 'context_type', '') or '',
                'content_bytes': len(part.content.encode('utf-8')) if part.content else 0,
                'token_hint': 0,
            }
            blocks.append(block)
        elif isinstance(part, dict):
            block = {
                'kind': part.get('part_type', 'unknown'),
                'content': part.get('content', ''),
                'language': part.get('language', ''),
                'title': part.get('title', ''),
                'context_type': part.get('context_type', ''),
                'content_bytes': len(part.get('content', '').encode('utf-8')),
                'token_hint': 0,
            }
            blocks.append(block)
        else:
            block = {
                'kind': 'unknown',
                'content': str(part) if part else '',
                'language': '',
                'title': '',
                'context_type': '',
                'content_bytes': 0,
                'token_hint': 0,
            }
            blocks.append(block)

    for block in blocks:
        block.setdefault('kind', 'unknown')
        block.setdefault('content', '')
        block.setdefault('language', '')
        block.setdefault('title', '')
        block.setdefault('context_type', '')
        block.setdefault('content_bytes', 0)
        block.setdefault('token_hint', 0)
    return blocks


def _parts_mode_from_raw(text: str) -> list[dict]:
    """说明:Bridge: raw string -> normalize via new normalizer -> viewer-compatible dicts.

    Args:
        text: Raw message content.

    Returns:
        Viewer-compatible block dictionaries.

    Usage in viewer.html: ``{% set blocks = content | parts_mode_from_raw %}``
    """
    if not text:
        return []
    parts = normalize_message_content(text)
    return _content_parts_to_blocks(parts)
