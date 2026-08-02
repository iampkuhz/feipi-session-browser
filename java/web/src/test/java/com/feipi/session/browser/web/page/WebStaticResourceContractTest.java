package com.feipi.session.browser.web.page;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.regex.Pattern;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Web 模板、样式和脚本中需要长期保留的用户可见契约（T-Dashboard-JS-CSS-Contract）。 */
@DisplayName("Web static resource contract")
class WebStaticResourceContractTest {

  /** 验收映射：DASHBOARD-JS-001、DASHBOARD-JS-004。 */
  @Test
  @DisplayName("Dashboard 不恢复已经移除的页面职责")
  void dashboardScriptDoesNotRestoreRetiredResponsibilities() {
    String javascript = resource("static/js/dashboard.js");

    assertThat(javascript)
        .doesNotContain(
            "density-toggle",
            "settingsDrawer",
            "settings-drawer",
            "chart-export",
            "chart-copy-link",
            "open-settings",
            "close-settings",
            "freshSpikeIndexes",
            "Fresh Spike",
            "fresh-spike-marker");
  }

  /** 验收映射：DASHBOARD-JS-002、DASHBOARD-JS-003。 */
  @Test
  @DisplayName("柱图、折线和提示信息保持同一业务语义")
  void dashboardPromptChartKeepsCoordinateAndTooltipSemantics() {
    String javascript = resource("static/js/dashboard.js");
    String linePath = between(javascript, "function linePath", "function isolatedLineMarkers");
    String missingPointBranch =
        between(linePath, "if (val == null || !isFinite(val))", "var cmd = open");
    String promptChart =
        between(javascript, "function renderPromptChart", "function buildCacheTooltip");
    String promptTooltip =
        between(javascript, "function buildPromptTooltip", "function renderSessionChart");

    assertThat(linePath)
        .contains("var resolveX = xFn || xBandCenterPct;")
        .contains("if (val == null || !isFinite(val)) {\n                    return;");
    assertThat(missingPointBranch).doesNotContain("open = false");
    assertThat(promptChart)
        .contains("linePath(data, maxAvg, function(d, i) { return avgValues[i]; }, xBandCenterPct)")
        .contains("class=\"line-plot line-plot--bar-aligned\"")
        .contains("class=\"prompt-line-markers\"");
    assertThat(promptTooltip)
        .contains("User Prompts (bars)", "Avg Prompts / Session (line)", "Auxiliary")
        .contains("tooltipLineRow")
        .doesNotContain("agent.label + ' Prompts'");
  }

  /** 验收映射：DASHBOARD-JS-005。 */
  @Test
  @DisplayName("Cache Health 使用动态坐标轴和折线图例")
  void dashboardCacheHealthKeepsDynamicLineChart() {
    String javascript = resource("static/js/dashboard.js");
    String cacheChart =
        between(javascript, "function renderCacheHealthChart", "function currentApiParams");

    assertThat(javascript).contains("function cacheAxisDomain", "function yPctRange");
    assertThat(cacheChart)
        .contains(
            "var domain = cacheAxisDomain(data, specs);",
            "plotGridHtml(domain.ticks, cacheY)",
            "isolatedLineMarkers(data, valueFn, xBandCenterPct, cacheY, cls)",
            "class=\"line-plot line-plot--bar-aligned\"",
            "class=\"chart-legend__line chart-legend__line--")
        .doesNotContain("class=\"chart-legend__dot chart-legend__dot--");
  }

  /** 验收映射：DASHBOARD-CSS-001。 */
  @Test
  @DisplayName("Dashboard 不重复定义共享基础组件")
  void dashboardCssDoesNotOwnSharedPrimitives() {
    String cssWithoutComments = removeCssComments(resource("static/css/dashboard.css"));

    for (String selector :
        new String[] {
          ".btn",
          ".btn--primary",
          ".badge",
          ".badge--danger",
          ".badge--warning",
          ".badge--info",
          ".data-table",
          ".tooltip",
          ".modal"
        }) {
      assertThat(hasCssRule(cssWithoutComments, selector))
          .as("dashboard.css 不应重新定义共享选择器 %s", selector)
          .isFalse();
    }
  }

