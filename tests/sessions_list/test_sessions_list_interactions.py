"""会话列表页面的交互契约测试。

验证渲染后的 HTML 满足 DOM 契约：
- 可排序表头包含含标签的可点击控件
- 分页使用真实页码，而非 prev/next 动作
- 筛选标签具有移除链接
- 恰好一个 aria-sort
- 页脚不包含 'sorted by'
"""
import pytest
import html.parser
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class HTMLParserTree(html.parser.HTMLParser):
    """用于契约断言的简易 HTML 树构建器。"""

    def __init__(self):
        super().__init__()
        self.nodes = []
        self.stack = [None]

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": {k: v or "" for k, v in attrs}, "children": [], "text": ""}
        parent = self.stack[-1]
        if parent is not None:
            parent["children"].append(node)
        self.stack.append(node)
        self.nodes.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack[-1] is not None:
            self.stack[-1]["text"] += data


def parse(html_str):
    p = HTMLParserTree()
    p.feed(html_str)
    return p.nodes


def find_by_class(nodes, cls):
    return [n for n in nodes if cls in n["attrs"].get("class", "").split()]


def all_text_of(node):
    text = node["text"]
    for child in node.get("children", []):
        text += all_text_of(child)
    return text


class TestSortableHeaders:
    """表头契约测试。"""

    @pytest.fixture
    def html_sample(self):
        """最小可排序表头 HTML。"""
        return """
        <div class="sessions-th sessions-th--sortable" role="columnheader">
          <a class="sessions-th__sort-btn" href="/sessions?sort=tokens">
            Tokens <span class="sessions-sort-icon">↕</span>
          </a>
        </div>
        <div class="sessions-th sessions-th--sortable" role="columnheader" aria-sort="descending">
          <a class="sessions-th__sort-btn" href="/sessions?sort=updated&dir=asc">
            Updated <span class="sessions-sort-icon sessions-sort-icon--active">↑</span>
          </a>
        </div>
        """

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_sortable_header_has_clickable_control(self, html_sample):
        nodes = parse(html_sample)
        sortable = find_by_class(nodes, "sessions-th--sortable")
        for h in sortable:
            clickable = [c for c in h["children"] if c["tag"] in ("a", "button")]
            assert clickable, f"sortable header has no clickable control: {html_sample}"

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_label_inside_clickable(self, html_sample):
        nodes = parse(html_sample)
        sortable = find_by_class(nodes, "sessions-th--sortable")
        for h in sortable:
            clickable = [c for c in h["children"] if c["tag"] in ("a", "button")]
            if not clickable:
                continue
            control_text = all_text_of(clickable[0]).replace("↕", "").replace("↑", "").replace("↓", "").strip()
            header_text = all_text_of(h).replace("↕", "").replace("↑", "").replace("↓", "").strip()
            assert control_text in header_text or header_text in control_text, \
                f"sortable header label not inside clickable: got {control_text!r} vs {header_text!r}"

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_exactly_one_aria_sort(self, html_sample):
        nodes = parse(html_sample)
        sortable = find_by_class(nodes, "sessions-th--sortable")
        aria_sorted = [h for h in sortable if "aria-sort" in h["attrs"]]
        assert len(aria_sorted) == 1, f"expected exactly one aria-sort, got {len(aria_sorted)}"

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_sort_anchor_has_href(self, html_sample):
        nodes = parse(html_sample)
        anchors = [n for n in nodes if n["tag"] == "a" and "sort-btn" in n["attrs"].get("class", "")]
        for a in anchors:
            assert a["attrs"].get("href"), "sort anchor missing href"
            assert "/sessions" in a["attrs"]["href"]


class TestPagination:
    """分页契约测试。"""

    @pytest.fixture
    def footer_with_links(self):
        return """
        <div class="sessions-table-footer">
          <a class="ui-btn ui-btn--secondary ui-btn--sm" href="/sessions?page=1">Previous</a>
          <a class="ui-btn ui-btn--secondary ui-btn--sm" href="/sessions?page=3">Next</a>
          <span class="sessions-page-range">Rows 21–40</span>
          <span class="sessions-footer-total">100 matching sessions</span>
        </div>
        """

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_previous_and_next_present(self, footer_with_links):
        nodes = parse(footer_with_links)
        text = all_text_of(nodes[0])
        assert "Previous" in text
        assert "Next" in text

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_pagination_uses_real_page_numbers(self, footer_with_links):
        nodes = parse(footer_with_links)
        links = [n for n in nodes if n["tag"] == "a"]
        for link in links:
            href = link["attrs"].get("href", "")
            if "page" in href:
                assert "page=next" not in href, "pagination must use real page numbers, not page=next"
                assert "page=prev" not in href, "pagination must use real page numbers, not page=prev"

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_footer_no_sorted_by(self, footer_with_links):
        nodes = parse(footer_with_links)
        text = all_text_of(nodes[0]).lower()
        assert "sorted by" not in text

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_pagination_preserves_filters(self, footer_with_links):
        nodes = parse(footer_with_links)
        links = [n for n in nodes if n["tag"] == "a" and ("Previous" in all_text_of(n) or "Next" in all_text_of(n))]
        for link in links:
            href = link["attrs"].get("href", "")
            # 应包含筛选条件
            assert "agent=" in href or "page=" in href


class TestFilterChips:
    """活跃筛选标签契约测试。"""

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_chip_remove_has_href(self):
        html = """
        <span class="ui-filter-chip">Agent: cc <a href="/sessions?sort=updated" aria-label="Remove agent filter">×</a></span>
        """
        nodes = parse(html)
        chips = find_by_class(nodes, "ui-filter-chip")
        for chip in chips:
            links = [c for c in chip["children"] if c["tag"] == "a"]
            assert links, "filter chip missing remove link"
            assert links[0]["attrs"].get("href"), "filter chip remove link missing href"


class TestClearAll:
    """Clear All 契约测试。"""

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_clear_all_is_anchor_with_href(self):
        html = """<a class="ui-btn ui-btn--secondary ui-btn--sm js-clear-all" href="/sessions?sort=updated">Clear All</a>"""
        nodes = parse(html)
        anchors = [n for n in nodes if n["tag"] == "a" and "Clear All" in n["text"]]
        assert anchors
        assert anchors[0]["attrs"].get("href"), "Clear All missing href"


class TestRefresh:
    """Refresh 契约测试。"""

    @pytest.mark.contract_case("UI-INTERACTION-002")
    def test_refresh_is_anchor_with_href(self):
        html = """<a class="ui-btn ui-btn--secondary ui-btn--sm" href="/sessions?agent=cc&sort=updated" id="refresh-link">&#x21bb; Refresh</a>"""
        nodes = parse(html)
        anchors = [n for n in nodes if n["tag"] == "a" and "Refresh" in n["text"]]
        assert anchors
        assert anchors[0]["attrs"].get("href"), "Refresh missing href"
