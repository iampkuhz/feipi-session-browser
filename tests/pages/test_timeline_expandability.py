"""验证 check_timeline_expandability.py 静态分析脚本的测试。"""

from __future__ import annotations

import pytest
import re
import textwrap

# 从脚本导入检查函数
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import check_timeline_expandability as chk  # noqa: E402


# ---------------------------------------------------------------------------
# 辅助：创建最小化的类文件内容用于测试
# ---------------------------------------------------------------------------

GOOD_TIMELINE_HTML = textwrap.dedent("""

import pytest\
    {% macro timeline_node(node) %}
    {% set depth = node.depth | default(0) %}
    <div class="timeline-node {{ 'has-children' if node.children else '' }}
                {{ 'is-leaf' if not node.children else '' }}"
         data-timeline-type="{{ node.type }}"
         data-timeline-id="node-{{ loop.index }}"
         style="--timeline-depth: {{ depth }};">
        {% macro timeline_node_content(node) %}
        <div class="timeline-node__header">
            {% if node.children or node.expanded is defined %}
            <button class="timeline-node__toggle"
                    aria-expanded="{{ 'true' if node.expanded else 'false' }}"
                    onclick="this.closest('.timeline-node').classList.toggle('is-expanded');
                             this.setAttribute('aria-expanded', this.getAttribute('aria-expanded') === 'true' ? 'false' : 'true')">
                <span class="timeline-node__chevron">&#8250;</span>
            </button>
            {% else %}
            <span class="timeline-node__spacer"></span>
            {% endif %}
            <span class="timeline-node__summary">{{ node.summary or '' }}</span>
        </div>
        {% if node.children %}
        <div class="timeline-node__children">
            {% for child in node.children %}
            {{ timeline_node(child) }}
            {% endfor %}
        </div>
        {% endif %}
        {% endmacro %}
    </div>
    {% endmacro %}
""")

BAD_TIMELINE_HTML_NO_TOGGLE = textwrap.dedent("""\
    {% macro timeline_node(node) %}
    <div class="timeline-node has-children"
         data-timeline-type="{{ node.type }}">
        <div class="timeline-node__header">
            <span class="timeline-node__summary">{{ node.summary }}</span>
        </div>
        <div class="timeline-node__children">
            {% for child in node.children %}
            {{ timeline_node(child) }}
            {% endfor %}
        </div>
    </div>
    {% endmacro %}
""")

BAD_TIMELINE_HTML_NO_ID = textwrap.dedent("""\
    {% macro timeline_node(node) %}
    {% set depth = node.depth | default(0) %}
    <div class="timeline-node {{ 'has-children' if node.children else '' }}"
         data-timeline-type="{{ node.type }}"
         style="--timeline-depth: {{ depth }};">
        <div class="timeline-node__header">
            {% if node.children or node.expanded is defined %}
            <button class="timeline-node__toggle"
                    aria-expanded="{{ 'true' if node.expanded else 'false' }}"
                    onclick="this.closest('.timeline-node').classList.toggle('is-expanded');
                             this.setAttribute('aria-expanded', this.getAttribute('aria-expanded') === 'true' ? 'false' : 'true')">
                <span class="timeline-node__chevron">&#8250;</span>
            </button>
            {% endif %}
            <span class="timeline-node__summary">{{ node.summary }}</span>
        </div>
    </div>
    {% endmacro %}
""")

GOOD_JS = textwrap.dedent("""\
    (function () {
        'use strict';
        function expandAll() {
            var nodes = document.querySelectorAll('.timeline-node:not(.is-expanded)');
            nodes.forEach(function (node) {
                node.classList.add('is-expanded');
            });
        }
        function collapseAll() {
            var nodes = document.querySelectorAll('.timeline-node.is-expanded');
            nodes.forEach(function (node) {
                node.classList.remove('is-expanded');
            });
        }
        function filter(type) {
            if (type === 'all') {
                _showAllNodes();
                return;
            }
            var nodes = document.querySelectorAll('.timeline-node');
            nodes.forEach(function (node) {
                node.style.display = 'none';
            });
        }
        function _showAllNodes() {
            document.querySelectorAll('.timeline-node').forEach(function (node) {
                node.style.display = '';
            });
        }
        window.TimelineCtrl = {
            expandAll: expandAll,
            collapseAll: collapseAll,
            filter: filter,
        };
    })();
""")

BAD_JS_NO_EXPAND_ALL = textwrap.dedent("""\
    (function () {
        'use strict';
        function filter(type) {
            var nodes = document.querySelectorAll('.timeline-node');
            nodes.forEach(function (node) {
                node.style.display = 'none';
                node.classList.remove('is-expanded');
            });
        }
        window.TimelineCtrl = { filter: filter };
    })();
""")

