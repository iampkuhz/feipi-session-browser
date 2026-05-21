/**
 * dashboard.js — canonical Dashboard page behavior for Feipi Session Browser.
 *
 * Responsibilities:
 *   - Chart scope switching (Day / Week / Month) via data-scope delegation
 *   - Chart range buttons (30d / 7d → 1d / 3d / 7d / 30d for Day scope)
 *   - Info button popover toggle (metric & chart card tooltips)
 *   - Chart menu toggle (export / detail / copy link)
 *   - Settings drawer open / close
 *   - Density toggle (delegates to ViewState)
 *
 * Uses data-action event delegation — no inline event handlers.
 * Does NOT duplicate logic already in ui_primitives.js or view-state.js.
 *
 * Routing:
 *   data-action="open-settings"   -> open settings drawer
 *   data-action="close-settings"  -> close settings drawer
 *   data-action="chart-menu"      -> open chart action menu popover
 *   data-action="density-toggle"  -> delegate to ViewState.toggleDensity()
 *   data-scope="day|week|month"   -> scope switch (Day/Week/Month)
 *
 * Consumes: UiPrimitives.showToast(), ViewState.toggleDensity()
 *
 * Target DOM elements (contract):
 *   - #infoPopover     — info tooltip overlay
 *   - #menuPopover     — chart action menu overlay
 *   - #settingsDrawer  — settings slide-out drawer
 *   - .scope-switch__btn[data-scope] — scope switch buttons
 *   - .range-btn[data-range] / .range-btn[data-action="chart-range"] — range tabs
 *   - .icon-button--info[data-info] — info buttons
 *   - .icon-button--ghost[data-action="chart-menu"] — chart menu buttons
 */
