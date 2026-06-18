"""T014: page_size 集合一致门禁测试。

验证后端 VALID_PAGE_SIZES、URL helper page_size_urls、UI 模板 options 三者一致，
包含 25/50/100，且非法值 fallback 到默认 25 不会导致空结果。

覆盖断言：
1. 后端 parse 接受 page_size=25/50/100
2. UI macro / sessions 模板不会产生后端不接受的值（如 10）
3. 非法 page_size fallback 到默认 25，不导致空结果
"""
from __future__ import annotations

import pytest
import pathlib
import re

from session_browser.web.presenters.sessions import (
    VALID_PAGE_SIZES,
    parse_sessions_query_params,
    compute_pagination,
)

# ── 源码路径 ─────────────────────────────────────────────────────────────

_UI_HELPERS = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "templates" / "components" / "ui_primitives" / "_helpers.html"
_URL_HELPERS = pathlib.Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "session_detail" / "url_helpers.py"


# ─── 1. 后端 parse 接受集合 ─────────────────────────────────────────────

class TestBackendPageSizeAcceptance:
    """后端 parse_sessions_query_params 必须接受指定集合。"""

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_accepts_all_valid_sizes(self):
        """VALID_PAGE_SIZES 中每个值都应被正确解析。"""
        for size in VALID_PAGE_SIZES:
            result = parse_sessions_query_params({"page_size": [str(size)]})
            assert result["page_size"] == size, f"page_size={size} was rejected"

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_accepts_page_size_50(self):
        """page_size=50 必须被接受（S-10 修复核心）。"""
        result = parse_sessions_query_params({"page_size": ["50"]})
        assert result["page_size"] == 50

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_accepts_page_size_25(self):
        result = parse_sessions_query_params({"page_size": ["25"]})
        assert result["page_size"] == 25

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_accepts_page_size_100(self):
        result = parse_sessions_query_params({"page_size": ["100"]})
        assert result["page_size"] == 100

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_valid_set_contains_50(self):
        """VALID_PAGE_SIZES 必须包含 50。"""
        assert 50 in VALID_PAGE_SIZES, "VALID_PAGE_SIZES must contain 50"

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_valid_set_contains_25_100(self):
        """VALID_PAGE_SIZES 必须包含 25, 100。"""
        for s in (25, 100):
            assert s in VALID_PAGE_SIZES, f"VALID_PAGE_SIZES must contain {s}"


# ─── 2. 非法值 fallback 到默认 25 ──────────────────────────────────────

class TestInvalidPageSizeFallback:
    """非法 page_size 必须 fallback 到 25，不导致空结果。"""

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_non_member_size_fallbacks_to_25(self):
        """不在 VALID_PAGE_SIZES 中的值应 fallback 到 25。"""
        for size in (10, 30, 99, 200, 1000):
            result = parse_sessions_query_params({"page_size": [str(size)]})
            assert result["page_size"] == 25, f"page_size={size} should fallback to 25"

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_non_numeric_fallbacks_to_25(self):
        for val in ("abc", "xyz", "", "  "):
            result = parse_sessions_query_params({"page_size": [val]})
            assert result["page_size"] == 25, f"page_size='{val}' should fallback to 25"

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_fallback_25_does_not_cause_empty_results(self):
        """fallback 到 25 后，compute_pagination 返回合理的分页结果。"""
        pag = compute_pagination(total_count=55, page=1, page_size=25)
        assert pag["total_pages"] >= 1
        assert pag["limit"] == 25
        assert pag["offset"] == 0

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_fallback_25_with_data_produces_pages(self):
        """有数据时 fallback 到 25 不导致总页数为 0。"""
        pag = compute_pagination(total_count=100, page=1, page_size=25)
        assert pag["total_pages"] == 4
        assert pag["has_next"] is True


# ─── 3. UI 模板 options 与后端集合一致性 ───────────────────────────────

