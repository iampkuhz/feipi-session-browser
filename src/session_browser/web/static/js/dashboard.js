/**
 * dashboard.js — Dashboard page behavior for Feipi Session Browser.
 *
 * 职责：
 *   - Agent scope 切换（URL 重载）
 *   - 时间粒度切换（URL 重载）
 *   - 图表渲染（Session Trend、Token Trend、Prompt Activity Trend、
 *     Token Trend by Composition、Cache Health、Model Mix、Tool Distribution）
 *   - 图表 tooltip hover/focus
 *   - Info 按钮 popover
 *   - All Agents 行点击切换 scope
 *   - View Sessions 跳转
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
            text: '当前 scope 下出现过 session 的 project key 去重数。二级指标：Active 24h（最近 24 小时有 session event 的项目数）、Active 7d（最近 7 天有 session event 的项目数）、New 7d（最近 7 天首次出现的项目数）。'
        },
        'sessions': {
            title: 'Sessions',
            text: '当前 scope 下已索引 session 总数。二级指标：Today（今日 session 数）、7d Avg（最近 7 天日均 session 数）、Median Duration（session 持续时间中位数）、Avg Rounds（平均每 session 轮数）。'
        },
        'total-tokens': {
            title: 'Total Tokens',
            text: 'Fresh + Cache Read + Cache Write + Output 的合计。二级指标分别展示四类 token 的绝对量。'
        },
        'prompt-activity': {
            title: 'Prompt Activity',
            text: '用户发起输入数量，按 user message 事件计数。二级指标：Assistant Turns（assistant message 总数）、Tool Calls（tool call 总数）、Prompts / Session（User Prompts / Sessions）。'
        },
        'cache-read-ratio': {
            title: 'Cache Read Ratio',
            text: 'Cache Read / Input-side Tokens，其中 Input-side = Fresh + Cache Read + Cache Write。二级指标：Eligible Sessions（Input-side > 0 的 session 数）、P50 Session Ratio（per-session cache read ratio 中位数）、Low-read Sessions（cache read ratio < 20% 的 session 数）。'
        },
        'failed-tools': {
            title: 'Failed Tools',
            text: '执行失败的工具调用次数。二级指标：Failure Rate（Failed Tools / Tool Calls）、Affected Sessions（failed > 0 的 session 数）、Repeated Failure Sessions（failed > 1 的 session 数）。'
        },
        'chart-sessions': {
            title: 'Session Trend',
            text: '纵向柱状图展示 session volume。All agents 下按 agent 分段堆叠（Claude Code、Qoder、Codex）。单 agent 下使用单一颜色。'
        },
        'chart-tokens': {
            title: 'Token Trend',
            text: '折线图展示 total tokens 趋势。All agents 下 tooltip 展示三个 agent 的 token 贡献值和占比。单 agent 下展示四类 token 分段。'
        },
        'chart-prompts': {
            title: 'Prompt Activity Trend',
            text: '纵向柱状图展示 user-initiated inputs。All agents 下按 agent 分段堆叠。'
        },
        'chart-composition': {
            title: 'Token Trend by Composition',
            text: '堆叠面积图展示 Fresh、Cache Read、Cache Write、Output 四类 token 随时间的变化。'
        },
        'chart-cache': {
            title: 'Cache Health',
            text: '单折线图展示 Cache Read Ratio (0%-100%)。红色三角标记 Fresh spike 异常点。'
        },
        'model-mix': {
            title: 'Model Mix',
            text: '横向柱状图展示当前 agent 下各模型的 token 分布。'
        },
        'tool-dist': {
            title: 'Tool Distribution',
            text: '横向柱状图展示各工具调用频率。'
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
        var popoverLeft = Math.min(window.innerWidth - 320, rect.left);
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
        var centerX = rect.left + rect.width / 2 + window.scrollX;
        var leftPos = centerX - tooltipWidth / 2;
        if (leftPos < 8) leftPos = 8;
        if (leftPos + tooltipWidth > window.innerWidth - 8) leftPos = window.innerWidth - tooltipWidth - 8;
        infoHoverTooltip.style.setProperty('--tooltip-top', (rect.bottom + 6 + window.scrollY) + 'px');
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
 * dashboard-charts.js — Chart rendering for Dashboard.
 * Reads data from JSON data blocks injected by Jinja2 template.
 */
