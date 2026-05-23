"""Tests for web/safe_render.py — JSON/Code/HTML safe rendering helpers."""

from __future__ import annotations

import json

import html as html_mod

import jinja2
import pytest

from session_browser.web.safe_render import (
    safe_html_block,
    safe_json_display,
    tojson_safe_html,
    register_filters,
)


# ─── safe_json_display ────────────────────────────────────────────────

class TestSafeJsonDisplay:
    def test_none_returns_null(self):
        assert safe_json_display(None) == "null"

    def test_empty_dict_returns_null(self):
        assert safe_json_display({}) == "null"

    def test_empty_list_returns_null(self):
        assert safe_json_display([]) == "null"

    def test_empty_string_returns_null(self):
        assert safe_json_display("") == "null"

    def test_simple_dict(self):
        result = safe_json_display({"key": "value"})
        # Must unescape first — the output is HTML-escaped for safe embedding
        assert json.loads(html_mod.unescape(result)) == {"key": "value"}

    def test_escapes_script_tag(self):
        """HTML entities in JSON values must be escaped."""
        payload = {"html": "<script>alert(1)</script>"}
        result = safe_json_display(payload)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_escapes_pre_close(self):
        """</pre> breakout must be prevented."""
        payload = {"code": "</pre><script>alert(1)</script>"}
        result = safe_json_display(payload)
        assert "</pre>" not in result
        assert "&lt;/pre&gt;" in result

    def test_escapes_ampersand(self):
        result = safe_json_display({"msg": "a & b"})
        assert "&amp;" in result
        assert json.loads(html_mod.unescape(result)) == {"msg": "a & b"}

    def test_indent_supported(self):
        result = safe_json_display({"a": 1, "b": 2}, indent=2)
        # Should contain newlines when indented
        assert "\n" in result
        assert json.loads(html_mod.unescape(result)) == {"a": 1, "b": 2}

    def test_unicode_preserved(self):
        result = safe_json_display({"text": "中文"})
        assert "中文" in result

    def test_safe_inside_pre(self):
        """Simulate the actual template context: inside <pre> tags."""
        payload = {"x": "</pre><img onerror=alert(1)>"}
        result = safe_json_display(payload)
        wrapped = f"<pre>{result}</pre>"
        # No executable HTML should exist
        assert "<img" not in wrapped
        # The escaped content should not contain literal </pre>
        # (only the outer closing tag should exist)
        assert wrapped.endswith("</pre>")
        # The inner data's </pre> must be escaped to &lt;/pre&gt;
        assert "&lt;/pre&gt;" in result


# ─── tojson_safe_html ────────────────────────────────────────────────

class TestTojsonSafeHtml:
    def test_none_returns_null(self):
        assert tojson_safe_html(None) == "null"

    def test_escapes_dangerous_html(self):
        value = {"note": "<b>bold</b>"}
        result = tojson_safe_html(value)
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    def test_roundtrip_json(self):
        value = {"key": "value with <tags>"}
        result = tojson_safe_html(value)
        # Unescape then parse
        import html
        parsed = json.loads(html.unescape(result))
        assert parsed == value

    def test_indent_parameter(self):
        result = tojson_safe_html({"a": 1}, indent=2)
        assert "\n" in result

    def test_list_value(self):
        value = [1, 2, {"x": "<script>"}]
        result = tojson_safe_html(value)
        assert "<script>" not in result


# ─── safe_html_block ─────────────────────────────────────────────────

class TestSafeHtmlBlock:
    def test_wraps_content(self):
        result = safe_html_block("<p>hello</p>")
        assert result == '<div class="safe-html-block"><p>hello</p></div>'

    def test_custom_class(self):
        result = safe_html_block("<span>x</span>", class_name="my-class")
        assert 'class="my-class"' in result

    def test_escapes_class_name(self):
        """Malicious class names must be escaped."""
        result = safe_html_block("x", class_name='"><script>alert(1)</script><"')
        assert "<script>" not in result


# ─── Jinja2 filter integration ───────────────────────────────────────

class TestJinjaFilterIntegration:
    @pytest.fixture
    def env(self):
        env = jinja2.Environment(loader=jinja2.BaseLoader())
        register_filters(env)
        return env

    def test_safe_json_display_filter(self, env):
        tpl = env.from_string("{{ data | safe_json_display }}")
        result = tpl.render(data={"key": "<script>alert(1)</script>"})
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_safe_html_block_filter(self, env):
        tpl = env.from_string("{{ html | safe_html_block }}")
        result = tpl.render(html="<p>test</p>")
        assert 'class="safe-html-block"' in result
        assert "<p>test</p>" in result

    def test_tojson_safe_html_filter(self, env):
        tpl = env.from_string("{{ data | tojson_safe_html }}")
        result = tpl.render(data={"x": "</script>"})
        assert "</script>" not in result
        assert "&lt;/script&gt;" in result

    def test_filter_chain_with_e(self, env):
        """safe_json_display followed by |e should not double-escape issues."""
        tpl = env.from_string("{{ data | safe_json_display }}")
        result = tpl.render(data={"msg": "a & b"})
        # The output should contain &amp; (escaped once by safe_json_display)
        assert "&amp;" in result

    def test_filter_in_pre_context(self, env):
        """Template: <pre>{{ data | safe_json_display }}</pre>"""
        tpl = env.from_string("<pre>{{ data | safe_json_display }}</pre>")
        result = tpl.render(data={"code": "</pre><script>x</script>"})
        # Should not contain executable HTML
        assert "<script>" not in result
        # The </pre> inside data should be escaped
        assert result.count("</pre>") == 1  # only the outer one


# ─── Backward compatibility with existing filters ────────────────────

class TestBackwardCompat:
    """Ensure the new safe_json_display replaces tojson_safe behavior
    without breaking existing template usage."""

    @pytest.fixture
    def env(self):
        from session_browser.web.routes import _template_env
        return _template_env

    def test_tojson_safe_is_now_safe(self, env):
        tpl = env.from_string("{{ data | tojson_safe }}")
        result = tpl.render(data={"x": "<script>alert(1)</script>"})
        assert "<script>" not in result

    def test_tojson_repo_is_now_safe(self, env):
        tpl = env.from_string("{{ data | tojson_repo }}")
        result = tpl.render(data={"path": "/foo", "note": "</pre>"})
        assert "</pre>" not in result

    def test_tojson_repo_with_indent(self, env):
        tpl = env.from_string("{{ data | tojson_repo(indent=2) }}")
        result = tpl.render(data={"a": 1, "b": "</pre>"})
        assert "\n" in result
        assert "</pre>" not in result
