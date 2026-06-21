"""Jinja2 template environment 和 filter registrations.

Extracted from routes.py to isolate template construction logic.
LLM block rendering is delegated to renderers.llm_blocks.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable, Mapping

import jinja2

from session_browser.web.renderers.llm_blocks import (
    _content_parts_to_blocks,
    _parts_mode_from_raw,
    normalize_llm_content,
    render_llm_blocks_html,
)
from session_browser.web.renderers.markdown import render_markdown
from session_browser.web.safe_render import (
    register_filters as _register_safe_filters,
)

logger = logging.getLogger('session_browser.web')

# 说明:─── Template directory ─────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).parent / 'templates'
_BYTES_PER_KIB = 1024
_COMPACT_THOUSAND = 1_000
_COMPACT_MILLION = 1_000_000
_TRUNCATED_PATH_LENGTH = 40
_SHORT_PATH_SEGMENTS = 3
_DAYS_PER_MONTH = 30
_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600

# 说明:─── Formatting helpers ──────────────────────────────────────────────


def _format_bytes(n: int | float | None) -> str:
    """格式化 byte count to human-readable string.

    Args:
        n: Byte count to display.

    Returns:
        Human-readable byte count with B/KB/MB/GB suffix.
    """
    if n is None or n == 0:
        return '0 B'
    n = int(n)
    if n < _BYTES_PER_KIB:
        return f'{n} B'
    if n < _BYTES_PER_KIB * _BYTES_PER_KIB:
        return f'{n / _BYTES_PER_KIB:.1f} KB'
    if n < _BYTES_PER_KIB * _BYTES_PER_KIB * _BYTES_PER_KIB:
        return f'{n / (_BYTES_PER_KIB * _BYTES_PER_KIB):.1f} MB'
    return f'{n / (_BYTES_PER_KIB * _BYTES_PER_KIB * _BYTES_PER_KIB):.1f} GB'


def _format_compact_token(n: int | float | None) -> str:
    """格式化 token count to compact string (e.g. 1.5K, 2.3M).

    Args:
        n: Token count to display.

    Returns:
        Compact token count using K/M suffixes when appropriate.
    """
    if n is None:
        return '0'
    if n >= _COMPACT_MILLION:
        return f'{n / _COMPACT_MILLION:.1f}M'
    if n >= _COMPACT_THOUSAND:
        return f'{n / _COMPACT_THOUSAND:.1f}K'
    return str(int(n))


def _format_compact_num(n: int | float | None) -> str:
    """格式化 number,使用 K/M suffix,用于 display.

    Args:
        n: Numeric value to display.

    Returns:
        Compact number using K/M suffixes when appropriate.
    """
    if n is None:
        return '0'
    if n >= _COMPACT_MILLION:
        return f'{n / _COMPACT_MILLION:.1f}M'
    if n >= _COMPACT_THOUSAND:
        return f'{n / _COMPACT_THOUSAND:.1f}K'
    return str(int(n))


def _renumber_lines(text: str) -> str:
    """Renumber lines starting,来源于 1, preserving tab-separated gutter.

    Args:
        text: Text that may contain a tab-separated line-number gutter.

    Returns:
        Text with line numbers regenerated, or the original text when no gutter exists.
    """
    if not text or not re.search(r'^\d+\t', text, flags=re.MULTILINE):
        return text
    tab = '\t'
    lines = []
    for i, line in enumerate(text.splitlines()):
        cleaned = re.sub(r'^\d+\t', '', line)
        lines.append(f'{i + 1}{tab}{cleaned}')
    return '\n'.join(lines) + '\n'


# 说明:─── Git repo root detection ─────────────────────────────────────────


def _get_repo_root(cwd: str | None = None) -> str | None:
    """Detect git repo root,来源于 cwd.

    Args:
        cwd: Directory used as the git command working directory.

    Returns:
        Repository root path, or ``None`` when not inside a git repository.
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=cwd or Path.cwd(),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


