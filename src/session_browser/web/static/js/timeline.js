/**
 * Timeline control bar: expand-all, collapse-all, type filter, jump-to.
 *
 * Works with both the round-summary-table (current) and the
 * timeline-structured / timeline-node tree (future).
 *
 * Exposes `window.TimelineCtrl` for inline onclick handlers.
 */
(function () {
    'use strict';

    var _activeFilter = 'all';

    /* ── Single node toggle ──────────────────────────────────── */

    function toggleNode(nodeOrEvent) {
        var node;
        if (nodeOrEvent && nodeOrEvent.target) {
            // Called from event delegation — find the .timeline-node ancestor
            node = nodeOrEvent.target.closest('.timeline-node');
        } else if (nodeOrEvent) {
            node = nodeOrEvent;
        }
        if (!node) return;
        if (!node.classList.contains('timeline-node')) return;

        var isExpanded = node.classList.contains('is-expanded');
        var toggle = node.querySelector('.timeline-node__toggle');

        if (isExpanded) {
            node.classList.remove('is-expanded');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        } else {
            node.classList.add('is-expanded');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        }
    }

    /* ── Round detail helpers ────────────────────────────────── */

    function expandRoundDetail(headerRow) {
        var detailRow = headerRow.nextElementSibling;
        if (!detailRow || !detailRow.classList.contains('round-detail-row')) return;
        if (detailRow.style.display === 'none' || detailRow.style.display === '') {
            detailRow.style.display = 'table-row';
            var chevron = headerRow.querySelector('.round-chevron-inline');
            if (chevron) chevron.style.transform = 'rotate(90deg)';
        }
    }

    function collapseRoundDetail(headerRow) {
        var detailRow = headerRow.nextElementSibling;
        if (!detailRow || !detailRow.classList.contains('round-detail-row')) return;
        if (detailRow.style.display !== 'none' && detailRow.style.display !== '') {
            detailRow.style.display = 'none';
            var chevron = headerRow.querySelector('.round-chevron-inline');
            if (chevron) chevron.style.transform = '';
        }
    }

    /* ── Node helpers ────────────────────────────────────────── */

    function expandNode(nodeEl) {
        if (!nodeEl || !nodeEl.classList.contains('timeline-node')) return;
        nodeEl.classList.add('is-expanded');
        var toggle = nodeEl.querySelector('.timeline-node__toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'true');
    }

    function collapseNode(nodeEl) {
        if (!nodeEl || !nodeEl.classList.contains('timeline-node')) return;
        nodeEl.classList.remove('is-expanded');
        var toggle = nodeEl.querySelector('.timeline-node__toggle');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
    }

    /* ── Expand / Collapse ───────────────────────────────── */

    function expandAll() {
        // Round summary table rows
        var headers = document.querySelectorAll('.round-header-row');
        headers.forEach(function (header) {
            expandRoundDetail(header);
        });

        // Timeline nodes with children
        var nodes = document.querySelectorAll('.timeline-node.has-children:not(.is-expanded)');
        nodes.forEach(function (node) {
            expandNode(node);
        });

        // Persist expand-all state
        var key = 'rounds_' + (window._sessionId || '');
        if (window.arpStorage && window._sessionId) {
            var allIdx = [];
            headers.forEach(function (h) { if (h.dataset.roundIdx) allIdx.push(h.dataset.roundIdx); });
            window.arpStorage.set(key, allIdx);
        }
        try { localStorage.setItem('arp_timelineExpandAll', 'expanded'); } catch (e) {}
    }

    function collapseAll() {
        // Round summary table rows
        var headers = document.querySelectorAll('.round-header-row');
        headers.forEach(function (header) {
            collapseRoundDetail(header);
        });

        // Timeline nodes
        var nodes = document.querySelectorAll('.timeline-node.is-expanded');
        nodes.forEach(function (node) {
            collapseNode(node);
        });

        // Persist collapse-all state
        if (window.arpStorage && window._sessionId) {
            window.arpStorage.set('rounds_' + window._sessionId, []);
        }
        try { localStorage.setItem('arp_timelineExpandAll', 'collapsed'); } catch (e) {}
    }

    /* ── Type filter ──────────────────────────────────────── */

    function filter(type) {
        _activeFilter = type;

        // Update active chip
        document.querySelectorAll('.timeline-toolbar__filter').forEach(function (chip) {
            chip.classList.toggle('active', chip.dataset.filter === type);
        });

        if (type === 'all') {
            _showAllNodes();
            return;
        }

        // Filter round summary table rows by type keywords in preview
        var rows = document.querySelectorAll('.round-header-row');
        rows.forEach(function (row) {
            var visible;
            if (type === 'error') {
                // Error only: check for error/fail status badges or row--failed class
                visible = row.classList.contains('row--failed') ||
                    !!row.querySelector('[class*="badge-error"], [class*="badge--status-error"]') ||
                    (row.dataset.status && row.dataset.status.toLowerCase().indexOf('fail') >= 0);
            } else if (type === 'expensive') {
                // High token only: check for token data above a threshold
                visible = _isHighTokenRow(row);
            } else {
                var preview = row.querySelector('.preview-cell__text');
                var text = preview ? preview.textContent.toLowerCase() : '';
                visible = _matchesFilter(text, type);
            }
            row.style.display = visible ? '' : 'none';
            // Hide corresponding detail row too
            var detailRow = row.nextElementSibling;
            if (detailRow && detailRow.classList.contains('round-detail-row')) {
                detailRow.style.display = visible ? '' : 'none';
            }
        });

        // Filter future timeline-structured nodes
        var nodes = document.querySelectorAll('.timeline-node');
        nodes.forEach(function (node) {
            var cls = node.className;
            if (type === 'error') {
                visible = cls.indexOf('timeline-node--error') >= 0 ||
                    cls.indexOf('row--failed') >= 0 ||
                    cls.indexOf('is-failed') >= 0;
            } else if (type === 'expensive') {
                visible = !!node.querySelector('[data-tokens]') && parseInt(node.dataset.tokens || '0') > 50000;
            } else {
                visible = _nodeMatchesType(cls, type);
            }
            node.style.display = visible ? '' : 'none';
        });
    }

    function _isHighTokenRow(row) {
        // Check for data attributes with raw token counts
        var tokens = row.dataset.tokens || row.dataset.totalTokens;
        if (tokens) {
            var n = parseInt(tokens, 10);
            if (!isNaN(n)) return n > 50000;
        }
        // Fallback: look for formatted token text like "123.4K" or "1.2M"
        var tokenCell = row.querySelector('[class*="token-cell"], td.numeric');
        if (tokenCell) {
            var text = tokenCell.textContent.trim();
            var m = text.match(/^([+-]?\d+\.?\d*)\s*([kKmM])?$/);
            if (m) {
                var val = parseFloat(m[1]);
                var suffix = (m[2] || '').toLowerCase();
                if (suffix === 'k') val *= 1000;
                else if (suffix === 'm') val *= 1000000;
                return val > 50000;
            }
        }
        return false;
    }

    function _matchesFilter(text, type) {
        if (type === 'message') return text.indexOf('user') >= 0 || text.indexOf('assistant') >= 0 || text.indexOf('msg') >= 0;
        if (type === 'tool') return text.indexOf('tool') >= 0 || text.indexOf('bash') >= 0;
        if (type === 'error') return text.indexOf('error') >= 0 || text.indexOf('fail') >= 0;
        return true;
    }

    function _nodeMatchesType(className, type) {
        if (type === 'message') return className.indexOf('timeline-node--message') >= 0;
        if (type === 'tool') return className.indexOf('timeline-node--tool-call') >= 0;
        if (type === 'error') return className.indexOf('timeline-node--error') >= 0;
        return true;
    }

    function _showAllNodes() {
        document.querySelectorAll('.round-header-row').forEach(function (row) {
            row.style.display = '';
            var detailRow = row.nextElementSibling;
            if (detailRow && detailRow.classList.contains('round-detail-row')) {
                detailRow.style.display = '';
            }
        });
        document.querySelectorAll('.timeline-node').forEach(function (node) {
            node.style.display = '';
        });
    }

    /* ── Jump to node ─────────────────────────────────────── */

    function _escapeSelector(s) {
        // CSS.escape polyfill for safe querySelector
        return s.replace(/"/g, '\\"').replace(/\\/g, '\\\\');
    }

    /**
     * Programmatic jump to a target element.
     * Ensures visibility, scrolls into view, and applies highlight.
     * @param {HTMLElement} target - The element to jump to.
     */
    function jumpToNode(target) {
        if (!target) return;
        _ensureVisible(target);
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        _flashHighlight(target);
    }

    function jumpOnKey(event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            jump();
        }
    }

    function jump() {
        var input = document.getElementById('timeline-jump-input');
        if (!input) return;
        var query = input.value.trim();
        if (!query) return;

        var target = null;

        // Try round number first: "#42" or "42" (most common, safest)
        var num = query.replace(/^#/, '');
        if (/^\d+$/.test(num)) {
            target = document.querySelector('.round-header-row[data-round-idx="' + _escapeSelector(num) + '"]');
        }

        // Try getElementById (safe, no selector injection)
        if (!target) {
            target = document.getElementById(query);
        }

        // Try data-timeline-id with escaped selector
        if (!target) {
            try {
                target = document.querySelector('[data-timeline-id="' + _escapeSelector(query) + '"]');
            } catch (e) {
                // Malformed selector, skip
            }
        }

        if (target) {
            // Expand parent if needed
            _ensureVisible(target);

            // Scroll into view
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });

            // Brief highlight
            _flashHighlight(target);
        }
    }

    function _ensureVisible(el) {
        // If inside a collapsed round detail, expand it
        var detailRow = el.closest('.round-detail-row');
        if (detailRow && detailRow.style.display === 'none') {
            var headerRow = detailRow.previousElementSibling;
            if (headerRow && headerRow.classList.contains('round-header-row')) {
                if (window.toggleRoundDetail) {
                    window.toggleRoundDetail(headerRow);
                }
            }
        }
        // Expand timeline-node parents
        var parent = el.parentElement;
        while (parent) {
            if (parent.classList && parent.classList.contains('timeline-node') &&
                !parent.classList.contains('is-expanded')) {
                toggleNode(parent);
            }
            parent = parent.parentElement;
        }
    }

    function _flashHighlight(el) {
        el.classList.add('timeline-node--jump-target');
        setTimeout(function () {
            el.classList.add('timeline-node--jump-fade');
        }, 1500);
        setTimeout(function () {
            el.classList.remove('timeline-node--jump-target', 'timeline-node--jump-fade');
        }, 3000);
    }

    /* ── Selection ──────────────────────────────────────────── */

    function selectNode(nodeEl) {
        if (!nodeEl || !nodeEl.classList.contains('timeline-node')) return;
        // Clear previous selection
        document.querySelectorAll('.timeline-node.is-selected').forEach(function (n) {
            n.classList.remove('is-selected');
        });
        nodeEl.classList.add('is-selected');
    }

    /* ── Public API ───────────────────────────────────────── */

    window.TimelineCtrl = {
        expandAll: expandAll,
        collapseAll: collapseAll,
        filter: filter,
        jump: jump,
        jumpOnKey: jumpOnKey,
        jumpToNode: jumpToNode,
        toggleNode: toggleNode,
        selectNode: selectNode,
        getActiveFilter: function () { return _activeFilter; }
    };

    /* ── Event delegation for toggle clicks ──────────────────── */

    document.addEventListener('click', function (e) {
        var header = e.target.closest('[data-timeline-toggle]');
        if (header) {
            e.preventDefault();
            e.stopPropagation();
            toggleNode(e);
            return;
        }
        var toggleBtn = e.target.closest('.timeline-node__toggle');
        if (toggleBtn) {
            e.preventDefault();
            e.stopPropagation();
            toggleNode(e);
            return;
        }
        // Select node on click (non-toggle areas)
        var node = e.target.closest('.timeline-node');
        if (node) {
            selectNode(node);
        }
    });

    /* ── Init: mark "All" filter as active + restore expand-all state ── */
    document.addEventListener('DOMContentLoaded', function () {
        var allChip = document.querySelector('.timeline-toolbar__filter[data-filter="all"]');
        if (allChip) allChip.classList.add('active');

        // Restore last expand-all state (does nothing if never set)
        try {
            var saved = localStorage.getItem('arp_timelineExpandAll');
            if (saved === 'expanded') expandAll();
            else if (saved === 'collapsed') collapseAll();
        } catch (e) {}
    });

})();
