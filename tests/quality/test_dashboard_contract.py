"""Dashboard JS/CSS contract 测试。

覆盖：
- dashboard.js 不含旧职责关键字
- dashboard.css 不重定义共享 primitive
- Dashboard 不出现 Dense/Comfortable/Columns/Export/Keyboard shortcuts
- Dashboard 不出现 Hot Sessions & Signals / Context Budget / All Sessions

T-Dashboard-JS-CSS-Contract
"""

from __future__ import annotations

import pytest
import re

_JS_PATH = "src/session_browser/web/static/js/dashboard.js"
_CSS_PATH = "src/session_browser/web/static/css/dashboard.css"
_TEMPLATE_PATH = "src/session_browser/web/templates/dashboard.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


class TestDashboardJSContract:
    """验证 dashboard.js 不含旧职责关键字。"""

    _BANNED_KEYWORDS = [
        "density-toggle",
        "settingsDrawer",
        "settings-drawer",
        "chart-export",
        "chart-detail",
        "chart-copy-link",
        "range-btn",
        "chart-range",
        "open-settings",
        "close-settings",
        "bar--line",
        "Y-axis:",
        "Failed-tool sessions",
    ]

    @pytest.mark.contract_case("DASHBOARD-JS-001")
    @pytest.mark.parametrize("keyword", _BANNED_KEYWORDS)
    def test_js_no_banned_keywords(self, keyword):
        """dashboard.js 不得包含禁止的关键字。"""
        js = _read(_JS_PATH)
        assert keyword not in js,             f"dashboard.js 包含禁止关键字 '{keyword}'"


