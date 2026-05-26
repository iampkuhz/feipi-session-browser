"""T015 · has_next / offset / page clamp consistency tests.

Guard: on the last page has_next must be false, and page/offset/total_pages
must form a consistent state. See S-09: session list next jumps from page 1
to page 3 with an empty page.

These tests declare the *expected* contract. If any fail, it signals that
compute_pagination's has_next logic needs fixing (source modification is
out of scope for this task).
"""

from __future__ import annotations

import pytest

from session_browser.web.presenters.sessions import compute_pagination


# ─── Core scenario: total_count=40, page_size=20 (exactly 2 pages) ──────

class TestHasNextConsistencyExactTwoPages:
    """total_count=40, page_size=20 → total_pages=2, each page full."""

    def test_page1_has_next_true(self):
        r = compute_pagination(40, 1, 20)
        assert r["total_pages"] == 2
        assert r["page"] == 1
        assert r["offset"] == 0
        assert r["has_next"] is True

    def test_page2_last_page_has_next_false(self):
        """Last page: has_next must be False.
        Current implementation: page_start=21, total_count=40 → 21 < 40 → True.
        This is the S-09 root cause."""
        r = compute_pagination(40, 2, 20)
        assert r["total_pages"] == 2
        assert r["page"] == 2
        assert r["offset"] == 20
        assert r["has_next"] is False, (
            f"last page has_next should be False, got {r['has_next']}; "
            f"page_start={r['page_start']}, total_count=40"
        )

    def test_page3_clamped_to_last(self):
        """Requesting page 3 must clamp to page 2."""
        r = compute_pagination(40, 3, 20)
        assert r["page"] == 2
        assert r["offset"] == 20
        assert r["has_next"] is False


# ─── Edge: partial last page ────────────────────────────────────────────

class TestHasNextPartialLastPage:
    """Last page has fewer items than page_size."""

    def test_last_page_partial_has_next_false(self):
        """total_count=45, page_size=20 → total_pages=3.
        page=3: offset=40, page_start=41, 41 < 45 → current impl returns True.
        Expected: False (this is the last page)."""
        r = compute_pagination(45, 3, 20)
        assert r["total_pages"] == 3
        assert r["page"] == 3
        assert r["offset"] == 40
        assert r["page_end"] == 45
        assert r["has_next"] is False, (
            f"partial last page has_next should be False, got {r['has_next']}"
        )


# ─── Edge: single-item last page ────────────────────────────────────────

class TestHasNextSingleItemLastPage:
    """Last page has exactly 1 item — the only case current impl gets right."""

    def test_single_item_last_page_has_next_false(self):
        """total_count=41, page_size=20 → total_pages=3.
        page=3: offset=40, page_start=41, 41 < 41 → False (correct by luck)."""
        r = compute_pagination(41, 3, 20)
        assert r["total_pages"] == 3
        assert r["page"] == 3
        assert r["offset"] == 40
        assert r["has_next"] is False


# ─── Edge: single page (total_count <= page_size) ───────────────────────

class TestHasNextSinglePage:
    """Only one page exists — has_next must be False."""

    def test_total_equals_page_size_has_next_false(self):
        """total_count=20, page_size=20 → exactly 1 page."""
        r = compute_pagination(20, 1, 20)
        assert r["total_pages"] == 1
        assert r["page"] == 1
        assert r["offset"] == 0
        assert r["has_next"] is False

    def test_total_less_than_page_size_has_next_false(self):
        r = compute_pagination(5, 1, 20)
        assert r["total_pages"] == 1
        assert r["has_next"] is False


# ─── Clamp consistency ──────────────────────────────────────────────────

class TestPageClampConsistency:
    """Clamped page must produce consistent offset + has_next."""

    def test_clamp_to_page_1(self):
        """total_count=10, page_size=20 → total_pages=1. page=5 → clamped to 1."""
        r = compute_pagination(10, 5, 20)
        assert r["page"] == 1
        assert r["offset"] == 0
        assert r["has_next"] is False

    def test_clamp_to_last_page_consistent(self):
        """total_count=50, page_size=20 → total_pages=3. page=10 → clamped to 3."""
        r = compute_pagination(50, 10, 20)
        assert r["page"] == 3
        assert r["offset"] == 40
        assert r["has_next"] is False, (
            f"clamped last page has_next should be False, got {r['has_next']}"
        )

    def test_offset_formula(self):
        """offset = (page - 1) * page_size, after clamp."""
        r = compute_pagination(40, 5, 20)
        assert r["page"] == 2
        assert r["offset"] == (r["page"] - 1) * 20


# ─── Contract: last page invariant ──────────────────────────────────────

class TestLastPageInvariant:
    """For any page == total_pages, has_next must be False."""

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
    def test_clamped_page_has_next_false(self, total_count, page_size):
        """Requesting page >> total_pages must clamp and has_next=False."""
        r = compute_pagination(total_count, 999, page_size)
        tp = max(1, (total_count + page_size - 1) // page_size)
        assert r["page"] == tp
        assert r["has_next"] is False, (
            f"clamped page has_next should be False for "
            f"total_count={total_count}, page_size={page_size}"
        )
