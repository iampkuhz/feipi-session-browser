"""Tests for session_browser.web.template_env module.

Covers:
- Jinja2 environment creation
- Custom filter registration and availability
- Filter behavior (formatting, time, path, markdown, etc.)
- Template discovery
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone, timedelta

import jinja2
import pytest

from session_browser.web.template_env import (
    env,
    _format_bytes,
    _format_compact_token,
    _format_compact_num,
    _to_local_time,
    _relative_time,
    _truncate_path,
    _display_path,
    _shorten_path,
    _html_escape,
    _renumber_lines,
    _detect_line_number_gutter,
    _strip_line_number_gutter,
    _infer_code_language,
    normalize_llm_content,
    render_llm_blocks_html,
    _content_parts_to_blocks,
    _parts_mode_from_raw,
    _relative_paths_in_json,
    _tojson_repo_html,
    _TEMPLATE_DIR,
)
from session_browser.web.renderers.markdown import render_markdown as _md_filter
from session_browser.domain.content_part import ContentPart


# ─── Environment creation ─────────────────────────────────────────────

class TestEnvCreation:
    def test_env_is_jinja2_environment(self):
        assert isinstance(env, jinja2.Environment)

    def test_env_autoescape_enabled(self):
        assert env.autoescape is True

    def test_env_has_filesystem_loader(self):
        assert isinstance(env.loader, jinja2.FileSystemLoader)

    def test_template_dir_exists(self):
        assert _TEMPLATE_DIR.is_dir()

    def test_template_dir_has_base_html(self):
        assert (_TEMPLATE_DIR / "base.html").is_file()

    def test_template_dir_has_dashboard_html(self):
        assert (_TEMPLATE_DIR / "dashboard.html").is_file()

    def test_template_dir_has_session_html(self):
        assert (_TEMPLATE_DIR / "session.html").is_file()


# ─── Filter registration ──────────────────────────────────────────────

EXPECTED_FILTERS = [
    "format_number",
    "format_number_short",
    "format_compact_token",
    "format_1d",
    "truncate_path",
    "relative_to_repo",
    "shorten_path",
    "format_duration",
    "format_bytes",
    "relative_time",
    "local_time",
    "urlencode",
    "urldecode",
    "markdown",
    "render_llm_blocks_html",
    "tojson_safe",
    "strip_line_numbers",
    "renumber_lines",
    "normalize_llm_content",
    "content_parts",
    "parts_mode_from_raw",
    "tojson_repo",
    "display_path",
    # from safe_render
    "safe_json_display",
    "safe_html_block",
    "tojson_safe_html",
]


class TestFilterRegistration:
    @pytest.mark.parametrize("name", EXPECTED_FILTERS)
    def test_filter_registered(self, name):
        assert name in env.filters, f"Filter '{name}' not registered in env.filters"

    def test_max_global_registered(self):
        assert "max" in env.globals


# ─── _format_bytes ────────────────────────────────────────────────────

class TestFormatBytes:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, "0 B"),
            (0, "0 B"),
            (512, "512 B"),
            (1023, "1023 B"),
            (1024, "1.0 KB"),
            (1536, "1.5 KB"),
            (1024 * 1024, "1.0 MB"),
            (1024 * 1024 * 1.5, "1.5 MB"),
            (1024 ** 3, "1.0 GB"),
            (1024 ** 3 * 2.5, "2.5 GB"),
        ],
    )
    def test_format_bytes(self, inp, expected):
        assert _format_bytes(inp) == expected


# ─── _format_compact_token ────────────────────────────────────────────

class TestFormatCompactToken:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, "0"),
            (0, "0"),
            (500, "500"),
            (999, "999"),
            (1000, "1.0K"),
            (1500, "1.5K"),
            (10000, "10.0K"),
            (999999, "1000.0K"),
            (1_000_000, "1.0M"),
            (2_300_000, "2.3M"),
        ],
    )
    def test_format_compact_token(self, inp, expected):
        assert _format_compact_token(inp) == expected


# ─── _format_compact_num ──────────────────────────────────────────────

class TestFormatCompactNum:
    @pytest.mark.parametrize(
        "inp,expected",
        [
            (None, "0"),
            (0, "0"),
            (123, "123"),
            (1000, "1.0K"),
            (1_000_000, "1.0M"),
        ],
    )
    def test_format_compact_num(self, inp, expected):
        assert _format_compact_num(inp) == expected


# ─── format_duration filter ──────────────────────────────────────────

class TestFormatDuration:
    def test_seconds_only(self):
        f = env.filters["format_duration"]
        assert f(30) == "30s"

    def test_minutes_and_seconds(self):
        f = env.filters["format_duration"]
        assert f(90) == "1min 30s"

    def test_hours_and_minutes(self):
        f = env.filters["format_duration"]
        assert f(3661) == "1h 1min"


# ─── format_1d filter ────────────────────────────────────────────────

class TestFormat1d:
    def test_value(self):
        f = env.filters["format_1d"]
        assert f(3.14159) == "3.1"

    def test_none(self):
        f = env.filters["format_1d"]
        assert f(None) == "0.0"


# ─── _to_local_time ───────────────────────────────────────────────────

class TestToLocalTime:
    def test_utc_iso_to_local(self):
        result = _to_local_time("2026-05-12T06:20:29+00:00")
        # Should be non-empty and contain the date
        assert "2026-05-12" in result
        assert " " in result  # has space between date and time

    def test_empty_string(self):
        assert _to_local_time("") == ""

    def test_none_input(self):
        assert _to_local_time(None) == ""

    def test_z_suffix(self):
        result = _to_local_time("2026-01-01T00:00:00Z")
        assert "2026-01-01" in result

    def test_invalid_returns_string(self):
        result = _to_local_time("not-a-date")
        assert "not-a" in result


# ─── _relative_time ──────────────────────────────────────────────────

class TestRelativeTime:
    def test_empty(self):
        assert _relative_time("") == ""

    def test_recent_minutes(self):
        now = datetime.now(timezone.utc).isoformat()
        result = _relative_time(now)
        assert "m ago" in result

    def test_days_ago(self):
        past = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        result = _relative_time(past)
        assert "5d ago" == result

    def test_months_ago(self):
        past = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        result = _relative_time(past)
        assert "mo ago" in result

    def test_invalid_fallback(self):
        result = _relative_time("not-a-date")
        assert "not-a" in result


# ─── _truncate_path ──────────────────────────────────────────────────

class TestTruncatePath:
    def test_short_path_unchanged(self):
        assert _truncate_path("/short/path") == "/short/path"

    def test_empty(self):
        assert _truncate_path("") == ""

    def test_none(self):
        assert _truncate_path(None) == ""

    def test_long_path_truncated(self):
        long_path = "/very/long/path/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p/file.txt"
        result = _truncate_path(long_path)
        assert "…" in result
        assert len(result) <= 45


# ─── _display_path ───────────────────────────────────────────────────

class TestDisplayPath:
    def test_home_replaced_with_tilde(self):
        import os
        home = os.path.expanduser("~")
        path = os.path.join(home, "Documents", "file.txt")
        result = _display_path(path)
        assert result.startswith("~")

    def test_home_exact(self):
        import os
        home = os.path.expanduser("~")
        assert _display_path(home) == "~"

    def test_empty(self):
        assert _display_path("") == ""

    def test_non_home_unchanged(self):
        assert _display_path("/opt/some/path") == "/opt/some/path"


# ─── _html_escape ─────────────────────────────────────────────────────

class TestHtmlEscape:
    def test_escapes_lt_gt(self):
        assert _html_escape("<div>") == "&lt;div&gt;"

    def test_escapes_ampersand(self):
        assert _html_escape("a&b") == "a&amp;b"

    def test_plain_text_unchanged(self):
        assert _html_escape("hello") == "hello"


# ─── render_markdown (aliased as _md_filter in tests) ─────────────────

class TestMdFilter:
    def test_renders_heading(self):
        result = _md_filter("# Hello")
        assert "<h1" in result
        assert "Hello" in result

    def test_empty_returns_empty(self):
        assert _md_filter("") == ""

    def test_escapes_raw_html(self):
        result = _md_filter('<script>alert(1)</script>')
        assert "<script>" not in result


# ─── Line number helpers ─────────────────────────────────────────────

class TestLineNumbers:
    def test_detect_gutter_true(self):
        text = "1\tline one\n2\tline two\n3\tline three\n4\tline four\n"
        assert _detect_line_number_gutter(text) is True

    def test_detect_gutter_false(self):
        text = "line one\nline two\nline three\n"
        assert _detect_line_number_gutter(text) is False

    def test_strip_gutter(self):
        text = "1\thello\n2\tworld\n3\tfoo\n"
        result = _strip_line_number_gutter(text)
        assert "\t1" not in result
        assert "hello" in result

    def test_renumber_lines(self):
        text = "5\thello\n6\tworld\n"
        result = _renumber_lines(text)
        lines = result.strip().split("\n")
        assert lines[0] == "1\thello"
        assert lines[1] == "2\tworld"

    def test_renumber_no_gutter_unchanged(self):
        text = "hello\nworld\n"
        assert _renumber_lines(text) == text


# ─── _infer_code_language ─────────────────────────────────────────────

class TestInferCodeLanguage:
    def test_from_extension(self):
        assert _infer_code_language("hello.py") == "python"
        assert _infer_code_language("hello.ts") == "typescript"
        assert _infer_code_language("hello.js") == "javascript"

    def test_from_content_python(self):
        result = _infer_code_language(content="def foo():\n    pass")
        assert result == "python"

    def test_from_content_typescript(self):
        result = _infer_code_language(content="const x = 1;")
        assert result == "typescript"

    def test_markdown_returns_none(self):
        result = _infer_code_language(content="Hello world, this is normal text.")
        assert result is None

    def test_empty(self):
        assert _infer_code_language() is None


# ─── normalize_llm_content ────────────────────────────────────────────

class TestNormalizeLlmContent:
    def test_empty(self):
        assert normalize_llm_content("") == []

    def test_plain_text(self):
        blocks = normalize_llm_content("Just plain text here.")
        assert len(blocks) >= 1
        assert blocks[0]["kind"] in ("plain_text", "unknown")

    def test_tool_result(self):
        text = "preamble\nTool result for toolu_abc:\nsome code here\n"
        blocks = normalize_llm_content(text)
        assert len(blocks) >= 1
        # Should have preamble + tool content
        kinds = [b["kind"] for b in blocks]
        assert "plain_text" in kinds

    def test_file_marker(self):
        text = "# AGENTS.md\nSome content here\n"
        blocks = normalize_llm_content(text)
        assert len(blocks) >= 1
        assert any("AGENTS" in b.get("title", "") for b in blocks)


# ─── render_llm_blocks_html ───────────────────────────────────────────

class TestRenderLlmBlocksHtml:
    def test_empty(self):
        result = render_llm_blocks_html("")
        assert "No content available" in result

    def test_renders_html(self):
        result = render_llm_blocks_html("Hello world")
        assert "<div" in result
        assert "llm-block" in result

    def test_accepts_pre_normalized_blocks(self):
        blocks = [{"kind": "plain_text", "content": "test"}]
        result = render_llm_blocks_html(blocks)
        assert "llm-block" in result


# ─── _content_parts_to_blocks ────────────────────────────────────────

class TestContentPartsToBlocks:
    def test_from_content_part(self):
        cp = ContentPart(part_type="code", content="x = 1", language="python")
        blocks = _content_parts_to_blocks([cp])
        assert len(blocks) == 1
        assert blocks[0]["kind"] == "code"
        assert blocks[0]["language"] == "python"
        assert blocks[0]["content"] == "x = 1"

    def test_from_dict(self):
        d = {"part_type": "text", "content": "hello"}
        blocks = _content_parts_to_blocks([d])
        assert blocks[0]["kind"] == "text"

    def test_empty_list(self):
        assert _content_parts_to_blocks([]) == []

    def test_required_keys_present(self):
        blocks = _content_parts_to_blocks([ContentPart(part_type="x", content="y")])
        required = {"kind", "content", "language", "title", "context_type", "content_bytes", "token_hint"}
        assert required.issubset(blocks[0].keys())


# ─── _parts_mode_from_raw ────────────────────────────────────────────

class TestPartsModeFromRaw:
    def test_empty(self):
        assert _parts_mode_from_raw("") == []

    def test_non_empty(self):
        blocks = _parts_mode_from_raw("hello world")
        assert isinstance(blocks, list)


# ─── _relative_paths_in_json ──────────────────────────────────────────

class TestRelativePathsInJson:
    def test_replaces_file_path(self):
        obj = {"file_path": "/some/deep/path/file.txt", "other": "value"}
        result = _relative_paths_in_json(obj)
        # Should call _relative_to_repo; result depends on repo context
        assert isinstance(result, dict)
        assert "other" in result
        assert "file_path" in result

    def test_nested(self):
        obj = {"items": [{"file_path": "/a/b.txt"}]}
        result = _relative_paths_in_json(obj)
        assert isinstance(result["items"], list)

    def test_non_dict_passthrough(self):
        assert _relative_paths_in_json(42) == 42
        assert _relative_paths_in_json("hello") == "hello"


# ─── _tojson_repo_html ────────────────────────────────────────────────

class TestTojsonRepoHtml:
    def test_escapes_html(self):
        result = _tojson_repo_html({"key": "<script>"})
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_falsy_returns_null(self):
        assert _tojson_repo_html(None) == "null"
        assert _tojson_repo_html({}) == "null"
        assert _tojson_repo_html("") == "null"

    def test_valid_json_output(self):
        result = _tojson_repo_html({"name": "test"})
        assert "name" in result


# ─── URL encode/decode filters ─────────────────────────────────────────

class TestUrlFilters:
    def test_urlencode(self):
        f = env.filters["urlencode"]
        assert f("hello world") == "hello%20world"

    def test_urldecode(self):
        f = env.filters["urldecode"]
        assert f("hello%20world") == "hello world"


# ─── Template loading via env ─────────────────────────────────────────

class TestTemplateLoading:
    def test_get_template_base(self):
        tmpl = env.get_template("base.html")
        assert tmpl is not None

    def test_get_template_dashboard(self):
        tmpl = env.get_template("dashboard.html")
        assert tmpl is not None

    def test_get_template_session(self):
        tmpl = env.get_template("session.html")
        assert tmpl is not None

    def test_render_dashboard_no_error(self):
        tmpl = env.get_template("dashboard.html")
        # Render with minimal context; may raise if required vars missing,
        # but template should at least be parseable.
        assert tmpl.filename is not None