class TestDashboardCSSContract:
    """验证 dashboard.css 不重定义共享 primitive。"""

    _SHARED_SELECTORS = [
        ".btn {",
        ".btn--primary {",
        ".badge {",
        ".badge--danger {",
        ".badge--warning {",
        ".badge--info {",
        ".data-table {",
        ".tooltip {",
        ".modal {",
    ]

    @pytest.mark.contract_case("DASHBOARD-CSS-001")
    @pytest.mark.parametrize("selector", _SHARED_SELECTORS)
    def test_css_no_shared_selectors(self, selector):
        """dashboard.css 不得重定义共享组件基础样式。"""
        css = _read(_CSS_PATH)
        # Allow comments mentioning shared selectors
        lines = css.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("/*"):
                continue
            if selector in stripped:
                pytest.fail(
                    f"dashboard.css 包含共享选择器 '{selector}' "
                    f"(第 {css.index(selector)+1} 行附近)"
                )

    @pytest.mark.contract_case("DASHBOARD-CSS-002")
    def test_line_and_area_plots_share_marker_coordinate_space(self):
        """折线/面积 SVG 不得比 marker/hover target 多一层横向缩进。"""
        css = _read(_CSS_PATH)
        assert "inset: 0 6px 0 6px" not in css
        assert "width: calc(100% - 12px)" not in css
        assert re.search(
            r"\.line-plot,\s*\.area-plot\s*\{[^}]*inset:\s*0;[^}]*width:\s*100%;",
            css,
            re.S,
        ), "line/area plot 必须使用完整 plot 坐标系"
        bar_aligned = re.search(
            r"\.line-plot--bar-aligned\s*\{(?P<body>[^}]*)\}",
            css,
            re.S,
        )
        assert bar_aligned, "bar-aligned 折线层必须显式声明坐标空间"
        body = bar_aligned.group("body")
        assert "width: auto" not in body, "bar-aligned 折线层不得退回 SVG 1:1 auto 宽度"
        assert "width: calc(100% - var(--plot-x-padding) - var(--plot-x-padding));" in body
        assert "inset-inline-start: var(--plot-x-padding);" in body
        assert "inset-inline-end: auto;" in body

    @pytest.mark.contract_case("DASHBOARD-CSS-003")
    def test_chart_tooltip_renders_above_markers(self):
        """hover tooltip 必须高于其它折线点和 hover target。"""
        css = _read(_CSS_PATH)
        assert re.search(
            r"\.bar:hover,\s*\.chart-hover-target:hover\s*\{[^}]*z-index:\s*130;",
            css,
            re.S,
        ), "hover 的整列必须抬升，避免兄弟节点点位压过 tooltip"
        assert re.search(
            r"\.dashboard-tooltip\s*\{[^}]*z-index:\s*140;",
            css,
            re.S,
        ), "dashboard tooltip 必须处于图表 marker 上层"

    @pytest.mark.contract_case("DASHBOARD-CSS-004")
    def test_prompt_activity_tooltip_uses_line_key(self):
        """折线 tooltip 和 legend 必须使用短虚线 key，而不是圆点。"""
        css = _read(_CSS_PATH)
        assert ".tooltip-line-key" in css
        assert ".tooltip-line-key--prompt-average" in css
        assert ".chart-legend__line--prompt-average" in css
        assert ".line-plot--bar-aligned" in css
        assert ".prompt-line-markers" in css
        assert "--dashboard-prompt-average-color" in css

    @pytest.mark.contract_case("DASHBOARD-CSS-005")
    def test_average_series_uses_neutral_color(self):
        """Average / All agents 颜色必须和 Claude Code 紫色拉开。"""
        css = _read(_CSS_PATH)
        assert "--dashboard-average-color: #111827;" in css
        for selector, prop in [
            (r"\.scope-selector__btn\[data-scope=\"all\"\]\.is-active", "background"),
            (r"\.line-series--average", "stroke"),
            (r"\.line-point--average", "background"),
            (r"\.chart-legend__line--average", "color"),
            (r"\.tooltip-line-key--average", "color"),
        ]:
            pattern = selector + r"\s*\{[^}]*" + prop + r":\s*var\(--dashboard-average-color\);"
            assert re.search(pattern, css, re.S), f"{selector} must use --dashboard-average-color"

        average_blocks = re.findall(
            r"\.(?:line-series|line-point|chart-legend__line|tooltip-line-key)--average\s*\{[^}]*\}",
            css,
            re.S,
        )
        assert average_blocks
        assert all("var(--brand)" not in block and "var(--purple)" not in block for block in average_blocks)

    @pytest.mark.contract_case("DASHBOARD-CSS-005")
    def test_scope_selector_agent_active_colors_use_agent_tokens(self):
        """Agent scope 选中态必须复用各 agent 默认色，不得统一使用品牌色。"""
        css = _read(_CSS_PATH)
        expected = {
            r"\.scope-selector__btn\[data-scope=\"claude-code\"\]\.is-active": (
                "--agent-claude"
            ),
            r"\.scope-selector__btn\[data-scope=\"qoder\"\]\.is-active": (
                "--agent-qoder"
            ),
            r"\.scope-selector__btn\[data-scope=\"codex\"\]\.is-active": (
                "--agent-codex"
            ),
        }
        for selector, token in expected.items():
            pattern = (
                selector
                + r"\s*\{[^}]*background:\s*var\("
                + re.escape(token)
                + r"\);"
            )
            assert re.search(pattern, css, re.S), f"{selector} must use {token}"

        scope_blocks = re.findall(
            r"\.scope-selector__btn[^{]*\.is-active\s*\{[^}]*\}",
            css,
            re.S,
        )
        assert scope_blocks
        assert all(
            "var(--brand)" not in block and "var(--purple)" not in block
            for block in scope_blocks
        )

    @pytest.mark.contract_case("DASHBOARD-CSS-005")
    def test_grain_control_active_color_is_neutral(self):
        """Day/Week/Month 选中态必须使用中性色，不得复用 agent 或品牌色。"""
        css = _read(_CSS_PATH)
        assert "--dashboard-grain-active-color: var(--gray-900);" in css
        match = re.search(
            r"\.grain-control__btn\.is-active\s*\{(?P<body>[^}]*)\}",
            css,
            re.S,
        )
        assert match, "grain control active block must exist"
        body = match.group("body")
        assert "background: var(--dashboard-grain-active-color);" in body
        for token in [
            "--agent-claude",
            "--agent-qoder",
            "--agent-codex",
            "--brand",
            "--purple",
        ]:
            assert f"var({token})" not in body

    @pytest.mark.contract_case("DASHBOARD-CSS-006")
    def test_cache_health_line_series_use_line_keys(self):
        """Cache Health 折线图例和 tooltip key 必须用短线，不用圆点。"""
        css = _read(_CSS_PATH)
        for cls in ["average", "claude_code", "qoder", "codex"]:
            assert f".chart-legend__line--{cls}" in css
        for cls in ["average", "claude", "qoder", "codex"]:
            assert f".tooltip-line-key--{cls}" in css
        assert ".plot--cache-health" in css
        assert ".plot-grid__line" in css
        assert ".line-isolated-marker.line-series--muted" in css

    @pytest.mark.contract_case("DASHBOARD-JS-001")
    def test_token_trend_tooltip_only_shows_token_types(self):
        """Token Trend tooltip 不得混入 agent token 行或 Cache Read Ratio。"""
        js = _read(_JS_PATH)
        start = js.index("function buildTokenTooltip")
        end = js.index("function buildPromptTooltip", start)
        body = js[start:end]
        assert "agent.label + ' tokens'" not in body
        assert "agent.tokenKey" not in body
        assert "Cache Read Ratio" not in body

    @pytest.mark.contract_case("DASHBOARD-JS-002")
    def test_prompt_activity_line_uses_bar_center_coordinates(self):
        """Prompt Activity 折线点位必须按柱状图单元格中心计算。"""
        js = _read(_JS_PATH)
        assert "function xBandCenterPct" in js
        start = js.index("function renderPromptChart")
        end = js.index("function buildCacheTooltip", start)
        body = js[start:end]
        assert "linePath(data, maxAvg, function(d, i) { return avgValues[i]; }, xBandCenterPct)" in body
        assert 'class="line-plot line-plot--bar-aligned"' in body
        assert 'class="prompt-line-markers"' in body

    @pytest.mark.contract_case("DASHBOARD-JS-002")
    def test_line_path_connects_across_missing_points(self):
        """折线缺失点应跳过并连接前后有效点，而不是断线。"""
        js = _read(_JS_PATH)
        start = js.index("function linePath")
        end = js.index("function isolatedLineMarkers", start)
        body = js[start:end]
        missing_branch = body[body.index("if (val == null || !isFinite(val))"):body.index("var cmd = open")]
        assert "open = false" not in missing_branch
        assert "var resolveX = xFn || xBandCenterPct;" in body

    @pytest.mark.contract_case("DASHBOARD-JS-003")
    def test_prompt_activity_tooltip_separates_bars_and_line(self):
        """Prompt Activity tooltip 不得把柱状图和折线值合并到同一 agent 行。"""
        js = _read(_JS_PATH)
        start = js.index("function buildPromptTooltip")
        end = js.index("function renderSessionChart", start)
        body = js[start:end]
        assert "User Prompts (bars)" in body
        assert "Avg Prompts / Session (line)" in body
        assert "Auxiliary" in body
        assert "tooltipLineRow" in body
        assert "agent.label + ' Prompts'" not in body
        assert "formatNumber(prompts), perSession" not in body

    @pytest.mark.contract_case("DASHBOARD-JS-005")
    def test_cache_health_uses_dynamic_axis_and_line_keys(self):
        """Cache Health 必须使用动态 y 轴和折线 key。"""
        js = _read(_JS_PATH)
        assert "function cacheAxisDomain" in js
        assert "function yPctRange" in js
        assert "function isolatedLineMarkers" in js
        start = js.index("function renderCacheHealthChart")
        end = js.index("renderSessionChart();", start)
        body = js[start:end]
        assert "var domain = cacheAxisDomain(data, specs);" in body
        assert "var cacheY = function(value) { return yPctRange(value, domain.min, domain.max, 5); };" in body
        assert "plotGridHtml(domain.ticks, cacheY)" in body
        assert "var isolatedMarkers = '';" in body
        assert "isolatedLineMarkers(data, valueFn, xBandCenterPct, cacheY, cls)" in body
        assert "paths + isolatedMarkers" in body
        assert 'class="line-plot line-plot--bar-aligned"' in body
        assert "normalizeCacheMetricFlags(applyScope(cacheRawData, getCacheFields()))" in body
        assert "ratio == null ? cacheY(domain.min)" not in body
        assert "var pointHtml = '';" in body
        assert "if (ratio != null && isFinite(ratio))" in body
        assert 'class="chart-legend__line chart-legend__line--' in body
        assert 'class="chart-legend__dot chart-legend__dot--' not in body
        assert "tooltipLineRow(item.line" in js[js.index("function buildCacheTooltip"):start]

    @pytest.mark.contract_case("DASHBOARD-JS-004")
    def test_dashboard_does_not_render_fresh_spikes(self):
        """Dashboard 是聚合统计页，不展示或前端计算 Fresh spike。"""
        js = _read(_JS_PATH)
        css = _read(_CSS_PATH)
        assert "freshSpikeIndexes" not in js
        assert "Fresh Spike" not in js
        assert "Fresh spike" not in js
        assert "fresh-spike-marker" not in js
        assert "fresh-spike-marker" not in css

    @pytest.mark.contract_case("DASHBOARD-CSS-002")
    def test_kpi_metric_rows_have_hover_tooltip_styles(self):
        """KPI 主指标、badge 和二级指标必须共用黑色 tooltip 样式。"""
        css = _read(_CSS_PATH)
        assert ".metric-card__tooltip-target[data-tooltip-def]" in css
        assert ".metric-card__tooltip-target[data-tooltip-def]:hover::after" in css
        assert ".metric-card__tooltip-target[data-tooltip-def]:focus-visible::after" in css
        assert "background: #0f172a;" in css
        assert "box-shadow: none;" in css
        assert "white-space: normal;" in css
        assert "overflow-wrap: anywhere;" in css
        assert "max-width: min(320px, calc(100vw - 32px));" in css
        assert ".chart-card__note" in css
        assert "max-width: 560px;" not in css


