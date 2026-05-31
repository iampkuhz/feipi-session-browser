"""Jinja2 template environment and filter registrations.

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
from typing import Any

import jinja2

from session_browser.web.renderers.markdown import render_markdown
from session_browser.web.renderers.llm_blocks import (
    normalize_llm_content,
    render_llm_blocks_html,
    _content_parts_to_blocks,
    _parts_mode_from_raw,
    # Re-export internal helpers for backward compatibility with tests
    _detect_line_number_gutter,
    _strip_line_number_gutter,
    _infer_code_language,
    _detect_file_marker,
    _html_escape,
)
from session_browser.web.safe_render import register_filters as _register_safe_filters, safe_json_display

logger = logging.getLogger("session_browser.web")

# ─── Template directory ─────────────────────────────────────────────

_TEMPLATE_DIR = Path(__file__).parent / "templates"

# ─── Formatting helpers ──────────────────────────────────────────────

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


def _format_compact_token(n: int | float | None) -> str:
    """Format token count to compact string (e.g. 1.5K, 2.3M)."""
    if n is None:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def _format_compact_num(n: int | float | None) -> str:
    """Format number with K/M suffix for display."""
    if n is None:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def _renumber_lines(text: str) -> str:
    """Renumber lines starting from 1, preserving tab-separated gutter."""
    if not text or not re.search(r'^\d+\t', text, flags=re.MULTILINE):
        return text
    tab = '\t'
    lines = []
    for i, line in enumerate(text.splitlines()):
        cleaned = re.sub(r'^\d+\t', '', line)
        lines.append(f"{i + 1}{tab}{cleaned}")
    return "\n".join(lines) + "\n"


# ─── Git repo root detection ─────────────────────────────────────────

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


# Cache the repo root at module load time
_REPO_ROOT = _get_repo_root()

# Per-request repo root (set before template render by routes.py)
_SESSION_REPO_ROOT: str | None = None


# ─── Path helpers ────────────────────────────────────────────────────

def _truncate_path(path: str) -> str:
    """Truncate a long path, keeping first and last segments."""
    if not path or len(path) <= 40:
        return path or ""
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return path[:40] + "…"
    # Keep first 2 and last 2 segments
    return "/".join(parts[:2]) + "/…/" + "/".join(parts[-2:])


def _display_path(path: str) -> str:
    """Replace the user's home prefix with ``~`` for display.

    Only affects paths that start with the current user's home directory.
    Non-home and short paths are returned unchanged.
    """
    if not path:
        return path or ""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    sep = os.sep
    if path.startswith(home + sep):
        return "~" + path[len(home):]
    return path


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


def _shorten_path(path: str) -> str:
    """Shorten a path for display: repo-relative -> ~ -> truncate.

    Order matters: repo-relative comparison requires absolute path,
    so we try that before replacing home with ~.
    """
    if not path:
        return path or ""
    # Step 1: try repo-relative (needs absolute path for comparison)
    abs_path = os.path.abspath(path)
    repo_root = _SESSION_REPO_ROOT or _REPO_ROOT
    if repo_root:
        try:
            if abs_path.startswith(repo_root + os.sep) or abs_path == repo_root:
                result = os.path.relpath(abs_path, repo_root)
                return _truncate_path(result)
        except Exception:
            pass
    # Not in repo: replace home with ~
    result = _display_path(path)
    # Step 2: truncate if still long
    return _truncate_path(result)


# ─── Time helpers ────────────────────────────────────────────────────

def _relative_time(iso_str: str) -> str:
    """Convert ISO8601 to relative time string."""
    if not iso_str:
        return ""
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

    E.g. "2026-05-12T06:20:29+00:00" -> "2026-05-12 14:20:29" (Beijing UTC+8).
    If already in local time (has non-zero offset), just reformat.
    """
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return str(iso_str)[:19].replace("T", " ")


# ─── JSON helpers with relative path support ─────────────────────────

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
    """tojson_repo with HTML escaping -- safe for <pre> embedding."""
    if not v:
        return "null"
    raw = json.dumps(_relative_paths_in_json(v), indent=indent, ensure_ascii=False)
    return html.escape(raw)


# ─── Template environment ────────────────────────────────────────────

env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)
_register_safe_filters(env)

# Register custom filters and globals
env.filters["format_number"] = _format_compact_num
env.filters["format_number_short"] = _format_compact_num
env.filters["format_compact_token"] = _format_compact_token
env.filters["format_1d"] = lambda n: f"{n:.1f}" if n is not None else "0.0"
env.globals["max"] = max
env.filters["truncate_path"] = lambda path: _truncate_path(path)
env.filters["relative_to_repo"] = lambda path: _relative_to_repo(path)
env.filters["shorten_path"] = lambda path: _shorten_path(path)
env.filters["format_duration"] = lambda seconds: (
    f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}min" if seconds >= 3600
    else f"{int(seconds // 60)}min {int(seconds % 60)}s" if seconds >= 60
    else f"{int(seconds)}s"
)
env.filters["format_bytes"] = _format_bytes
env.filters["relative_time"] = lambda iso_str: _relative_time(iso_str)
env.filters["local_time"] = lambda iso_str: _to_local_time(iso_str)
env.filters["urlencode"] = urllib.parse.quote
env.filters["urldecode"] = urllib.parse.unquote
env.filters["markdown"] = render_markdown
env.filters["render_llm_blocks_html"] = render_llm_blocks_html
env.filters["tojson_safe"] = lambda v: safe_json_display(v)
env.filters["strip_line_numbers"] = lambda text: (
    re.sub(r'^\d+\t', '', text, flags=re.MULTILINE)
    if text and re.search(r'^\d+\t', text, flags=re.MULTILINE)
    else text
)
env.filters["renumber_lines"] = _renumber_lines
env.filters["normalize_llm_content"] = normalize_llm_content
env.filters["content_parts"] = _content_parts_to_blocks
env.filters["parts_mode_from_raw"] = _parts_mode_from_raw
env.filters["tojson_repo"] = _tojson_repo_html
_PRECISION_LABEL_MAP = {
    "provider_reported": "实报",
    "transcript_exact": "内容精确",
    "exact": "精确",
    "estimated": "估算",
    "heuristic": "推断",
    "residual": "未定位",
    "unavailable": "不可用",
}


def _format_coverage(value: float | None) -> str:
    """Format coverage ratio as integer percentage."""
    if value is None:
        return "—"
    return f"{round(value * 100)}%"


def _precision_label(precision: str | None) -> str:
    """Map raw precision key to a short display label."""
    if not precision:
        return "不可用"
    return _PRECISION_LABEL_MAP.get(precision, precision)


env.filters["display_path"] = _display_path
env.filters["precision_label"] = _precision_label
env.globals["precision_label"] = _precision_label
env.filters["format_coverage"] = _format_coverage