(function () {
    'use strict';

    /* ── Info copy dictionary ──────────────────────────────────── */

    var INFO_COPY = {
        'projects': {
            title: 'Projects',
            text: 'Counts distinct indexed local workspaces. Click reveals the metric definition and counting scope.'
        },
        'sessions': {
            title: 'Sessions',
            text: 'Counts indexed agent runs. Click shows what qualifies as a session and which data sources are included.'
        },
        'tokens': {
            title: 'Total Tokens',
            text: 'Aggregates input, cache, and output token usage. Displayed in millions on the dashboard for readability.'
        },
        'failed-tools': {
            title: 'Failed Tools',
            text: 'Counts tool executions that returned failure states. Click opens the metric explanation and links to diagnostic views in the real product.'
        },
        'chart-sessions': {
            title: 'Session Trend',
            text: 'Stacked bars show session volume per agent. Total appears only inside the hover tooltip and is not rendered as a gray bar.'
        },
        'chart-tokens': {
            title: 'Token Trend',
            text: 'Stacked bars show token usage per agent. The range switch changes the chart horizon (e.g. 7 days vs 30 days).'
        },
        'chart-prompts': {
            title: 'Prompt Activity Trend',
            text: 'This chart tracks user-initiated inputs, approximating daily conversation starts or active prompt submissions.'
        }
    };

    /* ── State ─────────────────────────────────────────────────── */

    var currentScope = 'day';
    var chartTooltip = null;
    var infoPopover = null;
    var menuPopover = null;
    var settingsDrawer = null;

    function _cacheElements() {
        infoPopover = document.getElementById('infoPopover');
        menuPopover = document.getElementById('menuPopover');
        settingsDrawer = document.getElementById('settingsDrawer');
        // Chart tooltip may use various IDs across template versions
        chartTooltip = document.getElementById('chartTooltip')
            || document.querySelector('.chart-tooltip');
    }

    /* ── Helpers ───────────────────────────────────────────────── */

    /** Hide all floating overlays (popovers). */
    function hideFloating() {
        if (infoPopover) {
            infoPopover.setAttribute('aria-hidden', 'true');
            infoPopover.classList.remove('is-visible');
            infoPopover.style.display = 'none';
        }
        if (menuPopover) {
            menuPopover.setAttribute('aria-hidden', 'true');
            menuPopover.classList.remove('is-visible');
            menuPopover.style.display = 'none';
        }
        if (chartTooltip) {
            chartTooltip.setAttribute('aria-hidden', 'true');
            chartTooltip.classList.remove('is-visible');
            chartTooltip.style.display = 'none';
        }
    }

    /** Position and show the info popover below a button. */
    function showInfoPopover(button) {
        hideFloating();
        if (!infoPopover) return;

        var infoKey = button.getAttribute('data-info') || button.getAttribute('data-dashboard-info');
        var info = INFO_COPY[infoKey] || { title: 'Info', text: 'No description available.' };

        infoPopover.innerHTML = '<h4>' + info.title + '</h4><p>' + info.text + '</p>';
        infoPopover.style.display = '';
        infoPopover.setAttribute('aria-hidden', 'false');
        infoPopover.classList.add('is-visible');

        var rect = button.getBoundingClientRect();
        infoPopover.style.left = Math.min(window.innerWidth - 320, rect.left) + 'px';
        infoPopover.style.top = (rect.bottom + 10) + 'px';
    }

    /** Position and show the chart menu popover. */
    function showChartMenu(button) {
        hideFloating();
        if (!menuPopover) return;

        var chartName = button.getAttribute('data-chart') || 'chart';
        var menuHtml = '';
        menuHtml += '<button type="button" data-action="chart-export" data-chart="' + chartName + '">Export PNG preview</button>';
        menuHtml += '<button type="button" data-action="chart-detail" data-chart="' + chartName + '">Open detail analytics</button>';
        menuHtml += '<button type="button" data-action="chart-copy-link" data-chart="' + chartName + '">Copy chart link</button>';
        menuPopover.innerHTML = menuHtml;
        menuPopover.style.display = '';
        menuPopover.setAttribute('aria-hidden', 'false');
        menuPopover.classList.add('is-visible');

        var rect = button.getBoundingClientRect();
        menuPopover.style.left = Math.min(window.innerWidth - 240, rect.left - 180) + 'px';
        menuPopover.style.top = (rect.bottom + 8) + 'px';
    }

    /* ── Settings drawer ───────────────────────────────────────── */

    function openSettings() {
        if (!settingsDrawer) return;
        settingsDrawer.style.display = '';
        settingsDrawer.setAttribute('aria-hidden', 'false');
        if (typeof settingsDrawer.classList !== 'undefined') {
            settingsDrawer.classList.add('is-open');
        }
    }

    function closeSettings() {
        if (!settingsDrawer) return;
        settingsDrawer.setAttribute('aria-hidden', 'true');
        settingsDrawer.classList.remove('is-open');
        // Use setTimeout to allow transition to complete
        setTimeout(function () {
            if (!settingsDrawer.classList.contains('is-open')) {
                settingsDrawer.style.display = 'none';
            }
        }, 300);
    }

    /* ── Scope switching (Day / Week / Month) ──────────────────── */

    function handleScopeSwitch(scopeBtn) {
        var scope = scopeBtn.getAttribute('data-scope');
        if (!scope) return;

        // Update active state
        var allBtns = document.querySelectorAll('.scope-switch__btn');
        for (var i = 0; i < allBtns.length; i++) {
            allBtns[i].classList.remove('is-active');
        }
        scopeBtn.classList.add('is-active');

        currentScope = scope;

        // Update range buttons for the new scope
        updateRangeButtonsForScope(scope);

        // Dispatch custom event for chart re-render (consumed by template inline script)
        document.dispatchEvent(new CustomEvent('dashboard-scope-change', {
            detail: { scope: scope }
        }));

        // Show toast via UiPrimitives if available
        var toastFn = (window.UiPrimitives && window.UiPrimitives.showToast)
            ? window.UiPrimitives.showToast
            : null;
        if (toastFn) {
            toastFn('Switched to ' + scope.toUpperCase() + ' view');
        }
    }

    /**
     * Update range button labels based on scope.
     * Day scope → 1d/3d/7d/30d, Week/Month scope → visual-only labels.
     */
    function updateRangeButtonsForScope(scope) {
        var rangeContainers = document.querySelectorAll('.range-tabs');
        for (var c = 0; c < rangeContainers.length; c++) {
            var btns = rangeContainers[c].querySelectorAll('.range-btn');
            for (var i = 0; i < btns.length; i++) {
                var val = btns[i].getAttribute('data-range') || btns[i].textContent.trim().toLowerCase();
                if (scope === 'day') {
                    // Map existing labels to Day-scope labels
                    if (val === '30d' || btns[i].textContent.trim() === '30d') {
                        btns[i].textContent = '30d';
                        btns[i].setAttribute('data-range', '30d');
                    } else if (val === '7d' || btns[i].textContent.trim() === '7d') {
                        btns[i].textContent = '7d';
                        btns[i].setAttribute('data-range', '7d');
                    }
                } else if (scope === 'week') {
                    if (val === '30d' || btns[i].textContent.trim() === '30d') {
                        btns[i].textContent = '12w';
                        btns[i].setAttribute('data-range', '12w');
                    } else if (val === '7d' || btns[i].textContent.trim() === '7d') {
                        btns[i].textContent = '4w';
                        btns[i].setAttribute('data-range', '4w');
                    }
                } else if (scope === 'month') {
                    if (val === '30d' || btns[i].textContent.trim() === '30d') {
                        btns[i].textContent = '12m';
                        btns[i].setAttribute('data-range', '12m');
                    } else if (val === '7d' || btns[i].textContent.trim() === '7d') {
                        btns[i].textContent = '3m';
                        btns[i].setAttribute('data-range', '3m');
                    }
                }
            }
        }
    }

    /* ── Range button click ────────────────────────────────────── */

    function handleRangeClick(rangeBtn) {
        var range = rangeBtn.getAttribute('data-range')
            || rangeBtn.getAttribute('data-dashboard-range')
            || '30d';

        // Parse days from range value
        var days = 30;
        var numMatch = range.match(/^(\d+)/);
        if (numMatch) {
            var num = parseInt(numMatch[1], 10);
            var unit = range.replace(/^(\d+)/, '').toLowerCase();
            if (unit === 'w') {
                days = num * 7;
            } else if (unit === 'm') {
                days = num * 30;
            } else {
                days = num;
            }
        }

        // Update visual active state within the same chart card
        var chartCard = rangeBtn.closest('.chart-card');
        if (chartCard) {
            var siblings = chartCard.querySelectorAll('.range-btn');
            for (var i = 0; i < siblings.length; i++) {
                siblings[i].classList.remove('active');
            }
        }
        rangeBtn.classList.add('active');

        // Update data attribute for compatibility with existing code
        var chartContainer = rangeBtn.closest('[data-dashboard-chart]')
            || (chartCard ? chartCard.querySelector('[data-dashboard-chart]') : null);
        if (chartContainer) {
            chartContainer.setAttribute('data-range', range);
        }

        // Dispatch custom event for chart re-render
        document.dispatchEvent(new CustomEvent('dashboard-range-change', {
            detail: { days: days, range: range, button: rangeBtn }
        }));
    }

    /* ── Click outside popover closes it ───────────────────────── */

    function handleClickOutsidePopover(event) {
        var target = event.target;
        // Don't close if clicking inside a popover
        if (infoPopover && infoPopover.contains(target)) return;
        if (menuPopover && menuPopover.contains(target)) return;
        // Don't close if clicking the trigger button itself
        if (target.closest && target.closest('.icon-button--info')) return;
        if (target.closest && target.closest('[data-action="chart-menu"]')) return;
        hideFloating();
    }

    /* ── Main document-level click delegation ──────────────────── */

    document.addEventListener('click', function (event) {
        var target = event.target;
        var button = target.closest ? target.closest('button') : null;
        // Fallback for older browsers
        if (!button) {
            var el = target;
            while (el && el.nodeType === 1) {
                if (el.tagName === 'BUTTON') { button = el; break; }
                el = el.parentElement;
            }
        }
        if (!button) {
            handleClickOutsidePopover(event);
            return;
        }

        var action = button.getAttribute('data-action') || '';
        var hasScope = button.hasAttribute('data-scope');
        var hasInfo = button.hasAttribute('data-info') || button.hasAttribute('data-dashboard-info');

        // Scope switch buttons (data-scope, may not have data-action)
        if (hasScope) {
            handleScopeSwitch(button);
            return;
        }

        // Info buttons (data-info or data-dashboard-info, may not have data-action)
        if (hasInfo) {
            showInfoPopover(button);
            return;
        }

        // Route by data-action
        switch (action) {
            case 'chart-menu':
                showChartMenu(button);
                break;

            case 'open-settings':
                openSettings();
                break;

            case 'close-settings':
                closeSettings();
                break;

            case 'density-toggle':
                // Delegate to view-state.js
                if (window.ViewState && typeof window.ViewState.toggleDensity === 'function') {
                    window.ViewState.toggleDensity();
                }
                break;

            case 'chart-export':
            case 'chart-detail':
            case 'chart-copy-link':
                // Menu item actions — show toast
                var chartType = button.getAttribute('data-chart') || 'chart';
                var labels = {
                    'chart-export': 'Export PNG preview',
                    'chart-detail': 'Open detail analytics',
                    'chart-copy-link': 'Copy chart link'
                };
                var label = labels[action] || action;
                if (window.UiPrimitives && window.UiPrimitives.showToast) {
                    window.UiPrimitives.showToast(chartType + ': ' + label);
                }
                hideFloating();
                break;

            default:
                // Check for nav items with nav-* actions
                if (action.indexOf('nav-') === 0 && button.classList.contains('nav-item')) {
                    // Visual active state for preview
                    var allNav = document.querySelectorAll('.nav-item');
                    for (var i = 0; i < allNav.length; i++) {
                        allNav[i].classList.remove('is-active');
                    }
                    if (!button.classList.contains('nav-item--footer')) {
                        button.classList.add('is-active');
                    }
                    hideFloating();
                }
                // Let ui_primitives.js handle the default case via ui-action event
                break;
        }
    });

    /* ── Scope switch initialization ───────────────────────────── */

    // Bind scope buttons via delegation — scan for data-scope on load
    // This ensures buttons without inline handlers are captured
    var scopeBtns = document.querySelectorAll('.scope-switch__btn[data-scope]');
    // No individual binding needed — handled by document-level click above.
    // Mark them as initialized for debugging.
    for (var i = 0; i < scopeBtns.length; i++) {
        scopeBtns[i].setAttribute('data-initialized', 'true');
    }

    /* ── Range button delegation ───────────────────────────────── */

    // Range buttons may have onclick in legacy templates;
    // we intercept via document-level click and prevent default inline behavior
    // when the button has data-range or data-dashboard-range attribute.

    /* ── Settings drawer backdrop click ────────────────────────── */

    document.addEventListener('click', function (event) {
        if (settingsDrawer && event.target === settingsDrawer) {
            closeSettings();
        }
    });

    /* ── Window events ─────────────────────────────────────────── */

    window.addEventListener('resize', hideFloating);
    window.addEventListener('scroll', hideFloating, true);

    /* ── Keyboard: Escape closes popovers and drawer ───────────── */

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' || event.key === 'Esc') {
            var closed = false;
            if (menuPopover && menuPopover.classList.contains('is-visible')) {
                hideFloating();
                closed = true;
            }
            if (infoPopover && infoPopover.classList.contains('is-visible')) {
                hideFloating();
                closed = true;
            }
            if (settingsDrawer && settingsDrawer.classList.contains('is-open')) {
                closeSettings();
                closed = true;
            }
            if (closed) {
                event.preventDefault();
            }
        }
    });

    /* ── Public API ────────────────────────────────────────────── */

    window.DashboardPage = {
        getScope: function () { return currentScope; },
        setScope: function (scope) {
            var btn = document.querySelector('.scope-switch__btn[data-scope="' + scope + '"]');
            if (btn) handleScopeSwitch(btn);
        },
        openSettings: openSettings,
        closeSettings: closeSettings,
        showInfoPopover: showInfoPopover,
        showChartMenu: showChartMenu,
        hideFloating: hideFloating
    };

    /* ── Init ──────────────────────────────────────────────────── */

    _cacheElements();
})();
