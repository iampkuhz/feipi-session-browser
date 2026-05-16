"""HTTP server and routes for session-browser.

Uses Python's built-in http.server + jinja2 templates.
No external web framework needed for MVP.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import jinja2
from markdown_it import MarkdownIt

from session_browser.index.indexer import (
    _get_connection,
    get_dashboard_stats,
    list_sessions,
    count_sessions,
    list_projects,
    get_project_stats,
    get_session,
    get_trend_data,
    list_agents,
)
from session_browser.index.metrics import (
    get_token_breakdown,
    get_model_distribution,
    get_agent_distribution,
    compute_derived_metrics,
    compute_aggregate_metrics,
    compute_agent_efficiency,
)
from session_browser.index.anomalies import (
    detect_all_anomalies,
    get_needs_attention,
    enrich_sessions_with_anomalies,
    AnomalyType,
)
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
)

logger = logging.getLogger("session_browser.web")

# Template directory
_TEMPLATE_DIR = Path(__file__).parent / "templates"

from session_browser.web.safe_render import register_filters as _register_safe_filters, safe_json_display
from session_browser.domain.normalizer import normalize_message_content
from session_browser.domain.content_part import ContentPart

_template_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)
_register_safe_filters(_template_env)


def _get_repo_root(cwd: str | None = None) -> str | None:
    """Detect git repo root from cwd. Returns None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or os.getcwd(),
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

# Cache the repo root at server startup
_REPO_ROOT = _get_repo_root()

# Per-request repo root (set before template render)
_SESSION_REPO_ROOT: str | None = None

# Markdown renderer (shared instance) — CommonMark + table extension for basic table support.
# GFM plugins (strikethrough, tasklist) would require mdit_py_plugins — optional dependency.
_md = MarkdownIt().enable("table")


def _md_filter(text: str) -> str:
    """Render markdown to HTML. Escapes raw HTML in input to prevent XSS."""
    if not text:
        return ""
    import html
    escaped = html.escape(text)
    return _md.render(escaped)


# ─── LLM content block normalization ──────────────────────────────────

# Heuristic pattern for tool result boundaries:
# "Tool result for <tool_id>:" at the start of a line
_TOOL_RESULT_RE = re.compile(r'^(Tool result for (?:toolu_\S+|[^:]+):)\s*$', re.MULTILINE)

# Heuristic for file content markers: "# <filename>" at start of a line
# Only match if it looks like a file path/name, not a generic heading
_FILE_MARKER_RE = re.compile(r'^#\s+([\w\-]+\.\w+)\s*$', re.MULTILINE)

# Heuristic for presentation-style line numbers:
# A line starts with digits followed by a tab, and this pattern is consistent across many lines.
# We only strip when >60% of lines match, to avoid breaking real ordered lists.
_LINE_NUM_RE = re.compile(r'^\d+\t', re.MULTILINE)


def _detect_line_number_gutter(text: str) -> bool:
    """Return True if text looks like it has UI-added line numbers (tab-separated gutter)."""
    lines = text.splitlines()
    if len(lines) < 3:
        return False
    matched = sum(1 for line in lines if _LINE_NUM_RE.match(line))
    return matched > len(lines) * 0.6


def _strip_line_number_gutter(text: str) -> str:
    """Remove leading 'N\t' from each line when line numbers are detected."""
    if not _detect_line_number_gutter(text):
        return text
    return re.sub(r'^\d+\t', '', text, flags=re.MULTILINE)


def _infer_code_language(filename_hint: str = "", content: str = "") -> str | None:
    """Infer code block language from filename or content. Returns None for markdown."""
    filename_hint = (filename_hint or "").lower()
    md_extensions = {".md", ".markdown", ".mdx"}
    lang_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
        ".jsx": "jsx", ".yaml": "yaml", ".yml": "yaml", ".json": "json",
        ".sh": "bash", ".bash": "bash", ".zsh": "zsh", ".rb": "ruby",
        ".rs": "rust", ".go": "go", ".java": "java", ".cpp": "cpp",
        ".c": "c", ".cs": "csharp", ".swift": "swift", ".kt": "kotlin",
        ".scala": "scala", ".php": "php", ".html": "html", ".css": "css",
        ".scss": "scss", ".sql": "sql", ".xml": "xml", ".toml": "toml",
        ".ini": "ini", ".cfg": "ini", ".conf": "ini", ".env": "bash",
        ".Dockerfile": "dockerfile", "Dockerfile": "dockerfile",
        ".makefile": "makefile", "Makefile": "makefile",
        ".proto": "protobuf", ".graphql": "graphql",
    }
    for ext, lang in lang_map.items():
        if filename_hint.endswith(ext):
            return lang
    # Heuristic: if content looks like code (starts with common code patterns)
    # Check more specific patterns first (e.g. "import {" before "import ")
    stripped = content.lstrip()
    if stripped.startswith(("def ", "class ", "from ", "async def ")) or stripped.startswith("import ") and not stripped.startswith("import {"):
        return "python"
    if stripped.startswith(("const ", "let ", "var ", "function ", "export ", "import {")):
        return "typescript"
    return None


