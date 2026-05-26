"""Token variable homology gate: tokenbar segments and tooltip dots must
use the same --token-* semantic variables defined in tokens.css.

This test reads CSS source files statically (no browser execution) and
verifies that:

1. tokens.css defines the canonical --token-* semantic variables.
2. ui-primitives.css uses --token-* variables (not legacy --claude/--codex/
   --qoder/--output) for .tokenbar-seg and .dot-- classes.
3. sessions-list.css and session-detail.css do not use legacy agent/output
   variables for .dot-- classes.

Task T008 — 新增 tokenbar segment/dot 变量同源门禁
关联问题 S-05: token breakdown dot 颜色与 tokenbar segment 不一致
"""

from __future__ import annotations

import pathlib
import re

import pytest

# ── Paths to CSS files ──────────────────────────────────────────────────

_STATIC = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src" / "session_browser" / "web" / "static" / "css"
)

TOKENS_CSS = _STATIC / "tokens.css"
UI_PRIMITIVES_CSS = _STATIC / "ui-primitives.css"
SESSIONS_LIST_CSS = _STATIC / "sessions-list.css"
SESSION_DETAIL_CSS = _STATIC / "session-detail.css"

# Canonical --token-* variables that must be defined in tokens.css
CANONICAL_TOKEN_VARS = [
    "--token-input-fresh",
    "--token-cache-read",
    "--token-cache-write",
    "--token-output-visible",
]

# Legacy agent/output variables that should NOT be used for token
# categorization (they belong to agent branding, not token types).
LEGACY_AGENT_VARS = ["--claude", "--codex", "--qoder", "--output"]


def _read_css(path: pathlib.Path) -> str:
    """Read a CSS file and return its text content."""
    assert path.exists(), f"CSS file not found: {path}"
    return path.read_text(encoding="utf-8")


def _extract_css_variables(css: str) -> set[str]:
    """Extract all --variable-name definitions from CSS text."""
    # Match patterns like --variable-name: value;
    return set(re.findall(r'(--[\w-]+)\s*:', css))


def _extract_rules_for_selectors(css: str, selectors: list[str]) -> list[str]:
    """Extract CSS rule blocks matching any of the given selectors."""
    rules = []
    # Match selector { ... } blocks (handles multi-line)
    for selector in selectors:
        # Escape special regex chars in selector (dots, hyphens)
        escaped = re.escape(selector)
        pattern = rf'({escaped}\b[^{{}}]*\{{[^}}]*\}})'
        rules.extend(re.findall(pattern, css, re.DOTALL))
    return rules


def _rule_uses_variable(rule: str, var_name: str) -> bool:
    """Check if a CSS rule block uses a specific CSS variable."""
    return f"var({var_name}" in rule


def _rule_uses_legacy_agent_var(rule: str) -> list[str]:
    """Return list of legacy agent variables used in this rule."""
    found = []
    for var in LEGACY_AGENT_VARS:
        if f"var({var}" in rule:
            found.append(var)
    return found


# ── 1. tokens.css defines canonical --token-* variables ──────────────────