  /**
   * 这些用例编号对应仪表盘图表的验收要求。本测试集中确认图层定位、提示框锚点和关键样式名称，避免页面调整破坏图表之间的对齐关系：
   * DASHBOARD-CSS-002、DASHBOARD-CSS-003、DASHBOARD-CSS-004、DASHBOARD-CSS-006、ROUTE-API-005。
   */
  @Test
  @DisplayName("图表层级和 tooltip 锚点稳定")
  void dashboardCssKeepsChartLayersAligned() {
    String css = resource("static/css/dashboard.css");

    assertThat(cssBlock(css, ".line-plot--bar-aligned"))
        .contains(
            "inset-inline-start: var(--plot-x-padding);",
            "inset-inline-end: auto;",
            "width: calc(100% - var(--plot-x-padding) - var(--plot-x-padding));")
        .doesNotContain("width: auto");
    assertThat(cssBlock(css, ".bar")).contains("position: relative;");
    assertThat(cssBlock(css, ".dashboard-tooltip"))
        .contains("position: absolute;", "z-index: 140;")
        .doesNotContain("position: fixed;");
    assertThat(css)
        .contains(
            ".tooltip-line-key--prompt-average",
            ".chart-legend__line--prompt-average",
            ".plot--cache-health",
            ".line-isolated-marker.line-series--muted");
  }

  /** 验收映射：DASHBOARD-CSS-005。 */
  @Test
  @DisplayName("汇总、Agent 和粒度选择使用各自颜色")
  void dashboardCssKeepsColorRolesDistinct() {
    String css = resource("static/css/dashboard.css");

    assertThat(css)
        .contains(
            "--dashboard-average-color: #111827;",
            "--dashboard-grain-active-color: var(--gray-900);");
    assertThat(cssBlock(css, ".scope-selector__btn[data-scope=\"all\"].is-active"))
        .contains("background: var(--dashboard-average-color);");
    assertThat(cssBlock(css, ".scope-selector__btn[data-scope=\"claude-code\"].is-active"))
        .contains("background: var(--agent-claude);");
    assertThat(cssBlock(css, ".scope-selector__btn[data-scope=\"qoder\"].is-active"))
        .contains("background: var(--agent-qoder);");
    assertThat(cssBlock(css, ".scope-selector__btn[data-scope=\"codex\"].is-active"))
        .contains("background: var(--agent-codex);");
    assertThat(cssBlock(css, ".grain-control__btn.is-active"))
        .contains("background: var(--dashboard-grain-active-color);")
        .doesNotContain("var(--brand)", "var(--purple)");
  }

  /**
   * 这些用例编号要求仪表盘只展示当前的信息结构。本测试防止已删除的旧版模块重新进入模板：
   * DASHBOARD-TEMPLATE-001、DASHBOARD-TEMPLATE-002、DASHBOARD-TEMPLATE-006。
   */
  @Test
  @DisplayName("Dashboard 只保留当前信息架构")
  void dashboardTemplateKeepsCurrentInformationArchitecture() {
    String template = resource("templates/dashboard.html");

    assertThat(template)
        .doesNotContain(
            "Hot Sessions",
            "Context Budget",
            "Dense",
            "Comfortable",
            "Keyboard shortcuts",
            "data-action=\"export\"",
            "data-stat=\"fresh-spikes\"",
            " title=")
        .contains(
            "id=\"dashboard-all-agents-table\" data-table-enhanced",
            "id=\"dashboard-agent-model-efficiency-table\" data-table-enhanced",
            "data-sort-key=\"agent\"",
            "data-sort-key=\"tokens-per-session\"");
  }

  /**
   * 这些用例编号要求趋势图与解释文字保持相邻且顺序稳定。本测试直接检查模板结构，避免页面改动让说明脱离对应图表：
   * DASHBOARD-TEMPLATE-003、DASHBOARD-TEMPLATE-004、DASHBOARD-TEMPLATE-005。
   */
  @Test
  @DisplayName("趋势图和解释文本保持直接可见")
  void dashboardTemplateKeepsChartsAndExplanationsTogether() {
    String template = resource("templates/dashboard.html");
    String trendGrid = between(template, "<div class=\"trend-grid\">", "{# ── Scope 分支区");

    assertThat(trendGrid)
        .contains("data-chart-card=\"tokens\"", "data-chart-card=\"cache-health\"");
    assertThat(trendGrid.indexOf("data-chart-card=\"tokens\""))
        .isLessThan(trendGrid.indexOf("data-chart-card=\"cache-health\""));
    assertThat(template)
        .contains(
            "class=\"chart-card__note\"",
            "chart_notes.sessions",
            "chart_notes.prompts",
            "chart_notes.tokens",
            "chart_notes.cache_health",
            "data-kpi-tooltip=\"{{ kpi.label }}\"",
            "data-tooltip-def=\"{{ kpi.description }}\"")
        .doesNotContain("icon-button--info", "data-info=", "id=\"infoPopover\"");
  }