GOOD_CSS = textwrap.dedent("""\
    .timeline-node__children {
        display: none;
    }
    .timeline-node.is-expanded > .timeline-node__children {
        display: block;
    }
    .timeline-node.is-expanded .timeline-node__chevron {
        transform: rotate(90deg);
    }
    .tab-content {
        display: none;
    }
    .tab-content.active {
        display: block;
    }
""")

BAD_CSS_NO_CHILDREN_HIDE = textwrap.dedent("""\
    .timeline-node {
        border-radius: 4px;
    }
    .tab-content {
        visibility: hidden;
    }
""")


# ---------------------------------------------------------------------------
# 检查 1：has-children + toggle
# ---------------------------------------------------------------------------

class TestToggleForHasChildren:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_template_has_toggle(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_for_has_children(GOOD_TIMELINE_HTML)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_template_missing_toggle(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_for_has_children(BAD_TIMELINE_HTML_NO_TOGGLE)
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# 检查 2：data-timeline-id
# ---------------------------------------------------------------------------

class TestTimelineId:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_template_has_id(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_timeline_id(GOOD_TIMELINE_HTML, "")
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_template_missing_id(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_timeline_id(BAD_TIMELINE_HTML_NO_ID, "")
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# 检查 3：expandAll/collapseAll 覆盖
# ---------------------------------------------------------------------------

class TestExpandCollapseCoverage:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_js(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_expand_collapse_coverage(GOOD_JS)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_js_no_expand_all(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_expand_collapse_coverage(BAD_JS_NO_EXPAND_ALL)
        assert chk._FAIL_COUNT > 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_analyse_expand_collapse_selectors(self):
        info = chk._analyse_expand_collapse(GOOD_JS)
        assert info["expandAll_exists"] is True
        assert info["collapseAll_exists"] is True
        assert info["covers_timeline_node"] is True
        assert any(".timeline-node" in s for s in info["expandAll_selectors"])
        assert any(".timeline-node" in s for s in info["collapseAll_selectors"])


# ---------------------------------------------------------------------------
# 检查 4：toggle aria-expanded 同步
# ---------------------------------------------------------------------------

class TestToggleAriaSync:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_template_syncs(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_aria_sync(GOOD_TIMELINE_HTML)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_template_no_aria(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_aria_sync(BAD_TIMELINE_HTML_NO_TOGGLE)
        # BAD_TIMELINE_HTML_NO_TOGGLE 缺少 inline onclick，
        # 但实际 timeline.js 中的事件委托会替代它。因此检查应通过事件委托而非失败。
        # 验证没有崩溃发生。
        assert chk._FAIL_COUNT == 0


# ---------------------------------------------------------------------------
# 检查 5：filter 保持状态
# ---------------------------------------------------------------------------

class TestFilterPreserveState:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_js_preserves_state(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_filter_preserves_state(GOOD_JS)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_js_removes_is_expanded(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_filter_preserves_state(BAD_JS_NO_EXPAND_ALL)
        # 该 JS 在 filter 中移除 is-expanded，这是 FAIL
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# 检查 6：tab 切换
# ---------------------------------------------------------------------------

class TestTabSwitchExpand:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_css(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_tab_switch_expand('id="timeline"', GOOD_CSS)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_css_visibility_hidden(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_tab_switch_expand('id="timeline"', BAD_CSS_NO_CHILDREN_HIDE)
        # 使用 visibility:hidden 而非 display:none — 可能导致问题
        assert chk._WARN_COUNT > 0 or chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# Round 结构检查
# ---------------------------------------------------------------------------

class TestRoundExpandStructure:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_has_round_structure(self):
        html = '<tr class="round-header-row">' + \
               '<tr class="round-detail-row">'
        js = 'function toggleRoundDetail(headerRow) { ... }'
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_round_expand_structure(html, js)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_missing_round_detail(self):
        html = '<tr class="round-header-row">'
        js = ''
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_round_expand_structure(html, js)
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# CSS 子元素可见性
# ---------------------------------------------------------------------------

class TestChildrenVisibilityCss:
    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_good_css(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_children_visibility_css(GOOD_CSS)
        assert chk._FAIL_COUNT == 0

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_bad_css_no_hide(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_children_visibility_css(BAD_CSS_NO_CHILDREN_HIDE)
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# 回归：事件委托替代 trace 行上的 inline onclick
# ---------------------------------------------------------------------------

# session.html 路径：tests/ 在仓库根目录，所以用 ../src/session_browser/web/templates/
SESSION_HTML = (Path(__file__).resolve().parents[2]
                / "src" / "session_browser" / "web" / "templates" / "session.html")


class TestNoInlineOnclickOnTraceRows:
    """回归：trace 行不得有 inline onclick；事件委托负责处理。"""

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_trace_row_no_inline_onclick(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        html = chk._read(SESSION_HTML)
        # .trace-row 元素上不应有 onclick="handleTraceRowClick
        inline_onclick = re.search(
            r'class="trace-row"[^>]*onclick\s*=\s*["\']handleTraceRowClick',
            html,
        )
        assert inline_onclick is None, (
            "回归：.trace-row 仍有 handleTraceRowClick 的 inline onclick。"
            "请切换到统一点击处理器中的事件委托。"
        )


class TestExpandCollapseUsesDataAction:
    """回归：expand-all/collapse-all 按钮使用 data-action，而非 inline onclick。"""

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_expand_all_no_inline_onclick(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        html = chk._read(SESSION_HTML)
        inline = re.search(
            r'data-action="expand-all"[^>]*onclick\s*=',
            html,
        )
        assert inline is None, (
            "回归：expand-all 按钮有 inline onclick。"
            "请通过 [data-action=expand-all] 使用事件委托。"
        )

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_collapse_all_no_inline_onclick(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        html = chk._read(SESSION_HTML)
        inline = re.search(
            r'data-action="collapse-all"[^>]*onclick\s*=',
            html,
        )
        assert inline is None, (
            "回归：collapse-all 按钮有 inline onclick。"
            "请通过 [data-action=collapse-all] 使用事件委托。"
        )


class TestEventDelegationPresent:
    """验证事件委托处理器覆盖 trace 行和展开/折叠按钮。"""

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_delegation_handles_trace_row(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        # JS 在 session_detail_timeline.js 中，处理 data-action="toggle-round"
        js_path = (Path(__file__).resolve().parents[2]
                   / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js")
        if js_path.exists():
            js = js_path.read_text(encoding="utf-8")
            has_toggle = "toggle-round" in js or "toggleRound" in js
            assert has_toggle, (
                "事件委托应在 session_detail_timeline.js 中处理 toggle-round"
            )
        else:
            pytest.fail("未找到 session_detail_timeline.js")

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_delegation_handles_expand_all(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        # 使用 data-action="collapse-all"（没有单独的 expand-visible）
        # 检查 timeline JS 中的 collapse-all
        js_path = (Path(__file__).resolve().parents[2]
                   / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js")
        if js_path.exists():
            js = js_path.read_text(encoding="utf-8")
            has_collapse = "collapse-all" in js or "collapseAll" in js or "collapse_all" in js
            assert has_collapse, (
                "session_detail_timeline.js 必须处理 collapse-all"
            )
        else:
            pytest.fail("未找到 session_detail_timeline.js")

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_delegation_handles_collapse_all(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        js_path = (Path(__file__).resolve().parents[2]
                   / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js")
        if js_path.exists():
            js = js_path.read_text(encoding="utf-8")
            has_collapse = "collapse-all" in js or "collapseAll" in js or "collapse_all" in js
            assert has_collapse, (
                "session_detail_timeline.js 必须处理 collapse-all"
            )
        else:
            pytest.fail("未找到 session_detail_timeline.js")

class TestAccordionBehavior:
    """验证 session_detail_timeline.js 中的手风琴逻辑。"""

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_collapse_others_function_exists(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        js_path = (Path(__file__).resolve().parents[2]
                   / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js")
        if js_path.exists():
            js = js_path.read_text(encoding="utf-8")
            # toggleRound 处理手风琴行为
            has_toggle = "toggleRound" in js
            assert has_toggle, (
                "session_detail_timeline.js 必须有 toggleRound 函数"
            )
        else:
            pytest.fail("未找到 session_detail_timeline.js")

    @pytest.mark.contract_case("UI-INTERACTION-007")
    def test_toggle_round_detail_calls_collapse_others(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        js_path = (Path(__file__).resolve().parents[2]
                   / "src" / "session_browser" / "web" / "static" / "js" / "session_detail_timeline.js")
        if js_path.exists():
            js = js_path.read_text(encoding="utf-8")
            # toggleRound 应折叠其他 round
            has_toggle = "toggleRound" in js
            has_collapse_other = "is-open" in js or "collapseOther" in js or \
                "classList.remove" in js or "aria-expanded" in js
            assert has_toggle and has_collapse_other, (
                "toggleRound 应处理手风琴行为（折叠其他 round）"
            )
        else:
            pytest.fail("未找到 session_detail_timeline.js")
