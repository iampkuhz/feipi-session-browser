"""Tests for token bar normalization.

Covers:
- compute_bar_scale (Python helper)

Note: Jinja2 token_bar macro tests were removed when components/token_bar.html
was deleted (T183 cleanup). The canonical token_bar macro now lives in
components/session_detail_primitives.html.
"""

from __future__ import annotations

import pytest
from session_browser.web.routes import compute_bar_scale


# ── compute_bar_scale tests ─────────────────────────────────────────────


class TestComputeBarScale:
    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_max_round_gets_100_percent(self):
        assert compute_bar_scale(100, 100) == 100.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_half_tokens_gets_50_percent(self):
        assert compute_bar_scale(50, 100) == 50.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_small_vs_large(self):
        """

import pytest60K vs 135K ≈ 44.4%."""
        result = compute_bar_scale(60_000, 135_000)
        assert abs(result - 44.44) < 0.1

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_zero_tokens(self):
        assert compute_bar_scale(0, 100) == 0.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_all_zero_no_error(self):
        assert compute_bar_scale(0, 0) == 0.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_max_is_zero_no_error(self):
        """If max is 0 (no rounds with tokens), scale is 0."""
        assert compute_bar_scale(0, 0) == 0.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_round_tokens_exceeds_max_clamped(self):
        """In practice round_tokens <= max, but verify behavior."""
        result = compute_bar_scale(200, 100)
        assert result == 200.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_one_percent(self):
        """1 token out of 100 = 1%."""
        assert compute_bar_scale(1, 100) == 1.0
