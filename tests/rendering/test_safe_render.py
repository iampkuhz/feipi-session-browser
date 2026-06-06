"""web/safe_render.py 测试 — JSON/Code/HTML 安全渲染辅助函数。"""

from __future__ import annotations

import pytest
import json

import html as html_mod

import jinja2
from session_browser.web.safe_render import (
    safe_html_block,
    safe_json_display,
    tojson_safe_html,
    register_filters,
)


# ─── safe_json_display ────────────────────────────────────────────────

class TestSafeJsonDisplay:
    @pytest.mark.contract_case("ROUTE-API-003")
    def test_none_returns_null(self):
        assert safe_json_display(None) == "null"

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_empty_dict_returns_null(self):
        assert safe_json_display({}) == "null"

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_empty_list_returns_null(self):
        assert safe_json_display([]) == "null"

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_empty_string_returns_null(self):
        assert safe_json_display("") == "null"

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_simple_dict(self):
        result = safe_json_display({"key": "value"})
        # 必须先 unescape — 输出已进行 HTML 转义以安全嵌入
        assert json.loads(html_mod.unescape(result)) == {"key": "value"}

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_escapes_script_tag(self):
        """JSON 值中的 HTML 实体必须转义。"""
        payload = {"html": "<script>alert(1)</script>"}
        result = safe_json_display(payload)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_escapes_pre_close(self):
        """必须防止 </pre> 逃逸。"""
        payload = {"code": "</pre><script>alert(1)</script>"}
        result = safe_json_display(payload)
        assert "</pre>" not in result
        assert "&lt;/pre&gt;" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_escapes_ampersand(self):
        result = safe_json_display({"msg": "a & b"})
        assert "&amp;" in result
        assert json.loads(html_mod.unescape(result)) == {"msg": "a & b"}

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_indent_supported(self):
        result = safe_json_display({"a": 1, "b": 2}, indent=2)
        # 缩进时应包含换行
        assert "\n" in result
        assert json.loads(html_mod.unescape(result)) == {"a": 1, "b": 2}

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_unicode_preserved(self):
        result = safe_json_display({"text": "中文"})
        assert "中文" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_safe_inside_pre(self):
        """模拟真实模板上下文：位于 <pre> 标签内。"""
        payload = {"x": "</pre><img onerror=alert(1)>"}
        result = safe_json_display(payload)
        wrapped = f"<pre>{result}</pre>"
        # 不应存在可执行的 HTML
        assert "<img" not in wrapped
        # 转义后的内容不应包含字面量 </pre>
        # （只有外层闭合标签应存在）
        assert wrapped.endswith("</pre>")
        # 内部数据的 </pre> 必须转义为 &lt;/pre&gt;
        assert "&lt;/pre&gt;" in result


# ─── tojson_safe_html ────────────────────────────────────────────────

class TestTojsonSafeHtml:
    @pytest.mark.contract_case("ROUTE-API-003")
    def test_none_returns_null(self):
        assert tojson_safe_html(None) == "null"

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_escapes_dangerous_html(self):
        value = {"note": "<b>bold</b>"}
        result = tojson_safe_html(value)
        assert "<b>" not in result
        assert "&lt;b&gt;" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_roundtrip_json(self):
        value = {"key": "value with <tags>"}
        result = tojson_safe_html(value)
        # 先 unescape 再解析
        import html
        parsed = json.loads(html.unescape(result))
        assert parsed == value

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_indent_parameter(self):
        result = tojson_safe_html({"a": 1}, indent=2)
        assert "\n" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_list_value(self):
        value = [1, 2, {"x": "<script>"}]
        result = tojson_safe_html(value)
        assert "<script>" not in result


# ─── safe_html_block ─────────────────────────────────────────────────

class TestSafeHtmlBlock:
    @pytest.mark.contract_case("ROUTE-API-003")
    def test_wraps_content(self):
        result = safe_html_block("<p>hello</p>")
        assert result == '<div class="safe-html-block"><p>hello</p></div>'

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_custom_class(self):
        result = safe_html_block("<span>x</span>", class_name="my-class")
        assert 'class="my-class"' in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_escapes_class_name(self):
        """恶意类名必须被转义。"""
        result = safe_html_block("x", class_name='"><script>alert(1)</script><"')
        assert "<script>" not in result


# ─── Jinja2 filter integration ───────────────────────────────────────

class TestJinjaFilterIntegration:
    @pytest.fixture
    def env(self):
        env = jinja2.Environment(loader=jinja2.BaseLoader())
        register_filters(env)
        return env

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_safe_json_display_filter(self, env):
        tpl = env.from_string("{{ data | safe_json_display }}")
        result = tpl.render(data={"key": "<script>alert(1)</script>"})
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_safe_html_block_filter(self, env):
        tpl = env.from_string("{{ html | safe_html_block }}")
        result = tpl.render(html="<p>test</p>")
        assert 'class="safe-html-block"' in result
        assert "<p>test</p>" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_tojson_safe_html_filter(self, env):
        tpl = env.from_string("{{ data | tojson_safe_html }}")
        result = tpl.render(data={"x": "</script>"})
        assert "</script>" not in result
        assert "&lt;/script&gt;" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_filter_chain_with_e(self, env):
        """safe_json_display 后接 |e 不应出现双重转义问题。"""
        tpl = env.from_string("{{ data | safe_json_display }}")
        result = tpl.render(data={"msg": "a & b"})
        # 输出应包含 &amp;（由 safe_json_display 转义一次）
        assert "&amp;" in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_filter_in_pre_context(self, env):
        """模板：<pre>{{ data | safe_json_display }}</pre>"""
        tpl = env.from_string("<pre>{{ data | safe_json_display }}</pre>")
        result = tpl.render(data={"code": "</pre><script>x</script>"})
        # 不应包含可执行的 HTML
        assert "<script>" not in result
        # 数据中的 </pre> 应被转义
        assert result.count("</pre>") == 1  # 仅外层一个


class TestRepoJsonFilters:
    """验证 repo JSON filters 不渲染可执行 HTML。"""

    @pytest.fixture
    def env(self):
        from session_browser.web.template_env import env as _env
        return _env

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_tojson_repo_is_now_safe(self, env):
        tpl = env.from_string("{{ data | tojson_repo }}")
        result = tpl.render(data={"path": "/foo", "note": "</pre>"})
        assert "</pre>" not in result

    @pytest.mark.contract_case("ROUTE-API-003")
    def test_tojson_repo_with_indent(self, env):
        tpl = env.from_string("{{ data | tojson_repo(indent=2) }}")
        result = tpl.render(data={"a": 1, "b": "</pre>"})
        assert "\n" in result
        assert "</pre>" not in result