def normalize_llm_content(input: str) -> list[dict]:
    """Split raw LLM request/response string into structured content blocks.

    Returns a list of dicts with keys:
    - kind: 'tool_result' | 'file_code' | 'file_markdown' | 'plain_text' | 'unknown'
    - title: optional header text (e.g. tool_id, filename)
    - subtitle: optional subtitle
    - language: optional code language hint
    - content: the actual content string (clean, no UI line numbers for non-raw)
    - raw: the original content string (unchanged, for Raw tab reference)
    """
    if not input:
        return []

    text = input

    # Heuristic: if the text has presentation-style line numbers, strip them
    # for the rendered content but keep the original for raw display.
    has_line_numbers = _detect_line_number_gutter(text)
    clean_text = _strip_line_number_gutter(text) if has_line_numbers else text

    blocks: list[dict] = []

    # Try to split by "Tool result for <id>:" boundaries
    tool_parts = _TOOL_RESULT_RE.split(clean_text)
    # split() returns: [before, match_group1, match_group2, after, ...]
    # Odd indices are the captured group (tool_id), even are the content.

    if len(tool_parts) > 2:
        # We found tool result boundaries — parse structured blocks
        pre_text = tool_parts[0].strip()
        if pre_text:
            blocks.append(_make_plain_block(pre_text, "Message preamble"))

        i = 1
        while i + 1 < len(tool_parts):
            tool_id_match = tool_parts[i]
            content_part = tool_parts[i + 1].strip()
            # Extract tool_id from "Tool result for <id>:"
            tool_id = tool_id_match.replace("Tool result for ", "").rstrip(":")

            # Try to detect file content within this tool result
            file_blocks = _try_split_files(content_part)
            if file_blocks:
                # Prepend tool ID to the first block's title
                first = file_blocks[0]
                first["title"] = f"Tool Result: {tool_id}" + (f" · {first['title']}" if first.get("title") else "")
                blocks.extend(file_blocks)
            elif content_part:
                blocks.append(_make_block_from_content(content_part, f"Tool Result: {tool_id}"))

            i += 2

        # Any trailing text after last tool result
        if len(tool_parts) % 2 == 0:
            trailing = tool_parts[-1].strip()
            if trailing:
                blocks.append(_make_plain_block(trailing, "Trailing text"))
    else:
        # No tool result boundaries — try file-level splitting
        file_blocks = _try_split_files(clean_text)
        if file_blocks and len(file_blocks) > 1:
            blocks.extend(file_blocks)
        elif clean_text:
            # Single block — check if it looks like a file
            file_hint = _detect_file_marker(clean_text)
            if file_hint:
                lang = _infer_code_language(file_hint, clean_text)
                if lang:
                    blocks.append({
                        "kind": "file_code",
                        "title": f"File: {file_hint}",
                        "subtitle": "",
                        "language": lang,
                        "content": clean_text,
                        "raw": text,
                    })
                else:
                    blocks.append({
                        "kind": "file_markdown",
                        "title": f"File: {file_hint}",
                        "subtitle": "",
                        "language": "",
                        "content": clean_text,
                        "raw": text,
                    })
            else:
                blocks.append({
                    "kind": "plain_text",
                    "title": "",
                    "subtitle": "",
                    "language": "",
                    "content": clean_text,
                    "raw": text,
                })

    # Ensure at least one block
    if not blocks:
        blocks.append({
            "kind": "unknown",
            "title": "",
            "subtitle": "",
            "language": "",
            "content": text,
            "raw": text,
        })

    return blocks


def _make_plain_block(text: str, title: str = "") -> dict:
    """Create a plain text block."""
    if not text:
        return {"kind": "unknown", "title": title, "subtitle": "", "language": "", "content": text, "raw": text}
    lang = _infer_code_language(content=text)
    return {
        "kind": "plain_text",
        "title": title,
        "subtitle": "",
        "language": lang or "",
        "content": text,
        "raw": text,
    }


def _make_block_from_content(text: str, title: str = "") -> dict:
    """Create a block, trying to detect if it's code or markdown."""
    lang = _infer_code_language(content=text)
    if lang:
        return {
            "kind": "file_code",
            "title": title,
            "subtitle": "",
            "language": lang,
            "content": text,
            "raw": text,
        }
    return {
        "kind": "plain_text",
        "title": title,
        "subtitle": "",
        "language": "",
        "content": text,
        "raw": text,
    }


def _detect_file_marker(text: str) -> str | None:
    """Check if text starts with a file-like heading like '# AGENTS.md'."""
    first_lines = text.split("\n")[:5]
    for line in first_lines:
        stripped = line.strip()
        m = re.match(r'^#\s+([\w\-\./]+\.\w+)\s*$', stripped)
        if m:
            return m.group(1)
    return None


def _try_split_files(text: str) -> list[dict]:
    """Try to split text by file heading markers (lines like '# filename.ext').
    Returns list of blocks if split succeeds, empty list otherwise."""
    # Split on lines that look like file headings: # filename.ext
    file_header_re = re.compile(r'^(#\s+[\w\-\./]+\.(?:md|markdown|txt|py|ts|tsx|js|jsx|json|yaml|yml|sh|bash|rb|rs|go|java|cpp|c|css|html|xml|toml|ini|cfg|conf|sql|graphql|proto))\s*$', re.MULTILINE)

    parts = file_header_re.split(text)
    if len(parts) < 3:
        return []

    blocks = []
    i = 0
    # Check for pre-text before first file header
    if parts[0].strip():
        blocks.append(_make_plain_block(parts[0].strip(), "Message content"))
        i = 0
    else:
        i = 0

    while i + 1 < len(parts):
        header = parts[i + 1]  # e.g. "# AGENTS.md"
        content = parts[i + 2] if i + 2 < len(parts) else ""
        filename = re.sub(r'^#\s+', '', header).strip()

        content_stripped = content.strip()
        if not content_stripped:
            i += 2
            continue

        # Prepend the filename heading to content so the file marker is preserved
        content_with_heading = f"# {filename}\n{content_stripped}"

        lang = _infer_code_language(filename, content_with_heading)
        if lang:
            blocks.append({
                "kind": "file_code",
                "title": f"File: {filename}",
                "subtitle": "",
                "language": lang,
                "content": content_with_heading,
                "raw": content_with_heading,
            })
        else:
            blocks.append({
                "kind": "file_markdown",
                "title": f"File: {filename}",
                "subtitle": "",
                "language": "",
                "content": content_with_heading,
                "raw": content_with_heading,
            })
        i += 2

    return blocks if blocks else []


