/**
 * dashboard.js — Dashboard page behavior for Feipi Session Browser.
 *
 * 职责：
 *   - Agent scope 切换（URL 重载）
 *   - 时间粒度切换（URL 重载）
 *   - 图表渲染（Session Trend、Token Trend、Prompt Activity Trend、
 *     Cache Health、Model Mix、Tool Distribution）
 *   - 图表 tooltip hover/focus
 *   - Info 按钮 popover
 *   - All Agents 行点击切换 scope
 *
 * 使用 data-action 事件委托，不绑定 inline handler。
 * 不复制 ui_primitives.js 或 view-state.js 已有逻辑。
 */
(function () {
    'use strict';

    /* ── Info copy dictionary ──────────────────────────────────── */

    var INFO_COPY = {
        'projects': {
            title: 'Projects',
            text: '当前 scope 下出现过 session 的 project key 去重数。Badge 显示最近 7 天新出现的项目数；二级指标展示最近 24 小时活跃、最近 7 天活跃和最近 7 天首次出现的项目数。'
        },
        'sessions': {
            title: 'Sessions',
            text: '当前 scope 下已索引 session 总数。Badge 对比当前可见趋势窗口最后两个时间点；二级指标展示今日 session、7 天日均、生命周期中位时长和平均 assistant 轮数。'
        },
        'total-tokens': {
            title: 'Total Tokens',
            text: 'Fresh、Cache Read、Cache Write、Output 的合计。Badge 对比当前可见趋势窗口最后两个时间点；二级指标展示四类 token 的绝对量。'
        },
        'prompt-activity': {
            title: 'Prompt Activity',
            text: '用户发起输入数量，按 user message 事件计数。Badge 对比当前可见趋势窗口最后两个时间点；二级指标展示 assistant turns、tool calls 和每个 session 平均 user prompts。'
        },
        'cache-read-ratio': {
            title: 'Cache Read Ratio',
            text: 'Cache Read / Input-side Tokens，其中 Input-side = Fresh + Cache Read + Cache Write。Badge 对比当前可见趋势窗口最后两个时间点；二级指标展示可计算样本数、session 级中位数和低缓存复用 session 数。'
        },
        'failed-tools': {
            title: 'Failed Tools',
            text: '执行失败的工具结果数量。Badge 对比当前可见趋势窗口最后两个时间点，下降为正向；二级指标展示失败率、受影响 session 数和重复失败 session 数。'
        },
        'chart-sessions': {
            title: 'Session Trend',
            text: '按当前 Day、Week 或 Month 粒度展示 session 数。All agents 下按 Claude Code、Qoder、Codex 堆叠；单 agent 下只显示当前 agent。'
        },
        'chart-tokens': {
            title: 'Token Trend',
            text: '展示 token 总量随时间变化。面积层分别代表 Fresh、Cache Read、Cache Write、Output，折线连接每个时间点的 total tokens。'
        },
        'chart-prompts': {
            title: 'Prompt Activity Trend',
            text: '柱状图展示 User Prompts，右轴折线展示 Avg Prompts / Session。Assistant Turns 和 Tool Calls 只作为 tooltip 辅助信息，不作为主系列。'
        },
        'chart-cache': {
            title: 'Cache Health',
            text: '多折线展示 Average、Claude Code、Qoder、Codex 的 Cache Read Ratio。All agents 高亮 Average；单 agent 高亮当前 agent。Dashboard 只展示聚合趋势，不展示异常标记。'
        },
        'model-mix': {
            title: 'Model Mix',
            text: '圆环图展示当前 agent 下各模型的 token 消耗占比；旁边的表格分别展示 session 占比和 token 占比，方便判断数量贡献与成本贡献是否一致。'
        },
        'tool-dist': {
            title: 'Tool Distribution',
            text: '展示当前 agent 下工具调用分布。当前索引只有聚合 tool-call 数量，若缺少工具名称明细则显示空态。'
        }
    };

    /* ── State ─────────────────────────────────────────────────── */

    var chartTooltip = null;
    var infoPopover = null;
    var infoHoverTooltip = null;
    var infoHoverTimer = null;

    function _cacheElements() {
        infoPopover = document.getElementById('infoPopover');
        chartTooltip = document.getElementById('chartTooltip')
            || document.querySelector('.chart-tooltip');
    }

    /* ── Helpers ───────────────────────────────────────────────── */

    function hideFloating() {
        if (infoPopover) {
            infoPopover.setAttribute('aria-hidden', 'true');
            infoPopover.classList.remove('is-visible');
            infoPopover.hidden = true;
        }
        if (chartTooltip) {
            chartTooltip.setAttribute('aria-hidden', 'true');
            chartTooltip.classList.remove('is-visible');
            chartTooltip.hidden = true;
        }
        hideHoverTooltip();
    }

    function showInfoPopover(button) {
        hideFloating();
        if (!infoPopover) return;

        var infoKey = button.getAttribute('data-info') || button.getAttribute('data-dashboard-info');
        var info = INFO_COPY[infoKey] || { title: 'Info', text: 'No description available.' };

        while (infoPopover.firstChild) infoPopover.removeChild(infoPopover.firstChild);
        var h4 = document.createElement('h4');
        h4.textContent = info.title;
        infoPopover.appendChild(h4);
        var p = document.createElement('p');
        p.textContent = info.text;
        infoPopover.appendChild(p);
        infoPopover.hidden = false;
        infoPopover.setAttribute('aria-hidden', 'false');
        infoPopover.classList.add('is-visible');

        var rect = button.getBoundingClientRect();
        var popoverWidth = Math.min(300, window.innerWidth - 16);
        var popoverLeft = Math.max(8, Math.min(window.innerWidth - popoverWidth - 8, rect.left));
        infoPopover.style.setProperty('--popover-left', popoverLeft + 'px');
        infoPopover.style.setProperty('--popover-top', (rect.bottom + 10) + 'px');
        infoPopover.setAttribute('data-positioned', 'true');
    }

    /* ── Info icon hover tooltip ─────────────────────────────── */

    function createHoverTooltip() {
        var el = document.createElement('div');
        el.className = 'info-hover-tooltip';
        el.setAttribute('aria-hidden', 'true');
        el.hidden = true;
        document.body.appendChild(el);
        return el;
    }

    function showHoverTooltip(button) {
        if (!infoHoverTooltip) infoHoverTooltip = createHoverTooltip();
        var infoKey = button.getAttribute('data-info') || button.getAttribute('data-dashboard-info');
        var info = INFO_COPY[infoKey];
        if (!info) return;

        infoHoverTooltip.textContent = info.text;
        infoHoverTooltip.hidden = false;
        infoHoverTooltip.setAttribute('aria-hidden', 'false');

        var rect = button.getBoundingClientRect();
        var tooltipWidth = infoHoverTooltip.offsetWidth || 200;
        var centerX = rect.left + rect.width / 2;
        var leftPos = centerX - tooltipWidth / 2;
        if (leftPos < 8) leftPos = 8;
        if (leftPos + tooltipWidth > window.innerWidth - 8) leftPos = window.innerWidth - tooltipWidth - 8;
        infoHoverTooltip.style.setProperty('--tooltip-top', (rect.bottom + 6) + 'px');
        infoHoverTooltip.style.setProperty('--tooltip-left', leftPos + 'px');
        infoHoverTooltip.setAttribute('data-positioned', 'true');
    }

    function hideHoverTooltip() {
        if (infoHoverTooltip) {
            infoHoverTooltip.hidden = true;
            infoHoverTooltip.setAttribute('aria-hidden', 'true');
        }
        if (infoHoverTimer) {
            clearTimeout(infoHoverTimer);
            infoHoverTimer = null;
        }
    }

    function initInfoHoverListeners() {
        var infoButtons = document.querySelectorAll('.icon-button--info[data-info]');
        for (var i = 0; i < infoButtons.length; i++) {
            (function(btn) {
                btn.addEventListener('mouseenter', function() {
                    infoHoverTimer = setTimeout(function() { showHoverTooltip(btn); }, 150);
                });
                btn.addEventListener('mouseleave', hideHoverTooltip);
            })(infoButtons[i]);
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

    /* ── Click outside popover closes it ─────────────────────── */

    function handleClickOutsidePopover(event) {
        var target = event.target;
        if (infoPopover && infoPopover.contains(target)) return;
        if (target.closest && target.closest('.icon-button--info')) return;
        hideFloating();
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
        if (!button) { handleClickOutsidePopover(event); return; }

        var action = button.getAttribute('data-action') || '';
        var hasScope = button.hasAttribute('data-scope');
        var hasInfo = button.hasAttribute('data-info') || button.hasAttribute('data-dashboard-info');
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
        if (hasInfo && action !== 'agent-scope' && action !== 'grain') {
            showInfoPopover(button);
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
            if (infoPopover && infoPopover.classList.contains('is-visible')) {
                hideFloating();
                event.preventDefault();
            }
        }
    });

    /* ── Public API ──────────────────────────────────────────── */

    window.DashboardPage = {
        openSettings: null,
        closeSettings: null,
        showInfoPopover: showInfoPopover,
        hideFloating: hideFloating
    };

    /* ── Init ────────────────────────────────────────────────── */

    _cacheElements();
    if (typeof document !== 'undefined' && document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initInfoHoverListeners);
    } else {
        initInfoHoverListeners();
    }
})();