(function() {
    'use strict';

    document.addEventListener('DOMContentLoaded', function() {
        var rawDataEl = document.getElementById('dashboard-graph-data');
        var promptDataEl = document.getElementById('dashboard-prompt-data');
        var rawData = rawDataEl ? JSON.parse(rawDataEl.textContent || '[]') : [];
        var promptRawData = promptDataEl ? JSON.parse(promptDataEl.textContent || '[]') : [];

        if (!rawData.length && !promptRawData.length) return;

        /* ── Utility functions ─────────────────────────────────── */

        function weekKey(dateStr) {
            var d = new Date(dateStr);
            var jan1 = new Date(d.getFullYear(), 0, 1);
            var dayOfYear = Math.floor((d - jan1) / 86400000);
            var weekNum = Math.floor(dayOfYear / 7) + 1;
            return d.getFullYear() + '-W' + String(weekNum).padStart(2, '0');
        }

        function monthKey(dateStr) { return dateStr.substring(0, 7); }

        function aggregateByWeek(data, fields) {
            var map = {}, order = [];
            data.forEach(function(d) {
                var key = weekKey(d.date);
                if (!map[key]) { map[key] = { date: key }; order.push(key); }
                var row = map[key];
                fields.forEach(function(f) { row[f] = (row[f] || 0) + (d[f] || 0); });
            });
            return order.map(function(k) { return map[k]; });
        }

        function aggregateByMonth(data, fields) {
            var map = {}, order = [];
            data.forEach(function(d) {
                var key = monthKey(d.date);
                if (!map[key]) { map[key] = { date: key + '-01' }; order.push(key); }
                var row = map[key];
                fields.forEach(function(f) { row[f] = (row[f] || 0) + (d[f] || 0); });
            });
            return order.map(function(k) { return map[k]; });
        }

        function getGrain() {
            var el = document.querySelector('.grain-control__btn.is-active');
            return el ? (el.getAttribute('data-grain') || 'day') : 'day';
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
            var fieldList = fields || getTrendFields();
            if (grain === 'week') return aggregateByWeek(sliced, fieldList);
            if (grain === 'month') return aggregateByMonth(sliced, fieldList);
            return sliced;
        }

        function getTrendFields() {
            return ['claude_count', 'codex_count', 'qoder_count', 'total_count',
                    'total_tokens', 'fresh_input_tokens', 'cache_read_tokens',
                    'cache_write_tokens', 'output_tokens', 'tool_calls', 'failed_tools'];
        }

        function getPromptFields() {
            return ['claude_prompts', 'codex_prompts', 'qoder_prompts', 'total_prompts'];
        }

        function formatDisplayDate(dateStr) {
            var grain = getGrain();
            if (!dateStr) return '';
            if (grain === 'week') {
                var parts = dateStr.split('-W');
                return parts.length > 1 ? 'W' + parts[1] : dateStr.substring(5);
            }
            if (grain === 'month') return dateStr.substring(5, 7);
            return dateStr.substring(5);
        }

        function formatTokens(n) {
            if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
            if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
            if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
            return String(n);
        }

        function formatNumber(n) {
            if (n == null) return '0';
            return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        }

        /* ── Tooltip builders (3-column grid per common.md) ───── */

        function buildSessionTooltip(label, d) {
            var html = '<div class="dashboard-tooltip">';
            html += '<div class="tooltip-date">' + label + '</div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--claude"></i><span class="tooltip-label">Claude Code</span><b class="tooltip-value">' + (d.claude_count || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--qoder"></i><span class="tooltip-label">Qoder</span><b class="tooltip-value">' + (d.qoder_count || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--codex"></i><span class="tooltip-label">Codex</span><b class="tooltip-value">' + (d.codex_count || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + (d.total_count || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--red"></i><span class="tooltip-label">Failed-tool sessions</span><b class="tooltip-value">' + (d.failed_tools || 0) + '</b></div>';
            html += '</div>';
            return html;
        }

        function buildTokenTooltip(label, d) {
            var html = '<div class="dashboard-tooltip">';
            html += '<div class="tooltip-date">' + label + '</div>';
            var fresh = d.fresh_input_tokens || d.input_tokens || 0;
            var read = d.cache_read_tokens || 0;
            var write = d.cache_write_tokens || 0;
            var out = d.output_tokens || 0;
            var total = d.total_tokens || (fresh + read + write + out);
            var ratio = (fresh + read + write) > 0 ? (read / (fresh + read + write) * 100).toFixed(1) + '%' : 'N/A';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--fresh"></i><span class="tooltip-label">Fresh</span><b class="tooltip-value">' + formatTokens(fresh) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--read"></i><span class="tooltip-label">Cache Read</span><b class="tooltip-value">' + formatTokens(read) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--write"></i><span class="tooltip-label">Cache Write</span><b class="tooltip-value">' + formatTokens(write) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--out"></i><span class="tooltip-label">Output</span><b class="tooltip-value">' + formatTokens(out) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + formatTokens(total) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--read"></i><span class="tooltip-label">Cache Read Ratio</span><b class="tooltip-value">' + ratio + '</b></div>';
            html += '</div>';
            return html;
        }

        function buildPromptTooltip(label, d) {
            var html = '<div class="dashboard-tooltip">';
            html += '<div class="tooltip-date">' + label + '</div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--claude"></i><span class="tooltip-label">Claude Code</span><b class="tooltip-value">' + (d.claude_prompts || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--qoder"></i><span class="tooltip-label">Qoder</span><b class="tooltip-value">' + (d.qoder_prompts || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--codex"></i><span class="tooltip-label">Codex</span><b class="tooltip-value">' + (d.codex_prompts || 0) + '</b></div>';
            html += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + (d.total_prompts || 0) + '</b></div>';
            html += '</div>';
            return html;
        }

        /* ── Chart renderers ───────────────────────────────────── */

        function renderSessionChart() {
            var container = document.getElementById('trend-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_count || 0; })) || 1;
            var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
            var yHtml = '<div class="y-axis-label">Y-axis: Sessions (count)</div><div class="y-axis">' + yTicks.map(function(v) { return '<span>' + v + '</span>'; }).join('') + '</div>';

            var plotBars = '';
            data.forEach(function(d) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = (d.total_count / maxVal) * 100;
                var tc = d.total_count || 1;
                var claudePct = (d.claude_count || 0) / tc * 100;
                var qoderPct = (d.qoder_count || 0) / tc * 100;
                var codexPct = (d.codex_count || 0) / tc * 100;
                var tip = buildSessionTooltip(dateStr, d);
                plotBars += '<div class="bar" style="--h:' + pctH + '%"><div class="bar-stack">';
                if (d.codex_count > 0) plotBars += '<span class="seg-codex" style="height:' + codexPct + '%"></span>';
                if (d.claude_count > 0) plotBars += '<span class="seg-claude" style="height:' + claudePct + '%"></span>';
                if (d.qoder_count > 0) plotBars += '<span class="seg-qoder" style="height:' + qoderPct + '%"></span>';
                plotBars += '</div>' + tip + '</div>';
            });
            var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';

            var step = Math.max(Math.floor(data.length / 8), 1);
            var xLabels = data.map(function(d, i) {
                return '<span>' + (i % step === 0 ? formatDisplayDate(d.date) : '') + '</span>';
            }).join('');
            var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels + '</div>';

            container.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
        }

        function renderTokenChart() {
            var container = document.getElementById('token-trend-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_tokens || 0; })) || 1;
            var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
            var yHtml = '<div class="y-axis-label">Y-axis: Total Tokens (tokens)</div><div class="y-axis">' + yTicks.map(function(v) { return '<span>' + formatTokens(v) + '</span>'; }).join('') + '</div>';

            var plotBars = '';
            data.forEach(function(d) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = (d.total_tokens / maxVal) * 100;
                var tip = buildTokenTooltip(dateStr, d);
                plotBars += '<div class="bar bar--line" style="--h:' + pctH + '%">' + tip + '</div>';
            });
            var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';

            var step = Math.max(Math.floor(data.length / 8), 1);
            var xLabels = data.map(function(d, i) {
                return '<span>' + (i % step === 0 ? formatDisplayDate(d.date) : '') + '</span>';
            }).join('');
            var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels + '</div>';

            container.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
        }

        function renderPromptChart() {
            var container = document.getElementById('prompt-activity-chart');
            if (!container) return;
            var data = applyScope(promptRawData, getPromptFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

            var maxVal = Math.max.apply(null, data.map(function(d) { return d.total_prompts || 0; })) || 1;
            var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
            var yHtml = '<div class="y-axis-label">Y-axis: User Prompts (count)</div><div class="y-axis">' + yTicks.map(function(v) { return '<span>' + v + '</span>'; }).join('') + '</div>';

            var plotBars = '';
            data.forEach(function(d) {
                var dateStr = formatDisplayDate(d.date);
                var pctH = (d.total_prompts / maxVal) * 100;
                var tc = d.total_prompts || 1;
                var claudePct = (d.claude_prompts || 0) / tc * 100;
                var qoderPct = (d.qoder_prompts || 0) / tc * 100;
                var codexPct = (d.codex_prompts || 0) / tc * 100;
                var tip = buildPromptTooltip(dateStr, d);
                plotBars += '<div class="bar" style="--h:' + pctH + '%"><div class="bar-stack">';
                if (d.codex_prompts > 0) plotBars += '<span class="seg-codex" style="height:' + codexPct + '%"></span>';
                if (d.claude_prompts > 0) plotBars += '<span class="seg-claude" style="height:' + claudePct + '%"></span>';
                if (d.qoder_prompts > 0) plotBars += '<span class="seg-qoder" style="height:' + qoderPct + '%"></span>';
                plotBars += '</div>' + tip + '</div>';
            });
            var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';

            var step = Math.max(Math.floor(data.length / 8), 1);
            var xLabels = data.map(function(d, i) {
                return '<span>' + (i % step === 0 ? formatDisplayDate(d.date) : '') + '</span>';
            }).join('');
            var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels + '</div>';

            container.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
        }

        /* ── Token Trend by Composition (stacked bars) ─────────── */

        function renderCompositionChart() {
            var container = document.getElementById('token-composition-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

            var maxVal = 0;
            data.forEach(function(d) {
                var total = (d.fresh_input_tokens||0) + (d.cache_read_tokens||0) + (d.cache_write_tokens||0) + (d.output_tokens||0);
                if (total > maxVal) maxVal = total;
            });
            if (!maxVal) { container.innerHTML = '<p class="chart-empty">该时间窗口无 token 数据。</p>'; return; }

            var yTicks = [maxVal, Math.round(2/3*maxVal), Math.round(1/3*maxVal), 0];
            var yHtml = '<div class="y-axis-label">Y-axis: Tokens (tokens)</div><div class="y-axis">' + yTicks.map(function(v) { return '<span>' + formatTokens(v) + '</span>'; }).join('') + '</div>';

            var plotBars = '';
            data.forEach(function(d) {
                var dateStr = formatDisplayDate(d.date);
                var fresh = d.fresh_input_tokens || 0;
                var read = d.cache_read_tokens || 0;
                var write = d.cache_write_tokens || 0;
                var out = d.output_tokens || 0;
                var total = fresh + read + write + out;
                var pctH = (total / maxVal) * 100;

                var fPct = total > 0 ? (fresh / total * 100) : 0;
                var rPct = total > 0 ? (read / total * 100) : 0;
                var wPct = total > 0 ? (write / total * 100) : 0;
                var oPct = total > 0 ? (out / total * 100) : 0;

                var tip = '<div class="dashboard-tooltip"><div class="tooltip-date">' + dateStr + '</div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--fresh"></i><span class="tooltip-label">Fresh</span><b class="tooltip-value">' + formatTokens(fresh) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--read"></i><span class="tooltip-label">Cache Read</span><b class="tooltip-value">' + formatTokens(read) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--write"></i><span class="tooltip-label">Cache Write</span><b class="tooltip-value">' + formatTokens(write) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--out"></i><span class="tooltip-label">Output</span><b class="tooltip-value">' + formatTokens(out) + '</b></div>';
                tip += '<div class="tooltip-row" style="border-top:1px solid #334155;margin-top:4px;padding-top:4px"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Total</span><b class="tooltip-value">' + formatTokens(total) + '</b></div>';
                tip += '</div>';

                plotBars += '<div class="bar" style="--h:' + pctH + '%"><div class="bar-stack">';
                if (fresh > 0) plotBars += '<span class="seg-claude" style="height:' + fPct + '%"></span>';
                if (read > 0) plotBars += '<span class="seg-codex" style="height:' + rPct + '%"></span>';
                if (write > 0) plotBars += '<span class="seg-qoder" style="height:' + wPct + '%"></span>';
                if (out > 0) plotBars += '<span class="seg-claude" style="height:' + oPct + '%;opacity:0.7"></span>';
                plotBars += '</div>' + tip + '</div>';
            });
            var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';

            var step = Math.max(Math.floor(data.length / 8), 1);
            var xLabels = data.map(function(d, i) {
                return '<span>' + (i % step === 0 ? formatDisplayDate(d.date) : '') + '</span>';
            }).join('');
            var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels + '</div>';

            container.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
        }

        /* ── Cache Health (line chart) ────────────────────────── */

        function renderCacheHealthChart() {
            var container = document.getElementById('cache-health-chart');
            if (!container) return;
            var data = applyScope(rawData, getTrendFields());
            if (!data.length) { container.innerHTML = '<p class="chart-empty">该时间窗口无数据。</p>'; return; }

            // Compute ratios and spikes
            var ratios = [];
            var spikes = [];
            var freshVals = [];
            data.forEach(function(d) {
                var inp = (d.fresh_input_tokens||0) + (d.cache_read_tokens||0) + (d.cache_write_tokens||0);
                var ratio = inp > 0 ? (d.cache_read_tokens||0) / inp * 100 : null;
                ratios.push(ratio);
                freshVals.push(d.fresh_input_tokens || 0);
            });

            // Compute spike threshold
            var nonZeroFresh = freshVals.filter(function(v) { return v > 0; });
            var spikeThreshold = null;
            if (nonZeroFresh.length >= 3) {
                var sorted = nonZeroFresh.slice().sort(function(a,b){return a-b;});
                var mid = sorted.length >> 1;
                var median = sorted.length % 2 ? sorted[mid] : (sorted[mid-1] + sorted[mid]) / 2;
                var devs = nonZeroFresh.map(function(v){return Math.abs(v - median);}).sort(function(a,b){return a-b;});
                var mad = devs.length % 2 ? devs[mid] : (devs[mid-1] + devs[mid]) / 2;
                spikeThreshold = Math.max(1.8 * median, median + 2 * mad);
            }

            for (var fi = 0; fi < data.length; fi++) {
                if (spikeThreshold && freshVals[fi] > spikeThreshold) {
                    spikes.push(fi);
                }
            }

            var yHtml = '<div class="y-axis-label">Y-axis: Cache Read Ratio (0-100%)</div><div class="y-axis"><span>100%</span><span>75%</span><span>50%</span><span>25%</span><span>0%</span></div>';

            var plotBars = '';
            data.forEach(function(d, i) {
                var dateStr = formatDisplayDate(d.date);
                var ratio = ratios[i];
                var pctH = ratio !== null ? ratio : 0;
                var isSpike = spikes.indexOf(i) >= 0;

                var tip = '<div class="dashboard-tooltip"><div class="tooltip-date">' + dateStr + '</div>';
                if (ratio !== null) {
                    tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--read"></i><span class="tooltip-label">Cache Read Ratio</span><b class="tooltip-value">' + ratio.toFixed(1) + '%</b></div>';
                }
                var inp = (d.fresh_input_tokens||0) + (d.cache_read_tokens||0) + (d.cache_write_tokens||0);
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--total"></i><span class="tooltip-label">Input-side</span><b class="tooltip-value">' + formatTokens(inp) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--fresh"></i><span class="tooltip-label">Fresh</span><b class="tooltip-value">' + formatTokens(d.fresh_input_tokens||0) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--read"></i><span class="tooltip-label">Cache Read</span><b class="tooltip-value">' + formatTokens(d.cache_read_tokens||0) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--write"></i><span class="tooltip-label">Cache Write</span><b class="tooltip-value">' + formatTokens(d.cache_write_tokens||0) + '</b></div>';
                tip += '<div class="tooltip-row"><i class="tooltip-dot tooltip-dot--red"></i><span class="tooltip-label">Fresh Spike</span><b class="tooltip-value">' + (isSpike ? 'Yes' : 'No') + '</b></div>';
                tip += '</div>';

                var spikeMarker = isSpike ? '<span style="position:absolute;top:0;left:50%;transform:translateX(-50%);color:#ef4444;font-size:10px;line-height:1;">&#9650;</span>' : '';
                plotBars += '<div class="bar bar--line" style="--h:' + pctH + '%">' + spikeMarker + tip + '</div>';
            });
            var plotHtml = '<div class="plot" style="--n:' + data.length + '">' + plotBars + '</div>';

            var step = Math.max(Math.floor(data.length / 8), 1);
            var xLabels = data.map(function(d, i) {
                return '<span>' + (i % step === 0 ? formatDisplayDate(d.date) : '') + '</span>';
            }).join('');
            var xHtml = '<div class="x-axis" style="--n:' + data.length + '">' + xLabels + '</div>';

            container.innerHTML = '<div class="chart">' + yHtml + plotHtml + xHtml + '</div>';
        }

        /* ── Initial render ────────────────────────────────────── */

        renderSessionChart();
        renderTokenChart();
        renderPromptChart();
        renderCompositionChart();
        renderCacheHealthChart();

        /* ── Public API for external re-render ─────────────────── */

        window.renderDashboardCharts = function() {
            renderSessionChart();
            renderTokenChart();
            renderPromptChart();
            renderCompositionChart();
            renderCacheHealthChart();
        };
    });
})();
