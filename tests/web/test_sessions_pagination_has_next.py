"""T015 · has_next / offset / 页码钳制一致性测试。

门禁：在最后一页 has_next 必须为 false，且 page/offset/total_pages
必须构成一致的状态。参见 S-09：会话列表下一页从第 1 页跳到第 3 页且出现空页的问题。

这些测试声明*预期*契约。如果任何测试失败，表明 compute_pagination 的
has_next 逻辑需要修复（修改源码不在本任务范围内）。
"""

from __future__ import annotations

import pytest
from session_browser.web.presenters.sessions import compute_pagination


# ─── 核心场景：total_count=40, page_size=20（恰好 2 页）──────

class TestHasNextConsistencyExactTwoPages:
    """total_count=40, page_size=20 → total_pages=2，每页满额。"""

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_page1_has_next_true(self):
        r = compute_pagination(40, 1, 20)
        assert r["total_pages"] == 2
        assert r["page"] == 1
        assert r["offset"] == 0
        assert r["has_next"] is True

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_page2_last_page_has_next_false(self):
        """最后一页：has_next 必须为 False。
        当前实现：page_start=21, total_count=40 → 21 < 40 → True。
        这是 S-09 的根本原因。"""
        r = compute_pagination(40, 2, 20)
        assert r["total_pages"] == 2
        assert r["page"] == 2
        assert r["offset"] == 20
        assert r["has_next"] is False, (
            f"last page has_next should be False, got {r['has_next']}; "
            f"page_start={r['page_start']}, total_count=40"
        )

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_page3_clamped_to_last(self):
        """请求第 3 页必须钳制到第 2 页。"""
        r = compute_pagination(40, 3, 20)
        assert r["page"] == 2
        assert r["offset"] == 20
        assert r["has_next"] is False


# ─── 边界：最后一页不满 ────────────────────────────────────────────

class TestHasNextPartialLastPage:
    """最后一页项目数少于 page_size。"""

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_last_page_partial_has_next_false(self):
        """total_count=45, page_size=20 → total_pages=3。
        page=3：offset=40, page_start=41, 41 < 45 → 当前实现返回 True。
        预期：False（这是最后一页）。"""
        r = compute_pagination(45, 3, 20)
        assert r["total_pages"] == 3
        assert r["page"] == 3
        assert r["offset"] == 40
        assert r["page_end"] == 45
        assert r["has_next"] is False, (
            f"partial last page has_next should be False, got {r['has_next']}"
        )


# ─── 边界：最后一页恰好 1 项 ────────────────────────────────────────

class TestHasNextSingleItemLastPage:
    """最后一页恰好只有 1 个项目——当前实现唯一碰巧正确的情况。"""

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_single_item_last_page_has_next_false(self):
        """total_count=41, page_size=20 → total_pages=3。
        page=3：offset=40, page_start=41, 41 < 41 → False（碰巧正确）。"""
        r = compute_pagination(41, 3, 20)
        assert r["total_pages"] == 3
        assert r["page"] == 3
        assert r["offset"] == 40
        assert r["has_next"] is False


# ─── 边界：仅一页（total_count <= page_size）───────────────────────

class TestHasNextSinglePage:
    """仅有一页 — has_next 必须为 False。"""

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_total_equals_page_size_has_next_false(self):
        """total_count=20, page_size=20 → 恰好 1 页。"""
        r = compute_pagination(20, 1, 20)
        assert r["total_pages"] == 1
        assert r["page"] == 1
        assert r["offset"] == 0
        assert r["has_next"] is False

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_total_less_than_page_size_has_next_false(self):
        r = compute_pagination(5, 1, 20)
        assert r["total_pages"] == 1
        assert r["has_next"] is False


# ─── 页码钳制一致性 ─────────────────────────────────────────────────

class TestPageClampConsistency:
    """钳制后的页码必须产生一致的 offset + has_next。"""

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_clamp_to_page_1(self):
        """total_count=10, page_size=20 → total_pages=1。page=5 → 钳制为 1。"""
        r = compute_pagination(10, 5, 20)
        assert r["page"] == 1
        assert r["offset"] == 0
        assert r["has_next"] is False

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_clamp_to_last_page_consistent(self):
        """total_count=50, page_size=20 → total_pages=3。page=10 → 钳制为 3。"""
        r = compute_pagination(50, 10, 20)
        assert r["page"] == 3
        assert r["offset"] == 40
        assert r["has_next"] is False, (
            f"clamped last page has_next should be False, got {r['has_next']}"
        )

    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_offset_formula(self):
        """offset = (page - 1) * page_size，钳制后同样适用。"""
        r = compute_pagination(40, 5, 20)
        assert r["page"] == 2
        assert r["offset"] == (r["page"] - 1) * 20


# ─── 契约：最后一页不变量 ──────────────────────────────────────────

class TestLastPageInvariant:
    """对于任何 page == total_pages 的情况，has_next 必须为 False。"""

    @pytest.mark.parametrize("total_count,page_size", [
        (40, 20),
        (45, 20),
        (100, 20),
        (100, 10),
        (1, 20),
        (20, 20),
        (21, 20),
        (1000, 50),
    ])
    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_last_page_has_next_false(self, total_count, page_size):
        tp = max(1, (total_count + page_size - 1) // page_size)
        r = compute_pagination(total_count, tp, page_size)
        assert r["page"] == tp, (
            f"page should equal total_pages={tp}, got {r['page']}"
        )
        assert r["has_next"] is False, (
            f"total_count={total_count}, page_size={page_size}, "
            f"last_page={tp}: has_next={r['has_next']}, "
            f"page_start={r['page_start']}"
        )

    @pytest.mark.parametrize("total_count,page_size", [
        (40, 20),
        (45, 20),
        (100, 20),
        (100, 10),
        (1, 20),
        (20, 20),
        (21, 20),
        (1000, 50),
    ])
    @pytest.mark.contract_case("DATA-PRESENTER-007", "UI-INTERACTION-004")
    def test_clamped_page_has_next_false(self, total_count, page_size):
        """请求页码远超总页数时必须钳制且 has_next=False。"""
        r = compute_pagination(total_count, 999, page_size)
        tp = max(1, (total_count + page_size - 1) // page_size)
        assert r["page"] == tp
        assert r["has_next"] is False, (
            f"clamped page has_next should be False for "
            f"total_count={total_count}, page_size={page_size}"
        )
