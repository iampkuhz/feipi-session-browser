/**
 * dashboard.js — canonical Dashboard page behavior for Feipi Session Browser.
 *
 * Responsibilities:
 *   - Chart scope switching (Day / Week / Month) via data-scope delegation
 *   - Chart range buttons (30d / 7d → 1d / 3d / 7d / 30d for Day scope)
 *   - Info button popover toggle (metric & chart card tooltips)
 *   - Settings drawer open / close
 *   - Density toggle (delegates to ViewState)
 *
 * Uses data-action event delegation — no inline event handlers.
 * Does NOT duplicate logic already in ui_primitives.js or view-state.js.
 *
 * Routing:
 *   data-action="open-settings"   -> open settings drawer
 *   data-action="close-settings"  -> close settings drawer
 *   data-action="density-toggle"  -> delegate to ViewState.toggleDensity()
 *   data-scope="day|week|month"   -> scope switch (Day/Week/Month)
 *
 * Consumes: UiPrimitives.showToast(), ViewState.toggleDensity()
 *
 * Target DOM elements (contract):
 *   - #infoPopover     — info tooltip overlay
 *   - #settingsDrawer  — settings slide-out drawer
 *   - .scope-switch__btn[data-scope] — scope switch buttons
 *   - .range-btn[data-range] / .range-btn[data-action="chart-range"] — range tabs
 *   - .icon-button--info[data-info] — info buttons
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
                // Legacy menu item actions — show toast and close
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
        hideFloating: hideFloating
    };


    /* ── Init ──────────────────────────────────────────────────── */

    _cacheElements();
})();