# Cache 该 repo root at module load time
_REPO_ROOT = _get_repo_root()

# Per-request repo root (set,在之前 template render by routes.py)
_SESSION_REPO_ROOT: str | None = None


# 说明:─── Path helpers ────────────────────────────────────────────────────


def _truncate_path(path: str) -> str:
    """截断 一个 long path, keeping first 和 last segments.

    Args:
        path: Path string to truncate for display.

    Returns:
        Truncated path, or the original path when already short.
    """
    if not path or len(path) <= _TRUNCATED_PATH_LENGTH:
        return path or ''
    parts = path.replace('\\', '/').split('/')
    if len(parts) <= _SHORT_PATH_SEGMENTS:
        return path[:_TRUNCATED_PATH_LENGTH] + '…'
    # 保留 first 2 和 last 2 segments
    return '/'.join(parts[:2]) + '/…/' + '/'.join(parts[-2:])


def _display_path(path: str) -> str:
    """Replace 该 user's home prefix,使用 ``~``,用于 display.

    Args:
        path: Path string to format.

    Returns:
        Display path with a leading home directory replaced by ``~``.

    Only affects paths that start with the current user's home directory.
    Non-home and short paths are returned unchanged.
    """
    if not path:
        return path or ''
    home = str(Path('~').expanduser())
    if path == home:
        return '~'
    sep = os.sep
    if path.startswith(home + sep):
        return '~' + path[len(home) :]
    return path


def _relative_to_repo(path: str) -> str:
    """If path is within 该 current session's git repo, return relative path.

    Args:
        path: Path string to compare against the current repository root.

    Returns:
        Repository-relative path when possible, otherwise the original path.

    Falls back to server-level _REPO_ROOT, then absolute path.
    """
    if not path:
        return path or ''
    repo_root = _SESSION_REPO_ROOT or _REPO_ROOT
    if not repo_root:
        return path
    try:
        abs_path = str(Path(path).resolve())
        if abs_path.startswith(repo_root + os.sep) or abs_path == repo_root:
            return os.path.relpath(abs_path, repo_root)
    except Exception:
        pass
    return path


def _shorten_path(path: str) -> str:
    """Shorten 一个 path,用于 display: repo-relative -> ~ -> truncate.

    Args:
        path: Path string to shorten.

    Returns:
        Shortened display path.

    Order matters: repo-relative comparison requires absolute path,
    so we try that before replacing home with ~.
    """
    if not path:
        return path or ''
    # Step 1: try repo-relative (needs absolute path,用于 comparison)
    abs_path = str(Path(path).resolve())
    repo_root = _SESSION_REPO_ROOT or _REPO_ROOT
    if repo_root:
        try:
            if abs_path.startswith(repo_root + os.sep) or abs_path == repo_root:
                result = os.path.relpath(abs_path, repo_root)
                return _truncate_path(result)
        except Exception:
            pass
    # Not in repo: replace home,使用 ~
    result = _display_path(path)
    # Step 2: truncate,如果 still long
    return _truncate_path(result)


# 说明:─── Time helpers ────────────────────────────────────────────────────


def _relative_time(iso_str: str) -> str:
    """转换 ISO8601 to relative time string.

    Args:
        iso_str: ISO8601 timestamp string.

    Returns:
        Relative time label, or a truncated original timestamp on parse failure.
    """
    if not iso_str:
        return ''
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = now - dt
        days = delta.days
        if days > _DAYS_PER_MONTH:
            return f'{days // _DAYS_PER_MONTH}mo ago'
        if days > 0:
            return f'{days}d ago'
        hours = delta.seconds // 3600
        if hours > 0:
            return f'{hours}h ago'
        minutes = delta.seconds // 60
        return f'{minutes}m ago'
    except (ValueError, TypeError):
        return iso_str[:16]