def render_llm_blocks_html(input: str | list[dict]) -> str:
    """Accept a raw string or pre-normalized blocks, render as HTML cards.

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
        kind = block.get("kind", "unknown")
        title = block.get("title", "")
        subtitle = block.get("subtitle", "")
        language = block.get("language", "")
        content = block.get("content", "")

        # Build header
        header_parts = []
        if title:
            header_parts.append(_html_escape(title))
        if subtitle:
            header_parts.append(_html_escape(subtitle))
        if language and kind == "file_code":
            header_parts.append(f'<code class="block-lang-tag">{_html_escape(language)}</code>')

        header_html = ""
        if header_parts:
            header_html = '<div class="llm-block__header">' + " ".join(header_parts) + '</div>'

        # Build content based on kind
        if kind == "file_code":
            lang_attr = f' class="language-{_html_escape(language)}"' if language else ''
            content_html = f'<pre><code{lang_attr}>{_html_escape(content)}</code></pre>'
        elif kind == "file_markdown" or kind == "plain_text":
            # Render markdown content through the markdown renderer
            import html
            escaped = html.escape(content)
            content_html = _md.render(escaped)
        else:
            # unknown or tool_result — try markdown rendering
            import html
            escaped = html.escape(content)
            content_html = _md.render(escaped)

        parts.append(
            f'<div class="llm-block">{header_html}<div class="llm-block__content">{content_html}</div></div>'
        )

    return "\n".join(parts)


def _html_escape(text: str) -> str:
    """Escape HTML entities."""
    import html
    return html.escape(text)


def _format_bytes(n) -> str:
    """Format byte count to human-readable string."""
    if n is None or n == 0:
        return "0 B"
    n = int(n)
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.1f} GB"


# Register template filters
_template_env.filters["format_number"] = lambda n: (
    f"{n / 1_000_000:.1f}M" if n >= 1_000_000
    else f"{n / 1_000:.1f}K" if n >= 1_000
    else str(n)
)
_template_env.filters["format_number_short"] = lambda n: (
    f"{n / 1_000_000:.1f}M" if n >= 1_000_000
    else f"{n / 1_000:.0f}K" if n >= 1_000
    else str(n)
)
_template_env.globals["max"] = max
_template_env.filters["truncate_path"] = lambda path: (
    _truncate_path(path)
)
_template_env.filters["relative_to_repo"] = lambda path: (
    _relative_to_repo(path)
)
_template_env.filters["format_duration"] = lambda seconds: (
    f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}min" if seconds >= 3600
    else f"{int(seconds // 60)}min {int(seconds % 60)}s" if seconds >= 60
    else f"{int(seconds)}s"
)
_template_env.filters["format_bytes"] = _format_bytes
_template_env.filters["relative_time"] = lambda iso_str: (
    _relative_time(iso_str)
)
_template_env.filters["local_time"] = lambda iso_str: (
    _to_local_time(iso_str)
)
_template_env.filters["urlencode"] = urllib.parse.quote
_template_env.filters["urldecode"] = urllib.parse.unquote
_template_env.filters["markdown"] = _md_filter
_template_env.filters["render_llm_blocks_html"] = render_llm_blocks_html
_template_env.filters["tojson_safe"] = lambda v: safe_json_display(v)
_template_env.filters["strip_line_numbers"] = lambda text: (
    re.sub(r'^\d+\t', '', text, flags=re.MULTILINE)
    if text and re.search(r'^\d+\t', text, flags=re.MULTILINE)
    else text
)
def _renumber_lines(text: str) -> str:
    if not text or not re.search(r'^\d+\t', text, flags=re.MULTILINE):
        return text
    tab = '\t'
    lines = []
    for i, line in enumerate(text.splitlines()):
        cleaned = re.sub(r'^\d+\t', '', line)
        lines.append(f"{i + 1}{tab}{cleaned}")
    return "\n".join(lines) + "\n"

_template_env.filters["renumber_lines"] = _renumber_lines
_template_env.filters["normalize_llm_content"] = normalize_llm_content


def _content_parts_to_blocks(parts: list) -> list[dict]:
    """Convert [ContentPart, ...] to the dict format the viewer template expects.

    Maps ContentPart fields:
    - part_type -> kind
    - content -> content
    - language -> language
    - context_type -> context_type (I-08)
    - title -> title (I-08)
    - content_bytes -> content_bytes (I-08)
    - token_hint -> token_hint (I-08)
    - Adds fallback title from context_type or part_type if missing.
    """
    blocks = []
    for part in parts:
        if isinstance(part, ContentPart):
            kind = part.part_type
            title = part.title or part.metadata.get('title', '')
            if not title:
                # Derive title from context_type if available.
                ctx = part.context_type
                if ctx:
                    title = ctx.replace('_', ' ').capitalize()
                else:
                    title = kind.capitalize()
            blocks.append({
                'kind': kind,
                'title': title,
                'subtitle': '',
                'language': part.language or '',
                'content': part.content,
                'raw': part.content,
                'context_type': part.context_type,
                'content_bytes': part.content_bytes,
                'token_hint': part.token_hint,
            })
        elif isinstance(part, dict):
            # Already a dict (backward compat) — ensure new fields exist.
            block = dict(part)
            block.setdefault('context_type', '')
            block.setdefault('content_bytes', 0)
            block.setdefault('token_hint', 0)
            blocks.append(block)
    return blocks


_template_env.filters["content_parts"] = _content_parts_to_blocks


def _parts_mode_from_raw(text: str) -> list[dict]:
    """Bridge: raw string -> normalize via new normalizer -> viewer-compatible dicts.

    Usage in viewer.html: ``{% set blocks = content | parts_mode_from_raw %}``
    """
    if not text:
        return []
    parts = normalize_message_content(text)
    return _content_parts_to_blocks(parts)


_template_env.filters["parts_mode_from_raw"] = _parts_mode_from_raw


def _relative_paths_in_json(obj: any) -> any:
    """Recursively replace file_path values in a dict with relative-to-repo paths."""
    if isinstance(obj, dict):
        return {
            k: (_relative_to_repo(v) if k == "file_path" and isinstance(v, str) else _relative_paths_in_json(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_relative_paths_in_json(item) for item in obj]
    return obj


def _tojson_repo_html(v: Any, indent: int | None = None) -> str:
    """tojson_repo with HTML escaping — safe for <pre> embedding."""
    if not v:
        return "null"
    raw = json.dumps(_relative_paths_in_json(v), indent=indent, ensure_ascii=False)
    import html as _html
    return _html.escape(raw)

_template_env.filters["tojson_repo"] = _tojson_repo_html


def _truncate_path(path: str) -> str:
    """Truncate a long path, keeping first and last segments."""
    if not path or len(path) <= 40:
        return path or ""
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return path[:40] + "…"
    # Keep first 2 and last 2 segments
    return "/".join(parts[:2]) + "/…/" + "/".join(parts[-2:])


def _relative_to_repo(path: str) -> str:
    """If path is within the current session's git repo, return relative path.
    Falls back to server-level _REPO_ROOT, then absolute path."""
    if not path:
        return path or ""
    repo_root = _SESSION_REPO_ROOT or _REPO_ROOT
    if not repo_root:
        return path
    try:
        abs_path = os.path.abspath(path)
        if abs_path.startswith(repo_root + os.sep) or abs_path == repo_root:
            return os.path.relpath(abs_path, repo_root)
    except Exception:
        pass
    return path


def _relative_time(iso_str: str) -> str:
    """Convert ISO8601 to relative time string."""
    if not iso_str:
        return ""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        days = delta.days
        if days > 30:
            return f"{days // 30}mo ago"
        if days > 0:
            return f"{days}d ago"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        minutes = delta.seconds // 60
        return f"{minutes}m ago"
    except (ValueError, TypeError):
        return iso_str[:16]


def _to_local_time(iso_str: str) -> str:
    """Convert UTC ISO8601 timestamp to local-time display string.

    E.g. \"2026-05-12T06:20:29+00:00\" -> \"2026-05-12 14:20:29\" (Beijing UTC+8).
    If already in local time (has non-zero offset), just reformat.
    """
    if not iso_str:
        return ""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(iso_str)[:19].replace("T", " ")


def _build_rounds(
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    session_input_tokens: int,
    session_output_tokens: int,
    session_cached_tokens: int,
    session_cache_write_tokens: int,
    agent: str,
) -> list[ConversationRound]:
    """Group messages into conversation rounds and compute token ratios.

    Each assistant LLM response becomes its own round. Consecutive user
    messages before an assistant response are merged; assistant responses that
    happen during tool loops get an empty user_msg so repeated tool iterations
    stay visible instead of collapsing into one giant round.

    Token ratio is derived from the assistant message's usage data (Claude, Qoder)
    or set to zero when usage data is unavailable (Codex).
    """
    if not messages:
        return []

    total_session_tokens = session_input_tokens + session_output_tokens + session_cached_tokens + session_cache_write_tokens

    # Step 1: Render markdown and pair each assistant LLM response into its
    # own round. Tool-result pseudo-user messages are filtered in sources, so
    # consecutive assistant responses are expected during tool loops.
    pending_users: list[ChatMessage] = []
    rounds: list[ConversationRound] = []
    for msg in messages:
        msg.content_html = _md_filter(msg.content)

        if msg.role == "user":
            pending_users.append(msg)
            continue

        if msg.role == "assistant":
            if pending_users:
                merged_user = _merge_messages(pending_users)
                pending_users = []
            else:
                merged_user = ChatMessage(role="user", content="", timestamp=msg.timestamp)
            rounds.append(
                _make_round(merged_user, msg, tool_calls,
                            total_session_tokens, agent, session_cache_write_tokens)
            )

    if pending_users:
        rounds.append(
            _make_round(
                _merge_messages(pending_users),
                ChatMessage(role="assistant", content="", timestamp=""),
                tool_calls,
                total_session_tokens,
                agent,
                session_cache_write_tokens,
            )
        )

    return rounds


def _merge_messages(msgs: list[ChatMessage]) -> ChatMessage:
    """Merge a list of same-role messages into one ChatMessage."""
    if len(msgs) == 1:
        return msgs[0]

    content = "\n\n".join(m.content for m in msgs if m.content)
    content_html = "\n\n".join(m.content_html for m in msgs if m.content_html)
    # Use the latest timestamp
    timestamp = msgs[-1].timestamp
    # Merge tool_calls from all messages
    all_tool_calls = []
    for m in msgs:
        all_tool_calls.extend(m.tool_calls)
    # Merge usage (take the last non-None)
    usage = None
    for m in msgs:
        if m.usage:
            usage = m.usage

    return ChatMessage(
        role=msgs[0].role,
        content=content,
        timestamp=timestamp,
        model=msgs[-1].model,
        tool_calls=all_tool_calls,
        usage=usage,
        content_html=content_html,
        llm_call_id=msgs[-1].llm_call_id,
        llm_status=msgs[-1].llm_status,
    )


def _make_round(
    user_msg: ChatMessage,
    assistant_msg: ChatMessage,
    all_tool_calls: list[ToolCall],
    total_session_tokens: int,
    agent: str,
    session_cache_write_tokens: int = 0,
) -> ConversationRound:
    """Create a ConversationRound with token calculation and tool call matching."""
    # Match tool calls from assistant message
    round_tool_calls = []
    if assistant_msg.tool_calls:
        matched_ids = {
            mt.get("id")
            for mt in assistant_msg.tool_calls
            if mt.get("id")
        }
        for tc in all_tool_calls:
            if tc.tool_use_id and tc.tool_use_id in matched_ids:
                round_tool_calls.append(tc)

    # Token info (Claude and Qoder both have per-message usage data)
    round_input = 0
    round_output = 0
    round_cached = 0
    round_cache_write = 0
    if agent in ("claude_code", "qoder") and assistant_msg.usage:
        round_input = assistant_msg.usage.get("input_tokens", 0)
        round_output = assistant_msg.usage.get("output_tokens", 0)
        round_cached = assistant_msg.usage.get("cache_read_input_tokens", 0)
        round_cache_write = assistant_msg.usage.get("cache_creation_input_tokens", 0)

    round_total = round_input + round_output + round_cached + round_cache_write
    token_ratio = round_total / total_session_tokens if total_session_tokens > 0 else 0
    direct_llm_calls = 1 if assistant_msg.llm_call_id else 0
    nested_llm_calls = sum(tc.llm_call_count for tc in round_tool_calls)
    nested_llm_errors = sum(tc.llm_error_count for tc in round_tool_calls)

    return ConversationRound(
        user_msg=user_msg,
        assistant_msg=assistant_msg,
        tool_calls=round_tool_calls,
        total_tokens=round_total,
        token_ratio=token_ratio,
        llm_call_count=direct_llm_calls + nested_llm_calls,
        llm_error_count=nested_llm_errors,
    )


def _derive_prompt_preview(
    msg: ChatMessage,
    round_tool_calls: list[ToolCall],
    prev_call_tools: list[ToolCall],
    round: ConversationRound,
    messages: list[ChatMessage],
    call_index_in_round: int,
) -> str:
    """Derive a human-readable hint for what was sent as prompt to this LLM call.

    Returns a short string (≤120 chars) summarising the prompt context.
    """
    # First call in round → show user message
    if call_index_in_round == 0:
        user_text = round.user_msg.content[:80] if round.user_msg.content else ""
        if user_text:
            return f"User: {user_text}"

    # Subsequent calls → tool results from prior call(s)
    if prev_call_tools:
        tool_names = ", ".join(tc.name for tc in prev_call_tools[:3])
        suffix = f" +{len(prev_call_tools) - 3}" if len(prev_call_tools) > 3 else ""
        return f"{len(prev_call_tools)} tool results: {tool_names}{suffix}"

    return ""


def _build_llm_calls(
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    rounds: list[ConversationRound],
    subagent_runs: list[dict],
) -> list[LLMCall]:
    """Extract individual LLMCall objects (one per LLM turn).

    Main agent: one call per assistant message.
    Subagent: one call per internal turn (so the LLM Calls tab shows all).
    """
    llm_calls: list[LLMCall] = []

    # Map assistant llm_call_id -> round_index
    call_id_to_round: dict[str, int] = {}
    for r_idx, r in enumerate(rounds):
        if r.assistant_msg.llm_call_id:
            call_id_to_round[r.assistant_msg.llm_call_id] = r_idx

    # Main agent calls — track prior call's tools for prompt context
    main_calls_in_round: dict[int, list[LLMCall]] = {}
    for msg in messages:
        if msg.role != "assistant" or not msg.llm_call_id:
            continue
        r_idx = call_id_to_round.get(msg.llm_call_id, 0)
        usage = msg.usage or {}
        round_tools = rounds[r_idx].tool_calls if r_idx < len(rounds) else []
        round_obj = rounds[r_idx] if r_idx < len(rounds) else None

        prior_tools: list[ToolCall] = []
        call_index = 0
        if r_idx in main_calls_in_round and main_calls_in_round[r_idx]:
            prior_call = main_calls_in_round[r_idx][-1]
            prior_tools = prior_call.tool_calls
            call_index = len(main_calls_in_round[r_idx])

        prompt_hint = ""
        if round_obj:
            prompt_hint = _derive_prompt_preview(
                msg, round_tools, prior_tools, round_obj, messages, call_index
            )

        request_full = msg.request_full
        request_preview = request_full[:200] if request_full else prompt_hint

        llm_call = LLMCall(
            id=msg.llm_call_id,
            model=msg.model,
            scope="main",
            subagent_id="",
            round_index=r_idx,
            parent_id="",
            parent_tool_name="",
            timestamp=msg.timestamp,
            status=msg.llm_status,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_input_tokens", 0),
            cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
            prompt_preview=prompt_hint,
            request_preview=request_preview,
            request_full=request_full,
            response_preview=msg.content[:200],
            response_full=msg.content,
            tool_calls=[tc for tc in round_tools if tc.scope == "main"],
            tool_call_count=len([tc for tc in round_tools if tc.scope == "main"]),
            failed_tool_count=sum(1 for tc in round_tools if tc.scope == "main" and tc.is_failed),
            request_payload_raw="",
            request_payload_missing_reason="current session data source does not persist raw HTTP request payload",
            response_payload_raw="",
            response_payload_missing_reason="current session data source does not persist raw HTTP response",
            finish_reason="",
            tool_calls_raw="",
        )
        main_calls_in_round.setdefault(r_idx, []).append(llm_call)
        llm_calls.append(llm_call)

    # Subagent individual calls — one per internal LLM turn
    for run in subagent_runs:
        summary = run["summary"]
        agent_id = summary["agent_id"]

        parent_tc = None
        for tc in tool_calls:
            if tc.name == "Agent" and tc.subagent_summary.get("agent_id") == agent_id:
                parent_tc = tc
                break

        parent_round = 0
        if parent_tc:
            for r_idx, r in enumerate(rounds):
                if any(tc.tool_use_id == parent_tc.tool_use_id for tc in r.tool_calls):
                    parent_round = r_idx
                    break

        for msg in run["messages"]:
            if msg.role != "assistant" or not msg.llm_call_id:
                continue
            usage = msg.usage or {}

            request_full = msg.request_full if msg.request_full else ""
            request_preview = request_full[:200] if request_full else ""
            response_preview = msg.content[:200] if msg.content else ""

            llm_calls.append(LLMCall(
                id=msg.llm_call_id,
                model=msg.model,
                scope="subagent",
                subagent_id=agent_id,
                round_index=parent_round,
                parent_id=parent_tc.tool_use_id if parent_tc else "",
                parent_tool_name=parent_tc.name if parent_tc else "Agent",
                timestamp=msg.timestamp,
                status="ok",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                prompt_preview=f"Subagent turn ({msg.content[:80]})" if msg.content else "Subagent turn",
                request_preview=request_preview,
                request_full=request_full,
                response_preview=response_preview,
                response_full=msg.content,
                tool_calls=[],
                tool_call_count=0,
                failed_tool_count=0,
                request_payload_raw="",
                request_payload_missing_reason="current session data source does not persist raw HTTP request payload",
                response_payload_raw="",
                response_payload_missing_reason="current session data source does not persist raw HTTP response",
                finish_reason="",
                tool_calls_raw="",
            ))

    return llm_calls


def _build_subagent_interactions(
    llm_calls: list[LLMCall],
    subagent_runs: list[dict],
    tool_calls: list[ToolCall],
) -> list[LLMCall]:
    """Build one aggregated interaction per subagent run (for rounds view).

    Each subagent run becomes a single interaction that aggregates all its
    internal LLM calls and tools, so the round expand shows it as one nested
    block instead of repeating 260 times.
    """
    interactions: list[LLMCall] = []
    for run in subagent_runs:
        summary = run["summary"]
        agent_id = summary["agent_id"]

        parent_tc = None
        for tc in tool_calls:
            if tc.name == "Agent" and tc.subagent_summary.get("agent_id") == agent_id:
                parent_tc = tc
                break

        # Find individual subagent calls for this run
        sub_calls = [c for c in llm_calls if c.scope == "subagent" and c.subagent_id == agent_id]
        if not sub_calls:
            continue

        parent_round = sub_calls[0].round_index
        total_input = sum(c.input_tokens for c in sub_calls)
        total_output = sum(c.output_tokens for c in sub_calls)
        total_cr = sum(c.cache_read_tokens for c in sub_calls)
        total_cw = sum(c.cache_write_tokens for c in sub_calls)

        response = ""
        request_full = ""
        for c in reversed(sub_calls):
            if c.response_full:
                response = c.response_full
                break
        for c in sub_calls:
            if c.request_full:
                request_full = c.request_full
                break

        sub_tools = [tc for tc in tool_calls if tc.subagent_id == agent_id]

        interactions.append(LLMCall(
            id=f"subagent-{agent_id}",
            model=sub_calls[0].model if sub_calls else "",
            scope="subagent",
            subagent_id=agent_id,
            round_index=parent_round,
            parent_id=parent_tc.tool_use_id if parent_tc else "",
            parent_tool_name=parent_tc.name if parent_tc else "Agent",
            timestamp=sub_calls[0].timestamp,
            status="ok",
            input_tokens=total_input,
            output_tokens=total_output,
            cache_read_tokens=total_cr,
            cache_write_tokens=total_cw,
            prompt_preview="",
            request_preview=request_full[:200] if request_full else "",
            request_full=request_full,
            response_preview=response[:200],
            response_full=response,
            tool_calls=sub_tools,
            tool_call_count=len(sub_tools),
            failed_tool_count=sum(1 for t in sub_tools if t.is_failed),
            request_payload_raw="",
            request_payload_missing_reason="current session data source does not persist raw HTTP request payload",
            response_payload_raw="",
            response_payload_missing_reason="current session data source does not persist raw HTTP response",
            finish_reason="",
            tool_calls_raw="",
        ))

    return interactions


def compute_bar_scale(round_tokens: int, max_round_tokens: int) -> float:
    """Compute the proportional width for a round's token bar.

    Returns a percentage (0-100) representing how wide this round's
    bar should be relative to the maximum round in the timeline.
    The max round gets 100%, others are scaled proportionally.
    """
    if max_round_tokens <= 0:
        return 0
    return round_tokens / max_round_tokens * 100


def compute_round_signals(
    round,  # ConversationRound
    round_index: int,  # 1-based
    session_input_tokens: int = 0,
) -> list[dict]:
    """Compute actionable round-level signals for the Timeline tab.

    Only returns signals that represent "worth opening to investigate" events.
    Normal/positive/low-value states (warm-up, cache-hit, low-output) are
    intentionally excluded to reduce noise.

    Returns a list of dicts with keys: key, label, severity, reason.
    """
    signals: list[dict] = []

    rb = round.token_breakdown()
    round_input_total = rb["input"] + rb["cache_read"] + rb["cache_write"]
    round_tools = round.tool_calls
    failed_tools = [tc for tc in round_tools if tc.is_failed]
    total_session_input = session_input_tokens

    # ── Critical signals ────────────────────────────────────────────

    # Failed tool calls in a single round: warning at 1-2, critical at >= 3
    if len(failed_tools) >= 3:
        count = len(failed_tools)
        names = ", ".join(tc.name for tc in failed_tools[:3])
        suffix = f" +{count - 3}" if count > 3 else ""
        signals.append({
            "key": "failed-tool",
            "label": "failed tool",
            "severity": "critical",
            "reason": f"{count} failed tools: {names}{suffix}",
        })
    elif len(failed_tools) >= 1:
        count = len(failed_tools)
        names = ", ".join(tc.name for tc in failed_tools[:3])
        signals.append({
            "key": "failed-tool",
            "label": "failed tool",
            "severity": "warning",
            "reason": f"{count} failed tool{'s' if count != 1 else ''}: {names}",
        })

    # LLM errors in a single round: warning at 1-2, critical at >= 3
    if round.llm_error_count >= 3:
        signals.append({
            "key": "llm-error",
            "label": "llm error",
            "severity": "critical",
            "reason": f"{round.llm_error_count} LLM errors in this round",
        })
    elif round.llm_error_count >= 1:
        signals.append({
            "key": "llm-error",
            "label": "llm error",
            "severity": "warning",
            "reason": f"{round.llm_error_count} LLM error{'s' if round.llm_error_count != 1 else ''} in this round",
        })

    # ── Warning signals ─────────────────────────────────────────────

    # Single tool taking >= 5 minutes
    long_tools = [tc for tc in round_tools if tc.duration_ms >= 300_000]
    if long_tools:
        names = ", ".join(tc.name for tc in long_tools[:2])
        suffix = f" +{len(long_tools) - 2}" if len(long_tools) > 2 else ""
        signals.append({
            "key": "long-tool",
            "label": "long tool",
            "severity": "warning",
            "reason": f"{len(long_tools)} tool{'s' if len(long_tools) != 1 else ''} >= 5 min: {names}{suffix}",
        })

    # >= 20 tool calls in a round (possible loop / efficiency issue)
    if len(round_tools) >= 20:
        # Exclude the case where it's just a handful of small repeated tools
        tool_name_counts: dict[str, int] = {}
        for tc in round_tools:
            tool_name_counts[tc.name] = tool_name_counts.get(tc.name, 0) + 1
        # If top 3 tools account for >= 90% of calls, it's likely a tight loop
        sorted_counts = sorted(tool_name_counts.values(), reverse=True)
        top3 = sum(sorted_counts[:3])
        is_tight_loop = top3 >= int(len(round_tools) * 0.9)
        if not is_tight_loop or len(tool_name_counts) >= 5:
            signals.append({
                "key": "tool-burst",
                "label": "tool burst",
                "severity": "warning",
                "reason": f"{len(round_tools)} tool calls in round {round_index}",
            })

    # Cache write >= 300K tokens in a single round
    # (100K is common in long sessions; 300K+ indicates unusual context accumulation)
    if rb["cache_write"] >= 300_000:
        signals.append({
            "key": "high-write",
            "label": "high write",
            "severity": "warning",
            "reason": f"{rb['cache_write']:,} cache write tokens in round {round_index}",
        })

    # Large input: requires BOTH absolute (>= 200K) AND relative (>= 50% of session)
    # thresholds. An absolute-only check fires constantly as session context grows;
    # the percentage guard ensures it only fires when the round is truly
    # disproportionate to the session overall.
    if (round_input_total >= 200_000
            and total_session_input > 0
            and round_input_total / total_session_input >= 0.5):
        pct = round_input_total / total_session_input * 100
        signals.append({
            "key": "large-input",
            "label": "large input",
            "severity": "warning",
            "reason": f"{round_input_total:,} input tokens in round {round_index} ({pct:.0f}% of session)",
        })

    return signals


def _assign_interactions_to_rounds(
    rounds: list[ConversationRound],
    llm_calls: list[LLMCall],
    tool_calls: list[ToolCall],
    subagent_runs: list[dict],
) -> None:
    """Populate round.interactions.

    Main agent: individual calls stay as individual interactions.
    Subagent: replaced by one aggregated interaction per run (so round expand
    shows it as a single nested block, not repeated for every internal turn).
    """
    # Group main-agent calls by round
    main_by_round: dict[int, list[LLMCall]] = {}
    for call in llm_calls:
        if call.scope == "main":
            main_by_round.setdefault(call.round_index, []).append(call)

    # Build aggregated subagent interactions
    subagent_interactions = _build_subagent_interactions(llm_calls, subagent_runs, tool_calls)
    sub_by_round: dict[int, list[LLMCall]] = {}
    for ix in subagent_interactions:
        sub_by_round.setdefault(ix.round_index, []).append(ix)

    for r_idx, r in enumerate(rounds):
        main_calls = main_by_round.get(r_idx, [])
        sub_calls = sub_by_round.get(r_idx, [])
        # Main calls first, then subagent interactions
        r.interactions = main_calls + sub_calls


class SessionBrowserHandler(BaseHTTPRequestHandler):
    """HTTP request handler for session-browser."""

    def do_GET(self) -> None:  # noqa: N802
        started_at = time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/" or path == "/dashboard":
                self._serve_dashboard()
            elif path == "/favicon.ico":
                self._send_empty(204)
            elif path == "/projects":
                self._serve_projects()
            elif path.startswith("/projects/"):
                project_key = urllib.parse.unquote(path[len("/projects/"):])
                self._serve_project(project_key)
            elif path == "/sessions":
                self._serve_all_sessions()
            elif path.startswith("/sessions/"):
                # Parse query params for export=mhtml
                path_only = path.split("?", 1)[0]
                export_mhtml = params.get("export") == ["mhtml"]

                parts = path_only[len("/sessions/"):].split("/", 1)
                if len(parts) == 2:
                    agent, session_id = parts
                    self._serve_session(agent, session_id, export_mhtml=export_mhtml)
                else:
                    self._serve_all_sessions()
            elif path == "/agents":
                self._serve_agents()
            elif path.startswith("/agents/"):
                agent = urllib.parse.unquote(path[len("/agents/"):])
                self._serve_agent(agent)
            elif path == "/glossary":
                self._serve_glossary()
            elif path == "/search":
                self._serve_search(params)
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            else:
                self._send_404()
            elapsed_ms = (time.time() - started_at) * 1000
            logger.debug(
                "HTTP request handled: method=GET path=%s elapsed_ms=%.1f",
                path,
                elapsed_ms,
            )
        except BrokenPipeError:
            # Client closed the connection before we could respond — normal.
            logger.debug("Client disconnected before response: path=%s", path)
        except Exception as exc:
            logger.exception("HTTP request failed: method=GET path=%s query=%s", path, parsed.query)
            self._send_500(str(exc))

    def log_message(self, format: str, *args) -> None:
        """Route BaseHTTPRequestHandler access logs through configured logging."""
        logger.info(
            "HTTP access: client=%s message=%s",
            self.client_address[0] if self.client_address else "-",
            format % args,
        )

    def log_error(self, format: str, *args) -> None:
        """Route BaseHTTPRequestHandler error logs through configured logging."""
        logger.error(
            "HTTP handler error: client=%s message=%s",
            self.client_address[0] if self.client_address else "-",
            format % args,
        )

    def _render_template(self, name: str, **context) -> str:
        template = _template_env.get_template(name)
        return template.render(**context)

    def _send_html(self, html: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_empty(self, status: int = 204) -> None:
        self.send_response(status)
        self.end_headers()

    def _send_404(self) -> None:
        self._send_html(self._render_template("404.html"), 404)

    def _send_500(self, error: str) -> None:
        logger.error("Rendering 500 response: %s", error)
        self._send_html(self._render_template("error.html", error=error), 500)

    def _serve_dashboard(self) -> None:
        conn = _get_connection()
        stats = get_dashboard_stats(conn)
        projects = list_projects(conn, limit=10)
        recent = list_sessions(conn, limit=20, order_by="ended_at")
        trend = get_trend_data(conn, days=30)
        model_dist = get_model_distribution(conn)
        agent_dist = get_agent_distribution(conn)
        token_breakdown = get_token_breakdown(conn)
        aggregate_metrics = compute_aggregate_metrics(conn)

        # Anomaly detection for all sessions
        all_sessions_raw = list_sessions(conn, limit=2000, order_by="ended_at")
        sessions_data = []
        sessions_lookup = {}
        for s in all_sessions_raw:
            d = compute_derived_metrics(s.to_dict())
            sessions_data.append(d)
            sessions_lookup[d["session_key"]] = d

        anomalies_map = detect_all_anomalies(sessions_data)
        needs_attention = get_needs_attention(anomalies_map, sessions_lookup, limit=8)

        # Enrich recent sessions with anomalies
        recent_enriched = enrich_sessions_with_anomalies(recent, anomalies_map)

        conn.close()

        html = self._render_template(
            "dashboard.html",
            stats=stats,
            projects=projects,
            recent=recent_enriched,
            trend=trend,
            model_dist=model_dist.distribution,
            agent_dist=agent_dist,
            tokens=token_breakdown,
            aggregate=aggregate_metrics,
            needs_attention=needs_attention,
            active_page="dashboard",
        )
        self._send_html(html)

    def _serve_projects(self) -> None:
        conn = _get_connection()
        projects = list_projects(conn, limit=100)
        conn.close()

        html = self._render_template(
            "projects.html",
            projects=projects,
            active_page="projects",
        )
        self._send_html(html)

    def _serve_project(self, project_key: str) -> None:
        conn = _get_connection()
        pstats = get_project_stats(conn, project_key)
        sessions = list_sessions(conn, project_key=project_key, limit=100)
        conn.close()

        html = self._render_template(
            "project.html",
            project=pstats,
            sessions=sessions,
            project_key=project_key,
            active_page="projects",
        )
        self._send_html(html)

    def _serve_session(self, agent: str, session_id: str, export_mhtml: bool = False) -> None:
        session_key = f"{agent}:{session_id}"
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            self._send_404()
            return

        # Get raw conversation data from source
        if agent == "claude_code":
            from session_browser.sources.claude import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                session.project_key, session_id
            )
        elif agent == "qoder":
            from session_browser.sources.qoder import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                session.project_key, session_id
            )
        else:
            from session_browser.sources.codex import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(session_id)

        # Use freshly parsed detail counts on the session page so newly added
        # diagnostics do not require a rescan before they become visible.
        if raw_summary is not None:
            session.user_message_count = raw_summary.user_message_count
            session.assistant_message_count = raw_summary.assistant_message_count
            session.tool_call_count = raw_summary.tool_call_count
            session.failed_tool_count = raw_summary.failed_tool_count
            session.input_tokens = raw_summary.input_tokens
            session.output_tokens = raw_summary.output_tokens
            session.cached_input_tokens = raw_summary.cached_input_tokens
            session.cached_output_tokens = raw_summary.cached_output_tokens
            session.duration_seconds = raw_summary.duration_seconds or session.duration_seconds

        # Build conversation rounds with token data and markdown rendering
        rounds = _build_rounds(
            messages,
            tool_calls,
            session.input_tokens,
            session.output_tokens,
            session.cached_input_tokens,
            session.cached_output_tokens,
            agent,
        )

        # Build LLM calls and assign interactions to rounds
        llm_calls = _build_llm_calls(messages, tool_calls, rounds, subagent_runs)
        _assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        # Compute preview text for each round after interactions are assigned
        for r in rounds:
            r.compute_preview()

        # Compute derived metrics
        session_data = compute_derived_metrics(session.to_dict())

        # Detect anomalies for this session
        from session_browser.index.anomalies import detect_session_anomalies
        sa = detect_session_anomalies(session_data)

        # Payload visibility mismatch: check actual llm_calls for missing payloads.
        # Only flag when input tokens exist but NO call has request_full data.
        has_input = session.input_tokens > 0
        has_any_request = any(c.request_full for c in llm_calls) if llm_calls else False
        has_any_response = any(c.response_full for c in llm_calls) if llm_calls else False
        if has_input and not has_any_request and not has_any_response:
            from session_browser.index.anomalies import Anomaly, AnomalyType, SEVERITY_WARNING
            sa.anomalies.append(Anomaly(
                type=AnomalyType.PAYLOAD_VISIBILITY_MISMATCH,
                severity=SEVERITY_WARNING,
                label="Payload visibility mismatch",
                reason="Session has input tokens, but no LLM call has request/response payload data.",
            ))

        # Compute signals for each round after interactions are assigned
        round_signals = []
        for i, r in enumerate(rounds):
            round_signals.append(
                compute_round_signals(r, i + 1, session.input_tokens)
            )

        # Set repo root to session's project directory for relative path rendering
        global _SESSION_REPO_ROOT
        _SESSION_REPO_ROOT = _get_repo_root(session.project_key) if session.project_key else None

        # MHTML context
        if export_mhtml:
            logger.info("MHTML export: agent=%s session_id=%s", agent, session_id)
            from session_browser.web.mhtml import get_context
            mhtml_ctx = get_context(True)
        else:
            mhtml_ctx = {}

        html = self._render_template(
            "session.html",
            session=session,
            session_data=session_data,
            rounds=rounds,
            round_signals=round_signals,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            current_agent=agent,
            session_anomalies=sa,
            active_page="session",
            session_url=f"/sessions/{agent}/{session_id}",
            session_rounds=[
                {"idx": i + 1, "name": r.title or f"Round {i + 1}",
                 "status": getattr(r, "status", ""), "is_current": False}
                for i, r in enumerate(rounds)
            ],
            **mhtml_ctx,
        )
        self._send_html(html)

    def _serve_agent(self, agent: str) -> None:
        conn = _get_connection()
        agents = list_agents(conn)
        sessions = list_sessions(conn, agent=agent, limit=100, order_by="ended_at")
        conn.close()

        agent_info = None
        for a in agents:
            if a["agent"] == agent:
                agent_info = a
                break

        html = self._render_template(
            "agent.html",
            agents=agents,
            agent_info=agent_info,
            sessions=sessions,
            current_agent=agent,
            active_page="agents",
        )
        self._send_html(html)

    def _serve_agents(self) -> None:
        conn = _get_connection()
        agents = list_agents(conn)
        efficiency = compute_agent_efficiency(conn)
        conn.close()

        html = self._render_template(
            "agents.html",
            agents=agents,
            efficiency=efficiency,
            current_agent="__all__",
            active_page="agents",
        )
        self._send_html(html)

    def _serve_static(self, filename: str) -> None:
        static_dir = Path(__file__).parent / "static"
        filepath = static_dir / filename
        if not filepath.exists():
            self._send_404()
            return

        content_type = "text/css" if filename.endswith(".css") else "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(filepath.read_bytes())

    def _serve_all_sessions(self, sort_by: str = "ended_at") -> None:
        """Global sessions page — all sessions across all projects."""
        conn = _get_connection()
        sessions = list_sessions(conn, limit=200, order_by=sort_by)
        total_count = count_sessions(conn)

        # Get distinct models and projects for filters
        models = conn.execute(
            "SELECT DISTINCT model FROM sessions WHERE model != '' ORDER BY model"
        ).fetchall()
        projects = conn.execute(
            "SELECT DISTINCT project_key, project_name FROM sessions ORDER BY project_name"
        ).fetchall()

        # Anomaly detection for all sessions
        all_sessions_raw = list_sessions(conn, limit=2000, order_by="ended_at")
        sessions_data = []
        sessions_lookup = {}
        for s in all_sessions_raw:
            d = compute_derived_metrics(s.to_dict())
            sessions_data.append(d)
            sessions_lookup[d["session_key"]] = d

        anomalies_map = detect_all_anomalies(sessions_data)
        sessions_enriched = enrich_sessions_with_anomalies(sessions, anomalies_map)

        conn.close()

        model_list = [r["model"] for r in models]
        project_list = [(r["project_key"], r["project_name"]) for r in projects]

        html = self._render_template(
            "sessions.html",
            sessions=sessions_enriched,
            total_count=total_count,
            model_list=model_list,
            project_list=[p[0] for p in project_list],
            active_page="sessions",
        )
        self._send_html(html)

    def _serve_search(self, params: dict[str, list[str]]) -> None:
        """Search sessions by title, id, project, model, or agent."""
        query = (params.get("q", [""])[0] or "").strip().lower()
        conn = _get_connection()

        sessions = []
        if query:
            all_sessions = list_sessions(conn, limit=5000, order_by="ended_at")
            terms = [t for t in query.split() if t]
            for session in all_sessions:
                haystack = " ".join(
                    [
                        session.title or "",
                        session.session_id or "",
                        session.project_name or "",
                        session.project_key or "",
                        session.model or "",
                        session.agent or "",
                    ]
                ).lower()
                if all(term in haystack for term in terms):
                    sessions.append(session)
                if len(sessions) >= 200:
                    break

        conn.close()

        html = self._render_template(
            "search.html",
            query=query,
            sessions=sessions,
            active_page="search",
        )
        self._send_html(html)

    def _serve_glossary(self) -> None:
        """Token glossary page."""
        html = self._render_template(
            "glossary.html",
            active_page="glossary",
        )
        self._send_html(html)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8899,
) -> HTTPServer:
    """Create and return an HTTPServer instance."""
    server = HTTPServer((host, port), SessionBrowserHandler)
    server.allow_reuse_address = True
    return server