/**
 * dashboard-charts.js — Chart rendering extracted from dashboard.html inline script.
 * Reads data from JSON data blocks injected by Jinja2 template.
 * Wrapped in DOMContentLoaded because the script loads in <head> before chart elements exist.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var container = document.getElementById('trend-chart');
        if (!container) return;

        var rawDataEl = document.getElementById('dashboard-chart-data');
        var promptDataEl = document.getElementById('dashboard-prompt-data');
        var rawData = rawDataEl ? JSON.parse(rawDataEl.textContent || '[]') : [];
        var promptRawData = promptDataEl ? JSON.parse(promptDataEl.textContent || '[]') : [];
        var currentDays = 30;

    function weekKey(dateStr) {
        var d = new Date(dateStr);
        var dayOfYear = Math.floor((d - new Date(d.getFullYear(), 0, 1)) / 86400000);
        var weekNum = Math.floor(dayOfYear / 7) + 1;
        return d.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
    }

    function monthKey(dateStr) {
        return dateStr.substring(0, 7);
    }

    function aggregateByWeek(data, fields) {
        var map = {};
        var order = [];
        data.forEach(function(d) {
            var key = weekKey(d.date);
            if (!map[key]) { map[key] = { date: key }; order.push(key); }
            var row = map[key];
            fields.forEach(function(f) { row[f] = (row[f] || 0) + (d[f] || 0); });
        });
        return order.map(function(k) { return map[k]; });
    }

    function aggregateByMonth(data, fields) {
        var map = {};
        var order = [];
        data.forEach(function(d) {
            var key = monthKey(d.date);
            if (!map[key]) { map[key] = { date: key + '-01' }; order.push(key); }
            var row = map[key];
            fields.forEach(function(f) { row[f] = (row[f] || 0) + (d[f] || 0); });
        });
        return order.map(function(k) { return map[k]; });
    }

    function applyScope(data, days, fields) {
        var scope = (window.DashboardPage && window.DashboardPage.getScope) ? window.DashboardPage.getScope() : 'day';
        var sliced = data.slice(-days);
        if (!sliced.length) return [];
        var fieldList = fields || getTrendFields();
        if (scope === 'week') return aggregateByWeek(sliced, fieldList);
        if (scope === 'month') return aggregateByMonth(sliced, fieldList);
        return sliced;
    }

    function getTrendFields() {
        return ['claude_count', 'codex_count', 'qoder_count', 'total_count',
                'input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens',
                'tool_calls', 'failed_tools', 'total_tokens', 'claude_tokens', 'codex_tokens', 'qoder_tokens'];
    }

    function getPromptFields() {
        return ['claude_prompts', 'codex_prompts', 'qoder_prompts', 'total_prompts'];
    }

    function formatDisplayDate(dateStr, days) {
        var scope = (window.DashboardPage && window.DashboardPage.getScope) ? window.DashboardPage.getScope() : 'day';
        if (!dateStr) return '';
        if (scope === 'week') { var parts = dateStr.split('-W'); return parts.length > 1 ? 'W' + parts[1] : dateStr.substring(5); }
        if (scope === 'month') return dateStr.substring(5, 7);
        return dateStr.substring(5);
    }

    function formatTokens(n) {
        if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return String(n);
    }

    function buildSessionTooltip(label, d) {
        return '<div class="dashboard-tooltip">' +
            '<div class="tooltip-date">' + label + '</div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--claude"></i><span class="tooltip-label">Claude Code</span><b class="tooltip-value">' + d.claude_count + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--codex"></i><span class="tooltip-label">Codex</span><b class="tooltip-value">' + d.codex_count + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--qoder"></i><span class="tooltip-label">Qoder</span><b class="tooltip-value">' + d.qoder_count + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + d.total_count + '</b></div>' +
            '</div>';
    }

    function buildTokenTooltip(label, d) {
        return '<div class="dashboard-tooltip">' +
            '<div class="tooltip-date">' + label + '</div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--claude"></i><span class="tooltip-label">Claude Code</span><b class="tooltip-value">' + formatTokens(d.claude_tokens) + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--codex"></i><span class="tooltip-label">Codex</span><b class="tooltip-value">' + formatTokens(d.codex_tokens) + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--qoder"></i><span class="tooltip-label">Qoder</span><b class="tooltip-value">' + formatTokens(d.qoder_tokens) + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + formatTokens(d.total_tokens) + '</b></div>' +
            '</div>';
    }

    function buildPromptTooltip(label, d) {
        return '<div class="dashboard-tooltip">' +
            '<div class="tooltip-date">' + label + '</div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--claude"></i><span class="tooltip-label">Claude Code</span><b class="tooltip-value">' + d.claude_prompts + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--codex"></i><span class="tooltip-label">Codex</span><b class="tooltip-value">' + d.codex_prompts + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--qoder"></i><span class="tooltip-label">Qoder</span><b class="tooltip-value">' + d.qoder_prompts + '</b></div>' +
            '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + d.total_prompts + '</b></div>' +
            '</div>';
    }

    window.updateChart = function(days) {
        currentDays = days;
        var data = applyScope(rawData, days);
        if (!data.length) { container.innerHTML = '<p class="text-muted text-sm">No data</p>'; return; }
        var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_count; })) || 1;
        var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
        var yHtml = '<div class="y-axis">' + yTicks.map(function(v) { return '<span>' + v + '</span>'; }).join('') + '</div>';
        var plotBars = '';
        data.forEach(function(d) {
            var dateStr = formatDisplayDate(d.date, days);
            var pctH = (d.total_count / maxVal) * 100;
            var claudePct = d.total_count > 0 ? (d.claude_count / d.total_count * 100) : 0;
            var codexPct = d.total_count > 0 ? (d.codex_count / d.total_count * 100) : 0;
            var qoderPct = d.total_count > 0 ? (d.qoder_count / d.total_count * 100) : 0;
            var tip = buildSessionTooltip(dateStr, d);
            plotBars += '<div class="bar" style="--h:' + pctH + '%"><div class="bar-stack">';
            if (d.codex_count > 0) plotBars += '<span class="seg-codex" style="height:' + codexPct + '%"></span>';
            if (d.claude_count > 0) plotBars += '<span class="seg-claude" style="height:' + claudePct + '%"></span>';
            if (d.qoder_count > 0) plotBars += '<span class="seg-qoder" style="height:' + qoderPct + '%"></span>';
            plotBars += '</div>' + tip + '</div>';
        });
        var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';
        var step = Math.max(Math.floor(data.length / 8), 1);
        var xLabels = [];
        data.forEach(function(d, i) {
            xLabels.push('<span>' + (i % step === 0 ? formatDisplayDate(d.date, days) : '') + '</span>');
        });
        var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels.join('') + '</div>';
        container.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
        renderTokenChart(currentDays);
    };

    function renderTokenChart(days) {
        var sliced = rawData.slice(-days);
        if (!sliced.length) return;
        sliced.forEach(function(d) {
            d.total_tokens = d.input_tokens + d.output_tokens + d.cache_read_tokens + d.cache_write_tokens;
            var tt = d.total_tokens, tc = d.total_count || 1;
            d.claude_tokens = Math.round(tt * d.claude_count / tc);
            d.codex_tokens = Math.round(tt * d.codex_count / tc);
            d.qoder_tokens = Math.round(tt * d.qoder_count / tc);
        });
        var data = applyScope(sliced, days);
        if (!data.length) return;
        var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_tokens; })) || 1;
        var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
        var yHtml = '<div class="y-axis">' + yTicks.map(function(v) { return '<span>' + formatTokens(v) + '</span>'; }).join('') + '</div>';
        var plotBars = '';
        data.forEach(function(d) {
            var dateStr = formatDisplayDate(d.date, days);
            var pctH = (d.total_tokens / maxVal) * 100;
            var claudePct = d.total_tokens > 0 ? (d.claude_tokens / d.total_tokens * 100) : 0;
            var codexPct = d.total_tokens > 0 ? (d.codex_tokens / d.total_tokens * 100) : 0;
            var qoderPct = d.total_tokens > 0 ? (d.qoder_tokens / d.total_tokens * 100) : 0;
            var tip = buildTokenTooltip(dateStr, d);
            plotBars += '<div class="bar" style="--h:' + pctH + '%"><div class="bar-stack">';
            if (d.codex_tokens > 0) plotBars += '<span class="seg-codex" style="height:' + codexPct + '%"></span>';
            if (d.claude_tokens > 0) plotBars += '<span class="seg-claude" style="height:' + claudePct + '%"></span>';
            if (d.qoder_tokens > 0) plotBars += '<span class="seg-qoder" style="height:' + qoderPct + '%"></span>';
            plotBars += '</div>' + tip + '</div>';
        });
        var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';
        var step = Math.max(Math.floor(data.length / 8), 1);
        var xLabels = [];
        data.forEach(function(d, i) {
            xLabels.push('<span>' + (i % step === 0 ? formatDisplayDate(d.date, days) : '') + '</span>');
        });
        var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels.join('') + '</div>';
        var tokenContainer = document.getElementById('token-trend-chart');
        if (tokenContainer) tokenContainer.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
    }

    function renderPromptChart(days) {
        var data = applyScope(promptRawData, days, getPromptFields());
        if (!data.length) return;
        var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_prompts; })) || 1;
        var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
        var yHtml = '<div class="y-axis">' + yTicks.map(function(v) { return '<span>' + v + '</span>'; }).join('') + '</div>';
        var plotBars = '';
        data.forEach(function(d) {
            var dateStr = formatDisplayDate(d.date, days);
            var pctH = (d.total_prompts / maxVal) * 100;
            var claudePct = d.total_prompts > 0 ? (d.claude_prompts / d.total_prompts * 100) : 0;
            var codexPct = d.total_prompts > 0 ? (d.codex_prompts / d.total_prompts * 100) : 0;
            var qoderPct = d.total_prompts > 0 ? (d.qoder_prompts / d.total_prompts * 100) : 0;
            var tip = buildPromptTooltip(dateStr, d);
            plotBars += '<div class="bar" style="--h:' + pctH + '%"><div class="bar-stack">';
            if (d.codex_prompts > 0) plotBars += '<span class="seg-codex" style="height:' + codexPct + '%"></span>';
            if (d.claude_prompts > 0) plotBars += '<span class="seg-claude" style="height:' + claudePct + '%"></span>';
            if (d.qoder_prompts > 0) plotBars += '<span class="seg-qoder" style="height:' + qoderPct + '%"></span>';
            plotBars += '</div>' + tip + '</div>';
        });
        var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';
        var step = Math.max(Math.floor(data.length / 8), 1);
        var xLabels = [];
        data.forEach(function(d, i) {
            xLabels.push('<span>' + (i % step === 0 ? formatDisplayDate(d.date, days) : '') + '</span>');
        });
        var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels.join('') + '</div>';
        var promptContainer = document.getElementById('prompt-activity-chart');
        if (promptContainer) promptContainer.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
    }

    window.updateChart(30);
    renderTokenChart(30);
    renderPromptChart(30);

    document.addEventListener('dashboard-scope-change', function(e) {
        var days = 30;
        if (e.detail.scope === 'week') days = 7 * 12;
        else if (e.detail.scope === 'month') days = 30 * 12;
        window.updateChart(days);
        renderTokenChart(days);
        renderPromptChart(days);
    });
    }); // end DOMContentLoaded
})();
