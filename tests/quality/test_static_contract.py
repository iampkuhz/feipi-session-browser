"""scripts/quality/static_contract_check.py 纯函数测试。"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "quality"))

from static_contract_check import (
    check_no_important,
    check_css_load_order,
    check_no_dead_css,
    check_no_duplicate_base_css,
    check_payload_modal_ownership,
    check_shell_ownership,
    check_innerhtml_safety,
    check_css_ownership_gate,
    check_no_global_component_override,
    check_no_new_legacy_selector,
    check_selector_depth_new_block,
    check_no_raw_innerhtml_new_block,
    check_no_layout_inline_style_new_block,
)


# ── check_no_important ────────────────────────────────────────────────


class TestCheckNoImportant:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_clean_css_passes(self, tmp_path):
        css = tmp_path / "clean.css"
        css.write_text(".foo { color: red; }")
        assert check_no_important([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_important_blocks(self, tmp_path):
        css = tmp_path / "bad.css"
        css.write_text(".foo { color: red !important; }")
        errors = check_no_important([css])
        assert len(errors) == 1
        assert "!important" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_important_in_comment_still_matches(self, tmp_path):
        """import 正则匹配注释中的 !important — 门禁采取保守策略。"""
        css = tmp_path / "commented.css"
        css.write_text("/* color: red !important; */")
        errors = check_no_important([css])
        # 正则仍然匹配，因为我们不为此检查剥离注释
        # （实际 CSS 中没有活跃的 !important，但门禁采取保守策略）
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_multiple_files(self, tmp_path):
        good = tmp_path / "good.css"
        bad = tmp_path / "bad.css"
        good.write_text(".a { margin: 0; }")
        bad.write_text(".b { margin: 0 !important; }")
        errors = check_no_important([good, bad])
        assert len(errors) == 1
        assert "bad.css" in errors[0]


# ── check_css_load_order ──────────────────────────────────────────────


class TestCheckCssLoadOrder:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_correct_order_passes(self):
        html = """
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/base.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    {% block head_extra %}{% endblock %}
    """
        assert check_css_load_order(html) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_wrong_order_blocks(self):
        """ui-primitives 在 shell 之前应拦截。"""
        html = """
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/base.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    {% block head_extra %}{% endblock %}
    """
        errors = check_css_load_order(html)
        assert len(errors) >= 1
        assert "ui-primitives.css" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_missing_item_blocks(self):
        html = """
    <link rel="stylesheet" href="/static/css/tokens.css">
    {% block head_extra %}{% endblock %}
    """
        errors = check_css_load_order(html)
        assert len(errors) >= 1
        assert "缺失必需项" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_head_extra_before_page_css_blocks(self):
        """head_extra 必须出现在 page CSS 之前。"""
        html = """
    <link rel="stylesheet" href="/static/css/tokens.css">
    <link rel="stylesheet" href="/static/css/base.css">
    <link rel="stylesheet" href="/static/css/shell.css">
    <link rel="stylesheet" href="/static/css/ui-primitives.css">
    {% block head_extra %}<link rel="stylesheet" href="/static/css/page.css">{% endblock %}
    """
        # head_extra 中的 page CSS 在 shared primitives 之后是合法的
        errors = check_css_load_order(html)
        assert errors == []


# ── check_no_dead_css ─────────────────────────────────────────────────


class TestCheckNoDeadCss:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_valid_css_passes(self, tmp_path):
        css = tmp_path / "valid.css"
        css.write_text(".foo { color: red; }")
        assert check_no_dead_css([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_only_comments_blocks(self, tmp_path):
        css = tmp_path / "dead.css"
        css.write_text("/* This is a comment */\n/* Another comment */\n")
        errors = check_no_dead_css([css])
        assert len(errors) == 1
        assert "死 CSS 文件" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_empty_file_blocks(self, tmp_path):
        css = tmp_path / "empty.css"
        css.write_text("")
        errors = check_no_dead_css([css])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_only_whitespace_blocks(self, tmp_path):
        css = tmp_path / "whitespace.css"
        css.write_text("   \n\n   \t\n")
        errors = check_no_dead_css([css])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_comment_with_rules_passes(self, tmp_path):
        css = tmp_path / "has_rules.css"
        css.write_text("/* Header */\n.header { display: flex; }")
        assert check_no_dead_css([css]) == []


# ── check_no_duplicate_base_css ─────────────────────────────────────


class TestCheckNoDuplicateBaseCss:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_base_html_skipped(self, tmp_path):
        """base.html 本身应被跳过。"""
        base = tmp_path / "base.html"
        base.write_text('<link rel="stylesheet" href="/static/css/tokens.css">')
        assert check_no_duplicate_base_css([base]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_without_base_css_passes(self, tmp_path):
        """页面模板仅有页面级 CSS 应通过。"""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/dashboard.css">')
        assert check_no_duplicate_base_css([page]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_with_tokens_css_blocks(self, tmp_path):
        """页面加载 tokens.css 应拦截。"""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/tokens.css">')
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "tokens.css" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_with_base_css_blocks(self, tmp_path):
        """页面加载 base.css 应拦截。"""
        page = tmp_path / "dashboard.html"
        page.write_text('<link rel="stylesheet" href="/static/css/base.css">')
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "base.css" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_with_multiple_base_css_blocks(self, tmp_path):
        """页面加载多个基础 CSS 应全部列出。"""
        page = tmp_path / "page.html"
        page.write_text(
            '<link rel="stylesheet" href="/static/css/tokens.css">\n'
            '<link rel="stylesheet" href="/static/css/ui-primitives.css">'
        )
        errors = check_no_duplicate_base_css([page])
        assert len(errors) == 1
        assert "tokens.css" in errors[0]
        assert "ui-primitives.css" in errors[0]


# ── check_payload_modal_ownership ─────────────────────────────────────


class TestCheckPayloadModalOwnership:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_ui_primitives_exempt(self, tmp_path):
        """ui-primitives.css 是权威定义，不应报错或告警。"""
        css = tmp_path / "ui-primitives.css"
        css.write_text(".payload-modal { display: flex; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_bare_payload_modal_blocks(self, tmp_path):
        """非 primitives/legacy 文件中的裸 .payload-modal 应拦截。"""
        css = tmp_path / "session-detail.css"
        css.write_text(".payload-modal { display: flex; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert len(errors) == 1
        assert "payload-modal" in errors[0].lower()
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_scoped_not_warn(self, tmp_path):
        """页面级 .session-detail-page .payload-modal 不应拦截。"""
        css = tmp_path / "session-detail.css"
        css.write_text(".session-detail-page .payload-modal { width: 80vw; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert errors == []
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_level_payload_modal_passes(self, tmp_path):
        """页面级 .session-detail-page .payload-modal 不应拦截。"""
        css = tmp_path / "session-detail.css"
        css.write_text(".session-detail-page .payload-modal { width: 80vw; }")
        errors, warnings = check_payload_modal_ownership([css])
        assert errors == []
        assert warnings == []


# ── check_shell_ownership ─────────────────────────────────────────────


class TestCheckShellOwnership:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_shell_css_exempt(self, tmp_path):
        """shell.css 是 shell 权威定义，不应告警。"""
        css = tmp_path / "shell.css"
        css.write_text(".shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_base_css_exempt(self, tmp_path):
        """base.css 是基础文件，不应告警。"""
        css = tmp_path / "base.css"
        css.write_text("body { font-family: sans-serif; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_tokens_css_exempt(self, tmp_path):
        """tokens.css 是 tokens 文件，不应告警。"""
        css = tmp_path / "tokens.css"
        css.write_text(":root { --shell-w: 220px; }")
        warnings = check_shell_ownership([css])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_css_warns(self, tmp_path):
        """页面 CSS 中含 shell 选择器应告警。"""
        css = tmp_path / "dashboard.css"
        css.write_text(".app-shell { display: grid; }")
        warnings = check_shell_ownership([css])
        assert len(warnings) == 1
        assert ".app-shell" in warnings[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_body_hide_left_warns(self, tmp_path):
        """页面 CSS 中的 body.hide-left 应告警。"""
        css = tmp_path / "agents.css"
        css.write_text("body.hide-left .sidebar { display: none; }")
        warnings = check_shell_ownership([css])
        assert len(warnings) == 1
        assert "body.hide-left" in warnings[0]


# ── check_innerhtml_safety ────────────────────────────────────────────


class TestCheckInnerhtmlSafety:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_no_innerhtml_passes(self, tmp_path):
        """不含 innerHTML 的 JS 不应告警。"""
        js = tmp_path / "clean.js"
        js.write_text("var x = 1;")
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_innerhtml_with_escape_passes(self, tmp_path):
        """innerHTML 带 escapeHtml 辅助函数不应告警。"""
        js = tmp_path / "safe.js"
        js.write_text(
            "function escapeHtml(s) { return s; }"
            "el.innerHTML = escapeHtml(userInput);"
        )
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_innerhtml_with_sanitize_passes(self, tmp_path):
        """innerHTML 带 sanitize 不应告警。"""
        js = tmp_path / "safe.js"
        js.write_text("el.innerHTML = DOMPurify.sanitize(html);")
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_innerhtml_without_safety_warns(self, tmp_path):
        """裸 innerHTML 无安全防护应告警。"""
        js = tmp_path / "unsafe.js"
        js.write_text("el.innerHTML = '<div>' + userInput + '</div>';")
        warnings = check_innerhtml_safety([js])
        assert len(warnings) == 1
        assert "innerHTML" in warnings[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_innerhtml_clearing_not_warned(self, tmp_path):
        """清除 innerHTML (el.innerHTML = '') 不应告警。"""
        js = tmp_path / "clear.js"
        js.write_text("container.innerHTML = '';")
        warnings = check_innerhtml_safety([js])
        assert warnings == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_multiple_files_reports_per_file(self, tmp_path):
        """每个含不安全 innerHTML 的文件应各自产生一条告警。"""
        safe = tmp_path / "safe.js"
        unsafe = tmp_path / "unsafe.js"
        safe.write_text("el.innerHTML = DOMPurify.sanitize(x);")
        unsafe.write_text("el.innerHTML = userInput;")
        warnings = check_innerhtml_safety([safe, unsafe])
        assert len(warnings) == 1
        assert "unsafe.js" in warnings[0]


# ── 集成：真实仓库文件 ──


class TestActualRepoState:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_no_important_in_repo_css(self):
        static = ROOT / "src/session_browser/web/static"
        css_files = list(static.rglob("*.css"))
        errors = check_no_important(css_files)
        assert errors == [], f"!important found: {errors}"

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_css_load_order_in_base_html(self):
        base_html = ROOT / "src/session_browser/web/templates/base.html"
        text = base_html.read_text(encoding="utf-8")
        errors = check_css_load_order(text)
        assert errors == [], f"load order violation: {errors}"

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_no_dead_css_in_repo(self):
        """删除 session-detail-timeline.css 后，不应有死 CSS。"""
        static = ROOT / "src/session_browser/web/static"
        css_files = list(static.rglob("*.css"))
        errors = check_no_dead_css(css_files)
        assert errors == [], f"dead CSS found: {errors}"

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_timeline_css_deleted(self):
        """session-detail-timeline.css 应已被删除。"""
        path = ROOT / "src/session_browser/web/static/css/session-detail-timeline.css"
        assert not path.exists(), "session-detail-timeline.css should be deleted"


# ── CSS/JS ownership gates：bad-fixture 测试 ──


# ── check_css_ownership_gate ──────────────────────────────────────────


class TestCheckCssOwnershipGate:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_clean_page_css_passes(self, tmp_path):
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .card { padding: 16px; }")
        assert check_css_ownership_gate([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_shell_selector_in_page_blocks(self, tmp_path):
        """页面 CSS 定义 .shell 应拦截。"""
        css = tmp_path / "dashboard.css"
        css.write_text(".shell { grid-template-columns: 200px 1fr; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1
        assert ".shell" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_app_shell_in_page_blocks(self, tmp_path):
        """页面 CSS 定义 .app-shell 应拦截。"""
        css = tmp_path / "sessions.css"
        css.write_text(".app-shell { display: grid; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1
        assert ".app-shell" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_body_state_in_page_blocks(self, tmp_path):
        """页面 CSS 定义 body.hide-left 应拦截。"""
        css = tmp_path / "agents.css"
        css.write_text("body.hide-left .sidebar { display: none; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1
        assert "body" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_shell_css_exempt(self, tmp_path):
        """shell.css 定义 .shell 不应报错。"""
        css = tmp_path / "shell.css"
        css.write_text(".shell { grid-template-columns: var(--sidebar) 1fr; }")
        assert check_css_ownership_gate([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_tokens_with_selector_blocks(self, tmp_path):
        """tokens.css 使用非 :root 选择器应拦截。"""
        css = tmp_path / "tokens.css"
        css.write_text(".btn { color: red; }")
        errors = check_css_ownership_gate([css])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_page_grid_template_allowed(self, tmp_path):
        """页面 CSS 为内容网格使用 grid-template-columns 是允许的。"""
        css = tmp_path / "dashboard.css"
        css.write_text(".metric-grid { grid-template-columns: repeat(4, 1fr); }")
        assert check_css_ownership_gate([css]) == []


# ── check_no_global_component_override ────────────────────────────────


class TestCheckNoGlobalComponentOverride:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_clean_page_css_passes(self, tmp_path):
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .card { padding: 16px; }")
        assert check_no_global_component_override([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_bare_payload_modal_blocks(self, tmp_path):
        """页面 CSS 含裸 .payload-modal 应拦截。"""
        css = tmp_path / "session-detail.css"
        css.write_text(".payload-modal { display: flex; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".payload-modal" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_bare_data_table_blocks(self, tmp_path):
        """页面 CSS 含裸 .data-table 应拦截。"""
        css = tmp_path / "sessions.css"
        css.write_text(".data-table { width: 100%; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".data-table" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_bare_btn_blocks(self, tmp_path):
        """页面 CSS 含裸 .btn 应拦截。"""
        css = tmp_path / "dashboard.css"
        css.write_text(".btn { border-radius: 4px; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".btn" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_bare_modal_blocks(self, tmp_path):
        """页面 CSS 含裸 .modal 应拦截。"""
        css = tmp_path / "agents.css"
        css.write_text(".modal { z-index: 1000; }")
        errors = check_no_global_component_override([css])
        assert len(errors) == 1
        assert ".modal" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_ui_primitives_exempt(self, tmp_path):
        """ui-primitives.css 定义 primitives 是允许的。"""
        css = tmp_path / "ui-primitives.css"
        css.write_text(".payload-modal { display: flex; }\n.data-table { width: 100%; }")
        assert check_no_global_component_override([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_scoped_selector_allowed(self, tmp_path):
        """页面级后代选择器是允许的。"""
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .payload-modal { width: 80vw; }")
        assert check_no_global_component_override([css]) == []


# ── check_no_new_legacy_selector ──────────────────────────────────────


class TestCheckNoNewLegacySelector:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_clean_page_css_passes(self, tmp_path):
        css = tmp_path / "dashboard.css"
        css.write_text(".dashboard-page .card { padding: 16px; }")
        assert check_no_new_legacy_selector([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_legacy_app_shell_blocks(self, tmp_path):
        """页面 CSS 中新 .app-shell 引用应拦截。"""
        css = tmp_path / "dashboard.css"
        css.write_text(".app-shell { display: grid; }")
        errors = check_no_new_legacy_selector([css])
        assert len(errors) == 1
        assert ".app-shell" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_shell_css_exempt(self, tmp_path):
        """shell.css 中的遗留引用是允许的。"""
        css = tmp_path / "shell.css"
        css.write_text(".app-shell { display: grid; }")
        assert check_no_new_legacy_selector([css]) == []


# ── check_selector_depth_new_block ────────────────────────────────────


class TestCheckSelectorDepthNewBlock:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_shallow_selectors_pass(self, tmp_path):
        css = tmp_path / "clean.css"
        css.write_text(".foo { color: red; }\n.foo .bar { margin: 0; }")
        assert check_selector_depth_new_block([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_depth_3_passes(self, tmp_path):
        """深度 恰好为 3 应通过（BLOCK_THRESHOLD > 3）。"""
        css = tmp_path / "boundary.css"
        css.write_text(".a .b .c { color: red; }")
        assert check_selector_depth_new_block([css]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_depth_4_blocks(self, tmp_path):
        """深度 > 3 应拦截。"""
        css = tmp_path / "bad.css"
        css.write_text(".a .b .c .d { color: red; }")
        errors = check_selector_depth_new_block([css])
        assert len(errors) == 1
        assert "depth=4" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_child_combinator_counts(self, tmp_path):
        """子组合器计入深度。"""
        css = tmp_path / "bad.css"
        css.write_text(".a > .b + .c .d { color: red; }")
        errors = check_selector_depth_new_block([css])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_pseudo_class_not_extra(self, tmp_path):
        """伪类不增加深度。"""
        css = tmp_path / "ok.css"
        css.write_text(".a .b .c:hover { color: red; }")
        assert check_selector_depth_new_block([css]) == []


# ── check_no_raw_innerhtml_new_block ──────────────────────────────────


class TestCheckNoRawInnerhtmlNewBlock:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_clean_js_passes(self, tmp_path):
        js = tmp_path / "clean.js"
        js.write_text("var x = 1;")
        assert check_no_raw_innerhtml_new_block([js]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_raw_innerhtml_blocks(self, tmp_path):
        """裸 innerHTML = 应拦截。"""
        js = tmp_path / "unsafe.js"
        js.write_text("el.innerHTML = '<div>' + userInput + '</div>';")
        errors = check_no_raw_innerhtml_new_block([js])
        assert len(errors) == 1
        assert "innerHTML" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_innerhtml_clear_allowed(self, tmp_path):
        """清除 innerHTML (innerHTML = '') 不应拦截。"""
        js = tmp_path / "clear.js"
        js.write_text("container.innerHTML = '';")
        assert check_no_raw_innerhtml_new_block([js]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_escapehtml_helper_passes(self, tmp_path):
        """innerHTML 带 escapeHtml 辅助函数应通过。"""
        js = tmp_path / "safe.js"
        js.write_text("function escapeHtml(s) { return s; }\nel.innerHTML = escapeHtml(userInput);")
        assert check_no_raw_innerhtml_new_block([js]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_dompurify_passes(self, tmp_path):
        """innerHTML 带 DOMPurify 应通过。"""
        js = tmp_path / "safe.js"
        js.write_text("el.innerHTML = DOMPurify.sanitize(html);")
        assert check_no_raw_innerhtml_new_block([js]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_comment_line_skipped(self, tmp_path):
        """注释中的 innerHTML 应被跳过。"""
        js = tmp_path / "comment.js"
        js.write_text("// el.innerHTML = 'test';")
        assert check_no_raw_innerhtml_new_block([js]) == []


# ── check_no_layout_inline_style_new_block ────────────────────────────


class TestCheckNoLayoutInlineStyleNewBlock:
    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_clean_html_passes(self, tmp_path):
        html = tmp_path / "clean.html"
        html.write_text('<div class="foo">hello</div>')
        assert check_no_layout_inline_style_new_block([html], []) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_layout_inline_style_blocks(self, tmp_path):
        """HTML 含 layout 内联 style 应拦截。"""
        html = tmp_path / "bad.html"
        html.write_text('<div style="display: flex;">hello</div>')
        errors = check_no_layout_inline_style_new_block([html], [])
        assert len(errors) == 1
        assert "layout inline style" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_custom_property_only_passes(self, tmp_path):
        """纯 CSS 自定义属性不应拦截。"""
        html = tmp_path / "custom.html"
        html.write_text('<div style="--segment-width: 200px;">hello</div>')
        assert check_no_layout_inline_style_new_block([html], []) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_mixed_custom_property_blocks(self, tmp_path):
        """自定义属性 + layout 属性应拦截。"""
        html = tmp_path / "mixed.html"
        html.write_text('<div style="--segment-width: 200px; display: flex;">hello</div>')
        errors = check_no_layout_inline_style_new_block([html], [])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_template_variable_skipped(self, tmp_path):
        """模板变量注入应被跳过。"""
        html = tmp_path / "template.html"
        html.write_text('<div style="{{ grid_style }}">hello</div>')
        assert check_no_layout_inline_style_new_block([html], []) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_js_style_display_blocks(self, tmp_path):
        """JS .style.display = 应拦截。"""
        js = tmp_path / "bad.js"
        js.write_text("el.style.display = 'none';")
        errors = check_no_layout_inline_style_new_block([], [js])
        assert len(errors) == 1
        assert ".style" in errors[0]

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_js_style_position_blocks(self, tmp_path):
        """JS .style.position = 应拦截。"""
        js = tmp_path / "bad.js"
        js.write_text("el.style.position = 'absolute';")
        errors = check_no_layout_inline_style_new_block([], [js])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_js_style_width_blocks(self, tmp_path):
        """JS .style.width = 应拦截。"""
        js = tmp_path / "bad.js"
        js.write_text("el.style.width = '100px';")
        errors = check_no_layout_inline_style_new_block([], [js])
        assert len(errors) == 1

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_js_comment_skipped(self, tmp_path):
        """JS 注释中的 .style 应被跳过。"""
        js = tmp_path / "comment.js"
        js.write_text("// el.style.display = 'none';")
        assert check_no_layout_inline_style_new_block([], [js]) == []

    @pytest.mark.contract_case("HOOK-HARNESS-013")
    def test_new_important_blocks(self, tmp_path):
        """新增的 !important 仍应被 check_no_important 捕获。"""
        css = tmp_path / "bad.css"
        css.write_text(".foo { color: red !important; }")
        errors = check_no_important([css])
        assert len(errors) == 1
