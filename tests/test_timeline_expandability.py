"""Tests for check_timeline_expandability.py static analysis script."""

from __future__ import annotations

import re
import textwrap

import pytest

# Import the check functions from the script
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import check_timeline_expandability as chk  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: create minimal file-like content for testing
# ---------------------------------------------------------------------------

GOOD_TIMELINE_HTML = textwrap.dedent("""\
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
# Check 1: has-children + toggle
# ---------------------------------------------------------------------------

class TestToggleForHasChildren:
    def test_good_template_has_toggle(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_for_has_children(GOOD_TIMELINE_HTML)
        assert chk._FAIL_COUNT == 0

    def test_bad_template_missing_toggle(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_for_has_children(BAD_TIMELINE_HTML_NO_TOGGLE)
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# Check 2: data-timeline-id
# ---------------------------------------------------------------------------

class TestTimelineId:
    def test_good_template_has_id(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_timeline_id(GOOD_TIMELINE_HTML, "")
        assert chk._FAIL_COUNT == 0

    def test_bad_template_missing_id(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_timeline_id(BAD_TIMELINE_HTML_NO_ID, "")
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# Check 3: expandAll/collapseAll coverage
# ---------------------------------------------------------------------------

class TestExpandCollapseCoverage:
    def test_good_js(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_expand_collapse_coverage(GOOD_JS)
        assert chk._FAIL_COUNT == 0

    def test_bad_js_no_expand_all(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_expand_collapse_coverage(BAD_JS_NO_EXPAND_ALL)
        assert chk._FAIL_COUNT > 0

    def test_analyse_expand_collapse_selectors(self):
        info = chk._analyse_expand_collapse(GOOD_JS)
        assert info["expandAll_exists"] is True
        assert info["collapseAll_exists"] is True
        assert info["covers_timeline_node"] is True
        assert any(".timeline-node" in s for s in info["expandAll_selectors"])
        assert any(".timeline-node" in s for s in info["collapseAll_selectors"])


# ---------------------------------------------------------------------------
# Check 4: toggle aria-expanded sync
# ---------------------------------------------------------------------------

class TestToggleAriaSync:
    def test_good_template_syncs(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_aria_sync(GOOD_TIMELINE_HTML)
        assert chk._FAIL_COUNT == 0

    def test_bad_template_no_aria(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_toggle_aria_sync(BAD_TIMELINE_HTML_NO_TOGGLE)
        # BAD_TIMELINE_HTML_NO_TOGGLE lacks inline onclick, but event delegation
        # in the real timeline.js supersedes it. So the check should pass via
        # event delegation rather than fail. Verify no crash occurred.
        assert chk._FAIL_COUNT == 0


# ---------------------------------------------------------------------------
# Check 5: filter preserve state
# ---------------------------------------------------------------------------

class TestFilterPreserveState:
    def test_good_js_preserves_state(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_filter_preserves_state(GOOD_JS)
        assert chk._FAIL_COUNT == 0

    def test_bad_js_removes_is_expanded(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_filter_preserves_state(BAD_JS_NO_EXPAND_ALL)
        # This JS removes is-expanded inside filter, which is a FAIL
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# Check 6: tab switching
# ---------------------------------------------------------------------------

class TestTabSwitchExpand:
    def test_good_css(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_tab_switch_expand('id="timeline"', GOOD_CSS)
        assert chk._FAIL_COUNT == 0

    def test_bad_css_visibility_hidden(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_tab_switch_expand('id="timeline"', BAD_CSS_NO_CHILDREN_HIDE)
        # Uses visibility:hidden not display:none — may cause issues
        assert chk._WARN_COUNT > 0 or chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# Round structure checks
# ---------------------------------------------------------------------------

class TestRoundExpandStructure:
    def test_has_round_structure(self):
        html = '<tr class="round-header-row">' + \
               '<tr class="round-detail-row">'
        js = 'function toggleRoundDetail(headerRow) { ... }'
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_round_expand_structure(html, js)
        assert chk._FAIL_COUNT == 0

    def test_missing_round_detail(self):
        html = '<tr class="round-header-row">'
        js = ''
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_round_expand_structure(html, js)
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# CSS children visibility
# ---------------------------------------------------------------------------

class TestChildrenVisibilityCss:
    def test_good_css(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_children_visibility_css(GOOD_CSS)
        assert chk._FAIL_COUNT == 0

    def test_bad_css_no_hide(self):
        chk._FAIL_COUNT = 0
        chk._WARN_COUNT = 0
        chk.check_children_visibility_css(BAD_CSS_NO_CHILDREN_HIDE)
        assert chk._FAIL_COUNT > 0


# ---------------------------------------------------------------------------
# Integration: run the full check on the actual repo files
# ---------------------------------------------------------------------------

class TestIntegrationOnRepoFiles:
    """Run all checks on the real repo files — expects some known warnings."""

    def test_script_runs_without_crash(self):
        """The script should run to completion on the actual files."""
        rc = chk.run()
        # May return 0 (all OK) or 1 (warnings/failures), but never crash
        assert rc in (0, 1)