  /** 验收映射：UI-VISUAL-001。 */
  @Test
  @DisplayName("Projects 表格模板、脚本和样式使用同一 DOM 契约")
  void projectsResourcesShareOneTableContract() {
    String template = resource("templates/projects.html");
    String javascript = resource("static/js/projects.js");
    String css = resource("static/css/projects.css");

    assertThat(template)
        .contains(
            "id=\"projects-table\"",
            "data-api-rows=\"/api/projects/rows\"",
            ">Project</th>",
            ">Agents</th>",
            ">Sessions ",
            ">Tokens ",
            ">Tools ",
            ">Failed ",
            ">First Seen ",
            ">Last Active ");
    assertThat(javascript)
        .contains(
            "class=\"agents-cell\"",
            "class=\"agents-cell__inner\"",
            "tokenbar-seg fresh",
            "Token Breakdown");
    assertThat(cssBlock(css, ".p-projects .agents-cell"))
        .contains("vertical-align: middle;")
        .doesNotContain("display: flex");
    assertThat(cssBlock(css, ".p-projects .agents-cell__inner")).contains("display: flex;");
  }

  /** 验收映射：UI-VISUAL-011。 */
  @Test
  @DisplayName("实际字体 token 不低于可读性下限")
  void typographyTokensMeetReadableMinimums() {
    String tokens = resource("static/css/tokens.css");

    assertThat(pixelVariable(tokens, "--text-micro")).isGreaterThanOrEqualTo(10.0);
    assertThat(pixelVariable(tokens, "--text-xs")).isGreaterThanOrEqualTo(11.0);
    assertThat(pixelVariable(tokens, "--text-sm")).isGreaterThanOrEqualTo(13.0);
    assertThat(pixelVariable(tokens, "--text-base")).isGreaterThanOrEqualTo(14.0);
    assertThat(pixelVariable(tokens, "--text-lg")).isGreaterThanOrEqualTo(14.0);
    assertThat(pixelVariable(tokens, "--text-metric-sm")).isGreaterThanOrEqualTo(18.0);
    assertThat(pixelVariable(tokens, "--text-metric")).isGreaterThanOrEqualTo(22.0);
    assertThat(tokens).contains("--density-font-size:   var(--text-sm);");
  }

  /** 除了检查 token 数值，还要确认主要组件确实继承或声明了这些可读字号。表格、按钮和轮次预览使用全局基础字号，摘要条和值使用自己的显式下限。 */
  @Test
  @DisplayName("主要组件实际使用的字体不低于可读性下限")
  void primaryComponentsUseReadableFontSizes() {
    String tokens = resource("static/css/tokens.css");
    String base = resource("static/css/base.css");
    String buttons = resource("static/css/ui-primitives/_buttons.css");
    String tables = resource("static/css/ui-primitives/_tables.css");
    String header = resource("static/css/session-detail/02-header-summary.css");
    String timeline = resource("static/css/session-detail/04-timeline.css");

    assertThat(pixelVariable(tokens, "--text-base")).isGreaterThanOrEqualTo(14.0);
    assertThat(cssBlock(base, "html")).contains("font-size: var(--text-base);");
    assertThat(cssBlock(buttons, ".btn")).contains("font: inherit;").doesNotContain("font-size:");
    assertThat(cssBlock(tables, ".data-table")).doesNotContain("font-size:");
    assertThat(cssBlock(timeline, ".sd-round-preview__title")).doesNotContain("font-size:");
    assertThat(pixelFontSize(header, ".sd-summary-item")).isGreaterThanOrEqualTo(12.0);
    assertThat(pixelFontSize(header, ".sd-kpi__value")).isGreaterThanOrEqualTo(14.0);
  }