class TestTokensCssDefinesVariables:
    """tokens.css must define all canonical --token-* semantic variables."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(TOKENS_CSS)
        self.variables = _extract_css_variables(self.css)

    @pytest.mark.parametrize("var_name", CANONICAL_TOKEN_VARS)
    def test_variable_defined(self, var_name):
        assert var_name in self.variables, (
            f"tokens.css must define {var_name}"
        )


# ── 2. ui-primitives.css uses --token-* for tokenbar-seg ─────────────────


class TestUIPrimitivesTokenbarSegments:
    """.tokenbar-seg classes in ui-primitives.css must use --token-* vars."""

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

    def test_fresh_segment_uses_token_var(self):
        """Fresh segment must use --token-input-fresh, not --claude."""
        rules = self._get_segment_rules()
        fresh_rules = [r for r in rules if ".fresh" in r]
        assert len(fresh_rules) > 0, "No .tokenbar-seg.fresh rule found"
        for rule in fresh_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.fresh uses legacy var(s) {legacy}; "
                f"should use --token-input-fresh"
            )

    def test_read_segment_uses_token_var(self):
        """Read segment must use --token-cache-read, not --codex."""
        rules = self._get_segment_rules()
        read_rules = [r for r in rules if ".read" in r and ".fresh" not in r]
        assert len(read_rules) > 0, "No .tokenbar-seg.read rule found"
        for rule in read_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.read uses legacy var(s) {legacy}; "
                f"should use --token-cache-read"
            )

    def test_write_segment_uses_token_var(self):
        """Write segment must use --token-cache-write, not --qoder."""
        rules = self._get_segment_rules()
        write_rules = [r for r in rules if ".write" in r]
        assert len(write_rules) > 0, "No .tokenbar-seg.write rule found"
        for rule in write_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.write uses legacy var(s) {legacy}; "
                f"should use --token-cache-write"
            )

    def test_out_segment_uses_token_var(self):
        """Out segment must use --token-output-visible, not --output."""
        rules = self._get_segment_rules()
        out_rules = [r for r in rules if ".out" in r and "first-of-type" not in r]
        assert len(out_rules) > 0, "No .tokenbar-seg.out rule found"
        for rule in out_rules:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".tokenbar-seg.out uses legacy var(s) {legacy}; "
                f"should use --token-output-visible"
            )


# ── 3. ui-primitives.css uses --token-* for dot-- classes ────────────────


class TestUIPrimitivesDotClasses:
    """.dot-- classes in ui-primitives.css must use --token-* vars."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(UI_PRIMITIVES_CSS)

    def _get_dot_rules(self):
        return _extract_rules_for_selectors(
            self.css,
            [".dot--fresh", ".dot--read", ".dot--write", ".dot--out"],
        )

    def test_dot_fresh_uses_token_var(self):
        """.dot--fresh must use --token-input-fresh, not --claude."""
        rules = self._get_dot_rules()
        fresh = [r for r in rules if "fresh" in r]
        assert len(fresh) > 0, "No .dot--fresh rule found"
        for rule in fresh:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--fresh uses legacy var(s) {legacy}; "
                f"should use --token-input-fresh"
            )

    def test_dot_read_uses_token_var(self):
        """.dot--read must use --token-cache-read, not --codex."""
        rules = self._get_dot_rules()
        read = [r for r in rules if "read" in r]
        assert len(read) > 0, "No .dot--read rule found"
        for rule in read:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--read uses legacy var(s) {legacy}; "
                f"should use --token-cache-read"
            )

    def test_dot_write_uses_token_var(self):
        """.dot--write must use --token-cache-write, not --qoder."""
        rules = self._get_dot_rules()
        write = [r for r in rules if "write" in r]
        assert len(write) > 0, "No .dot--write rule found"
        for rule in write:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--write uses legacy var(s) {legacy}; "
                f"should use --token-cache-write"
            )

    def test_dot_out_uses_token_var(self):
        """.dot--out must use --token-output-visible, not --output."""
        rules = self._get_dot_rules()
        out = [r for r in rules if "out" in r]
        assert len(out) > 0, "No .dot--out rule found"
        for rule in out:
            legacy = _rule_uses_legacy_agent_var(rule)
            assert not legacy, (
                f".dot--out uses legacy var(s) {legacy}; "
                f"should use --token-output-visible"
            )


# ── 4. sessions-list.css must not use legacy vars for .dot-- ─────────────


class TestSessionsListDotNoLegacy:
    """sessions-list.css must not use --claude/--codex/--qoder/--output
    for .dot-- classes (these are old agent-specific variables)."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(SESSIONS_LIST_CSS)

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


# ── 5. session-detail.css must not use legacy vars for .dot-- ────────────


class TestSessionDetailDotNoLegacy:
    """session-detail.css must not use --claude/--codex/--qoder/--output
    for .dot-- classes (these are old agent-specific variables)."""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.css = _read_css(SESSION_DETAIL_CSS)

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
