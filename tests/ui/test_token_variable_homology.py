"""Token 变量同源性门禁：tokenbar 分段和 tooltip 圆点必须
使用 tokens.css 中定义的同一批 --token-* 语义变量。

此测试静态读取 CSS 源文件（无浏览器执行）并验证：

1. tokens.css 定义规范的 --token-* 语义变量。
2. ui-primitives.css 在 .tokenbar-seg 和 .dot-- 类中使用 --token-* 变量
   （而非遗留的 --claude/--codex/--qoder/--output）。
3. sessions-list.css 和 session-detail.css 不在 .dot-- 类中使用
   遗留 agent/output 变量。

Task T008 — 新增 tokenbar segment/dot 变量同源门禁
关联问题 S-05: token breakdown dot 颜色与 tokenbar segment 不一致
"""

from __future__ import annotations

import pytest
import pathlib
import re

# ── CSS 文件路径 ──────────────────────────────────────────────────────────

_STATIC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src" / "session_browser" / "web" / "static" / "css"
)

TOKENS_CSS = _STATIC / "tokens.css"
UI_PRIMITIVES_CSS = _STATIC / "ui-primitives.css"
SESSIONS_LIST_CSS = _STATIC / "sessions-list.css"
SESSION_DETAIL_CSS = _STATIC / "session-detail.css"

# tokens.css 中必须定义的规范 --token-* 变量
CANONICAL_TOKEN_VARS = [
    "--token-input-fresh",
    "--token-cache-read",
    "--token-cache-write",
    "--token-output-visible",
]

# 不应再用于 token 分类的旧 agent/output 变量
# （它们属于 agent 品牌标识，而非 token 类型）
LEGACY_AGENT_VARS = ["--claude", "--codex", "--qoder", "--output"]


def _read_css(path: pathlib.Path) -> str:
    """读取 CSS 文件并返回其文本内容。"""
    assert path.exists(), f"CSS file not found: {path}"
    return path.read_text(encoding="utf-8")


def _extract_css_variables(css: str) -> set[str]:
    """从 CSS 文本中提取所有 --variable-name 定义。"""
    # 匹配 --variable-name: value; 模式
    return set(re.findall(r'(--[\w-]+)\s*:', css))


def _extract_rules_for_selectors(css: str, selectors: list[str]) -> list[str]:
    """提取匹配给定选择器的 CSS 规则块。"""
    rules = []
    # 匹配 selector { ... } 块（支持多行）
    for selector in selectors:
        # 转义选择器中的特殊正则字符（点、连字符）
        escaped = re.escape(selector)
        pattern = rf'({escaped}\b[^{{}}]*\{{[^}}]*\}})'
        rules.extend(re.findall(pattern, css, re.DOTALL))
    return rules


def _rule_uses_variable(rule: str, var_name: str) -> bool:
    """检查 CSS 规则块是否使用了特定的 CSS 变量。"""
    return f"var({var_name}" in rule


def _rule_uses_legacy_agent_var(rule: str) -> list[str]:
    """返回此规则中使用的旧 agent 变量列表。"""
    found = []
    for var in LEGACY_AGENT_VARS:
        if f"var({var}" in rule:
            found.append(var)
    return found


# ── 1. tokens.css 定义规范 --token-* 变量 ─────────────────────────


class TestTokensCssDefinesVariables:
    """tokens.css 必须定义所有规范的 --token-* 语义变量。"""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(TOKENS_CSS)
        self.variables = _extract_css_variables(self.css)

    @pytest.mark.parametrize("var_name", CANONICAL_TOKEN_VARS)
    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_variable_defined(self, var_name):
        assert var_name in self.variables, (
            f"tokens.css must define {var_name}"
        )


# ── 2. ui-primitives.css 在 tokenbar-seg 中使用 --token-* ─────────────────


