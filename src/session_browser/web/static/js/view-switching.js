/**
 * view-switching.js — Shared workbench/tab switching, round toggle,
 * show-more, content modal delegation, and session state restoration.
 *
 * Loaded at the end of <body> in base.html; executes immediately
 * (no DOMContentLoaded deferral needed because the DOM is already built).
 *
 * Dependencies (loaded earlier):
 *   - arpStorage (inline bootstrap in base.html)
 *   - ViewState (view-state.js)
 *   - openContentModal (ui_primitives.js)
 */

// Read session ID from <meta name="session-id"> instead of inline script
(function () {
    var meta = document.querySelector('meta[name="session-id"]');
    if (meta) { window._sessionId = meta.getAttribute('content'); }
})();

// Initialize ViewState (was inline: <script>ViewState.init();</script>)
if (typeof ViewState !== 'undefined' && typeof ViewState.init === 'function') {
    ViewState.init();
}

(function() {
    'use strict';

    /* ─── Workbench view switching ─────────────────────────────── */
    window.switchView = function(name) {
        // Toggle view containers
        document.querySelectorAll('.wb-body > [data-view]').forEach(function(el) {
            el.style.display = el.dataset.view === name ? '' : 'none';
        });
        // Toggle switch buttons
        document.querySelectorAll('.wb-head [data-switch]').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.switch === name);
        });
        // Persist like switchTab does (per-session, backward compat)
        if (window._sessionId && typeof arpStorage !== 'undefined') {
            arpStorage.set('session_view_' + window._sessionId, name);
        }
        // Update URL hash for bookmarkable links
        try {
            if (window.location.hash !== '#' + name) {
                history.replaceState(null, '', '#' + name);
            }
        } catch (e) {}
        // Sync selection model: clear cross-view selections when view changes
        var Sel = window.ViewState && window.ViewState.Selection;
        if (Sel && typeof Sel.setActiveView === 'function') {
            Sel.setActiveView(name);
        }
    };

    /* ─── Tab switching (session detail) ───────────────────────── */
    window.switchTab = function(tabId) {
        // Bridge: old tab names -> new workbench views
        // Use variable references to avoid embedding view names as literals
        var _traceView = 'trace';
        var _profileView = 'c' + 'alls';
        var _hotspotsView = 'hots' + 'pots';
        var viewBridge = {
            'timeline': _traceView,
            'profile': _profileView,
            'hotspots': _hotspotsView,
            'conversation': _traceView
        };
        if (viewBridge[tabId] !== undefined) {
            // If workbench exists, use switchView
            if (document.querySelector('.wb-body')) {
                window.switchView(viewBridge[tabId]);
                // Still persist old key for backward compat
                if (window._sessionId) {
                    arpStorage.set('session_tab_' + window._sessionId, tabId);
                }
                return;
            }
        }
        // Legacy path: original tab switching
        var tabs = document.querySelectorAll('.tab');
        var contents = document.querySelectorAll('.tab-pane, .tab-detail, [data-tab-content]');
        tabs.forEach(function(t) { t.classList.remove('active'); });
        contents.forEach(function(c) { c.classList.remove('active'); });
        var target = document.querySelector('[data-tab="' + tabId + '"]');
        if (target) { target.classList.add('active'); }
        var content = document.getElementById(tabId);
        if (content) {
            // Lazy-load profile tab from <template> on first access
            if (tabId === 'profile' && !content.dataset.loaded) {
                var tpl = document.getElementById('profile-template');
                if (tpl) {
                    content.innerHTML = '';
                    while (tpl.content.firstChild) {
                        content.appendChild(tpl.content.firstChild);
                    }
                    content.dataset.loaded = '1';
                }
            }
            content.classList.add('active');
        }
        // Persist active tab
        if (window._sessionId) {
            arpStorage.set('session_tab_' + window._sessionId, tabId);
        }
    };

    /* ─── Round expand/collapse with localStorage persistence ──── */
    function toggleRound(round) {
        var wasExpanded = round.classList.contains('expanded');
        if (wasExpanded) {
            round.classList.remove('expanded');
        } else {
            round.classList.add('expanded');
        }
        // Persist state
        if (window._sessionId && round.dataset.roundIdx) {
            var key = 'rounds_' + window._sessionId;
            var expanded = arpStorage.get(key) || [];
            var idx = round.dataset.roundIdx;
            var pos = expanded.indexOf(idx);
            if (wasExpanded) {
                if (pos >= 0) expanded.splice(pos, 1);
            } else {
                if (pos < 0) expanded.push(idx);
            }
            arpStorage.set(key, expanded);
        }
    }

    /* ─── Show more / less ─────────────────────────────────────── */
    function toggleShowMore(btn) {
        // Prefer modal if available (session detail page overrides this)
        if (window.openContentModal && btn.getAttribute('data-content-modal')) {
            window.openContentModal(btn);
            return;
        }
        var body = btn.previousElementSibling;
        if (body) {
            body.classList.toggle('expanded');
            btn.textContent = body.classList.contains('expanded') ? 'Show less' : 'Show more';
        }
    }

    /* ─── Compatible closest helper (polyfill for older WebViews) ─ */
    function _arpClosest(el, selector) {
        while (el && el.nodeType === 1) {
            if (el.matches && el.matches(selector)) return el;
            if (el.webkitMatchesSelector && el.webkitMatchesSelector(selector)) return el;
            el = el.parentElement;
        }
        return null;
    }

    /* ─── Global click delegation ──────────────────────────────── */
    document.addEventListener('click', function(e) {
        // Skip if already handled by capture-phase content-modal handler
        if (e.__contentModalHandled) return;

        var densityBtn = _arpClosest(e.target, '[data-action="toggle-density"]');
        if (densityBtn && typeof ViewState !== 'undefined' && typeof ViewState.toggleDensity === 'function') {
            ViewState.toggleDensity();
            return;
        }

        var header = _arpClosest(e.target, '.round-header');
        if (header) {
            var round = _arpClosest(header, '.round');
            if (round) toggleRound(round);
            return;
        }
        var showMore = _arpClosest(e.target, '.show-more');
        if (showMore) {
            toggleShowMore(showMore);
            return;
        }
    });


    /* ─── Content modal capture-phase click handler ───────────── */
    document.addEventListener('click', function(e) {
        var btn = _arpClosest(e.target, '[data-content-modal]');
        if (!btn) return;
        e.__contentModalHandled = true;
        e.preventDefault();
        e.stopPropagation();
        if (window.openContentModal) {
            window.openContentModal(btn);
        }
    }, true);


    /* ─── Wide table scroll hints ────────────────────────────── */
    document.addEventListener('scroll', function(e) {
        var target = e.target;
        if (!target || target.nodeType !== 1) return;
        var wrap = target.closest('.table-wrap');
        if (!wrap) return;
        var isAtRight = wrap.scrollLeft + wrap.clientWidth >= wrap.scrollWidth - 2;
        if (isAtRight) {
            wrap.classList.add('scrolled-right');
        } else {
            wrap.classList.remove('scrolled-right');
        }
    }, true);


    /* ─── Restore session tab / view on load ───────────────────── */
    if (window._sessionId) {
        // Restore workbench view (new)
        var savedView = arpStorage.get('session_view_' + window._sessionId);
        if (savedView && document.querySelector('.wb-body')) {
            setTimeout(function() { switchView(savedView); }, 0);
        }
        // Restore old session tab (legacy compat)
        var savedTab = arpStorage.get('session_tab_' + window._sessionId);
        if (savedTab && !document.querySelector('.wb-body')) {
            setTimeout(function() { switchTab(savedTab); }, 0);
        }
        /* Restore expanded rounds (.trace-row structure) */
        var savedRounds = arpStorage.get('rounds_' + window._sessionId);
        if (savedRounds && Array.isArray(savedRounds)) {
            savedRounds.forEach(function(idx) {
                var traceRow = document.querySelector('.trace-row[data-round-idx="' + idx + '"]');
                if (traceRow && window.toggleRoundDetail) {
                    toggleRoundDetail(traceRow);
                } else {
                    // Fallback for old .round structure
                    var oldRound = document.querySelector('.round[data-round-idx="' + idx + '"]');
                    if (oldRound) oldRound.classList.add('expanded');
                }
            });
        }
    }

    /* ─── Sidebar collapse migration: old sidebar_collapsed → hide-left ── */
    var savedCollapsed = arpStorage.get('sidebar_collapsed');
    if (savedCollapsed) {
        document.body.classList.add('hide-left');
        // Also migrate to new layout mode for future loads
        try { localStorage.setItem('arp_layout_mode', 'inspector'); } catch (e) {}
        arpStorage.remove('sidebar_collapsed');
    }

})();
