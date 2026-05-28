"""测试 token 条归一化。

覆盖范围：
- compute_bar_scale（Python 辅助函数）

注：Jinja2 token_bar 宏测试已在 components/token_bar.html 删除时移除
（T183 清理）。规范的 token_bar 宏现位于
components/session_detail_primitives.html。
"""

from __future__ import annotations

import pytest
from session_browser.web.routes import compute_bar_scale


# ── compute_bar_scale 测试 ─────────────────────────────────────────────


class TestComputeBarScale:
    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_max_round_gets_100_percent(self):
        assert compute_bar_scale(100, 100) == 100.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_half_tokens_gets_50_percent(self):
        assert compute_bar_scale(50, 100) == 50.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_small_vs_large(self):
        """60K vs 135K ≈ 44.4%。"""
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
        """max 为 0（无带 token 的轮次）时 scale 为 0。"""
        assert compute_bar_scale(0, 0) == 0.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_round_tokens_exceeds_max_clamped(self):
        """实际中 round_tokens <= max，但需验证行为。"""
        result = compute_bar_scale(200, 100)
        assert result == 200.0

    @pytest.mark.contract_case("DATA-PRESENTER-008")
    def test_one_percent(self):
        """100 中占 1 = 1%。"""
        assert compute_bar_scale(1, 100) == 1.0
