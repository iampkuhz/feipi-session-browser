"""Contract test: ui.token_cell Qoder profile rendering.

S-06: Qoder token breakdown should NOT show cache write/cache read.
This test defines the expected contract and serves as a quality gate.
It will FAIL until the source template is updated to support per-provider profiles.

Contract:
- Qoder (profile="qoder"): only 2 rows — Fresh input + Output
- Non-Qoder (e.g. claude_code): 4 rows — Fresh / Cached Rd / Cached Wr / Output
"""

from __future__ import annotations

import pytest
import pathlib

import jinja2
# ── Jinja2 environment (mirrors test_ui_primitives.py) ──────────────────

_TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "templates"


def _make_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    return env


def _render_token_cell(**kwargs) -> str:
    """Render token_cell macro with the given kwargs."""
    env = _make_env()
    args = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    tmpl_str = (
        '{% from "components/ui_primitives.html" import token_cell %}'
        "{{ token_cell(" + args + ") }}"
    )
    return env.from_string(tmpl_str).render()


def _render_with_profile(provider: str) -> str:
    """Render token_cell as it would be called for a given provider.

    Simulates the caller template logic that would pass a `profile`
    parameter or selectively suppress cache rows.
    """
    # Current macro does not accept profile, so we render with
    # representative values that a real caller would pass.
    # For Qoder: cache values should be zero/absent.
    if provider == "qoder":
        return _render_token_cell(
            total="1.0K",
            fresh_pct=70.0, read_pct=0, write_pct=0, out_pct=30.0,
            fresh_val="700", read_val="0", write_val="0", out_val="300",
            fresh_pct_val="70.0", read_pct_val="0.0", write_pct_val="0.0", out_pct_val="30.0",
            profile="qoder",
        )
    else:
        return _render_token_cell(
            total="2.0K",
            fresh_pct=40.0, read_pct=20.0, write_pct=10.0, out_pct=30.0,
            fresh_val="800", read_val="400", write_val="200", out_val="600",
            fresh_pct_val="40.0", read_pct_val="20.0", write_pct_val="10.0", out_pct_val="30.0",
        )


# ── Token cell type-name rows ────────────────────────────────────────────

_QODER_ALLOWED_TYPE_NAMES = {"Fresh input", "Output"}
_NON_QODER_TYPE_NAMES = {"Fresh input", "Cached Rd", "Cached Wr", "Output"}

_CACHE_KEYWORDS = ["Cached Rd", "Cached Wr", "Cache read", "Cache write", "dot--read", "dot--write"]


class TestTokenCellQoderContract:
    """Qoder profile: only Fresh input and Output rows.

    The token-cell tooltip must NOT contain any cache-related rows
    when rendered for a Qoder session.
    """

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_no_cached_read_row(self):
        html = _render_with_profile("qoder")
        # The contract says Qoder should NOT show Cached Rd
        # This test will FAIL until source template is updated to support profile
        assert "Cached Rd" not in html, (
            "Qoder token_cell must not contain 'Cached Rd' row"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_no_cached_write_row(self):
        html = _render_with_profile("qoder")
        assert "Cached Wr" not in html, (
            "Qoder token_cell must not contain 'Cached Wr' row"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_no_cache_read_keyword(self):
        html = _render_with_profile("qoder")
        for kw in ["Cache read", "cache-read", "cache_read"]:
            assert kw.lower() not in html.lower(), (
                f"Qoder token_cell must not contain '{kw}'"
            )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_no_cache_write_keyword(self):
        html = _render_with_profile("qoder")
        for kw in ["Cache write", "cache-write", "cache_write"]:
            assert kw.lower() not in html.lower(), (
                f"Qoder token_cell must not contain '{kw}'"
            )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_no_read_dot_class(self):
        """No dot--read CSS class in Qoder output."""
        html = _render_with_profile("qoder")
        assert "dot--read" not in html, (
            "Qoder token_cell must not contain dot--read class"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_no_write_dot_class(self):
        """No dot--write CSS class in Qoder output."""
        html = _render_with_profile("qoder")
        assert "dot--write" not in html, (
            "Qoder token_cell must not contain dot--write class"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_has_fresh_row(self):
        html = _render_with_profile("qoder")
        assert "Fresh" in html, "Qoder token_cell must contain Fresh row"

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_has_output_row(self):
        html = _render_with_profile("qoder")
        assert "Output" in html, "Qoder token_cell must contain Output row"

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_type_name_count(self):
        """Qoder tooltip should have exactly 2 type-name rows."""
        html = _render_with_profile("qoder")
        type_names = _extract_type_names(html)
        # Contract: only Fresh + Output = 2
        assert len(type_names) == 2, (
            f"Qoder token_cell should have exactly 2 type rows, got {len(type_names)}: {type_names}"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_qoder_only_allowed_type_names(self):
        """Qoder type names must be a subset of {Fresh, Output}."""
        html = _render_with_profile("qoder")
        type_names = _extract_type_names(html)
        assert type_names <= _QODER_ALLOWED_TYPE_NAMES, (
            f"Qoder token_cell has unexpected type names: {type_names - _QODER_ALLOWED_TYPE_NAMES}"
        )


class TestTokenCellNonQoderContract:
    """Non-Qoder (e.g. claude_code): full 4-segment breakdown.

    Must still show Fresh, Cached Rd, Cached Wr, and Output rows.
    """

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_claude_has_cached_read(self):
        html = _render_with_profile("claude_code")
        assert "Cached Rd" in html, (
            "Non-Qoder token_cell must contain Cached Rd row"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_claude_has_cached_write(self):
        html = _render_with_profile("claude_code")
        assert "Cached Wr" in html, (
            "Non-Qoder token_cell must contain Cached Wr row"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_claude_has_fresh(self):
        html = _render_with_profile("claude_code")
        assert "Fresh" in html, "Non-Qoder token_cell must contain Fresh row"

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_claude_has_output(self):
        html = _render_with_profile("claude_code")
        assert "Output" in html, "Non-Qoder token_cell must contain Output row"

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_claude_four_type_names(self):
        """Non-Qoder tooltip should have exactly 4 type-name rows."""
        html = _render_with_profile("claude_code")
        type_names = _extract_type_names(html)
        assert len(type_names) == 4, (
            f"Non-Qoder token_cell should have exactly 4 type rows, got {len(type_names)}: {type_names}"
        )

    @pytest.mark.contract_case("UI-SESSIONS-016")
    def test_claude_all_expected_type_names(self):
        """Non-Qoder type names must match the expected set."""
        html = _render_with_profile("claude_code")
        type_names = _extract_type_names(html)
        assert type_names == _NON_QODER_TYPE_NAMES, (
            f"Non-Qoder token_cell type names mismatch: got {type_names}"
        )


# ── Helper ───────────────────────────────────────────────────────────────

def _extract_type_names(html: str) -> set[str]:
    """Extract all token-tooltip__type-name values from rendered HTML."""
    import re
    pattern = r'<span class="token-tooltip__type-name">([^<]+)</span>'
    return set(re.findall(pattern, html))