class TestUIPageSizeOptionsConsistency:
    """UI 模板的 page_size_options 必须与后端 VALID_PAGE_SIZES 一致。"""

    def _extract_ui_primitives_options(self) -> list[int]:
        """从 ui_primitives.html 中提取 pagination macro 的默认 options。"""
        with open(_UI_HELPERS) as f:
            content = f.read()
        # 匹配 Jinja2 set 语句中的 default options 列表
        # e.g. {%- set effective_options = page_size_options if page_size_options else [25, 50, 100] -%}
        match = re.search(r'else\s+\[([^\]]+)\]', content)
        if not match:
            pytest.fail("无法在 ui_primitives.html 中找到 effective_options 默认值")
        return [int(x.strip()) for x in match.group(1).split(",")]

    def _extract_routes_page_size_urls(self) -> list[str]:
        """从 URL helper 中提取 page_size_urls 的键集合。"""
        with open(_URL_HELPERS) as f:
            content = f.read()
        # 匹配 for ps in ("20", "100", "500", "all")
        match = re.search(r'for\s+ps\s+in\s+\(([^)]+)\)', content)
        if not match:
            pytest.fail("无法在 routes.py 中找到 page_size_urls 循环")
        return [x.strip().strip('"\'') for x in match.group(1).split(",")]

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_ui_options_are_subset_of_valid_page_sizes(self):
        """UI options 的每个值必须在 VALID_PAGE_SIZES 中。

        如果 UI 产生后端不接受的值（如 10），用户选择后数据会消失。
        """
        ui_options = self._extract_ui_primitives_options()
        invalid = set(ui_options) - VALID_PAGE_SIZES
        assert not invalid, (
            f"UI page_size_options 包含后端不接受的值: {invalid}。"
            f"VALID_PAGE_SIZES = {VALID_PAGE_SIZES}，"
            f"UI options = {ui_options}"
        )

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_ui_options_contains_50(self):
        """UI options 必须包含 50（S-10 修复核心）。"""
        ui_options = self._extract_ui_primitives_options()
        assert 50 in ui_options, (
            f"UI page_size_options 必须包含 50，当前为 {ui_options}"
        )

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_routes_page_size_urls_matches_backend(self):
        """URL helper 中 page_size_urls 的数字部分必须在 VALID_PAGE_SIZES 中。"""
        ps_keys = self._extract_routes_page_size_urls()
        numeric_keys = {int(k) for k in ps_keys if k != "all"}
        invalid = numeric_keys - VALID_PAGE_SIZES
        assert not invalid, (
            f"routes.py page_size_urls 包含 VALID_PAGE_SIZES 之外的值: {invalid}"
        )

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_routes_page_size_urls_contains_50(self):
        """URL helper page_size_urls 必须包含 50。"""
        ps_keys = self._extract_routes_page_size_urls()
        assert "50" in ps_keys, (
            f"URL helper page_size_urls 必须包含 '50'，当前为 {ps_keys}"
        )

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_ui_and_routes_options_consistent(self):
        """UI options 与 routes page_size_urls 数字部分应一致。"""
        ui_options = self._extract_ui_primitives_options()
        ps_keys = self._extract_routes_page_size_urls()
        numeric_keys = {int(k) for k in ps_keys if k != "all"}
        assert set(ui_options) == numeric_keys, (
            f"UI options {ui_options} 与 routes page_size_urls {sorted(numeric_keys)} 不一致"
        )


# ─── 4. 分页完整性：各 size 下翻页不丢失数据 ───────────────────────────

class TestPageSizePaginationIntegrity:
    """不同 page_size 下分页必须覆盖全部数据，不丢失。"""

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_all_page_sizes_cover_same_total(self):
        """page_size=25/50/100 的总条目数应一致。"""
        total = 237
        results = {}
        for size in [25, 50, 100]:
            pag = compute_pagination(total_count=total, page=1, page_size=size)
            results[size] = pag

        for size, pag in results.items():
            expected_pages = -(-total // size)
            assert pag["total_pages"] == expected_pages, (
                f"page_size={size}: expected {expected_pages} pages, got {pag['total_pages']}"
            )

    @pytest.mark.contract_case("DATA-PRESENTER-014")
    def test_page_size_50_produces_valid_pagination(self):
        """page_size=50 是 S-10 修复核心，必须正常工作。"""
        pag = compute_pagination(total_count=123, page=1, page_size=50)
        assert pag["total_pages"] == 3
        assert pag["limit"] == 50
        assert pag["offset"] == 0

        pag2 = compute_pagination(total_count=123, page=2, page_size=50)
        assert pag2["offset"] == 50
        assert pag2["limit"] == 50

        pag3 = compute_pagination(total_count=123, page=3, page_size=50)
        assert pag3["offset"] == 100
        assert pag3["page_end"] == 123
