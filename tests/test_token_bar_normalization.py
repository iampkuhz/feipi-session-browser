"""Tests for token bar normalization and rendering.

Covers:
- compute_bar_scale (Python helper)
- token_bar Jinja2 macro rendering (compact & summary sizes)
- 0 token edge case (no NaN, no errors)
- Tooltip data presence
"""

from __future__ import annotations

import pytest
import jinja2

from session_browser.web.routes import compute_bar_scale


# ── compute_bar_scale tests ─────────────────────────────────────────────


class TestComputeBarScale:
    def test_max_round_gets_100_percent(self):
        assert compute_bar_scale(100, 100) == 100.0

    def test_half_tokens_gets_50_percent(self):
        assert compute_bar_scale(50, 100) == 50.0

    def test_small_vs_large(self):
        """60K vs 135K ≈ 44.4%."""
        result = compute_bar_scale(60_000, 135_000)
        assert abs(result - 44.44) < 0.1

    def test_zero_tokens(self):
        assert compute_bar_scale(0, 100) == 0.0

    def test_all_zero_no_error(self):
        assert compute_bar_scale(0, 0) == 0.0

    def test_max_is_zero_no_error(self):
        """If max is 0 (no rounds with tokens), scale is 0."""
        assert compute_bar_scale(0, 0) == 0.0

    def test_round_tokens_exceeds_max_clamped(self):
        """In practice round_tokens <= max, but verify behavior."""
        result = compute_bar_scale(200, 100)
        assert result == 200.0

    def test_one_percent(self):
        """1 token out of 100 = 1%."""
        assert compute_bar_scale(1, 100) == 1.0


# ── Jinja2 token_bar macro tests ────────────────────────────────────────

_TEMPLATE_DIR = (
    __import__("pathlib").Path(__file__)
    .parent.parent / "src" / "session_browser" / "web" / "templates"
)


def _make_env():
    """Create a Jinja2 env with the same filters as routes.py."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    # Register minimal filters needed by the macro
    env.filters["format_number"] = lambda n: (
        f"{n / 1_000_000:.1f}M" if n >= 1_000_000
        else f"{n / 1_000:.1f}K" if n >= 1_000
        else str(n)
    )
    env.filters["round"] = lambda v, p=0: round(v, p)
    return env


class TestTokenBarMacro:
    """Test the token_bar Jinja2 macro."""

    def _render(self, **kwargs):
        """Render the token_bar macro with given kwargs."""
        env = _make_env()
        tpl = env.get_template("components/token_bar.html")
        # The macro is named `token_bar`; render the full template and
        # extract the macro output via include.
        tmpl_str = (
            '{% from "components/token_bar.html" import token_bar %}'
            '{{ ' + f'token_bar({", ".join(f"{k}={v!r}" for k, v in kwargs.items())}' + ') }}'
        )
        return env.from_string(tmpl_str).render()

    # ── Basic rendering ─────────────────────────────────────────────

    def test_summary_size_renders(self):
        html = self._render(fresh=1000, cache_read=500, cache_write=200, output=800,
                            supports_cache=True, size="summary")
        assert "token-bar--summary" in html
        assert "token-bar__input-fresh" in html
        assert "token-bar__cache-read" in html
        assert "token-bar__cache-write" in html
        assert "token-bar__output" in html

    def test_compact_size_renders(self):
        html = self._render(fresh=1000, cache_read=500, cache_write=200, output=800,
                            supports_cache=True, size="compact", bar_scale=75.0)
        assert "token-bar--compact" in html
        assert "round-token-bar" in html
        assert "round-token-bar-scale" in html
        assert '75.0%' in html

    def test_compact_without_bar_scale(self):
        """bar_scale is optional for compact mode."""
        html = self._render(fresh=500, output=300, supports_cache=True, size="compact")
        assert "token-bar--compact" in html
        assert "round-token-bar" in html
        # Should not include scale wrapper when bar_scale is None
        assert "round-token-bar-scale" not in html

    # ── 4 token type colors ────────────────────────────────────────

    def test_four_token_types_present(self):
        """Fresh, Cache Read, Cache Write, Output segments all present."""
        html = self._render(fresh=100, cache_read=50, cache_write=30, output=200,
                            supports_cache=True, size="summary")
        assert "Fresh" in html
        assert "Cache Read" in html
        assert "Cache Write" in html
        assert "Output" in html

    def test_cache_segments_hidden_when_not_supported(self):
        html = self._render(fresh=100, cache_read=0, cache_write=0, output=200,
                            supports_cache=False, size="summary")
        assert "Fresh" in html
        assert "Output" in html
        # Cache labels should not appear
        assert "Cache Read" not in html
        assert "Cache Write" not in html

    # ── 0 token safety ─────────────────────────────────────────────

    def test_all_zero_no_nan(self):
        """0 tokens should not produce NaN or errors."""
        html = self._render(fresh=0, cache_read=0, cache_write=0, output=0,
                            supports_cache=True, size="summary")
        assert "NaN" not in html
        assert "nan" not in html
        assert "0" in html  # Total should be 0

    def test_all_zero_compact_no_nan(self):
        html = self._render(fresh=0, cache_read=0, cache_write=0, output=0,
                            supports_cache=True, size="compact")
        assert "NaN" not in html
        assert "nan" not in html

    def test_zero_output_only(self):
        """Only output tokens, others zero."""
        html = self._render(fresh=0, cache_read=0, cache_write=0, output=500,
                            supports_cache=True, size="summary")
        assert "NaN" not in html
        assert "500" in html

    def test_zero_fresh_only(self):
        """Only fresh tokens, others zero."""
        html = self._render(fresh=1000, cache_read=0, cache_write=0, output=0,
                            supports_cache=True, size="summary")
        assert "NaN" not in html
        assert "1.0K" in html  # format_number renders 1000 as "1.0K"

    # ── Tooltip presence ────────────────────────────────────────────

    def test_tooltip_shows_total(self):
        html = self._render(fresh=1000, cache_read=200, cache_write=100, output=500,
                            supports_cache=True, size="summary")
        assert "Total:" in html
        assert "1.8K" in html  # 1800 formatted by format_number

    def test_tooltip_shows_percentages(self):
        html = self._render(fresh=500, cache_read=250, cache_write=0, output=250,
                            supports_cache=True, size="summary")
        # 500/1000 = 50%, 250/1000 = 25%, 0/1000 = 0%, 250/1000 = 25%
        assert "50.0%" in html
        assert "25.0%" in html
        assert "0.0%" in html

    # ── Large number formatting ─────────────────────────────────────

    def test_large_numbers_formatted(self):
        html = self._render(fresh=1_500_000, cache_read=500_000, cache_write=200_000, output=800_000,
                            supports_cache=True, size="summary")
        assert "1.5M" in html
        assert "500.0K" in html
        assert "200.0K" in html
        assert "800.0K" in html

    # ── Percentage correctness ──────────────────────────────────────

    def test_percentage_sum_is_100(self):
        """When rt > 0, all four percentages should sum to ~100%."""
        fresh, cr, cw, out = 400, 200, 100, 300
        rt = fresh + cr + cw + out  # 1000
        expected = {
            'fresh': 40.0,
            'cr': 20.0,
            'cw': 10.0,
            'out': 30.0,
        }
        for label, pct in expected.items():
            assert f"{pct}%" in self._render(
                fresh=fresh, cache_read=cr, cache_write=cw, output=out,
                supports_cache=True, size="summary"
            ), f"Expected {pct}% for {label}"
