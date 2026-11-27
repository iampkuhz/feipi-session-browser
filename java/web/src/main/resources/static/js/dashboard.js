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

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── State ───────────────────────────────────────────────────` */

    var chartTooltip = null;

    function _cacheElements() {
        chartTooltip = document.getElementById('chartTooltip')
            || document.querySelector('.chart-tooltip');
    }

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Helpers ─────────────────────────────────────────────────` */

    function hideFloating() {
        if (chartTooltip) {
            chartTooltip.setAttribute('aria-hidden', 'true');
            chartTooltip.classList.remove('is-visible');
            chartTooltip.hidden = true;
        }
    }

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Agent scope selector → URL reload ─────────────────────` */

    function agentScopeUrl(scope) {
        var params = new URLSearchParams(window.location.search);
        if (scope === 'all') {
            params.delete('agent');
        } else {
            params.set('agent', scope);
        }
        params.delete('page');
        var query = params.toString();
        return window.location.pathname + (query ? '?' + query : '');
    }

    function dashboardScope(agent) {
        return agent === 'claude_code' ? 'claude-code' : agent;
    }

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Time grain control → URL reload ───────────────────────` */

    function handleGrain(grain) {
        var params = new URLSearchParams(window.location.search);
        params.set('grain', grain);
        var url = window.location.pathname + '?' + params.toString();
        window.location.href = url;
    }

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Main document-level click delegation ──────────────────` */

    document.addEventListener('click', function (event) {
        var target = event.target;
        if (target.closest && !event.defaultPrevented && event.button === 0
            && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey
            && !target.closest('a, button, details, input, select, textarea, label')
            && !window.getSelection().toString()) {
            var row = target.closest('tr[data-drilldown]');
            var link = row && row.querySelector('a[data-drilldown-link]');
            if (link) {
                window.location.assign(link.href);
                return;
            }
        }
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
            window.location.href = agentScopeUrl(button.getAttribute('data-scope'));
            return;
        }
        if (action === 'grain' && hasGrain) {
            event.preventDefault();
            handleGrain(button.getAttribute('data-grain'));
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

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Window events ─────────────────────────────────────────` */

    window.addEventListener('resize', hideFloating);
    window.addEventListener('scroll', hideFloating, true);

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Keyboard: Escape closes popovers ──────────────────────` */

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' || event.key === 'Esc') {
            hideFloating();
        }
    });

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Public API ────────────────────────────────────────────` */

    window.DashboardPage = {
        openSettings: null,
        closeSettings: null,
        hideFloating: hideFloating
    };

    /* 中文说明：维护当前前端样式或交互约束，原注释作为代码上下文保留：`── Init ──────────────────────────────────────────────────` */

    _cacheElements();

    // Dashboard 图表与表格由同一批资源 API 填充。
    document.addEventListener('DOMContentLoaded', function() {
        var trends = {
            sessions: { rows: sessionTrendRows },
            tokens: { rows: tokenTrendRows },
            prompts: { rows: promptTrendRows },
            'cache-health': { rows: cacheHealthRows }
        };

        var AGENTS = [
            { key: 'claude_code', scope: 'claude-code', label: 'Claude Code', countKey: 'claude_count', promptKey: 'claude_prompts', dot: 'claude' },
            { key: 'qoder', scope: 'qoder', label: 'Qoder', countKey: 'qoder_count', promptKey: 'qoder_prompts', dot: 'qoder' },
            { key: 'codex', scope: 'codex', label: 'Codex', countKey: 'codex_count', promptKey: 'codex_prompts', dot: 'codex' }
        ];
        var TOKEN_LAYERS = [
            { key: 'fresh_input_tokens', token: 'fresh', cls: 'fresh', label: 'Fresh' },
            { key: 'cache_read_tokens', token: 'cacheRead', cls: 'read', label: 'Cache Read' },
            { key: 'cache_write_tokens', token: 'cacheWrite', cls: 'write', label: 'Cache Write' },
            { key: 'output_tokens', token: 'output', cls: 'out', label: 'Output' }
        ];

        /** 解析 UTC cohort 日期；未知日期不回退为今天，也不使用浏览器本地时区。 */
        function utcDateKey(dateStr) {
            if (typeof dateStr !== 'string' || !/^\d{4}-\d{2}-\d{2}(?:$|T)/.test(dateStr)) return '';
            var value = dateStr;
            if (value.length > 10 && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) value += 'Z';
            var date = new Date(value);
            if (isNaN(date.getTime())) return '';
            var key = date.toISOString().substring(0, 10);
            return dateStr.length === 10 && key !== dateStr ? '' : key;
        }

        function weekKey(dateStr) {
            if (/^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$/.test(dateStr || '')) return dateStr;
            var key = utcDateKey(dateStr);
            if (!key) return '';
            var d = new Date(key + 'T00:00:00Z');
            var tmp = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
            var day = tmp.getUTCDay() || 7;
            tmp.setUTCDate(tmp.getUTCDate() + 4 - day);
            var yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
            var week = Math.ceil((((tmp - yearStart) / 86400000) + 1) / 7);
            return tmp.getUTCFullYear() + '-W' + String(week).padStart(2, '0');
        }

        function monthKey(dateStr) {
            return utcDateKey(dateStr).substring(0, 7);
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
                if (d.observed) map[key].observed = true;
                fields.forEach(function(f) {
                    if (knownNumber(d[f])) map[key][f] = (map[key][f] || 0) + d[f];
                });
                Object.keys(d).forEach(function(f) {
                    if (f === 'provenance' || /_provenance$/.test(f)) {
                        map[key][f] = TokenProvenance.merge(map[key][f], d[f]);
                    } else if (/_cache_metric_known$/.test(f)) {
                        map[key][f] = map[key][f] !== false && d[f] === true;
                    }
                });
            });
            return order.sort().map(function(k) {
                var point = map[k];
                if (!point.observed) fields.forEach(function(f) { point[f] = 0; });
                return point;
            });
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

        /** 日历窗口以当前 UTC 桶为终点，而不是最后一个有数据日。 */
        function calendarWindow() {
            var today = new Date().toISOString().substring(0, 10);
            var start = new Date(today + 'T00:00:00Z');
            var grain = getGrain();
            if (grain === 'week') {
                start.setUTCDate(start.getUTCDate() - ((start.getUTCDay() + 6) % 7) - 19 * 7);
            } else if (grain === 'month') {
                start.setUTCDate(1);
                start.setUTCMonth(start.getUTCMonth() - 11);
            } else {
                start.setUTCDate(start.getUTCDate() - 29);
            }
            return { start: start.toISOString().substring(0, 10), end: today };
        }

        function windowCohorts(data, fields) {
            var grain = getGrain();
            var window = calendarWindow();
            var now = Date.now();
            var dated = data.map(function(point) {
                if (typeof point.date === 'string' && point.date.length > 10) {
                    var instant = point.date;
                    if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(instant)) instant += 'Z';
                    if (Date.parse(instant) > now) return null;
                }
                var date = utcDateKey(point.date);
                return date && date >= window.start && date <= window.end
                    ? Object.assign({}, point, { date: date, observed: true }) : null;
            }).filter(function(point) { return point !== null; });
            if (!dated.length) return [];
            // 空日期只表示该日没有开始会话；不伪造 token/cache 测量来源。
            var present = {};
            dated.forEach(function(point) { present[point.date] = true; });
            var cursor = new Date(window.start + 'T00:00:00Z');
            while (cursor.toISOString().substring(0, 10) <= window.end) {
                var key = cursor.toISOString().substring(0, 10);
                if (!present[key]) dated.push({ date: key });
                cursor.setUTCDate(cursor.getUTCDate() + 1);
            }
            if (grain === 'week') return aggregateByKey(dated, fields, weekKey);
            if (grain === 'month') return aggregateByKey(dated, fields, monthKey, function(k) { return k + '-01'; });
            return aggregateByKey(dated, fields, utcDateKey);
        }

        function getSessionFields() {
            return ['claude_count', 'codex_count', 'qoder_count', 'total_count', 'failed_tools'];
        }

        function getTokenFields() {
            return [
                'total_tokens', 'fresh_input_tokens', 'cache_read_tokens', 'cache_write_tokens', 'output_tokens'
            ];
        }

        function knownNumber(value) {
            return typeof value === 'number' && Number.isFinite(value) && value >= 0;
        }

        function getPromptFields() {
            var fields = ['claude_prompts', 'codex_prompts', 'qoder_prompts',
                'total_prompts', 'assistant_turns', 'tool_calls'];
            ['', 'claude_code_', 'codex_', 'qoder_'].forEach(function(prefix) {
                fields.push(prefix + 'measured_user_messages', prefix + 'user_message_sample_count');
            });
            return fields;
        }

        function measuredPromptAverage(point, prefix) {
            prefix = prefix || '';
            var samples = point[prefix + 'user_message_sample_count'];
            var messages = point[prefix + 'measured_user_messages'];
            return samples > 0 && typeof messages === 'number' && Number.isFinite(messages)
                ? messages / samples : null;
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

        function formatCount(n) {
            return knownNumber(n) ? formatNumber(n) : 'N/A';
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

        function formatCacheRatio(value) {
            return TokenProvenance.percent(value).replace(/^(\d+)%$/, '$1.0%');
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

        function setTableBodyMarkup(container, markup) {
            var parsed = new DOMParser().parseFromString('<table><tbody>' + markup + '</tbody></table>', 'text/html');
            var tbody = parsed.querySelector('tbody');
            container.replaceChildren.apply(container, Array.prototype.slice.call(tbody.childNodes));
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
            return '<div class="y-axis' + (extraClass ? ' ' + extraClass : '') + '">' + ticks.map(function(v, i) {
                return '<span style="--tick-position:' + (i / (ticks.length - 1) * 100).toFixed(2) + '%">'
                    + escapeHtml(formatter ? formatter(v) : v) + '</span>';
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
                return '<span data-bucket="' + escapeHtml(d.date) + '" title="' + escapeHtml(d.date + ' UTC') + '">'
                    + (i % step === 0 ? escapeHtml(formatDisplayDate(d.date)) : '') + '</span>';
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
            if (knownNumber(d.total_tokens)) return d.total_tokens;
            var values = TOKEN_LAYERS.map(function(layer) { return d[layer.key]; });
            var total = values.filter(knownNumber).reduce(function(sum, value) { return sum + value; }, 0);
            return total > 0 || values.every(knownNumber) ? total : null;
        }

        function inputSide(d, prefix) {
            return (d[prefix + '_fresh_input_tokens'] || 0) +
                (d[prefix + '_cache_read_tokens'] || 0) +
                (d[prefix + '_cache_write_tokens'] || 0);
        }

        function cacheMetricKnown(d, prefix) {
            return d && d[prefix + '_cache_metric_known'] === true
                && TokenProvenance.measuredInput({ provenance: d[prefix + '_provenance'] });
        }

        function cacheRatio(d, prefix) {
            if (!cacheMetricKnown(d, prefix)) return null;
            var input = inputSide(d, prefix);
            if (!input) return null;
            return (d[prefix + '_cache_read_tokens'] || 0) / input * 100;
        }

        function linePath(data, maxVal, valueFn, xFn, yFn) {
            var parts = [];
            var open = false;
            var resolveX = xFn || xBandCenterPct;
            var resolveY = yFn || function(val) { return yPct(val, maxVal); };
            data.forEach(function(d, i) {
                var val = valueFn(d, i);
                if (val == null || !isFinite(val)) {
                    open = false;
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
            validIndexes.forEach(function(i, position) {
                // A measured bucket needs a marker only when neither adjacent bucket is measured.
                if (validIndexes[position - 1] === i - 1 || validIndexes[position + 1] === i + 1) return;
                var val = valueFn(data[i], i);
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
                var value = d[agent.countKey];
                if (activeScope !== 'all' && !value) return;
                rows.push(tooltipRow(agent.dot, agent.label, formatCount(value),
                    knownNumber(value) ? share(value, d.total_count || 0) : ''));
            });
            rows.push(tooltipRow('total', 'Total', formatCount(d.total_count), share(d.total_count || 0, rangeTotal), 'tooltip-row--total'));
            var delta = previous && knownNumber(previous.total_count) && knownNumber(d.total_count)
                ? (d.total_count > previous.total_count ? '+' : '') + formatNumber(d.total_count - previous.total_count) : 'N/A';
            rows.push(tooltipRow('total', 'Delta', delta, ''));
            return tooltipShell(label, rows);
        }

        function tokenTooltipData(label, d, rangeTotal, previous) {
            var total = totalTokens(d);
            var prevTotal = previous ? plottableTokenTotal(previous) : null;
            var delta = prevTotal == null || plottableTokenTotal(d) == null ? 'N/A' : formatSignedTokens(total - prevTotal);
            return { tokens: trendMeasurement(d), title: label, providerOnly: true,
                scale: '总量占当前时间窗口：' + (plottableTokenTotal(d) == null ? 'N/A' : share(total, rangeTotal)) + '；与前桶差值：' + delta };
        }

        function trendMeasurement(d) {
            return { total: totalTokens(d), fresh: d.fresh_input_tokens, cacheRead: d.cache_read_tokens,
                cacheWrite: d.cache_write_tokens, output: d.output_tokens, provenance: d.provenance };
        }

        function plottableTokenTotal(d) {
            var total = totalTokens(d);
            var precision = TokenProvenance.state(trendMeasurement(d));
            return total > 0 || (total === 0 && (precision === 'provider_reported' || precision === 'estimated')) ? total : null;
        }

        function promptTotal(point) {
            if (!point.observed) return 0;
            return knownNumber(point.total_prompts)
                && (point.total_prompts > 0 || point.user_message_sample_count > 0) ? point.total_prompts : null;
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
            var totalSessions = trendPoint && trendPoint.total_count;
            var average = measuredPromptAverage(d);
            var totalAverage = average === null ? 'N/A' : average.toFixed(1);

            rows.push(tooltipSection('User Prompts (bars)'));
            scopedAgents.forEach(function(agent) {
                var prompts = d[agent.promptKey];
                var samples = d[agent.key + '_user_message_sample_count'];
                var starts = trendPoint && trendPoint[agent.countKey];
                var measured = knownNumber(prompts) && (prompts > 0 || samples > 0 || starts === 0 || !d.observed);
                rows.push(tooltipRow(agent.dot, agent.label, measured ? formatNumber(prompts) : 'N/A',
                    measured ? share(prompts, totalPrompts) : ''));
            });
            rows.push(tooltipRow('total', 'Total User Prompts',
                promptTotal(d) == null ? 'N/A' : formatNumber(totalPrompts), '', 'tooltip-row--total'));

            rows.push(tooltipSection('Avg Prompts / Session (line)'));
            rows.push(tooltipLineRow('prompt-average', 'Overall', totalAverage,
                '/ measured session · samples ' + formatNumber(d.user_message_sample_count) + ' / ' + formatCount(totalSessions) + ' cohort'));
            if (activeScope === 'all') {
                scopedAgents.forEach(function(agent) {
                    var sessions = trendPoint && trendPoint[agent.countKey];
                    var agentAverage = measuredPromptAverage(d, agent.key + '_');
                    var perSession = agentAverage === null ? 'N/A' : agentAverage.toFixed(1);
                    rows.push(tooltipLineRow(agent.dot, agent.label, perSession,
                        '/ measured session · samples ' + formatNumber(d[agent.key + '_user_message_sample_count'])
                        + ' / ' + formatCount(sessions) + ' cohort'));
                });
            }

            rows.push(tooltipSection('Auxiliary'));
            rows.push(tooltipRow('total', 'Assistant Messages', formatCount(d.assistant_turns), ''));
            rows.push(tooltipRow('total', 'Tool Calls', formatCount(d.tool_calls), ''));
            return tooltipShell(label, rows);
        }

        function renderSessionChart(container, data) {
            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_count || 0; })) || 1;
            var rangeTotal = data.reduce(function(sum, d) { return sum + (d.total_count || 0); }, 0);
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatNumber);

            var bars = '';
            var activeScope = getActiveScope();
            data.forEach(function(d, i) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = ((d.total_count || 0) / maxVal) * 100;
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

        function renderTokenChart(container, data) {
            var maxVal = Math.max.apply(null, data.map(totalTokens)) || 1;
            var rangeTotal = data.reduce(function(sum, d) { return sum + totalTokens(d); }, 0);
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatTokens);

            var cumulative = data.map(function() { return 0; });
            var paths = '';
            TOKEN_LAYERS.forEach(function(layer) {
                var upper = [];
                var lower = [];
                function closeArea() {
                    if (!upper.length) return;
                    if (upper.length === 1) {
                        var width = 28 / data.length;
                        upper = [[upper[0][0] - width, upper[0][1]], [upper[0][0] + width, upper[0][1]]];
                        lower = [[lower[0][0] - width, lower[0][1]], [lower[0][0] + width, lower[0][1]]];
                    }
                    var coords = upper.concat(lower.reverse()).map(function(p) { return p[0].toFixed(2) + ',' + p[1].toFixed(2); });
                    paths += '<path class="area-layer area-layer--' + layer.cls + '" d="M ' + coords.join(' L ') + ' Z"></path>';
                    upper = [];
                    lower = [];
                }
                data.forEach(function(d, i) {
                    var value = d[layer.key] || 0;
                    var measurement = TokenProvenance.state(trendMeasurement(d), layer.token);
                    if (plottableTokenTotal(d) == null || !knownNumber(d[layer.key])
                        || (!value && !['provider_reported', 'estimated'].includes(measurement))) {
                        closeArea();
                        return;
                    }
                    var x = xBandCenterPct(i, data.length);
                    var low = cumulative[i];
                    var high = low + value;
                    lower.push([x, yPct(low, maxVal)]);
                    upper.push([x, yPct(high, maxVal)]);
                    cumulative[i] = high;
                });
                closeArea();
            });
            paths += '<path class="area-total-line" d="' + linePath(data, maxVal, plottableTokenTotal) + '"></path>';

            var targets = '';
            data.forEach(function(d, i) {
                var total = plottableTokenTotal(d);
                var x = xBandCenterPct(i, data.length);
                var y = yPct(total, maxVal);
                var tip = tokenTooltipData(formatDisplayDate(d.date), d, rangeTotal, i > 0 ? data[i - 1] : null);
                var edge = edgeClass(i, data.length, 'chart-hover-target');
                targets += '<span class="chart-hover-target' + (edge ? ' ' + edge : '') + '" tabindex="0" data-token-breakdown="' + escapeHtml(JSON.stringify(tip)) + '" style="--point-x:' + x.toFixed(2) + '%;--point-y:' + y.toFixed(2) + '%"><span class="chart-hover-guide"></span>'
                    + (total == null ? '' : '<span class="area-point"></span>') + '</span>';
            });

            var legend = TOKEN_LAYERS.map(function(layer) {
                var value = observedSum(data, function(d) { return d[layer.key]; });
                var p = data.reduce(function(previous, d) { return d.provenance ? TokenProvenance.merge(previous, d.provenance) : previous; }, null);
                var tokens = { provenance: p };
                tokens[layer.token] = value;
                return '<span class="chart-legend__item"><i class="chart-legend__dot chart-legend__dot--' + layer.cls + '"></i>' +
                    escapeHtml(layer.label) + ' ' + escapeHtml(TokenProvenance.amount(tokens, layer.token, formatTokens)) + '</span>';
            }).join('');

            setChartMarkup(container, '<div class="chart">' + yHtml +
                '<div class="plot plot--area" style="--n:' + data.length + '"><svg class="area-plot line-plot--bar-aligned" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + paths + '</svg><div class="line-targets line-targets--bar-aligned">' + targets + '</div></div>' +
                xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>');
            TokenProvenance.bindTooltips(container);
        }

        function renderPromptChart(container, data, trendData) {
            var trendByDate = {};
            trendData.forEach(function(d) { trendByDate[d.date] = d; });
            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_prompts || 0; })) || 1;
            var avgValues = data.map(function(d) {
                return measuredPromptAverage(d);
            });
            var avgCandidates = avgValues.filter(function(v) { return v != null && isFinite(v); });
            var maxAvg = avgCandidates.length ? Math.max.apply(null, avgCandidates) : 1;
            if (!maxAvg || !isFinite(maxAvg)) maxAvg = 1;
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatNumber);
            var yRightHtml = yAxisHtml([maxAvg, 2 / 3 * maxAvg, 1 / 3 * maxAvg, 0], function(v) { return Number(v || 0).toFixed(1); }, 'y-axis--right');

            var bars = '';
            data.forEach(function(d, i) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = ((d.total_prompts || 0) / maxVal) * 100;
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
                rows.push(tooltipLineRow(item.line, item.label, formatCacheRatio(ratio), item.prefix === highlightPrefix ? 'selected' : ''));
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
            var tokens = { fresh: d[highlightPrefix + '_fresh_input_tokens'], cacheRead: d[highlightPrefix + '_cache_read_tokens'],
                cacheWrite: d[highlightPrefix + '_cache_write_tokens'], provenance: d[highlightPrefix + '_provenance'] };
            rows.push(tooltipRow('fresh', 'Fresh', TokenProvenance.value(tokens, 'fresh', formatTokens), ''));
            rows.push(tooltipRow('read', 'Cache Read', TokenProvenance.value(tokens, 'cacheRead', formatTokens), ''));
            rows.push(tooltipRow('write', 'Cache Write', TokenProvenance.value(tokens, 'cacheWrite', formatTokens), ''));
            rows.push(tooltipRow('total', 'Measurement', TokenProvenance.note(tokens), ''));
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

        function cacheSeries(highlightPrefix) {
            var specs = [
                { prefix: 'average', label: 'Average' },
                { prefix: 'claude_code', label: 'Claude Code' },
                { prefix: 'qoder', label: 'Qoder' },
                { prefix: 'codex', label: 'Codex' }
            ];
            return highlightPrefix === 'average' ? specs : specs.filter(function(spec) { return spec.prefix === highlightPrefix; });
        }

        function renderCacheHealthChart(container, data, highlightPrefix, specs) {
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

        var dashboardSnapshot = window.IndexSnapshot.create();
        var dashboardParts = [];
        var renderQueued = false;

        function scheduleRender() {
            if (renderQueued) return;
            renderQueued = true;
            queueMicrotask(function () {
                renderQueued = false;
                renderAll();
            });
        }

        function trendJob(key, url) {
            var trend = trends[key];
            return {
                key: 'dashboard/trends/' + key,
                url: url,
                validate: function (part) {
                    if (!part || !Array.isArray(part.points) || part.points.some(function (point) {
                        return !point || typeof point !== 'object' || Array.isArray(point);
                    })) {
                        throw new Error('Invalid trend response');
                    }
                },
                apply: function (part) {
                    trend.data = trend.rows(part);
                    trend.failure = null;
                    scheduleRender();
                },
                error: function (error, retry) {
                    trend.data = undefined;
                    trend.failure = { message: error.message, retry: retry };
                    scheduleRender();
                }
            };
        }

        function loadDashboardApiData() {
            if (!window.fetch) return Promise.resolve(null);
            var params = currentApiParams();
            var activeScope = getActiveScope();
            var paths = ['summary', 'trends/sessions', 'trends/tokens', 'trends/prompts', 'trends/cache-health', 'agents/contribution', 'agents/efficiency',
                'agents/' + encodeURIComponent(activeScope === 'all' ? 'claude-code' : activeScope) + '/deep-dive'];
            return dashboardSnapshot.load(paths.map(function (path, index) {
                var url = '/api/dashboard/' + path + '?' + params.toString();
                if (path.indexOf('trends/') === 0) return trendJob(path.slice(7), url);
                return { key: 'dashboard/' + path, url: url, apply: function (part) {
                    dashboardParts[index] = part;
                    if (index === 0) updateDashboardSummary(part);
                    if (index === 5) updateAgentContribution(part);
                    if (index === 6 || index === 7) updateAgentEfficiency(dashboardParts[6], dashboardParts[7]);
                    scheduleRender();
                } };
            }));
        }

        function updateDashboardSummary(summary) {
            if (!summary) return;
            setKpiValue('Sessions', formatNumber(summary.sessionCount));
            setKpiValue('Projects', formatNumber(summary.projectCount));
            setKpiValue('Total Tokens', TokenProvenance.total(summary.tokens, formatTokens), summary.tokens);
            setKpiValue('Prompt Activity', formatNumber(summary.userMessages));
            setKpiValue('Failed Tools', formatNumber(summary.failedTools));
            setKpiValue('Cache Read Ratio', TokenProvenance.ratio(summary.tokens, summary.cacheReadRatio), summary.tokens);
            applyCacheReadStatistics(summary.cacheReadStatistics, summary.tokens);
            applyMessageStatistics(summary);
        }

        function applyMessageStatistics(summary) {
            [
                { label: 'Prompts / Session', role: 'user', samples: 'userMessageSampleCount', average: 'avgUserMessagesPerSession' },
                { label: 'Avg Assistant Messages', role: 'assistant', samples: 'assistantMessageSampleCount', average: 'avgAssistantMessagesPerSession' }
            ].forEach(function(metric) {
                var row = Array.from(document.querySelectorAll('.metric-card__secondary-row')).find(function(item) {
                    var label = item.querySelector('.metric-card__secondary-label');
                    return label && label.textContent.trim() === metric.label;
                });
                if (!row) return;
                var samples = summary[metric.samples];
                var average = summary[metric.average];
                var validSamples = typeof samples === 'number' && Number.isFinite(samples) && samples >= 0;
                var value = row.querySelector('.metric-card__secondary-value');
                if (value) value.textContent = validSamples && samples > 0
                    && typeof average === 'number' && Number.isFinite(average) && average >= 0 ? average.toFixed(1) : 'N/A';
                var description = metric.role + ' 消息测量样本 ' + (validSamples ? formatNumber(samples) : 'N/A')
                    + ' / ' + formatNumber(summary.sessionCount) + '；当前 scope：'
                    + (summary.filters && summary.filters.agent || getActiveScope())
                    + '。仅这些已测消息数会话参与均值，保留实测 0；内容或 usage 可用不代表消息已测，不代表完整真人历史。';
                row.setAttribute('data-tooltip-def', description);
                row.setAttribute('aria-label', metric.label + '：' + description);
            });
        }

        function applyCacheReadStatistics(statistics, tokens) {
            var card = Array.from(document.querySelectorAll('.metric-card--kpi')).find(function(item) {
                var label = item.querySelector('.metric-card__label');
                return label && label.textContent.trim() === 'Cache Read Ratio';
            });
            if (!card) return;
            var validBasis = statistics && statistics.basis === 'provider_reported_input';
            function count(key) {
                var value = validBasis && statistics[key];
                return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? formatNumber(value) : 'N/A';
            }
            var median = validBasis && Number(statistics.eligibleSessions) > 0 ? statistics.p50SessionRatio : null;
            var values = [count('eligibleSessions'), typeof median === 'number' && median >= 0 && median <= 1 ? formatPct(median * 100) : 'N/A', count('lowReadSessions')];
            card.querySelectorAll('.metric-card__secondary-value').forEach(function(value, index) {
                value.textContent = values[index] || 'N/A';
            });
            var note = document.createElement('p');
            note.setAttribute('data-cache-measurement', '');
            note.textContent = validBasis ? 'Cache ratio uses cache-read tokens divided by reported input tokens. Session statistics use ' + count('eligibleSessions')
                + ' sessions with positive provider-reported input. Excluded: ' + count('excludedSessions') + ' sessions.'
                : 'Cache session distribution not reported by API; measurable subset is unknown.';
            TokenProvenance.attach(card, tokens, note);
        }

        function setKpiValue(label, value, tokens) {
            var cards = document.querySelectorAll('.metric-card--kpi');
            for (var i = 0; i < cards.length; i++) {
                var labelEl = cards[i].querySelector('.metric-card__label');
                if (!labelEl || labelEl.textContent.trim() !== label) continue;
                var valueEl = cards[i].querySelector('.metric-card__value');
                if (valueEl) valueEl.textContent = value;
                if (tokens && label !== 'Cache Read Ratio') TokenProvenance.attach(cards[i], tokens);
                if (tokens && label === 'Total Tokens') {
                    cards[i].querySelectorAll('.metric-card__secondary-row').forEach(function(row) {
                        var secondaryLabel = row.querySelector('.metric-card__secondary-label');
                        var key = { Fresh: 'fresh', 'Cache Read': 'cacheRead', 'Cache Write': 'cacheWrite', Output: 'output' }[secondaryLabel ? secondaryLabel.textContent.trim() : ''];
                        var value = row.querySelector('.metric-card__secondary-value');
                        if (value && key) value.textContent = TokenProvenance.value(tokens, key, formatTokens);
                    });
                }
                if (label === 'Cache Read Ratio' && !TokenProvenance.measuredInput(tokens || {})) {
                    cards[i].querySelectorAll('.metric-card__secondary-value').forEach(function(value) {
                        value.textContent = 'N/A';
                    });
                    cards[i].querySelectorAll('.metric-card__badge').forEach(function(badge) {
                        badge.textContent = 'N/A';
                        badge.removeAttribute('data-kpi-badge-tooltip');
                        badge.removeAttribute('data-tooltip-def');
                    });
                }
            }
        }

        function sessionTrendRows(resp) {
            return (resp && resp.points || []).map(function(point) {
                return {
                    date: point.date, total_count: point.totalCount, claude_count: point.claudeCount,
                    codex_count: point.codexCount, qoder_count: point.qoderCount,
                    failed_tools: point.failedTools
                };
            });
        }

        function tokenTrendRows(resp) {
            return (resp && resp.points || []).map(function(point) {
                var tokens = point.tokens || {};
                return {
                    date: point.date, provenance: tokens.provenance,
                    fresh_input_tokens: tokens.fresh, cache_read_tokens: tokens.cacheRead,
                    cache_write_tokens: tokens.cacheWrite, output_tokens: tokens.output,
                    total_tokens: tokens.total
                };
            });
        }

        function promptTrendRows(resp) {
            return (resp && resp.points || []).map(function(point) {
                var row = {
                    date: point.date,
                    claude_prompts: point.claudePrompts,
                    codex_prompts: point.codexPrompts,
                    qoder_prompts: point.qoderPrompts,
                    total_prompts: point.totalPrompts,
                    assistant_turns: point.assistantTurns,
                    tool_calls: point.toolCalls
                };
                [['', ''], ['claude_code_', 'claude'], ['codex_', 'codex'], ['qoder_', 'qoder']].forEach(function(pair) {
                    var apiPrefix = pair[1];
                    var messages = point[apiPrefix ? apiPrefix + 'MeasuredUserMessages' : 'measuredUserMessages'];
                    var samples = point[apiPrefix ? apiPrefix + 'UserMessageSampleCount' : 'userMessageSampleCount'];
                    var known = typeof messages === 'number' && Number.isFinite(messages) && messages >= 0
                        && typeof samples === 'number' && Number.isInteger(samples) && samples >= 0;
                    // 缺少任一权重字段的旧 mock 不是实测零，也不从 raw prompt/session 数猜测覆盖。
                    row[pair[0] + 'measured_user_messages'] = known ? messages : 0;
                    row[pair[0] + 'user_message_sample_count'] = known ? samples : 0;
                });
                return row;
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
            if (!tuple) return;
            var p = tuple.provenance || tuple.ratio && tuple.ratio.provenance || {};
            var values = [tuple.fresh, tuple.cacheRead, tuple.cacheWrite];
            // CacheInputDto's empty agent placeholder is not a missing measurement from a real cohort.
            if (values.every(function(value) { return value === 0; }) && p.estimationMethod === ''
                && ['freshInput', 'cacheRead', 'cacheWrite', 'output'].every(function(key) { return p[key] === 'unknown'; })
                && ['unknownSessionCount', 'estimatedSessionCount', 'unavailableSessionCount'].every(function(key) { return p[key] === 0; })) return;
            target[prefix + '_fresh_input_tokens'] = tuple.fresh;
            target[prefix + '_cache_read_tokens'] = tuple.cacheRead;
            target[prefix + '_cache_write_tokens'] = tuple.cacheWrite;
            target[prefix + '_provenance'] = p;
            target[prefix + '_cache_metric_known'] = values.every(knownNumber)
                && TokenProvenance.measuredInput({ provenance: target[prefix + '_provenance'] })
                && (Boolean(tuple.ratio && tuple.ratio.value != null) || inputSide(target, prefix) === 0);
        }

        function observedSum(points, value) {
            return points.reduce(function(sum, point) {
                var amount = point.observed ? value(point) : null;
                return knownNumber(amount) ? (sum || 0) + amount : sum;
            }, null);
        }

        function updateChartStats(sessions, tokens, prompts, caches, prefix) {
            var latestSession = sessions[sessions.length - 1];
            var latestToken = tokens[tokens.length - 1];
            var latestPrompt = prompts[prompts.length - 1];
            var latestCache = caches[caches.length - 1];
            var rangeTokens = tokens.reduce(function(total, point) {
                if (point.provenance) total.provenance = TokenProvenance.merge(total.provenance, point.provenance);
                return total;
            }, { total: observedSum(tokens, plottableTokenTotal), provenance: null });
            var sessionTotal = function(point) { return point.total_count; };
            setTrendStat('sessions', 'latest-sessions', 'Latest', formatCount(latestSession && latestSession.total_count));
            setTrendStat('sessions', 'range-total-sessions', 'Range total', formatCount(observedSum(sessions, sessionTotal)));
            setTrendStat('tokens', 'latest-tokens', 'Latest', latestToken
                ? TokenProvenance.amount(trendMeasurement(latestToken), 'total', formatTokens) : 'N/A');
            setTrendStat('tokens', 'range-total-tokens', 'Range total', TokenProvenance.amount(rangeTokens, 'total', formatTokens));
            setTrendStat('prompts', 'latest-prompts', 'Latest', formatCount(latestPrompt && promptTotal(latestPrompt)));
            setTrendStat('prompts', 'range-total-prompts', 'Range total', formatCount(observedSum(prompts, promptTotal)));
            var tokenChart = document.getElementById('token-trend-chart');
            TokenProvenance.attach(tokenChart && tokenChart.parentElement, rangeTokens);
            var latestRatio = cacheRatio(latestCache, prefix);
            var ratios = caches.map(function(point) { return cacheRatio(point, prefix); })
                .filter(function(value) { return value !== null; });
            var cacheChart = document.getElementById('cache-health-chart');
            TokenProvenance.attach(cacheChart && cacheChart.parentElement,
                { provenance: latestCache && latestCache[prefix + '_provenance'] });
            setTrendStat('cache-health', 'latest-ratio', 'Latest ratio', formatCacheRatio(latestRatio));
            setTrendStat('cache-health', 'lowest-ratio', 'Lowest ratio', formatCacheRatio(ratios.length ? Math.min.apply(null, ratios) : null));
            var evidence = document.querySelector('[data-trend-first-evidence]');
            function first(key, points, value) {
                var trend = trends[key];
                if (trendLoading(trend)) return '加载中';
                if (trend.failure) return '加载失败';
                var match = points.find(function(point) { return point.observed && knownNumber(value(point)); });
                return match ? match.date : '窗口内无证据';
            }
            if (evidence) evidence.textContent = '窗口内首个有数据的桶：Session ' + first('sessions', sessions, sessionTotal)
                + ' · Prompt ' + first('prompts', prompts, promptTotal)
                + ' · Token ' + first('tokens', tokens, plottableTokenTotal)
                + ' · Cache ' + first('cache-health', caches, function(point) { return cacheRatio(point, prefix); });
            var window = calendarWindow();
            document.querySelectorAll('[data-stat]').forEach(function(el) {
                el.setAttribute('aria-description', 'UTC session-start cohort ' + window.start + ' — ' + window.end
                    + '; ' + getGrain() + ' buckets; 当前桶未完成。Lowest ratio 仅比较窗口内可计算桶。');
            });
            updateCohortBadges(sessions, tokens, prompts, caches, prefix);
        }

        function updateCohortBadges(sessions, tokens, prompts, caches, prefix) {
            var latest = sessions[sessions.length - 1] || {};
            var previous = sessions[sessions.length - 2] || {};
            var latestToken = tokens[tokens.length - 1];
            var previousToken = tokens[tokens.length - 2];
            var latestPrompt = prompts[prompts.length - 1];
            var previousPrompt = prompts[prompts.length - 2];
            var latestCache = caches[caches.length - 1];
            var previousCache = caches[caches.length - 2];
            var description = 'UTC ' + getGrain() + ' session-start cohort：当前桶对比紧邻前桶；当前桶未完成。会话整段累计，不是事件实际发生日。';
            function setBadge(label, value, tone) {
                var target = Array.from(document.querySelectorAll('.metric-card--kpi')).find(function(card) {
                    var name = card.querySelector('.metric-card__label');
                    return name && name.textContent.trim() === label;
                });
                var badge = target && target.querySelector('.metric-card__badge');
                if (!target) return;
                if (!badge) {
                    if (value === 'N/A') return;
                    var primary = target.querySelector('.metric-card__value');
                    if (!primary) return;
                    badge = document.createElement('span');
                    badge.className = 'metric-card__badge metric-card__tooltip-target';
                    badge.tabIndex = 0;
                    primary.parentElement.appendChild(badge);
                }
                badge.textContent = value;
                ['positive', 'negative', 'neutral'].forEach(function(name) {
                    badge.classList.toggle('metric-card__badge--' + name, name === tone);
                });
                var detail = description;
                if (label === 'Total Tokens') detail += ' 仅比较四段完整 provider 测量桶；估算/部分/未知不推断涨跌。';
                if (label === 'Cache Read Ratio') detail += ' 输入三段均实测且分母大于零才可比较；缺测不跳桶回溯。';
                if (label === 'Prompt Activity' || label === 'Failed Tools') detail += ' 仅已观测事件计数，不代表完整源覆盖。';
                badge.setAttribute('data-kpi-badge-tooltip', label);
                badge.setAttribute('data-tooltip-def', detail);
                badge.setAttribute('aria-label', label + ' badge：' + detail);
            }
            function delta(label, current, prior, inverted) {
                if (!knownNumber(current) || !knownNumber(prior)) { setBadge(label, 'N/A', 'neutral'); return; }
                var value = current - prior;
                setBadge(label, (value > 0 ? '+' : '') + formatNumber(value),
                    value === 0 ? 'neutral' : ((value > 0) !== inverted ? 'positive' : 'negative'));
            }
            var sessionKnown = sessions.some(function(point) { return point.observed && knownNumber(point.total_count); });
            var promptKnown = prompts.some(function(point) { return point.observed && promptTotal(point) !== null; });
            var failuresKnown = sessions.some(function(point) { return point.observed && knownNumber(point.failed_tools); });
            delta('Sessions', sessionKnown ? latest.total_count : null, previous.total_count, false);
            delta('Prompt Activity', promptKnown && latestPrompt ? promptTotal(latestPrompt) : null,
                previousPrompt && promptTotal(previousPrompt), false);
            delta('Failed Tools', failuresKnown ? latest.failed_tools : null, previous.failed_tools, true);
            var tokenKnown = [latestToken, previousToken].every(function(point) {
                return point && TOKEN_LAYERS.every(function(layer) {
                    return knownNumber(point[layer.key]) && TokenProvenance.state(trendMeasurement(point), layer.token) === 'provider_reported';
                });
            });
            var previousTokens = previousToken && totalTokens(previousToken);
            var percent = tokenKnown && previousTokens > 0
                ? (totalTokens(latestToken) - previousTokens) / previousTokens * 100 : null;
            setBadge('Total Tokens', percent === null ? 'N/A' : (percent > 0 ? '+' : '') + percent.toFixed(1) + '%', 'neutral');
            var currentRatio = cacheRatio(latestCache, prefix);
            var priorRatio = cacheRatio(previousCache, prefix);
            var pp = currentRatio !== null && priorRatio !== null ? currentRatio - priorRatio : null;
            setBadge('Cache Read Ratio', pp === null ? 'N/A' : (pp >= 0 ? '+' : '') + pp.toFixed(1) + 'pp',
                pp === null || pp === 0 ? 'neutral' : (pp > 0 ? 'positive' : 'negative'));
        }

        function setTrendStat(key, name, label, text) {
            var el = document.querySelector('[data-stat="' + name + '"]');
            if (el) el.textContent = label + ': ' + (trendLoading(trends[key]) ? 'Loading…' : text);
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
            setTableBodyMarkup(tbody, resp.rows.map(function(row) {
                return '<tr class="agent-row" data-drilldown>' +
                    '<td data-sort-value="' + escapeHtml(row.label) + '"><a data-drilldown-link class="agent-badge agent-badge--' + escapeHtml(row.agent) +
                    '" href="' + escapeHtml(agentScopeUrl(dashboardScope(row.agent))) + '">' + escapeHtml(row.label) + '</a></td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.sessionCount) + '">' + formatNumber(row.sessionCount) + ' <span class="muted">· ' + formatPct(row.sessionShare) + '</span></td>' +
                    '<td class="numeric token-cell" data-sort-value="' + escapeHtml(row.tokens && row.tokens.total) + '">' + escapeHtml(TokenProvenance.total(row.tokens, formatTokens)) + ' <span class="muted">· ' + formatPct(row.tokenShare) + '</span></td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.prompts) + '">' + formatNumber(row.prompts) + ' <span class="muted">· ' + formatPct(row.promptShare) + '</span></td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.projectCount) + '">' + formatNumber(row.projectCount) + '</td>' +
                    '<td class="numeric" data-sort-value="' + escapeHtml(row.failedTools) + '">' + formatNumber(row.failedTools) + ' failed <span class="muted">· ' + (Number(row.prompts) > 0 ? (Number(row.failedTools || 0) / Number(row.prompts)).toFixed(2) : 'N/A') + ' / prompt</span></td></tr>';
            }).join(''));
            Array.from(tbody.rows).forEach(function(tr, index) {
                TokenProvenance.attach(tr.querySelector('.token-cell'), resp.rows[index].tokens);
            });
        }

        function renderContributionBar(name, rows, valueKey, shareKey, formatter) {
            var bar = document.querySelector('[data-hbar="' + name + '"]');
            if (!bar) return;
            setChartMarkup(bar, rows.filter(function(row) { return valueOf(row, valueKey) > 0; }).map(function(row) {
                var value = valueOf(row, valueKey);
                var shareValue = Math.min(100, Math.max(0, Number(row[shareKey]) || 0));
                return '<div class="hbar-seg hbar-seg--' + escapeHtml(row.agent) + '" style="--seg-width: ' + shareValue + '%" data-agent="' + escapeHtml(row.label) + '" data-value="' + escapeHtml(value) + '" data-share="' + escapeHtml(formatPct(shareValue)) + '">' +
                    '</div>';
            }).join(''));
            var legend = bar.parentElement.querySelector('.hbar-legend');
            if (legend) {
                legend.replaceChildren();
                rows.forEach(function(row) {
                    var item = document.createElement('div');
                    item.className = 'hbar-legend__item';
                    var dot = document.createElement('span');
                    dot.className = 'hbar-legend__dot hbar-legend__dot--' + row.agent;
                    dot.setAttribute('aria-hidden', 'true');
                    var displayValue = name === 'token-share' ? TokenProvenance.total(row.tokens, formatter) : formatter(valueOf(row, valueKey));
                    item.append(dot, document.createTextNode(row.label + ' · ' + displayValue + ' · ' + formatPct(row[shareKey] || 0)));
                    if (name === 'token-share') TokenProvenance.attach(item, row.tokens);
                    legend.append(item);
                });
            }
        }

        function valueOf(row, key) {
            return typeof key === 'function' ? Number(key(row) || 0) : Number(row[key] || 0);
        }

        function updateAgentEfficiency(allResp, deepResp) {
            var table = document.getElementById('dashboard-agent-model-efficiency-table');
            if (table && allResp && Array.isArray(allResp.rows)) {
                var tbody = table.querySelector('tbody');
                if (tbody) {
                    setTableBodyMarkup(tbody, allResp.rows.map(efficiencyRowHtml).join(''));
                    attachEfficiencyProvenance(tbody, allResp.rows, 3);
                }
            }
            var modelMixTable = document.querySelector('section[data-chart-card="model-mix"] table.data-table tbody');
            if (modelMixTable && deepResp && Array.isArray(deepResp.rows)) {
                setTableBodyMarkup(modelMixTable, deepResp.rows.length
                    ? deepResp.rows.map(modelMixRowHtml).join('')
                    : '<tr><td colspan="4"><div class="empty-state" role="status" aria-live="polite">' +
                        '<h2 class="empty-state__title">No model mix data</h2>' +
                        '<p class="empty-state__text">No model rows are available for this agent and time range.</p>' +
                        '</div></td></tr>');
                attachEfficiencyProvenance(modelMixTable, deepResp.rows, 2);
            }
            var detailTable = document.querySelector('section[aria-label="Model Efficiency Detail"] table.data-table tbody');
            if (detailTable && deepResp && Array.isArray(deepResp.rows)) {
                setTableBodyMarkup(detailTable, deepResp.rows.map(efficiencyDetailRowHtml).join(''));
                attachEfficiencyProvenance(detailTable, deepResp.rows, 7);
            }
        }

        function attachEfficiencyProvenance(body, rows, column) {
            Array.from(body.rows).forEach(function(tr, index) {
                if (rows[index]) {
                    var samples = efficiencySamples(rows[index]);
                    var note;
                    if (samples) {
                        note = document.createElement('p');
                        note.textContent = samples;
                    }
                    var cell = tr.cells[column];
                    TokenProvenance.attach(cell, { provenance: rows[index].provenance }, note);
                    if (column === 7 && !cell.firstChild) cell.textContent = 'Provider reported';
                }
            });
        }

        function efficiencyTokenMean(row) {
            if (typeof row.tokenSampleCount !== 'number') {
                return TokenProvenance.total({ total: row.avgTokensPerSession, provenance: row.provenance }, formatTokens);
            }
            return row.tokenSampleCount > 0 ? formatTokens(row.avgTokensPerSession) : 'N/A';
        }

        function efficiencySamples(row) {
            if (typeof row.contentSampleCount !== 'number') return '';
            return 'Samples: wall ' + row.durationSampleCount + '/' + row.sessionCount
                + ', complete provider tokens ' + row.tokenSampleCount + '/' + row.sessionCount
                + ', content ' + row.contentSampleCount + '/' + row.sessionCount;
        }

        function modelDrilldownLink(row) {
            var query = new URLSearchParams({ agent: row.agent, model: row.model });
            return '<a data-drilldown-link href="/sessions?' + escapeHtml(query.toString()) + '">' + escapeHtml(row.model) + '</a>';
        }

        function modelMixRowHtml(row) {
            return '<tr class="clickable-row" data-drilldown>' +
                '<td class="mono">' + modelDrilldownLink(row) + '</td>' +
                '<td class="numeric">' + formatNumber(row.sessionCount) + '</td>' +
                '<td class="numeric">' + escapeHtml(efficiencyTokenMean(row)) + '</td>' +
                '<td class="numeric">' + escapeHtml(TokenProvenance.ratio(null, { value: row.cacheReuseRatio, provenance: row.provenance })) + '</td></tr>';
        }

        function efficiencyRowHtml(row) {
            return '<tr class="clickable-row" data-drilldown>' +
                '<td data-sort-value="' + escapeHtml(row.agent) + '"><span class="agent-badge agent-badge--' + escapeHtml(row.agent) + '">' + escapeHtml(row.agent) + '</span></td>' +
                '<td class="mono" data-sort-value="' + escapeHtml(row.model) + '">' + modelDrilldownLink(row) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.sessionCount) + '">' + formatNumber(row.sessionCount) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.avgTokensPerSession) + '">' + escapeHtml(efficiencyTokenMean(row)) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.cacheReuseRatio || 0) + '">' + escapeHtml(TokenProvenance.ratio(null, { value: row.cacheReuseRatio, provenance: row.provenance })) + '</td>' +
                '<td class="numeric" data-sort-value="' + escapeHtml(row.failedPerSession == null ? '' : row.failedPerSession) + '">' + (row.failedPerSession == null ? 'N/A' : row.failedPerSession.toFixed(1)) + '</td></tr>';
        }

        function efficiencyDetailRowHtml(row) {
            return '<tr class="clickable-row" data-drilldown>' +
                '<td class="mono">' + modelDrilldownLink(row) + '</td><td class="numeric">' + formatNumber(row.sessionCount) + '</td>' +
                '<td class="numeric">' + escapeHtml(efficiencyTokenMean(row)) + '</td>' +
                '<td class="numeric">' + (row.durationSampleCount === 0 ? 'N/A' : formatDuration(row.avgDurationSeconds)) + '</td>' +
                '<td class="numeric">' + escapeHtml(TokenProvenance.ratio(null, { value: row.cacheReuseRatio, provenance: row.provenance })) + '</td>' +
                '<td class="numeric">' + (row.contentSampleCount === 0 || row.avgToolsPerSession == null ? 'N/A' : row.avgToolsPerSession.toFixed(1)) + '</td>' +
                '<td class="numeric">' + (row.failedPerSession == null ? 'N/A' : row.failedPerSession.toFixed(1)) + '</td>' +
                '<td></td></tr>';
        }

        function trendLoading(trend) {
            return trend.retrying || (!trend.failure && !trend.data);
        }

        function renderTrend(key, points, value, render, dependency) {
            var trend = trends[key];
            var state = trendLoading(trend) ? 'loading' : trend.failure ? 'error' : !points.length ? 'empty'
                : points.some(function(point) { return point.observed && knownNumber(value(point)); }) ? 'ready' : 'unavailable';
            var container = document.querySelector('[data-dashboard-chart="' + key + '"]');
            if (!container) return [];
            var previousState = container.getAttribute('data-trend-state');
            container.setAttribute('data-trend-state', state);
            container.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
            if (state === 'ready') {
                var windowEnd = calendarWindow().end;
                // 保留无关卡片的交互节点，避免其他卡片重试时丢失键盘焦点。
                if (previousState !== state || !container.firstChild || trend.displayedData !== trend.data
                    || trend.displayedDependency !== dependency || trend.displayedWindowEnd !== windowEnd) {
                    render(container, points);
                    trend.displayedData = trend.data;
                    trend.displayedDependency = dependency;
                    trend.displayedWindowEnd = windowEnd;
                }
                return points;
            }
            var failure = trend.failure;
            if (state === previousState && container.firstChild && failure === trend.displayedFailure) return [];
            trend.displayedFailure = failure;
            var message = document.createElement('p');
            message.className = 'chart-empty';
            message.setAttribute('role', state === 'error' ? 'alert' : 'status');
            if (state === 'error') {
                var path = 'dashboard/trends/' + key;
                message.setAttribute('data-snapshot-error', path);
                message.textContent = 'Unable to load ' + path + ': ' + failure.message + '. ';
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'btn';
                button.textContent = 'Retry';
                button.addEventListener('click', function () {
                    var restoreFocus = document.activeElement === button;
                    button.disabled = true;
                    trend.retrying = true;
                    renderAll();
                    Promise.resolve().then(failure.retry).catch(function (error) {
                        console.error('Dashboard trend retry failed:', error);
                    }).finally(function () {
                        trend.retrying = false;
                        renderAll();
                        if (!restoreFocus || document.activeElement !== document.body || container.closest('[hidden]')) return;
                        var target = container.querySelector('[data-snapshot-error] button') || container;
                        if (target === container) container.tabIndex = -1;
                        target.focus({ preventScroll: true });
                    });
                });
                message.appendChild(button);
            } else {
                message.textContent = {
                    loading: '正在加载趋势数据…',
                    empty: '该时间窗口无数据。',
                    unavailable: '该时间窗口内的记录缺少可用计量。'
                }[state];
            }
            container.replaceChildren(message);
            return [];
        }

        function renderAll() {
            var prefix = scopeToAgentKey(getActiveScope());
            var sessionPoints = windowCohorts(trends.sessions.data || [], getSessionFields());
            var tokenPoints = windowCohorts(trends.tokens.data || [], getTokenFields());
            var promptPoints = windowCohorts(trends.prompts.data || [], getPromptFields());
            var cachePoints = windowCohorts(trends['cache-health'].data || [], getCacheFields());
            var sessions = renderTrend('sessions', sessionPoints, function(point) { return point.total_count; }, renderSessionChart);
            var tokens = renderTrend('tokens', tokenPoints, plottableTokenTotal, renderTokenChart);
            var prompts = renderTrend('prompts', promptPoints, promptTotal, function(container, points) {
                renderPromptChart(container, points, sessions);
            }, sessions.length ? trends.sessions.data : null);
            var cacheSpecs = cacheSeries(prefix);
            var caches = renderTrend('cache-health', cachePoints, function(point) {
                return cacheSpecs.some(function(spec) { return cacheRatio(point, spec.prefix) !== null; }) ? 1 : null;
            }, function(container, points) {
                renderCacheHealthChart(container, points, prefix, cacheSpecs);
            });
            updateChartStats(sessions, tokens, prompts, caches, prefix);
        }

        renderAll();
        loadDashboardApiData().catch(function(err) {
            console.error('Dashboard API hydration failed:', err.message || err);
        });

        window.renderDashboardCharts = function() {
            renderAll();
        };
        window.addEventListener('index-snapshot-restored', renderAll);
    });
})();