/**
 * dashboard-charts.js - Chart rendering for Dashboard.
 * Reads data from JSON data blocks injected by Jinja2 template.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var rawData = parseJsonBlock('dashboard-graph-data');
        var promptRawData = parseJsonBlock('dashboard-prompt-data');
        var cacheRawData = parseJsonBlock('dashboard-cache-health-data');

        if (!rawData.length && !promptRawData.length && !cacheRawData.length) return;

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

        function parseJsonBlock(id) {
            var el = document.getElementById(id);
            if (!el) return [];
            try {
                var data = JSON.parse(el.textContent || '[]');
                return Array.isArray(data) ? data : [];
            } catch (err) {
                return [];
            }
        }

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

        function cacheRatio(d, prefix) {
            var input = inputSide(d, prefix);
            if (!input) return null;
            return (d[prefix + '_cache_read_tokens'] || 0) / input * 100;
        }

        function linePath(data, maxVal, valueFn, xFn, yFn) {
            var parts = [];
            var open = false;
            var resolveX = xFn || xPct;
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
            data.forEach(function(d, i) {
                var val = valueFn(d, i);
                if (val == null || !isFinite(val)) return;
                var prev = i > 0 ? valueFn(data[i - 1], i - 1) : null;
                var next = i < data.length - 1 ? valueFn(data[i + 1], i + 1) : null;
                var hasPrev = prev != null && isFinite(prev);
                var hasNext = next != null && isFinite(next);
                if (hasPrev || hasNext) return;
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
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

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

            container.innerHTML = '<div class="chart">' + yHtml +
                '<div class="plot" style="--n:' + data.length + '">' + bars + '</div>' +
                xAxisHtml(data) + '</div>';
        }

        function renderTokenChart() {
            var container = document.getElementById('token-trend-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

            var maxVal = Math.max.apply(null, data.map(totalTokens)) || 1;
            if (!maxVal) { container.innerHTML = '<p class="chart-empty">该时间窗口无 token 数据。</p>'; return; }
            var rangeTotal = data.reduce(function(sum, d) { return sum + totalTokens(d); }, 0);
            var yHtml = yAxisHtml([maxVal, Math.round(2 / 3 * maxVal), Math.round(1 / 3 * maxVal), 0], formatTokens);

            var cumulative = data.map(function() { return 0; });
            var paths = '';
            TOKEN_LAYERS.forEach(function(layer) {
                var upper = [];
                var lower = [];
                data.forEach(function(d, i) {
                    var x = xPct(i, data.length);
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
                var x = xPct(i, data.length);
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

            container.innerHTML = '<div class="chart">' + yHtml +
                '<div class="plot plot--area" style="--n:' + data.length + '"><svg class="area-plot" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + paths + '</svg>' + targets + '</div>' +
                xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>';
        }

        function renderPromptChart() {
            var container = document.getElementById('prompt-activity-chart');
            if (!container) return;
            var data = applyScope(promptRawData, getPromptFields());
            var trendData = applyScope(rawData, getTrendFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

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

            container.innerHTML = '<div class="chart chart--dual-axis">' + yHtml +
                '<div class="plot" style="--n:' + data.length + '">' + avgLine + '<div class="prompt-line-markers" aria-hidden="true">' + avgMarkers + '</div>' + bars + '</div>' +
                yRightHtml + xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>';
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
            rows.push(tooltipRow('total', 'Input-side Tokens', formatTokens(input), '', 'tooltip-row--total'));
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
            var data = applyScope(cacheRawData, getCacheFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

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
                paths += '<path class="' + cls + '" d="' + linePath(data, 100, valueFn, null, cacheY) + '"></path>';
                isolatedMarkers += isolatedLineMarkers(data, valueFn, xPct, cacheY, cls);
            });

            var targets = '';
            data.forEach(function(d, i) {
                var ratio = cacheRatio(d, highlightPrefix);
                var y = ratio == null ? cacheY(domain.min) : cacheY(ratio);
                var x = xPct(i, data.length);
                var tip = buildCacheTooltip(formatDisplayDate(d.date), d, highlightPrefix);
                var edge = edgeClass(i, data.length, 'chart-hover-target');
                targets += '<span class="chart-hover-target' + (edge ? ' ' + edge : '') + '" style="--point-x:' + x.toFixed(2) + '%;--point-y:' + y.toFixed(2) + '%"><span class="chart-hover-guide"></span><span class="line-point line-point--' + highlightPrefix + '"></span>' +
                    tip + '</span>';
            });

            var legend = specs.map(function(spec) {
                return '<span class="chart-legend__item"><i class="chart-legend__line chart-legend__line--' + spec.prefix + '"></i>' + escapeHtml(spec.label) + '</span>';
            }).join('');

            container.innerHTML = '<div class="chart chart--cache-health">' + yHtml +
                '<div class="plot plot--line plot--cache-health" style="--n:' + data.length + '">' + gridHtml + '<svg class="line-plot" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' + paths + isolatedMarkers + '</svg>' + targets + '</div>' +
                xAxisHtml(data) + '<div class="chart-legend">' + legend + '</div></div>';
        }

        renderSessionChart();
        renderTokenChart();
        renderPromptChart();
        renderCacheHealthChart();

        window.renderDashboardCharts = function() {
            renderSessionChart();
            renderTokenChart();
            renderPromptChart();
            renderCacheHealthChart();
        };
    });
})();