class TestUIPrimitivesTokenbarSegments:
    """ui-primitives.css 中 .tokenbar-seg 类必须使用 --token-* 变量。"""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(UI_PRIMITIVES_CSS)

    def _get_segment_rules(self):
        return _extract_rules_for_selectors(
            self.css,
            [".tokenbar-seg.fresh", ".tokenbar-seg.read",
             ".tokenbar-seg.write", ".tokenbar-seg.out"],
        )

    def _get_t_prefix_rules(self):
        return _extract_rules_for_selectors(
            self.css,
            [".t-fresh", ".t-read", ".t-write", ".t-out"],
        )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_fresh_segment_uses_token_var(self):
        """Fresh segment 必须使用 --token-input-fresh，而非 --claude。"""
        rules = self._get_segment_rules()
        fresh_rules = [r for r in rules if ".fresh" in r]
        assert len(fresh_rules) > 0, "No .tokenbar-seg.fresh rule found"
        for rule in fresh_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.fresh uses legacy var(s) {legacy}; "
                f"should use --token-input-fresh"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_read_segment_uses_token_var(self):
        """Read segment 必须使用 --token-cache-read，而非 --codex。"""
        rules = self._get_segment_rules()
        read_rules = [r for r in rules if ".read" in r and ".fresh" not in r]
        assert len(read_rules) > 0, "No .tokenbar-seg.read rule found"
        for rule in read_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.read uses legacy var(s) {legacy}; "
                f"should use --token-cache-read"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_write_segment_uses_token_var(self):
        """Write segment 必须使用 --token-cache-write，而非 --qoder。"""
        rules = self._get_segment_rules()
        write_rules = [r for r in rules if ".write" in r]
        assert len(write_rules) > 0, "No .tokenbar-seg.write rule found"
        for rule in write_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.write uses legacy var(s) {legacy}; "
                f"should use --token-cache-write"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_out_segment_uses_token_var(self):
        """Out segment 必须使用 --token-output-visible，而非 --output。"""
        rules = self._get_segment_rules()
        out_rules = [r for r in rules if ".out" in r and "first-of-type" not in r]
        assert len(out_rules) > 0, "No .tokenbar-seg.out rule found"
        for rule in out_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.out uses legacy var(s) {legacy}; "
                f"should use --token-output-visible"
            )


# ── 3. ui-primitives.css 在 dot-- 类中使用 --token-* ─────────────────────


class TestUIPrimitivesDotClasses:
    """ui-primitives.css 中 .dot-- 类必须使用 --token-* 变量。"""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(UI_PRIMITIVES_CSS)

    def _get_dot_rules(self):
        return _extract_rules_for_selectors(
            self.css,
            [".dot--fresh", ".dot--read", ".dot--write", ".dot--out"],
        )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_dot_fresh_uses_token_var(self):
        """.dot--fresh 必须使用 --token-input-fresh，而非 --claude。"""
        rules = self._get_dot_rules()
        fresh = [r for r in rules if "fresh" in r]
        assert len(fresh) > 0, "No .dot--fresh rule found"
        for rule in fresh:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--fresh uses legacy var(s) {legacy}; "
                f"should use --token-input-fresh"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_dot_read_uses_token_var(self):
        """.dot--read 必须使用 --token-cache-read，而非 --codex。"""
        rules = self._get_dot_rules()
        read = [r for r in rules if "read" in r]
        assert len(read) > 0, "No .dot--read rule found"
        for rule in read:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--read uses legacy var(s) {legacy}; "
                f"should use --token-cache-read"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_dot_write_uses_token_var(self):
        """.dot--write 必须使用 --token-cache-write，而非 --qoder。"""
        rules = self._get_dot_rules()
        write = [r for r in rules if "write" in r]
        assert len(write) > 0, "No .dot--write rule found"
        for rule in write:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--write uses legacy var(s) {legacy}; "
                f"should use --token-cache-write"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_dot_out_uses_token_var(self):
        """.dot--out 必须使用 --token-output-visible，而非 --output。"""
        rules = self._get_dot_rules()
        out = [r for r in rules if "out" in r]
        assert len(out) > 0, "No .dot--out rule found"
        for rule in out:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--out uses legacy var(s) {legacy}; "
                f"should use --token-output-visible"
            )


# ── 4. sessions-list.css 不得在 .dot-- 中使用旧变量 ─────────────────────


class TestSessionsListDotNoLegacy:
    """sessions-list.css 不得在 .dot-- 类中使用 --claude/--codex/--qoder/--output
    （这些是旧的 agent 专属变量）。"""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(SESSIONS_LIST_CSS)

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_no_legacy_vars_in_dot_classes(self):
        dot_rules = _extract_rules_for_selectors(
            self.css,
            [".dot--fresh", ".dot--read", ".dot--write", ".dot--out"],
        )
        for rule in dot_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f"sessions-list.css .dot-- uses legacy var(s) {legacy}"
            )


# ── 5. session-detail.css 不得在 .dot-- 中使用旧变量 ────────────────────


class TestSessionDetailDotNoLegacy:
    """session-detail.css 不得在 .dot-- 类中使用 --claude/--codex/--qoder/--output
    （这些是旧的 agent 专属变量）。"""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(SESSION_DETAIL_CSS)

    @pytest.mark.contract_case("DATA-PRESENTER-013")
    def test_no_legacy_vars_in_dot_classes(self):
        dot_rules = _extract_rules_for_selectors(
            self.css,
            [".dot--fresh", ".dot--read", ".dot--write", ".dot--out"],
        )
        for rule in dot_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f"session-detail.css .dot-- uses legacy var(s) {legacy}"
            )