  /** 验收映射：UI-SD-016。 */
  @Test
  @DisplayName("Session Detail 模板接入唯一 shell 和主要内容区")
  void sessionDetailTemplateWiresShellAndPrimaryRegions() {
    String base = resource("templates/base.html");
    String session = resource("templates/session.html");

    assertThat(base)
        .contains(
            "class=\"shell {% block shell_class %}{% endblock %}\"", "data-session-detail-shell");
    assertThat(session)
        .contains(
            "{% block shell_class %}no-inspector session-detail-page sd-shell{% endblock %}",
            "href=\"/static/css/session-detail.css\"",
            "data-session-overview-hero",
            "data-session-metrics-shell",
            "data-session-diagnostics",
            "data-session-tabs",
            "data-trace-panel",
            "data-payload-sources-container");
  }

  /** 验收映射：UI-SD-016。 */
  @Test
  @DisplayName("Session Detail shell 和 hero 保持单列且不会横向撑破")
  void sessionDetailCssKeepsSingleColumnWithinShell() {
    String shellCss = resource("static/css/shell.css");
    String headerCss = resource("static/css/session-detail/02-header-summary.css");

    assertThat(cssBlock(shellCss, "body.hide-left .shell.no-inspector"))
        .contains("grid-template-columns: minmax(0, 1fr);");
    assertThat(cssBlock(shellCss, ".sd-shell")).contains("min-width: 0;", "max-width: 100%;");
    assertThat(cssBlock(headerCss, ".sd-hero__top"))
        .contains("flex-direction: column;", "min-width: 0;", "max-width: 100%;");
    assertThat(cssBlock(headerCss, ".sd-hero h1"))
        .contains("white-space: nowrap;", "overflow: hidden;", "text-overflow: ellipsis;")
        .doesNotContain("overflow-wrap: anywhere", "word-break: break-all");
  }

  /** 从测试 classpath 读取生产资源；缺失资源直接形成可读断言。 */
  private static String resource(String path) {
    try (var input =
        WebStaticResourceContractTest.class.getClassLoader().getResourceAsStream(path)) {
      assertThat(input).as("测试资源 %s", path).isNotNull();
      return new String(input.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  /** 提取两个稳定锚点之间的代码，使断言只关注一个函数或页面区域。 */
  private static String between(String source, String startMarker, String endMarker) {
    int start = source.indexOf(startMarker);
    assertThat(start).as("起始锚点 %s", startMarker).isNotNegative();
    int end = source.indexOf(endMarker, start + startMarker.length());
    assertThat(end).as("结束锚点 %s", endMarker).isGreaterThan(start);
    return source.substring(start, end);
  }

  /** 提取指定 CSS 选择器的声明块，避免整份文件中的同名属性造成误判。 */
  private static String cssBlock(String css, String selector) {
    var matcher =
        Pattern.compile(Pattern.quote(selector) + "\\s*\\{([^}]*)}", Pattern.DOTALL).matcher(css);
    assertThat(matcher.find()).as("CSS 选择器 %s", selector).isTrue();
    return matcher.group(1);
  }

  /** 判断 CSS 是否真正声明选择器；注释已由调用方移除。 */
  private static boolean hasCssRule(String css, String selector) {
    return Pattern.compile("(?m)^\\s*" + Pattern.quote(selector) + "\\s*\\{").matcher(css).find();
  }

  private static String removeCssComments(String css) {
    return Pattern.compile("/\\*.*?\\*/", Pattern.DOTALL).matcher(css).replaceAll("");
  }

  /** 读取真实 CSS token 的 px 数值；找不到或改成不可比较单位时明确失败。 */
  private static double pixelVariable(String css, String variable) {
    var matcher =
        Pattern.compile(Pattern.quote(variable) + "\\s*:\\s*([0-9.]+)px\\s*;").matcher(css);
    assertThat(matcher.find()).as("像素 token %s", variable).isTrue();
    return Double.parseDouble(matcher.group(1));
  }

  /** 读取选择器中显式声明的像素字号；缺少声明或改用不可比较单位时明确失败。 */
  private static double pixelFontSize(String css, String selector) {
    String block = cssBlock(css, selector);
    var matcher = Pattern.compile("font-size\\s*:\\s*([0-9.]+)px\\s*;").matcher(block);
    assertThat(matcher.find()).as("选择器 %s 的像素字号", selector).isTrue();
    return Double.parseDouble(matcher.group(1));
  }
}