class TestDashboardTemplateContract:
    """验证 Dashboard 模板不出现禁止项。"""

    _BANNED_PHRASES = [
        "Hot Sessions",
        "Context Budget",
        "Dense",
        "Comfortable",
        "Columns",
        "Export",
        "Keyboard shortcuts",
        "Token Trend by Composition",
        'data-action="view-sessions"',
        'data-stat="fresh-spikes"',
        'data-chart-card="token-composition"',
        'id="token-composition-chart"',
        'class="chart-card__subtitle"',
        'aria-label="Agent Sessions"',
    ]

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-001")
    @pytest.mark.parametrize("phrase", _BANNED_PHRASES)
    def test_template_no_banned_phrases(self, phrase):
        """Dashboard 模板不得包含禁止短语。"""
        tmpl = _read(_TEMPLATE_PATH)
        # "Export" is allowed in "Export PNG" context but not as a button label
        if phrase == "Export":
            # Check for standalone Export button/link
            assert 'data-action="export"' not in tmpl,                 "Dashboard 不得有 Export data-action"
            assert "keyboard" not in tmpl.lower(),                 "Dashboard 不得有 keyboard shortcuts"
        else:
            assert phrase not in tmpl,                 f"Dashboard 模板包含禁止短语 '{phrase}'"

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-002")
    def test_dashboard_tables_are_sortable(self):
        """All Agents 和 Agent / Model Efficiency 必须启用列排序。"""
        tmpl = _read(_TEMPLATE_PATH)
        assert 'id="dashboard-all-agents-table" data-table-enhanced' in tmpl
        assert 'id="dashboard-agent-model-efficiency-table" data-table-enhanced' in tmpl
        for key in [
            'data-sort-key="agent"',
            'data-sort-key="sessions"',
            'data-sort-key="tokens"',
            'data-sort-key="prompts"',
            'data-sort-key="projects"',
            'data-sort-key="failure"',
            'data-sort-key="model"',
            'data-sort-key="tokens-per-session"',
            'data-sort-key="cache-read"',
        ]:
            assert key in tmpl, f"Dashboard sortable table missing {key}"

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-003")
    def test_token_trend_pairs_with_cache_health_in_trend_grid(self):
        """Token Trend 和 Cache Health 必须在同一个 trend grid 中同级渲染。"""
        tmpl = _read(_TEMPLATE_PATH)
        start = tmpl.index('<div class="trend-grid">')
        end = tmpl.index('{# ── Scope 分支区', start)
        body = tmpl[start:end]
        assert 'data-chart-card="tokens"' in body
        assert 'data-chart-card="cache-health"' in body
        assert 'class="chart-card cache-health-section"' in body
        assert body.index('data-chart-card="tokens"') < body.index('data-chart-card="cache-health"')

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-004")
    def test_kpi_cards_use_row_tooltips_not_info_buttons(self):
        """KPI 卡片不得保留 info icon，主指标、badge 和二级指标必须有 tooltip。"""
        tmpl = _read(_TEMPLATE_PATH)
        start = tmpl.index('<section class="kpi-grid">')
        end = tmpl.index('{# ── Trend 总览区', start)
        body = tmpl[start:end]
        assert 'icon-button--info' not in body
        assert 'data-action="kpi-info"' not in body
        assert 'class="metric-card__label metric-card__tooltip-target"' not in body
        assert 'data-kpi-tooltip="{{ kpi.label }}"' in body
        assert 'data-tooltip-def="{{ kpi.description }}"' in body
        assert 'data-kpi-badge-tooltip="{{ kpi.label }}"' in body
        assert 'data-tooltip-def="{{ kpi.badge_description }}"' in body
        assert 'metric-card__secondary-row metric-card__tooltip-target' in body
        assert 'tabindex="0"' in body

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-005")
    def test_chart_info_uses_inline_notes_not_info_buttons(self):
        """Dashboard 图表说明必须是常驻小字，不得回退到 info icon/popover。"""
        tmpl = _read(_TEMPLATE_PATH)
        assert 'icon-button--info' not in tmpl
        assert 'data-info=' not in tmpl
        assert 'id="infoPopover"' not in tmpl
        assert 'class="chart-card__note"' in tmpl
        assert "chart_notes.sessions" in tmpl

    @pytest.mark.contract_case("DASHBOARD-TEMPLATE-006")
    def test_dashboard_template_has_no_native_title_tooltips(self):
        """Dashboard 不得使用原生 title，避免灰色浏览器 tooltip。"""
        tmpl = _read(_TEMPLATE_PATH)
        assert " title=" not in tmpl
