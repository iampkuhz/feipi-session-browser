/**
 * dashboard.js — Dashboard page behavior for Feipi Session Browser.
 *
 * 职责：
 *   - Agent scope 切换（URL 重载）
 *   - 时间粒度切换（URL 重载）
 *   - 图表渲染（Session Trend、Token Trend、Prompt Activity Trend、
 *     Cache Health、Model Mix、Tool Distribution）
 *   - 图表 tooltip hover/focus
 *   - All Agents 行点击切换 scope
 *
 * 使用 data-action 事件委托，不绑定 inline handler。
 * 不复制 ui_primitives.js 或 view-state.js 已有逻辑。
 */
(function () {
    'use strict';

    /* ── State ─────────────────────────────────────────────────── */

    var chartTooltip = null;

    function _cacheElements() {
        chartTooltip = document.getElementById('chartTooltip')
            || document.querySelector('.chart-tooltip');
    }

    /* ── Helpers ───────────────────────────────────────────────── */

    function hideFloating() {
        if (chartTooltip) {
            chartTooltip.setAttribute('aria-hidden', 'true');
            chartTooltip.classList.remove('is-visible');
            chartTooltip.hidden = true;
        }
    }

    /* ── Agent scope selector → URL reload ───────────────────── */

    function handleAgentScope(scope) {
        var params = new URLSearchParams(window.location.search);
        if (scope === 'all') {
            params.delete('agent');
            params.delete('page');
        } else {
            params.set('agent', scope);
            params.delete('page');
        }
        var url = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
        window.location.href = url;
    }

    /* ── Time grain control → URL reload ─────────────────────── */

    function handleGrain(grain) {
        var params = new URLSearchParams(window.location.search);
        params.set('grain', grain);
        var url = window.location.pathname + '?' + params.toString();
        window.location.href = url;
    }

    /* ── Main document-level click delegation ────────────────── */

    document.addEventListener('click', function (event) {
        var target = event.target;
        var button = target.closest ? target.closest('button, a[data-action]') : null;
        if (!button) {
            var el = target;
            while (el && el.nodeType === 1) {
                if (el.tagName === 'BUTTON' || (el.tagName === 'A' && el.hasAttribute('data-action'))) {
                    button = el; break;
                }
                el = el.parentElement;
            }
        }
        if (!button) return;

        var action = button.getAttribute('data-action') || '';
        var hasScope = button.hasAttribute('data-scope');
        var hasGrain = button.hasAttribute('data-grain');

        if (action === 'agent-scope' && hasScope) {
            event.preventDefault();
            handleAgentScope(button.getAttribute('data-scope'));
            return;
        }
        if (action === 'grain' && hasGrain) {
            event.preventDefault();
            handleGrain(button.getAttribute('data-grain'));
            return;
        }
        if (action === 'switch-agent-scope' && hasScope) {
            event.preventDefault();
            handleAgentScope(button.getAttribute('data-scope'));
            return;
        }
        if (action === 'go-sessions-agent-model') {
            var agent = button.getAttribute('data-agent') || '';
            var model = button.getAttribute('data-model') || '';
            var url = '/sessions?agent=' + encodeURIComponent(agent) + '&model=' + encodeURIComponent(model);
            window.location.href = url;
            return;
        }
        if (action === 'go-session') {
            var agent = button.getAttribute('data-agent') || '';
            var sessionId = button.getAttribute('data-session') || '';
            var url = '/sessions/' + agent + '/' + sessionId;
            window.location.href = url;
            return;
        }
        switch (action) {
            default:
                if (action.indexOf('nav-') === 0 && button.classList.contains('nav-item')) {
                    var allNav = document.querySelectorAll('.nav-item');
                    for (var i = 0; i < allNav.length; i++) allNav[i].classList.remove('is-active');
                    if (!button.classList.contains('nav-item--footer')) button.classList.add('is-active');
                    hideFloating();
                }
                break;
        }
    });

    /* ── Window events ───────────────────────────────────────── */

    window.addEventListener('resize', hideFloating);
    window.addEventListener('scroll', hideFloating, true);

    /* ── Keyboard: Escape closes popovers ────────────────────── */

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' || event.key === 'Esc') {
            hideFloating();
        }
    });

    /* ── Public API ──────────────────────────────────────────── */

    window.DashboardPage = {
        openSettings: null,
        closeSettings: null,
        hideFloating: hideFloating
    };

    /* ── Init ────────────────────────────────────────────────── */

    _cacheElements();
})();