def _to_local_time(iso_str: str) -> str:
    """转换 UTC ISO8601 timestamp to local-time display string.

    Args:
        iso_str: ISO8601 timestamp string.

    Returns:
        Local time formatted as ``YYYY-MM-DD HH:MM:SS``.

    E.g. "2026-05-12T06:20:29+00:00" -> "2026-05-12 14:20:29" (Beijing UTC+8).
    If already in local time (has non-zero offset), just reformat.
    """
    if not iso_str:
        return ''
    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        local_dt = dt.astimezone()
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return str(iso_str)[:19].replace('T', ' ')


# ─── JSON helpers,使用 relative path support ─────────────────────────


def _relative_paths_in_json(obj: object) -> object:
    """Recursively replace file_path values in 一个 dict,使用 relative-to-repo paths.

    Args:
        obj: JSON-like value to rewrite.

    Returns:
        JSON-like value with ``file_path`` fields made repository-relative when possible.
    """
    if isinstance(obj, dict):
        return {
            k: (
                _relative_to_repo(v)
                if k == 'file_path' and isinstance(v, str)
                else _relative_paths_in_json(v)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_relative_paths_in_json(item) for item in obj]
    return obj


def _tojson_repo_html(v: object, indent: int | None = None) -> str:
    """tojson_repo,使用 HTML escaping -- 安全,用于 <pre> embedding.

    Args:
        v: JSON-serializable value to render.
        indent: Optional JSON indentation level.

    Returns:
        HTML-escaped JSON string.
    """
    if not v:
        return 'null'
    raw = json.dumps(_relative_paths_in_json(v), indent=indent, ensure_ascii=False)
    return html.escape(raw)


# 说明:─── Template environment ────────────────────────────────────────────

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)
_register_safe_filters(env)

# 注册 custom filters 和 globals
env.filters['format_number'] = _format_compact_num
env.filters['format_number_short'] = _format_compact_num
env.filters['format_compact_token'] = _format_compact_token
env.filters['format_1d'] = lambda n: f'{n:.1f}' if n is not None else '0.0'
env.globals['max'] = max
env.filters['truncate_path'] = _truncate_path
env.filters['relative_to_repo'] = _relative_to_repo
env.filters['shorten_path'] = _shorten_path
env.filters['format_duration'] = lambda seconds: (
    f'{int(seconds // _SECONDS_PER_HOUR)}h {int((seconds % _SECONDS_PER_HOUR) // _SECONDS_PER_MINUTE)}min'
    if seconds >= _SECONDS_PER_HOUR
    else f'{int(seconds // _SECONDS_PER_MINUTE)}min {int(seconds % _SECONDS_PER_MINUTE)}s'
    if seconds >= _SECONDS_PER_MINUTE
    else f'{int(seconds)}s'
)
env.filters['format_bytes'] = _format_bytes
env.filters['relative_time'] = _relative_time
env.filters['local_time'] = _to_local_time
env.filters['urlencode'] = urllib.parse.quote
env.filters['urldecode'] = urllib.parse.unquote
env.filters['markdown'] = render_markdown
env.filters['render_llm_blocks_html'] = render_llm_blocks_html
env.filters['strip_line_numbers'] = lambda text: (
    re.sub(r'^\d+\t', '', text, flags=re.MULTILINE)
    if text and re.search(r'^\d+\t', text, flags=re.MULTILINE)
    else text
)
env.filters['renumber_lines'] = _renumber_lines
env.filters['normalize_llm_content'] = normalize_llm_content
env.filters['content_parts'] = _content_parts_to_blocks
env.filters['parts_mode_from_raw'] = _parts_mode_from_raw
env.filters['tojson_repo'] = _tojson_repo_html
_PRECISION_LABEL_MAP = {
    'provider_reported': '实报',
    'transcript_exact': '内容精确',
    'exact': '精确',
    'estimated': '估算',
    'heuristic': '推断',
    'residual': '未定位',
    'unavailable': '不可用',
}


