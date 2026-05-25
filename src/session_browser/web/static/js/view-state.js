/**
 * view-state.js — Density toggle & Saved Views
 *
 * 职责：
 * 1. density 切换（compact / comfortable），通过 body class + localStorage 持久化
 * 2. 简单 saved views（存储当前 URL 参数集合）
 *
 * 用法：
 *   // 初始化：恢复上一次 density 状态
 *   ViewState.init();
 *
 *   // 切换 density
 *   ViewState.toggleDensity();
 *
 *   // 读取当前 density
 *   ViewState.getDensity(); // 'compact' | 'comfortable'
 *
 *   // Saved Views
 *   ViewState.saveView('my-view');
 *   ViewState.loadView('my-view');
 *   ViewState.deleteView('my-view');
 *   ViewState.listViews(); // [{ name, url, savedAt }]
 */
(function () {
    'use strict';

    var STORAGE_PREFIX = 'arp_';
    var DENSITY_KEY = STORAGE_PREFIX + 'density';
    var VIEWS_KEY_PREFIX = STORAGE_PREFIX + 'view_';
    var VIEWS_LIST_KEY = STORAGE_PREFIX + 'views_list';

    var DEFAULT_DENSITY = 'compact';
    var DENSITY_CLASSES = {
        compact: '',
        comfortable: 'density-comfortable'
    };

    /* ── Density ─────────────────────────────────────────────── */

    function getDensity() {
        try {
            var saved = localStorage.getItem(DENSITY_KEY);
            return saved === 'comfortable' ? 'comfortable' : DEFAULT_DENSITY;
        } catch (e) {
            return DEFAULT_DENSITY;
        }
    }

    function setDensity(mode) {
        try {
            localStorage.setItem(DENSITY_KEY, mode);
        } catch (e) { /* storage full */ }
        applyDensity(mode);
    }

    function applyDensity(mode) {
        var cls = DENSITY_CLASSES[mode] || '';
        if (cls) {
            document.body.classList.add(cls);
        } else {
            document.body.classList.remove('density-comfortable');
        }
    }

    function toggleDensity() {
        var current = getDensity();
        var next = current === 'compact' ? 'comfortable' : 'compact';
        setDensity(next);
        updateToggleUI(next);
    }

    function updateToggleUI(mode) {
        var btn = document.getElementById('density-toggle');
        if (!btn) return;
        var isComfortable = mode === 'comfortable';
        btn.classList.toggle('density-toggle--active', isComfortable);
        btn.setAttribute('aria-pressed', String(isComfortable));
        btn.title = isComfortable ? '当前：宽松 · 点击切换为紧凑' : '当前：紧凑 · 点击切换为宽松';
    }

    /* ── Layout Mode (Map / Inspector / Focus) ───────────────── */

    var LAYOUT_KEY = STORAGE_PREFIX + 'layout_mode';
    var VALID_LAYOUTS = ['map', 'inspector', 'focus'];
    var DEFAULT_LAYOUT = 'map';

    function getLayoutMode() {
        try {
            var saved = localStorage.getItem(LAYOUT_KEY);
            return VALID_LAYOUTS.indexOf(saved) >= 0 ? saved : DEFAULT_LAYOUT;
        } catch (e) {
            return DEFAULT_LAYOUT;
        }
    }

    function setLayoutMode(mode) {
        if (VALID_LAYOUTS.indexOf(mode) < 0) mode = DEFAULT_LAYOUT;
        try {
            localStorage.setItem(LAYOUT_KEY, mode);
        } catch (e) { /* storage full */ }
        applyLayoutMode(mode);
        updateLayoutBtns(mode);
    }

    function applyLayoutMode(mode) {
        var body = document.body;
        body.classList.remove('hide-left', 'hide-right', 'focus');
        if (mode === 'inspector') {
            body.classList.add('hide-left');
        } else if (mode === 'focus') {
            body.classList.add('focus');
        }
        // 'map' = default, no class needed
    }

    function updateLayoutBtns(mode) {
        document.querySelectorAll('[data-layout-mode]').forEach(function(btn) {
            btn.classList.toggle('top-btn--active', btn.dataset.layoutMode === mode);
        });
    }

    /* ── Workbench View (Trace / Calls / Hotspots) ──────────────── */

    var WORKBENCH_KEY = STORAGE_PREFIX + 'workbench_view';
    var VALID_VIEWS = ['trace', 'calls', 'hotspots'];
    var DEFAULT_VIEW = 'trace';

    /** Get the preferred workbench view. */
    function getWorkbenchView() {
        try {
            var saved = localStorage.getItem(WORKBENCH_KEY);
            return VALID_VIEWS.indexOf(saved) >= 0 ? saved : DEFAULT_VIEW;
        } catch (e) {
            return DEFAULT_VIEW;
        }
    }

    /** Set and apply the workbench view, persisting to localStorage. */
    function setWorkbenchView(name) {
        if (VALID_VIEWS.indexOf(name) < 0) name = DEFAULT_VIEW;
        try {
            localStorage.setItem(WORKBENCH_KEY, name);
        } catch (e) { /* storage full */ }
        _applyWorkbenchView(name);
        _updateViewSwitchBtns(name);
    }

    /** Apply view visibility in the DOM. Uses window.switchView if available. */
    function _applyWorkbenchView(name) {
        if (typeof window.switchView === 'function') {
            window.switchView(name);
            return;
        }
        // Direct DOM fallback
        var wbBody = document.querySelector('.wb-body');
        if (!wbBody) return;
        wbBody.querySelectorAll('[data-view]').forEach(function(el) {
            el.hidden = el.dataset.view !== name;
        });
    }

    /** Update active state on view switch buttons. */
    function _updateViewSwitchBtns(name) {
        document.querySelectorAll('.wb-head [data-switch]').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.switch === name);
        });
    }

    /**
     * Initialize workbench view: restore from URL hash > localStorage > default.
     * Defers until the workbench body exists in the DOM.
     */
    function initWorkbenchView() {
        function restore() {
            if (!document.querySelector('.wb-body')) return;

            // 1. URL hash takes highest precedence
            var hash = window.location.hash.replace('#', '').toLowerCase();
            if (VALID_VIEWS.indexOf(hash) >= 0) {
                try { localStorage.setItem(WORKBENCH_KEY, hash); } catch (e) {}
                setWorkbenchView(hash);
                return;
            }

            // 2. Fall back to saved preference
            var saved = getWorkbenchView();
            if (saved !== DEFAULT_VIEW) {
                setWorkbenchView(saved);
            }
        }

        // DOM may not be ready — defer
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                setTimeout(restore, 0);
            });
        } else {
            setTimeout(restore, 0);
        }
    }

    /* ── Saved Views ────────────────────────────────────────── */

    function saveView(name) {
        if (!name) return false;
        var view = {
            name: name,
            url: window.location.search || window.location.pathname,
            savedAt: new Date().toISOString()
        };
        try {
            localStorage.setItem(VIEWS_LIST_KEY + ':' + name, JSON.stringify(view));
            var list = listViews();
            if (!list.some(function (v) { return v.name === name; })) {
                list.push({ name: name, savedAt: view.savedAt });
                localStorage.setItem(VIEWS_LIST_KEY, JSON.stringify(list));
            }
            return true;
        } catch (e) {
            return false;
        }
    }

    function loadView(name) {
        try {
            var raw = localStorage.getItem(VIEWS_LIST_KEY + ':' + name);
            if (!raw) return null;
            return JSON.parse(raw);
        } catch (e) {
            return null;
        }
    }

    function deleteView(name) {
        try {
            localStorage.removeItem(VIEWS_LIST_KEY + ':' + name);
            var list = listViews().filter(function (v) { return v.name !== name; });
            localStorage.setItem(VIEWS_LIST_KEY, JSON.stringify(list));
            return true;
        } catch (e) {
            return false;
        }
    }

    function listViews() {
        try {
            var raw = localStorage.getItem(VIEWS_LIST_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (e) {
            return [];
        }
    }

    /* ── Unified Selection Model ───────────────────────────────── */

    /**
     * Selection tracks a single active object across all workbench views.
     *
     * State shape:
     *   {
     *     activeView: 'trace' | 'calls' | 'hotspots',
     *     selectedRoundId: string|null,
     *     selectedSpanId: string|null,
     *     selectedCallId: string|null,
     *     selectedHotspotId: string|null,
     *   }
     *
     * Only one of selectedRoundId/selectedSpanId/selectedCallId/selectedHotspotId
     * is non-null at any time — they represent the currently selected object.
     */
    var _selection = {
        activeView: 'trace',
        selectedRoundId: null,
        selectedSpanId: null,
        selectedCallId: null,
        selectedHotspotId: null,
    };

    function _applySelectionCSS() {
        // Remove .selected from all selectable elements
        document.querySelectorAll('.trace-row.selected, .span.selected, .table-row.selected, .hot-card.selected').forEach(function(el) {
            el.classList.remove('selected');
        });
        // Re-apply based on current state
        if (_selection.selectedRoundId) {
            var row = document.querySelector('.trace-row[data-round-idx="' + _selection.selectedRoundId + '"]');
            if (row) row.classList.add('selected');
        }
        if (_selection.selectedSpanId) {
            var span = document.querySelector('.span[data-span-id="' + _selection.selectedSpanId + '"]');
            if (span) span.classList.add('selected');
        }
        if (_selection.selectedCallId) {
            var tRow = document.querySelector('.table-row[data-call-idx="' + _selection.selectedCallId + '"]');
            if (tRow) tRow.classList.add('selected');
        }
        if (_selection.selectedHotspotId) {
            var hs = document.querySelector('.hot-card[data-hotspot-id="' + _selection.selectedHotspotId + '"]');
            if (hs) hs.classList.add('selected');
        }
    }

    function _renderInspector() {
        if (!window.openInspector) return;

        if (_selection.selectedSpanId) {
            if (typeof window.openToolInspector === 'function') {
                var span = document.querySelector('.span[data-span-id="' + _selection.selectedSpanId + '"]');
                if (span) window.openToolInspector(span);
            }
            return;
        }

        if (_selection.selectedCallId) {
            if (typeof window.openLLMInspector === 'function') {
                var row = document.querySelector('.table-row[data-call-idx="' + _selection.selectedCallId + '"]');
                if (row) window.openLLMInspector(row);
            }
            return;
        }

        if (_selection.selectedRoundId) {
            if (typeof window.openRoundInspector === 'function') {
                var row = document.querySelector('.trace-row[data-round-idx="' + _selection.selectedRoundId + '"]');
                if (row) window.openRoundInspector(row);
            }
            return;
        }

        // Hotspot: no dedicated inspector; open generic inspector
        if (_selection.selectedHotspotId) {
            var card = document.querySelector('.hot-card[data-hotspot-id="' + _selection.selectedHotspotId + '"]');
            if (card) {
                var type = card.getAttribute('data-hotspot-type') || '';
                var label = card.getAttribute('data-hotspot-label') || card.textContent.trim().substring(0, 60);
                window.openInspector({
                    title: 'Hotspot: ' + type,
                    subtitle: label,
                    objectType: 'hotspot',
                    objectId: _selection.selectedHotspotId,
                    overview: { metadata: { 'Type': type, 'Label': label }, warnings: [] },
                    payload: { missingReason: 'Hotspot detail not yet available.' }
                });
            }
            return;
        }
    }

    function _fireChange() {
        _applySelectionCSS();
        _renderInspector();
        // Broadcast for other consumers
        if (typeof window.dispatchEvent === 'function') {
            try {
                window.dispatchEvent(new CustomEvent('selection:change', { detail: getSelection() }));
            } catch (e) {}
        }
    }

    /** Get a snapshot of the current selection state. */
    function getSelection() {
        return {
            activeView: _selection.activeView,
            selectedRoundId: _selection.selectedRoundId,
            selectedSpanId: _selection.selectedSpanId,
            selectedCallId: _selection.selectedCallId,
            selectedHotspotId: _selection.selectedHotspotId,
        };
    }

    /** Clear all selection state. */
    function clearSelection() {
        _selection.selectedRoundId = null;
        _selection.selectedSpanId = null;
        _selection.selectedCallId = null;
        _selection.selectedHotspotId = null;
        _fireChange();
    }

    /** Select a round in the Trace view. Expands if collapsed. */
    function selectRound(roundId, expand) {
        _selection.selectedRoundId = String(roundId);
        _selection.selectedSpanId = null;
        _selection.selectedCallId = null;
        _selection.selectedHotspotId = null;
        // Optionally expand the round detail
        if (expand !== false) {
            var row = document.querySelector('.trace-row[data-round-idx="' + roundId + '"]');
            if (row && typeof window.toggleRoundDetail === 'function') {
                var detail = row.nextElementSibling;
                if (detail && detail.classList.contains('trace-detail') && detail.hidden) {
                    window.toggleRoundDetail(row);
                }
            }
        }
        _fireChange();
    }

    /** Select a span/tool-call node inside a trace-detail. */
    function selectSpan(spanId) {
        _selection.selectedSpanId = String(spanId);
        _selection.selectedRoundId = null;
        _selection.selectedCallId = null;
        _selection.selectedHotspotId = null;
        _fireChange();
    }

    /** Select a call in the Calls view. */
    function selectCall(callId) {
        _selection.selectedCallId = String(callId);
        _selection.selectedRoundId = null;
        _selection.selectedSpanId = null;
        _selection.selectedHotspotId = null;
        _fireChange();
    }

    /** Select a hotspot card. */
    function selectHotspot(hotspotId) {
        _selection.selectedHotspotId = String(hotspotId);
        _selection.selectedRoundId = null;
        _selection.selectedSpanId = null;
        _selection.selectedCallId = null;
        _fireChange();
    }

    /** Set the active workbench view and clear cross-view selection. */
    function setActiveView(viewName) {
        _selection.activeView = viewName;
        // Clear selections that belong to other views
        if (viewName === 'trace') {
            _selection.selectedCallId = null;
            _selection.selectedHotspotId = null;
        } else if (viewName === 'calls') {
            _selection.selectedRoundId = null;
            _selection.selectedSpanId = null;
            _selection.selectedHotspotId = null;
        } else if (viewName === 'hotspots') {
            _selection.selectedRoundId = null;
            _selection.selectedSpanId = null;
            _selection.selectedCallId = null;
        }
        _fireChange();
    }

    /* ── Public API ─────────────────────────────────────────── */

    window.ViewState = {
        getDensity: getDensity,
        setDensity: setDensity,
        toggleDensity: toggleDensity,
        getLayoutMode: getLayoutMode,
        setLayoutMode: setLayoutMode,
        applyLayoutMode: applyLayoutMode,
        updateLayoutBtns: updateLayoutBtns,
        getWorkbenchView: getWorkbenchView,
        setWorkbenchView: setWorkbenchView,
        initWorkbenchView: initWorkbenchView,
        saveView: saveView,
        loadView: loadView,
        deleteView: deleteView,
        listViews: listViews,
        init: function () {
            var mode = getDensity();
            applyDensity(mode);
            updateToggleUI(mode);
            var layoutMode = getLayoutMode();
            applyLayoutMode(layoutMode);
            updateLayoutBtns(layoutMode);
            initWorkbenchView();
        },
        // Selection API
        Selection: {
            get: getSelection,
            clear: clearSelection,
            selectRound: selectRound,
            selectSpan: selectSpan,
            selectCall: selectCall,
            selectHotspot: selectHotspot,
            setActiveView: setActiveView,
        }
    };
})();