/**
 * dashboard-charts.js - Chart rendering for Dashboard.
 * Business data is hydrated from Dashboard resource APIs.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var rawData = [];
        var promptRawData = [];
        var cacheRawData = [];

        var AGENTS = [
            { key: 'claude_code', scope: 'claude-code', label: 'Claude Code', countKey: 'claude_count', promptKey: 'claude_prompts', tokenKey: 'claude_tokens', dot: 'claude' },
            { key: 'qoder', scope: 'qoder', label: 'Qoder', countKey: 'qoder_count', promptKey: 'qoder_prompts', tokenKey: 'qoder_tokens', dot: 'qoder' },
            { key: 'codex', scope: 'codex', label: 'Codex', countKey: 'codex_count', promptKey: 'codex_prompts', tokenKey: 'codex_tokens', dot: 'codex' }
        ];
        var TOKEN_LAYERS = [
            { key: 'fresh_input_tokens', cls: 'fresh', label: 'Fresh' },
            { key: 'cache_read_tokens', cls: 'read', label: 'Cache Read' },
            { key: 'cache_write_tokens', cls: 'write', label: 'Cache Write' },
            { key: 'output_tokens', cls: 'out', label: 'Output' }
        ];

        function weekKey(dateStr) {
            if (!dateStr) return '';
            if (dateStr.indexOf('-W') > 0) return dateStr;
            var d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            var tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
            var day = tmp.getUTCDay() || 7;
            tmp.setUTCDate(tmp.getUTCDate() + 4 - day);
            var yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
            var week = Math.ceil((((tmp - yearStart) / 86400000) + 1) / 7);
            return tmp.getUTCFullYear() + '-W' + String(week).padStart(2, '0');
        }

        function monthKey(dateStr) {
            return (dateStr || '').substring(0, 7);
        }

        function aggregateByKey(data, fields, keyFn, dateFn) {
            var map = {};
            var order = [];
            data.forEach(function(d) {
                var key = keyFn(d.date || '');
                if (!key) return;
                if (!map[key]) {
                    map[key] = { date: dateFn ? dateFn(key) : key };
                    order.push(key);
                }
                fields.forEach(function(f) {
                    map[key][f] = (map[key][f] || 0) + (d[f] || 0);
                });
            });
            return order.map(function(k) { return map[k]; });
        }

        function getGrain() {
            var el = document.querySelector('.grain-control__btn.is-active');
            return el ? (el.getAttribute('data-grain') || 'day') : 'day';
        }

        function getActiveScope() {
            var el = document.querySelector('.scope-selector__btn.is-active');
            return el ? (el.getAttribute('data-scope') || 'all') : 'all';
        }

        function scopeToAgentKey(scope) {
            if (scope === 'claude-code') return 'claude_code';
            if (scope === 'qoder') return 'qoder';
            if (scope === 'codex') return 'codex';
            return 'average';
        }

        function getDaysForGrain(grain) {
            if (grain === 'week') return 20 * 7;
            if (grain === 'month') return 12 * 30;
            return 30;
        }

        function applyScope(data, fields) {
            var grain = getGrain();
            var sliced = data.slice(-getDaysForGrain(grain));
            if (!sliced.length) return [];
            if (grain === 'week') {
                return aggregateByKey(sliced, fields, weekKey, function(k) { return k; });
            }
            if (grain === 'month') {
                return aggregateByKey(sliced, fields, monthKey, function(k) { return k + '-01'; });
            }
            return sliced;
        }

        function getTrendFields() {
            return [
                'claude_count', 'codex_count', 'qoder_count', 'total_count',
                'claude_tokens', 'codex_tokens', 'qoder_tokens', 'total_tokens',
                'fresh_input_tokens', 'cache_read_tokens', 'cache_write_tokens',
                'output_tokens', 'tool_calls', 'failed_tools'
            ];
        }

        function getPromptFields() {
            return [
                'claude_prompts', 'codex_prompts', 'qoder_prompts',
                'total_prompts', 'assistant_turns', 'tool_calls'
            ];
        }

        function getCacheFields() {
            var fields = [];
            ['average', 'claude_code', 'qoder', 'codex'].forEach(function(prefix) {
                ['fresh_input_tokens', 'cache_read_tokens', 'cache_write_tokens'].forEach(function(metric) {
                    fields.push(prefix + '_' + metric);
                });
            });
            fields.push('qoder_unreported_input_side_tokens');
            return fields;
        }

        function formatDisplayDate(dateStr) {
            var grain = getGrain();
            if (!dateStr) return '';
            if (grain === 'week') return dateStr.indexOf('-W') > 0 ? dateStr : weekKey(dateStr);
            if (grain === 'month') return dateStr.substring(0, 7);
            return dateStr.substring(5, 10);
        }

        function formatTokens(n) {
            n = Number(n || 0);
            if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
            if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
            if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
            return String(Math.round(n));
        }

        function formatSignedTokens(n) {
            n = Number(n || 0);
            if (n > 0) return '+' + formatTokens(n);
            if (n < 0) return '-' + formatTokens(Math.abs(n));
            return '0';
        }

        function formatNumber(n) {
            if (n == null) return '0';
            return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        }

        function formatDuration(seconds) {
            var n = Math.max(0, Math.round(Number(seconds || 0)));
            if (n >= 3600) return Math.floor(n / 3600) + 'h ' + Math.floor((n % 3600) / 60) + 'm';
            if (n >= 60) return Math.floor(n / 60) + 'm ' + (n % 60) + 's';
            return n + 's';
        }

        function formatPct(n) {
            if (n == null || !isFinite(n)) return '';
            return n.toFixed(1) + '%';
        }

        function escapeHtml(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function setChartMarkup(container, markup) {
            var parsed = new DOMParser().parseFromString(markup, 'text/html');
            container.replaceChildren.apply(container, Array.prototype.slice.call(parsed.body.childNodes));
        }

        function xPct(index, length) {
            return length <= 1 ? 50 : (index / (length - 1) * 100);
        }

        function xBandCenterPct(index, length) {
            return length <= 0 ? 50 : ((index + 0.5) / length * 100);
        }

        function yPct(value, maxVal) {
            return 100 - ((Number(value || 0) / Math.max(1, maxVal)) * 100);
        }

        function yPctRange(value, minVal, maxVal, insetPct) {
            var span = Math.max(1, maxVal - minVal);
            var normalized = (Number(value || 0) - minVal) / span;
            normalized = Math.max(0, Math.min(1, normalized));
            var inset = Number(insetPct || 0);
            return inset + (1 - normalized) * (100 - inset * 2);
        }

        function yAxisHtml(ticks, formatter, extraClass) {
            return '<div class="y-axis' + (extraClass ? ' ' + extraClass : '') + '">' + ticks.map(function(v) {
                return '<span>' + escapeHtml(formatter ? formatter(v) : v) + '</span>';
            }).join('') + '</div>';
        }

        function plotGridHtml(ticks, yFn) {
            return '<div class="plot-grid" aria-hidden="true">' + ticks.map(function(tick) {
                return '<span class="plot-grid__line" style="--grid-y:' + yFn(tick).toFixed(2) + '%"></span>';
            }).join('') + '</div>';
        }

        function xAxisHtml(data) {
            var step = Math.max(Math.floor(data.length / 8), 1);
            var labels = data.map(function(d, i) {
                return '<span>' + (i % step === 0 ? escapeHtml(formatDisplayDate(d.date)) : '') + '</span>';
            }).join('');
            return '<div class="x-axis" style="--n:' + data.length + '">' + labels + '</div>';
        }

        function tooltipRow(dotClass, label, value, share, rowClass) {
            var cls = 'tooltip-row' + (rowClass ? ' ' + rowClass : '');
            return '<div class="' + cls + '"><i class="tooltip-dot tooltip-dot--' + dotClass + '"></i><span class="tooltip-label">' +
                escapeHtml(label) + '</span><b class="tooltip-value">' + escapeHtml(value) +
                '</b><span class="tooltip-share">' + escapeHtml(share || '') + '</span></div>';
        }

        function tooltipLineRow(lineClass, label, value, share, rowClass) {
            var cls = 'tooltip-row tooltip-row--line' + (rowClass ? ' ' + rowClass : '');
            return '<div class="' + cls + '"><i class="tooltip-line-key tooltip-line-key--' + lineClass + '"></i><span class="tooltip-label">' +
                escapeHtml(label) + '</span><b class="tooltip-value">' + escapeHtml(value) +
                '</b><span class="tooltip-share">' + escapeHtml(share || '') + '</span></div>';
        }

        function tooltipSection(title) {
            return '<div class="tooltip-section-title">' + escapeHtml(title) + '</div>';
        }

        function tooltipShell(label, rows) {
            return '<div class="dashboard-tooltip"><div class="tooltip-date">' + escapeHtml(label) + '</div>' + rows.join('') + '</div>';
        }

        function edgeClass(index, length, base) {
            if (length <= 2) return '';
            if (index <= 1) return base + '--edge-left';
            if (index >= length - 2) return base + '--edge-right';
            return '';
        }

        function share(value, total) {
            if (!total) return '';
            return (value / total * 100).toFixed(1) + '%';
        }

        function totalTokens(d) {
            return (d.total_tokens || 0) || TOKEN_LAYERS.reduce(function(sum, layer) {
                return sum + (d[layer.key] || 0);
            }, 0);
        }

        function inputSide(d, prefix) {
            return (d[prefix + '_fresh_input_tokens'] || 0) +
                (d[prefix + '_cache_read_tokens'] || 0) +
                (d[prefix + '_cache_write_tokens'] || 0);
        }

        function cacheMetricKnown(d, prefix) {
            return d[prefix + '_cache_metric_known'] !== false;
        }

        function cacheRatio(d, prefix) {
            if (!cacheMetricKnown(d, prefix)) return null;
            var input = inputSide(d, prefix);
            if (!input) return null;
            return (d[prefix + '_cache_read_tokens'] || 0) / input * 100;
        }

        function normalizeCacheMetricFlags(data) {
            data.forEach(function(d) {
                var qoderKnownInput = inputSide(d, 'qoder');
                var qoderUnreported = d.qoder_unreported_input_side_tokens || 0;
                d.qoder_cache_metric_known = !(qoderUnreported > 0 && qoderKnownInput <= 0);
            });
            return data;
        }

        function linePath(data, maxVal, valueFn, xFn, yFn) {
            var parts = [];
            var open = false;
            var resolveX = xFn || xBandCenterPct;
            var resolveY = yFn || function(val) { return yPct(val, maxVal); };
            data.forEach(function(d, i) {
                var val = valueFn(d, i);
                if (val == null || !isFinite(val)) {
                    return;
                }
                var cmd = open ? 'L ' : 'M ';
                parts.push(cmd + resolveX(i, data.length).toFixed(2) + ',' + resolveY(val).toFixed(2));
                open = true;
            });
            return parts.join(' ');
        }

        function isolatedLineMarkers(data, valueFn, xFn, yFn, className) {
            var resolveX = xFn || xPct;
            var markers = [];
            var validIndexes = [];
            data.forEach(function(d, i) {
                var value = valueFn(d, i);
                if (value != null && isFinite(value)) validIndexes.push(i);
            });
            if (validIndexes.length !== 1) return '';
            data.forEach(function(d, i) {
                if (i !== validIndexes[0]) return;
                var val = valueFn(d, i);
                if (val == null || !isFinite(val)) return;
                var x = resolveX(i, data.length);
                var y = yFn(val);
                markers.push('<line class="' + className + ' line-isolated-marker" x1="' +
                    Math.max(0, x - 1.2).toFixed(2) + '" x2="' + Math.min(100, x + 1.2).toFixed(2) +
                    '" y1="' + y.toFixed(2) + '" y2="' + y.toFixed(2) + '"></line>');
            });
            return markers.join('');
        }

        function buildSessionTooltip(label, d, rangeTotal, previous, activeScope) {
            var rows = [];
            AGENTS.forEach(function(agent) {
                var value = d[agent.countKey] || 0;
                if (activeScope !== 'all' && !value) return;
                rows.push(tooltipRow(agent.dot, agent.label, formatNumber(value), share(value, d.total_count || 0)));
            });
            rows.push(tooltipRow('total', 'Total', formatNumber(d.total_count || 0), share(d.total_count || 0, rangeTotal), 'tooltip-row--total'));
            var prevTotal = previous ? (previous.total_count || 0) : null;
            var delta = prevTotal == null ? 'N/A' : ((d.total_count || 0) - prevTotal > 0 ? '+' : '') + formatNumber((d.total_count || 0) - prevTotal);
            rows.push(tooltipRow('total', 'Delta', delta, ''));
            return tooltipShell(label, rows);
        }

        function buildTokenTooltip(label, d, rangeTotal, previous) {
            var rows = [];
            var total = totalTokens(d);
            TOKEN_LAYERS.forEach(function(layer) {
                var value = d[layer.key] || 0;
                rows.push(tooltipRow(layer.cls, layer.label, formatTokens(value), share(value, total)));
            });
            rows.push(tooltipRow('total', 'Total', formatTokens(total), share(total, rangeTotal), 'tooltip-row--total'));
            var prevTotal = previous ? totalTokens(previous) : null;
            var delta = prevTotal == null ? 'N/A' : formatSignedTokens(total - prevTotal);
            rows.push(tooltipRow('total', 'Delta', delta, ''));
            return tooltipShell(label, rows);
        }

        function buildPromptTooltip(label, d, trendPoint) {
            var rows = [];
            var activeScope = getActiveScope();
            var scopedAgents = activeScope === 'all'
                ? AGENTS
                : AGENTS.filter(function(agent) { return agent.scope === activeScope; });
            if (!scopedAgents.length) scopedAgents = AGENTS;

            var primaryAgent = scopedAgents[0];
            var totalPrompts = activeScope === 'all'
                ? (d.total_prompts || 0)
                : (d[primaryAgent.promptKey] || d.total_prompts || 0);
            var totalSessions = activeScope === 'all'
                ? (trendPoint ? (trendPoint.total_count || 0) : 0)
                : (trendPoint ? (trendPoint[primaryAgent.countKey] || trendPoint.total_count || 0) : 0);
            var totalAverage = totalSessions > 0 ? (totalPrompts / totalSessions).toFixed(1) : 'N/A';

            rows.push(tooltipSection('User Prompts (bars)'));
            scopedAgents.forEach(function(agent) {
                var prompts = d[agent.promptKey] || 0;
                if (!prompts && activeScope !== 'all') return;
                rows.push(tooltipRow(agent.dot, agent.label, formatNumber(prompts), share(prompts, totalPrompts)));
            });
            rows.push(tooltipRow('total', 'Total User Prompts', formatNumber(totalPrompts), '', 'tooltip-row--total'));

            rows.push(tooltipSection('Avg Prompts / Session (line)'));
            rows.push(tooltipLineRow('prompt-average', 'Overall', totalAverage, '/ session'));
            if (activeScope === 'all') {
                scopedAgents.forEach(function(agent) {
                    var prompts = d[agent.promptKey] || 0;
                    var sessions = trendPoint ? (trendPoint[agent.countKey] || 0) : 0;
                    var perSession = sessions > 0 ? (prompts / sessions).toFixed(1) : 'N/A';
                    rows.push(tooltipLineRow(agent.dot, agent.label, perSession, '/ session'));
                });
            }

            rows.push(tooltipSection('Auxiliary'));
            rows.push(tooltipRow('total', 'Assistant Turns', formatNumber(d.assistant_turns || 0), ''));
            rows.push(tooltipRow('total', 'Tool Calls', formatNumber(d.tool_calls || 0), ''));
            return tooltipShell(label, rows);
        }

        function renderSessionChart() {
            var container = document.getElementById('trend-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { setChartMarkup(container, '<p class="chart-empty">该时间窗口无数据。</p>'); return; }

            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_count || 0; })) || 1;
            var rangeTotal = data.reduce(function(sum, d) { return sum + (d.total_count || 0); }, 0);
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatNumber);

            var bars = '';
            var activeScope = getActiveScope();
            data.forEach(function(d, i) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = (d.total_count / maxVal) * 100;
                var total = d.total_count || 1;
                var tip = buildSessionTooltip(dateStr, d, rangeTotal, i > 0 ? data[i - 1] : null, activeScope);
                var edge = edgeClass(i, data.length, 'bar');
                bars += '<div class="bar' + (edge ? ' ' + edge : '') + '" style="--h:' + pctH + '%"><span class="chart-hover-guide"></span><div class="bar-stack">';
                if (d.codex_count > 0) bars += '<span class="seg-codex" style="height:' + ((d.codex_count || 0) / total * 100) + '%"></span>';
                if (d.claude_count > 0) bars += '<span class="seg-claude" style="height:' + ((d.claude_count || 0) / total * 100) + '%"></span>';
                if (d.qoder_count > 0) bars += '<span class="seg-qoder" style="height:' + ((d.qoder_count || 0) / total * 100) + '%"></span>';
                bars += '</div>' + tip + '</div>';
            });

            setChartMarkup(container, '<div class="chart">' + yHtml +
                '<div class="plot" style="--n:' + data.length + '">' + bars + '</div>' +
                xAxisHtml(data) + '</div>');
        }

        function renderTokenChart() {
            var container = document.getElementById('token-trend-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { setChartMarkup(container, '<p class="chart-empty">该时间窗口无数据。</p>'); return; }

            var maxVal = Math.max.apply(null, data.map(totalTokens)) || 1;
            if (!maxVal) { setChartMarkup(container, '<p class="chart-empty">该时间窗口无 token 数据。</p>'); return; }
            var rangeTotal = data.reduce(function(sum, d) { return sum + totalTokens(d); }, 0);
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatTokens);

            var cumulative = data.map(function() { return 0; });
            var paths = '';
            TOKEN_LAYERS.forEach(function(layer) {
                var upper = [];
                var lower = [];
                data.forEach(function(d, i) {
                    var x = xBandCenterPct(i, data.length);
                    var low = cumulative[i];
                    var high = low + (d[layer.key] || 0);
                    lower.push([x, yPct(low, maxVal)]);
                    upper.push([x, yPct(high, maxVal)]);
                    cumulative[i] = high;
                });
                var dPath = 'M ' + upper.map(function(p) { return p[0].toFixed(2) + ',' + p[1].toFixed(2); }).join(' L ');
                dPath += ' L ' + lower.slice().reverse().map(function(p) { return p[0].toFixed(2) + ',' + p[1].toFixed(2); }).join(' L ');
                dPath += ' Z';
                paths += '<path class="area-layer area-layer--' + layer.cls + '" d="' + dPath + '"></path>';
            });
            paths += '<path class="area-total-line" d="' + linePath(data, maxVal, totalTokens) + '"></path>';

            var activeScope = getActiveScope();
            var targets = '';
            data.forEach(function(d, i) {
                var total = totalTokens(d);
                var x = xBandCenterPct(i, data.length);
                var y = yPct(total, maxVal);
                var tip = buildTokenTooltip(formatDisplayDate(d.date), d, rangeTotal, i > 0 ? data[i - 1] : null);
                var edge = edgeClass(i, data.length, 'chart-hover-target');
                targets += '<span class="chart-hover-target' + (edge ? ' ' + edge : '') + '" style="--point-x:' + x.toFixed(2) + '%;--point-y:' + y.toFixed(2) + '%"><span class="chart-hover-guide"></span><span class="area-point"></span>' + tip + '</span>';
            });

            var legend = TOKEN_LAYERS.map(function(layer) {
                var value = data.reduce(function(sum, d) { return sum + (d[layer.key] || 0); }, 0);
                return '<span class="chart-legend__item"><i class="chart-legend__dot chart-legend__dot--' + layer.cls + '"></i>' +
                    escapeHtml(layer.label) + ' ' + escapeHtml(formatTokens(value)) + ' ' + escapeHtml(share(value, rangeTotal)) + '</span>';
            }).join('');

            setChartMarkup(container, '<div class="chart">' + yHtml +
                '<div class="plot plot--area" style="--n:' + data.length + '"><svg class="area-plot" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + paths + '</svg>' + targets + '</div>' +
                xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>');
        }

        function renderPromptChart() {
            var container = document.getElementById('prompt-activity-chart');
            if (!container) return;
            var data = applyScope(promptRawData, getPromptFields());
            var trendData = applyScope(rawData, getTrendFields());
            if (!data.length) { setChartMarkup(container, '<p class="chart-empty">该时间窗口无数据。</p>'); return; }

            var trendByDate = {};
            trendData.forEach(function(d) { trendByDate[d.date] = d; });
            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_prompts || 0; })) || 1;
            var avgValues = data.map(function(d) {
                var sessions = trendByDate[d.date] ? (trendByDate[d.date].total_count || 0) : 0;
                return sessions > 0 ? (d.total_prompts || 0) / sessions : null;
            });
            var avgCandidates = avgValues.filter(function(v) { return v != null && isFinite(v); });
            var maxAvg = avgCandidates.length ? Math.max.apply(null, avgCandidates) : 1;
            if (!maxAvg || !isFinite(maxAvg)) maxAvg = 1;
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatNumber);
            var yRightHtml = yAxisHtml([maxAvg, 2 / 3 * maxAvg, 1 / 3 * maxAvg, 0], function(v) { return Number(v || 0).toFixed(1); }, 'y-axis--right');

            var bars = '';
            data.forEach(function(d, i) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = (d.total_prompts / maxVal) * 100;
                var total = d.total_prompts || 1;
                var tip = buildPromptTooltip(dateStr, d, trendByDate[d.date]);
                var edge = edgeClass(i, data.length, 'bar');
                bars += '<div class="bar' + (edge ? ' ' + edge : '') + '" style="--h:' + pctH + '%"><span class="chart-hover-guide"></span><div class="bar-stack">';
                if (d.codex_prompts > 0) bars += '<span class="seg-codex" style="height:' + ((d.codex_prompts || 0) / total * 100) + '%"></span>';
                if (d.claude_prompts > 0) bars += '<span class="seg-claude" style="height:' + ((d.claude_prompts || 0) / total * 100) + '%"></span>';
                if (d.qoder_prompts > 0) bars += '<span class="seg-qoder" style="height:' + ((d.qoder_prompts || 0) / total * 100) + '%"></span>';
                bars += '</div>' + tip + '</div>';
            });

            var avgPath = linePath(data, maxAvg, function(d, i) { return avgValues[i]; }, xBandCenterPct);
            var avgLine = '<svg class="line-plot line-plot--bar-aligned" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' +
                '<path class="line-series line-series--prompt-average" d="' + avgPath + '"></path></svg>';
            var avgMarkers = avgValues.map(function(value, i) {
                if (value == null || !isFinite(value)) return '';
                return '<span class="line-point line-point--prompt-average" style="--point-x:' + xBandCenterPct(i, data.length).toFixed(2) + '%;--point-y:' + yPct(value, maxAvg).toFixed(2) + '%"></span>';
            }).join('');
            var legend = '<span class="chart-legend__item"><i class="chart-legend__line chart-legend__line--prompt-average"></i>Avg Prompts / Session</span>';

            setChartMarkup(container, '<div class="chart chart--dual-axis">' + yHtml +
                '<div class="plot" style="--n:' + data.length + '">' + avgLine + '<div class="prompt-line-markers" aria-hidden="true">' + avgMarkers + '</div>' + bars + '</div>' +
                yRightHtml + xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>');
        }

        function buildCacheTooltip(label, d, highlightPrefix) {
            var rows = [];
            [
                { prefix: 'average', label: 'Average', line: 'average' },
                { prefix: 'claude_code', label: 'Claude Code', line: 'claude' },
                { prefix: 'qoder', label: 'Qoder', line: 'qoder' },
                { prefix: 'codex', label: 'Codex', line: 'codex' }
            ].forEach(function(item) {
                var ratio = cacheRatio(d, item.prefix);
                rows.push(tooltipLineRow(item.line, item.label, ratio == null ? 'N/A' : ratio.toFixed(1) + '%', item.prefix === highlightPrefix ? 'selected' : ''));
            });
            var input = inputSide(d, highlightPrefix);
            if (!cacheMetricKnown(d, highlightPrefix)) {
                rows.push(tooltipRow('total', 'Input-side Tokens', 'N/A', '', 'tooltip-row--total'));
                var unreported = d[highlightPrefix + '_unreported_input_side_tokens'] || 0;
                if (unreported > 0) {
                    rows.push(tooltipRow('total', 'Unreported Input-side', formatTokens(unreported), ''));
                }
            } else {
                rows.push(tooltipRow('total', 'Input-side Tokens', formatTokens(input), '', 'tooltip-row--total'));
            }
            rows.push(tooltipRow('fresh', 'Fresh', formatTokens(d[highlightPrefix + '_fresh_input_tokens'] || 0), ''));
            rows.push(tooltipRow('read', 'Cache Read', formatTokens(d[highlightPrefix + '_cache_read_tokens'] || 0), ''));
            rows.push(tooltipRow('write', 'Cache Write', formatTokens(d[highlightPrefix + '_cache_write_tokens'] || 0), ''));
            return tooltipShell(label, rows);
        }

        function cacheAxisDomain(data, specs) {
            var values = [];
            data.forEach(function(d) {
                specs.forEach(function(spec) {
                    var ratio = cacheRatio(d, spec.prefix);
                    if (ratio != null && isFinite(ratio)) values.push(ratio);
                });
            });
            if (!values.length) return { min: 0, max: 100, ticks: [100, 75, 50, 25, 0] };
            var minVal = Math.min.apply(null, values);
            var lower = Math.max(0, Math.floor((minVal - 5) / 5) * 5);
            if (minVal <= 0) lower = 0;
            if (lower >= 100) lower = 95;
            var span = 100 - lower;
            return {
                min: lower,
                max: 100,
                ticks: [100, lower + span * 0.75, lower + span * 0.5, lower + span * 0.25, lower]
            };
        }

        function formatCacheTick(v) {
            return (Math.abs(v - Math.round(v)) < 0.05 ? Math.round(v) : v.toFixed(1)) + '%';
        }

        function renderCacheHealthChart() {
            var container = document.getElementById('cache-health-chart');
            if (!container) return;
            var data = normalizeCacheMetricFlags(applyScope(cacheRawData, getCacheFields()));
            if (!data.length) { setChartMarkup(container, '<p class="chart-empty">该时间窗口无数据。</p>'); return; }

            var activeScope = getActiveScope();
            var highlightPrefix = scopeToAgentKey(activeScope);
            var specs = [
                { prefix: 'average', label: 'Average' },
                { prefix: 'claude_code', label: 'Claude Code' },
                { prefix: 'qoder', label: 'Qoder' },
                { prefix: 'codex', label: 'Codex' }
            ];
            var domain = cacheAxisDomain(data, specs);
            var cacheY = function(value) { return yPctRange(value, domain.min, domain.max, 5); };
            var yHtml = yAxisHtml(domain.ticks, formatCacheTick);
            var gridHtml = plotGridHtml(domain.ticks, cacheY);
            var paths = '';
            var isolatedMarkers = '';
            specs.forEach(function(spec) {
                var highlight = spec.prefix === highlightPrefix;
                var cls = 'line-series line-series--' + spec.prefix + (highlight ? ' line-series--highlight' : ' line-series--muted');
                var valueFn = function(d) { return cacheRatio(d, spec.prefix); };
                paths += '<path class="' + cls + '" d="' + linePath(data, 100, valueFn, xBandCenterPct, cacheY) + '"></path>';
                isolatedMarkers += isolatedLineMarkers(data, valueFn, xBandCenterPct, cacheY, cls);
            });

            var targets = '';
            data.forEach(function(d, i) {
                var ratio = cacheRatio(d, highlightPrefix);
                var x = xBandCenterPct(i, data.length);
                var pointStyle = '';
                var pointHtml = '';
                if (ratio != null && isFinite(ratio)) {
                    pointStyle = '--point-y:' + cacheY(ratio).toFixed(2) + '%;';
                    pointHtml = '<span class="line-point line-point--' + highlightPrefix + '"></span>';
                }
                var tip = buildCacheTooltip(formatDisplayDate(d.date), d, highlightPrefix);
                var edge = edgeClass(i, data.length, 'chart-hover-target');
                targets += '<span class="chart-hover-target' + (edge ? ' ' + edge : '') + '" style="--point-x:' + x.toFixed(2) + '%;' + pointStyle + '"><span class="chart-hover-guide"></span>' +
                    pointHtml + tip + '</span>';
            });

            var legend = specs.map(function(spec) {
                return '<span class="chart-legend__item"><i class="chart-legend__line chart-legend__line--' + spec.prefix + '"></i>' + escapeHtml(spec.label) + '</span>';
            }).join('');

            setChartMarkup(container, '<div class="chart chart--cache-health">' + yHtml +
                '<div class="plot plot--line plot--cache-health" style="--n:' + data.length + '">' + gridHtml + '<svg class="line-plot line-plot--bar-aligned" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + paths + isolatedMarkers + '</svg><div class="line-targets line-targets--bar-aligned">' + targets + '</div></div>' +
                xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>');
        }

        function currentApiParams() {
            var params = new URLSearchParams(window.location.search || '');
            params.set('agent', getActiveScope());
            params.set('grain', getGrain());
            return params;
        }

        function apiGet(path, params) {
            var qs = params ? params.toString() : '';
            return fetch(path + (qs ? '?' + qs : ''), { headers: { 'Accept': 'application/json' } })
                .then(function(response) {
                    if (!response.ok) throw new Error('HTTP ' + response.status);
                    return response.json();
                });
        }

        function loadDashboardApiData() {
            if (!window.fetch) return Promise.resolve(null);
            var params = currentApiParams();
            var activeScope = getActiveScope();
            return Promise.all([
                apiGet('/api/dashboard/summary', params),
                apiGet('/api/dashboard/trends/sessions', params),
                apiGet('/api/dashboard/trends/tokens', params),
                apiGet('/api/dashboard/trends/prompts', params),
                apiGet('/api/dashboard/trends/cache-health', params),
                apiGet('/api/dashboard/agents/contribution', params),
                apiGet('/api/dashboard/agents/efficiency', params),
                apiGet('/api/dashboard/agents/' + encodeURIComponent(activeScope === 'all' ? 'claude-code' : activeScope) + '/deep-dive', params)
            ]).then(function(parts) {
                updateDashboardSummary(parts[0]);
                rawData = mergeSessionTokenTrends(parts[1], parts[2]);
                promptRawData = promptTrendRows(parts[3]);
                cacheRawData = cacheHealthRows(parts[4]);
                updateAgentContribution(parts[5]);
                updateAgentEfficiency(parts[6], parts[7]);
                updateChartStats(parts[1], parts[2], parts[3], parts[4]);
                renderAll();
            });
        }

        function updateDashboardSummary(summary) {
            if (!summary) return;
            setKpiValue('Sessions', formatNumber(summary.sessionCount));
            setKpiValue('Projects', formatNumber(summary.projectCount));
            setKpiValue('Total Tokens', formatTokens(summary.tokens && summary.tokens.total));
            setKpiValue('User Prompts', formatNumber(summary.userMessages));
            setKpiValue('Failed Tools', formatNumber(summary.failedTools));
            setKpiValue('Cache Read Ratio', summary.cacheReadRatio && summary.cacheReadRatio.value != null
                ? formatPct(summary.cacheReadRatio.value * 100)
                : 'N/A');
        }

        function setKpiValue(label, value) {
            var cards = document.querySelectorAll('.metric-card--kpi');
            for (var i = 0; i < cards.length; i++) {
                var labelEl = cards[i].querySelector('.metric-card__label');
                if (!labelEl || labelEl.textContent.trim() !== label) continue;
                var valueEl = cards[i].querySelector('.metric-card__value');
                if (valueEl) valueEl.textContent = value;
            }
        }

        function mergeSessionTokenTrends(sessionResp, tokenResp) {
            var byDate = {};
            (sessionResp && sessionResp.points || []).forEach(function(point) {
                byDate[point.date] = byDate[point.date] || { date: point.date };
                byDate[point.date].total_count = point.totalCount || 0;
                byDate[point.date].claude_count = point.claudeCount || 0;
                byDate[point.date].codex_count = point.codexCount || 0;
                byDate[point.date].qoder_count = point.qoderCount || 0;
                byDate[point.date].tool_calls = point.toolCalls || 0;
                byDate[point.date].failed_tools = point.failedTools || 0;
            });
            (tokenResp && tokenResp.points || []).forEach(function(point) {
                byDate[point.date] = byDate[point.date] || { date: point.date };
                var tokens = point.tokens || {};
                byDate[point.date].fresh_input_tokens = tokens.fresh || 0;
                byDate[point.date].cache_read_tokens = tokens.cacheRead || 0;
                byDate[point.date].cache_write_tokens = tokens.cacheWrite || 0;
                byDate[point.date].output_tokens = tokens.output || 0;
                byDate[point.date].total_tokens = tokens.total || 0;
                byDate[point.date].claude_tokens = point.claudeTokens || 0;
                byDate[point.date].codex_tokens = point.codexTokens || 0;
                byDate[point.date].qoder_tokens = point.qoderTokens || 0;
            });
            return Object.keys(byDate).sort().map(function(key) { return byDate[key]; });
        }

        function promptTrendRows(resp) {
            return (resp && resp.points || []).map(function(point) {
                return {
                    date: point.date,
                    claude_prompts: point.claudePrompts || 0,
                    codex_prompts: point.codexPrompts || 0,
                    qoder_prompts: point.qoderPrompts || 0,
                    total_prompts: point.totalPrompts || 0,
                    assistant_turns: point.assistantTurns || 0,
                    tool_calls: point.toolCalls || 0
                };
            });
        }

        function cacheHealthRows(resp) {
            return (resp && resp.points || []).map(function(point) {
                var row = { date: point.date };
                copyCacheTuple(row, 'average', point.average);
                copyCacheTuple(row, 'claude_code', point.claudeCode);
                copyCacheTuple(row, 'codex', point.codex);
                copyCacheTuple(row, 'qoder', point.qoder);
                return row;
            });
        }

        function copyCacheTuple(target, prefix, tuple) {
            tuple = tuple || {};
            target[prefix + '_fresh_input_tokens'] = tuple.fresh || 0;
            target[prefix + '_cache_read_tokens'] = tuple.cacheRead || 0;
            target[prefix + '_cache_write_tokens'] = tuple.cacheWrite || 0;
            target[prefix + '_cache_metric_known'] = !(tuple.ratio && tuple.ratio.value == null);
        }

        function updateChartStats(sessions, tokens, prompts, cache) {
            setStatText('range-total-sessions', 'Range total: ' + formatNumber(sessions && sessions.rangeTotal));
            setStatText('range-total-tokens', 'Range total: ' + formatTokens(tokens && tokens.rangeTotals && tokens.rangeTotals.total));
            setStatText('range-total-prompts', 'Range total: ' + formatNumber(prompts && prompts.rangeTotalPrompts));
            setStatText('latest-ratio', 'Latest ratio: ' + ratioText(cache && cache.latestRatio));
            setStatText('lowest-ratio', 'Lowest ratio: ' + ratioText(cache && cache.lowestRatio));
        }

        function ratioText(ratio) {
            return ratio && ratio.value != null ? formatPct(ratio.value * 100) : 'N/A';
        }

        function setStatText(name, text) {
            var el = document.querySelector('[data-stat="' + name + '"]');
            if (el) el.textContent = text;
        }

        function updateAgentContribution(resp) {
            if (!resp || !Array.isArray(resp.rows)) return;
            renderContributionBar('session-share', resp.rows, 'sessionCount', 'sessionShare', formatNumber);
            renderContributionBar('token-share', resp.rows, function(row) { return row.tokens && row.tokens.total; }, 'tokenShare', formatTokens);
            renderContributionBar('prompt-share', resp.rows, 'prompts', 'promptShare', formatNumber);
            var table = document.getElementById('dashboard-all-agents-table');
            if (!table) return;
            var tbody = table.querySelector('tbody');
            if (!tbody) return;
            setChartMarkup(tbody, resp.rows.map(function(row) {
                var scope = row.agent === 'claude_code' ? 'claude-code' : row.agent;
                return '<tr class="agent-row" data-action="switch-agent-scope" data-scope="' + escapeHtml(scope) + '">' +
                    '<td data-sort-value="' + escapeHtml(row.label) + '"><span class="agent-badge agent-badge--' + escapeHtml(row.agent) + '">' + escapeHtml(row.label) + '</span></td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.sessionCount) + '">' + formatNumber(row.sessionCount) + ' <span class="muted">· ' + formatPct(row.sessionShare) + '</span></td>' +
                    '<td class="numeric token-cell" data-sort-value="' + escapeHtml(row.tokens && row.tokens.total) + '">' + formatTokens(row.tokens && row.tokens.total) + ' <span class="muted">· ' + formatPct(row.tokenShare) + '</span></td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.prompts) + '">' + formatNumber(row.prompts) + ' <span class="muted">· ' + formatPct(row.promptShare) + '</span></td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.projectCount) + '">' + formatNumber(row.projectCount) + '</td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.failedTools) + '">' + formatNumber(row.failedTools) + ' failed</td><td class="numeric">—</td></tr>';
            }).join(''));
        }

        function renderContributionBar(name, rows, valueKey, shareKey, formatter) {
            var bar = document.querySelector('[data-hbar="' + name + '"]');
            if (!bar) return;
            setChartMarkup(bar, rows.filter(function(row) { return valueOf(row, valueKey) > 0; }).map(function(row) {
                var value = valueOf(row, valueKey);
                var shareValue = row[shareKey] || 0;
                return '<div class="hbar-seg hbar-seg--' + escapeHtml(row.agent) + '" style="--seg-width: ' + Math.max(2, shareValue) + '%" data-agent="' + escapeHtml(row.label) + '" data-value="' + escapeHtml(value) + '" data-share="' + escapeHtml(formatPct(shareValue)) + '">' +
                    '<span class="hbar-seg__label">' + escapeHtml(row.label) + '</span><span class="hbar-seg__pct">' + escapeHtml(formatPct(shareValue)) + '</span></div>';
            }).join(''));
        }

        function valueOf(row, key) {
            return typeof key === 'function' ? Number(key(row) || 0) : Number(row[key] || 0);
        }

        function updateAgentEfficiency(allResp, deepResp) {
            var table = document.getElementById('dashboard-agent-model-efficiency-table');
            if (table && allResp && Array.isArray(allResp.rows)) {
                var tbody = table.querySelector('tbody');
                if (tbody) {
                    setChartMarkup(tbody, allResp.rows.map(efficiencyRowHtml).join(''));
                }
            }
            var detailTable = document.querySelector('section[aria-label="Model Efficiency Detail"] table.data-table tbody');
            if (detailTable && deepResp && Array.isArray(deepResp.rows)) {
                setChartMarkup(detailTable, deepResp.rows.map(efficiencyDetailRowHtml).join(''));
            }
        }

        function efficiencyRowHtml(row) {
            var scope = row.agent === 'claude_code' ? 'claude-code' : row.agent;
            return '<tr class="clickable-row" data-action="go-sessions-agent-model" data-agent="' + escapeHtml(scope) + '" data-model="' + escapeHtml(row.model) + '">' +
                '<td data-sort-value="' + escapeHtml(row.agent) + '"><span class="agent-badge agent-badge--' + escapeHtml(row.agent) + '">' + escapeHtml(row.agent) + '</span></td>' +
                '<td class="mono" data-sort-value="' + escapeHtml(row.model) + '">' + escapeHtml(row.model) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.sessionCount) + '">' + formatNumber(row.sessionCount) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.avgTokensPerSession) + '">' + formatTokens(row.avgTokensPerSession) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.cacheReuseRatio || 0) + '">' + (row.cacheReuseRatio == null ? 'N/A' : formatPct(row.cacheReuseRatio * 100)) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.failedPerSession || 0) + '">' + (row.failedPerSession == null ? '0.0' : row.failedPerSession.toFixed(1)) + '</td></tr>';
        }

        function efficiencyDetailRowHtml(row) {
            var scope = row.agent === 'claude_code' ? 'claude-code' : row.agent;
            return '<tr class="clickable-row" data-action="go-sessions-agent-model" data-agent="' + escapeHtml(scope) + '" data-model="' + escapeHtml(row.model) + '">' +
                '<td class="mono">' + escapeHtml(row.model) + '</td><td class="numeric">' + formatNumber(row.sessionCount) + '</td>' +
                '<td class="numeric">' + formatTokens(row.avgTokensPerSession) + '</td>' +
                '<td class="numeric">' + formatDuration(row.avgDurationSeconds) + '</td>' +
                '<td class="numeric">' + (row.cacheReuseRatio == null ? 'N/A' : formatPct(row.cacheReuseRatio * 100)) + '</td>' +
                '<td class="numeric">' + (row.avgToolsPerSession == null ? '0.0' : row.avgToolsPerSession.toFixed(1)) + '</td>' +
                '<td class="numeric">' + (row.failedPerSession == null ? '0.0' : row.failedPerSession.toFixed(1)) + '</td>' +
                '<td><span class="badge badge-info">API contract</span></td></tr>';
        }

        function renderAll() {
            renderSessionChart();
            renderTokenChart();
            renderPromptChart();
            renderCacheHealthChart();
        }

        renderAll();
        loadDashboardApiData().catch(function(err) {
            console.error('Dashboard API hydration failed:', err.message || err);
        });

        window.renderDashboardCharts = function() {
            renderAll();
        };
    });
})();