def _format_coverage(value: float | None) -> str:
    """格式化 coverage ratio as integer percentage.

    Args:
        value: Coverage ratio from 0 to 1.

    Returns:
        Integer percentage label or an em dash when unavailable.
    """
    if value is None:
        return '—'
    return f'{round(value * 100)}%'


def _precision_label(precision: str | None) -> str:
    """映射 raw precision key to 一个 short display label.

    Args:
        precision: Raw precision key.

    Returns:
        Human-readable precision label.
    """
    if not precision:
        return '不可用'
    return _PRECISION_LABEL_MAP.get(precision, precision)


env.filters['display_path'] = _display_path
env.filters['precision_label'] = _precision_label
env.globals['precision_label'] = _precision_label
env.filters['format_coverage'] = _format_coverage

# 说明:─── Dashboard-specific filters ─────────────────────────────────────

_KPI_ICON_COLORS = ['purple', 'blue', 'orange', 'green', 'red', 'purple']
_KPI_ICONS = ['📁', '🧭', '🪙', '💬', '⚡', '🚨']


def _kpi_icon_color(index: int) -> str:
    """映射 1-based KPI index to icon color class.

    Args:
        index: 1-based KPI index.

    Returns:
        Icon color class name.
    """
    return _KPI_ICON_COLORS[(index - 1) % len(_KPI_ICON_COLORS)]


def _kpi_icon(index: int) -> str:
    """映射 1-based KPI index to icon emoji.

    Args:
        index: 1-based KPI index.

    Returns:
        KPI icon glyph.
    """
    return _KPI_ICONS[(index - 1) % len(_KPI_ICONS)]


def _sum_attribute(seq: Iterable[object] | None, attr: str, default: int | float = 0) -> int | float:
    """求和 一个 attribute across 一个 sequence of dicts.

    Args:
        seq: Sequence of dict-like or object-like values.
        attr: Attribute or mapping key to sum.
        default: Default value used when an item does not contain ``attr``.

    Returns:
        Sum of truthy attribute values.
    """
    total = 0
    for item in seq or []:
        val = item.get(attr, default) if isinstance(item, Mapping) else getattr(item, attr, default)
        if val:
            total += val
    return total


_DB_TO_SCOPE = {
    'claude_code': 'claude-code',
    'qoder': 'qoder',
    'codex': 'codex',
}


def _db_agent_to_scope(db_agent: str) -> str:
    """转换 DB agent value to URL scope parameter.

    Args:
        db_agent: Agent value stored in the database.

    Returns:
        URL scope parameter.
    """
    return _DB_TO_SCOPE.get(db_agent, db_agent)


def _scope_to_agent_url(scope: str) -> str:
    """转换 URL scope to agent path segment,用于 /sessions/<agent>/... URLs.

    Args:
        scope: URL scope parameter.

    Returns:
        Agent path segment for session URLs.
    """
    if scope == 'all':
        return 'claude_code'  # 说明:default; should not happen for single-agent rows
    return _DB_TO_SCOPE.get(scope, scope).replace('-', '_') if '-' in scope else scope


def _severity_variant(severity: str) -> str:
    """映射 severity string to badge variant class.

    Args:
        severity: Severity label.

    Returns:
        Badge variant class name.
    """
    s = (severity or '').lower()
    if 'high' in s or 'error' in s:
        return 'danger'
    if 'medium' in s or 'warning' in s:
        return 'warning'
    return 'info'


env.filters['kpi_icon_color'] = _kpi_icon_color
env.filters['kpi_icon'] = _kpi_icon
env.filters['sum_attribute'] = _sum_attribute
env.filters['db_agent_to_scope'] = _db_agent_to_scope
env.filters['scope_to_agent_url'] = _scope_to_agent_url
env.filters['severity_variant'] = _severity_variant
