package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.DashboardUseCase;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.api.IndexQueryException;
import com.feipi.session.browser.index.api.query.ActivityTrend;
import com.feipi.session.browser.index.api.query.AgentBreakdown;
import com.feipi.session.browser.index.api.query.AgentEfficiency;
import com.feipi.session.browser.index.api.query.DashboardStats;
import com.feipi.session.browser.index.api.query.KpiSupplement;
import com.feipi.session.browser.index.api.query.TrendDay;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import com.feipi.session.browser.web.model.WebDisplayValues;
import com.feipi.session.browser.web.template.DisplayFormatters;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Dashboard 页面路由处理器。
 *
 * <p>处理 {@code GET /} 和 {@code GET /dashboard} 请求：解析 agent scope 和 grain 参数， 调用 Dashboard use
 * case，组装模板上下文，渲染 HTML 响应。
 *
 * <p>Dashboard 页面沿用主干模板 DOM 契约，并由 Java 查询层组装图表、KPI 与 agent 分支 view model。
 */
public final class DashboardPage {

  private static final Logger LOG = LoggerFactory.getLogger(DashboardPage.class);
  private static final Set<String> VALID_AGENT_SCOPES =
      Set.of("all", "claude-code", "qoder", "codex");
  private static final Set<String> VALID_GRAINS = Set.of("day", "week", "month");
  private static final double COMPACT_BILLION = 1_000_000_000.0;
  private static final double COMPACT_MILLION = 1_000_000.0;
  private static final double COMPACT_THOUSAND = 1_000.0;

  /** scope URL 参数到 DB agent 值的映射。 */
  private static final Map<String, String> SCOPE_TO_DB =
      Map.of("claude-code", "claude_code", "qoder", "qoder", "codex", "codex");

  /** grain 到趋势窗口天数的映射。 */
  private static final Map<String, Integer> GRAIN_DAYS =
      Map.of("day", 30, "week", 140, "month", 360);

  private final QueryCompositionRoot queryRoot;
  private final PebbleEnvironment templates;

  /**
   * 创建 Dashboard 页面处理器。
   *
   * @param queryRoot 查询 composition root
   * @param templates Pebble 模板环境
   */
  public DashboardPage(QueryCompositionRoot queryRoot, PebbleEnvironment templates) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 GET / 或 GET /dashboard 请求。
   *
   * @param ctx Javalin 请求上下文
   */
  public void handle(Context ctx) {
    Map<String, String> params = SessionsPage.flatQueryParams(ctx);

    String agentScope = normalizeAgentScope(params.getOrDefault("agent", "all"));
    String grain = normalizeGrain(params.getOrDefault("grain", "day"));

    try {
      DashboardUseCase useCase = queryRoot.dashboard();

      // 全局统计
      AgentFilter agentFilter = buildAgentFilter(agentScope);
      DashboardStats stats = useCase.stats(agentFilter);
      KpiSupplement kpiSupplement = useCase.kpiSupplement(agentFilter);

      // 趋势数据
      int days = GRAIN_DAYS.getOrDefault(grain, 30);
      TrendFilter trendFilter = TrendFilter.ofDays(days);
      if (!agentFilter.isUnfiltered()) {
        trendFilter = trendFilter.withAgent(agentFilter);
      }
      List<TrendDay> trendRows = useCase.trendData(trendFilter);
      // cache health 使用未过滤的全局时间轴（与 Python 主分支对齐）
      List<TrendDay> unfilteredTrendRows = useCase.trendData(TrendFilter.ofDays(days));
      List<ActivityTrend> activityRows = useCase.activityTrend(trendFilter);
      List<AgentEfficiency> efficiencyRows = useCase.agentEfficiency();
      List<AgentBreakdown> agentBreakdown = useCase.agentBreakdown();

      // 组装模板上下文
      Map<String, Object> context = new HashMap<>();
      context.put("stats", stats);
      context.put("agent_scope", agentScope);
      context.put("grain", grain);
      context.put("is_single_agent", !"all".equals(agentScope));
      context.put("active_page", "dashboard");
      context.put("hide_sidebar_extra", true);
      context.put("kpis", buildKpis(stats, kpiSupplement, trendRows, activityRows));
      context.put("trend", buildTrend(trendRows));
      context.put("prompt_activity", buildPromptActivity(activityRows));
      Map<String, Object> cacheHealth = buildCacheHealth(unfilteredTrendRows, agentScope);
      context.put("cache_health", cacheHealth);
      context.put("chart_notes", buildChartNotes());
      context.put("dashboard_summary", buildDashboardSummary(trendRows, activityRows, cacheHealth));
      context.put(
          "all_agents_branch",
          buildAllAgentsBranch(stats, trendRows, activityRows, efficiencyRows, agentBreakdown));
      context.put("single_agent_branch", buildSingleAgentBranch(agentScope, efficiencyRows));
      context.put("needs_attention", List.of());
      context.put("agent_sessions_total", stats.totalSessions());
      context.put("agent_sessions_page", 1);
      context.put("agent_sessions_total_pages", 1);
      context.put("agent_sessions_page_size", stats.totalSessions());

      String html = templates.render("dashboard.html", context);
      ctx.html(html);

    } catch (IndexQueryException e) {
      LOG.error("Dashboard 查询失败", e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(
          templates.render(
              "error.html", Map.of("error", "查询 Dashboard 数据失败", "active_page", "dashboard")));
    }
  }

  private static String normalizeAgentScope(String value) {
    if (value == null || !VALID_AGENT_SCOPES.contains(value)) {
      return "all";
    }
    return value;
  }

  private static String normalizeGrain(String value) {
    if (value == null || !VALID_GRAINS.contains(value)) {
      return "day";
    }
    return value;
  }

  private static AgentFilter buildAgentFilter(String agentScope) {
    if ("all".equals(agentScope)) {
      return AgentFilter.NONE;
    }
    String dbAgent = SCOPE_TO_DB.getOrDefault(agentScope, "");
    if (dbAgent.isEmpty()) {
      return AgentFilter.NONE;
    }
    return AgentFilter.of(dbAgent);
  }

  private static List<Map<String, Object>> buildKpis(
      DashboardStats stats,
      KpiSupplement supplement,
      List<TrendDay> trendRows,
      List<ActivityTrend> activityRows) {
    long inputSide =
        stats.totalFreshInputTokens()
            + stats.totalCacheReadTokens()
            + stats.totalCacheWriteTokens();
    long totalSessions = stats.totalSessions();
    long totalToolCalls = stats.totalToolCalls();
    long totalFailedTools = stats.totalFailedTools();
    long totalUserMessages = stats.totalUserMessages();
    long totalAssistantMessages = stats.totalAssistantMessages();

    // 说明:Badge 计算——对比当前可见窗口最后两个 range point
    long latestSessions =
        trendRows.isEmpty() ? 0 : trendRows.get(trendRows.size() - 1).totalCount();
    long prevSessions = trendRows.size() < 2 ? 0 : trendRows.get(trendRows.size() - 2).totalCount();
    long sessionDelta = latestSessions - prevSessions;

    long latestTokens = trendRows.isEmpty() ? 0 : trendRows.get(trendRows.size() - 1).totalTokens();
    long prevTokens = trendRows.size() < 2 ? 0 : trendRows.get(trendRows.size() - 2).totalTokens();

    long latestPrompts =
        activityRows.isEmpty() ? 0 : activityRows.get(activityRows.size() - 1).totalPrompts();
    long prevPrompts =
        activityRows.size() < 2 ? 0 : activityRows.get(activityRows.size() - 2).totalPrompts();
    long promptDelta = latestPrompts - prevPrompts;

    long latestFailed = trendRows.isEmpty() ? 0 : trendRows.get(trendRows.size() - 1).failedTools();
    long prevFailed = trendRows.size() < 2 ? 0 : trendRows.get(trendRows.size() - 2).failedTools();
    long failedDelta = latestFailed - prevFailed;

    // 说明:Cache Read Ratio badge——最后两个可计算点的百分点变化
    String cacheRatioBadge = null;
    String cacheRatioBadgeTone = "neutral";
    {
      Double latest = null;
      Double prev = null;
      for (int i = trendRows.size() - 1; i >= 0 && latest == null; i--) {
        TrendDay r = trendRows.get(i);
        long is = r.freshInputTokens() + r.cacheReadTokens() + r.cacheWriteTokens();
        if (is > 0) {
          latest = (double) r.cacheReadTokens() / is;
          for (int j = i - 1; j >= 0; j--) {
            TrendDay p = trendRows.get(j);
            long pis = p.freshInputTokens() + p.cacheReadTokens() + p.cacheWriteTokens();
            if (pis > 0) {
              prev = (double) p.cacheReadTokens() / pis;
              break;
            }
          }
          break;
        }
      }
      if (latest != null && prev != null) {
        double deltaPp = (latest - prev) * 100.0;
        if (Math.abs(deltaPp) < 0.05) {
          deltaPp = 0.0;
        }
        cacheRatioBadge = String.format(java.util.Locale.ROOT, "%+.1fpp", deltaPp);
        cacheRatioBadgeTone = deltaPp >= 0 ? "positive" : "negative";
      } else if (latest != null) {
        cacheRatioBadge = "N/A";
      }
    }

    // 说明:Token badge 百分比
    String tokenBadge;
    String tokenBadgeTone;
    if (prevTokens > 0) {
      double pct = ((double) (latestTokens - prevTokens) / prevTokens) * 100.0;
      tokenBadge = String.format(java.util.Locale.ROOT, "%+.1f%%", pct);
      tokenBadgeTone = "neutral";
    } else {
      tokenBadge = latestTokens > 0 ? "N/A" : null;
      tokenBadgeTone = "neutral";
    }

    // 说明:Project badge——最近 7d 相对上个 7d 的变化
    long projectDelta = supplement.activeProjects7d() - supplement.activeProjectsPrevious7d();
    String projectBadge = projectDelta > 0 ? "+" + projectDelta : String.valueOf(projectDelta);
    String projectBadgeTone = projectDelta >= 0 ? "positive" : "negative";

    // 说明:Sessions badge
    String sessionBadge = formatDeltaBadge(sessionDelta);
    String sessionBadgeTone;
    sessionBadgeTone = sessionDelta >= 0 ? "positive" : "negative";

    // 说明:Prompt Activity badge
    String promptBadge = formatDeltaBadge(promptDelta);
    String promptBadgeTone;
    promptBadgeTone = promptDelta >= 0 ? "positive" : "negative";

    // 说明:Failed Tools badge
    String failedBadge = formatDeltaBadge(failedDelta);
    String failedBadgeTone;
    failedBadgeTone = failedDelta <= 0 ? "positive" : "negative";

    // 说明:二级指标计算
    double avgRounds = totalSessions > 0 ? (double) totalAssistantMessages / totalSessions : 0;
    double promptsPerSession = totalSessions > 0 ? (double) totalUserMessages / totalSessions : 0;
    Double cacheRatio = inputSide > 0 ? (double) stats.totalCacheReadTokens() / inputSide : null;
    Double failureRate = totalToolCalls > 0 ? (double) totalFailedTools / totalToolCalls : null;

    return List.of(
        kpi(
            new KpiCard(
                "Projects",
                formatDashboardInteger(stats.projectCount()),
                "当前 scope 下出现过 session 的 project 数量",
                "🗂",
                "purple",
                projectBadge,
                projectBadgeTone,
                List.of(
                    secondary(
                        "Active 24h",
                        formatDashboardInteger(supplement.activeProjects24h()),
                        "最近 24 小时内有 session event 的 project 去重数。"),
                    secondary(
                        "Active 7d",
                        formatDashboardInteger(supplement.activeProjects7d()),
                        "最近 7 个自然日内有 session event 的 project 去重数。"),
                    secondary(
                        "New 7d",
                        formatDashboardInteger(supplement.newProjects7d()),
                        "first seen timestamp 落在最近 7 个自然日内的 project 去重数。")))),
        kpi(
            new KpiCard(
                "Sessions",
                formatDashboardInteger(totalSessions),
                "当前 scope 下已索引 session 总数",
                "🧵",
                "blue",
                sessionBadge,
                sessionBadgeTone,
                List.of(
                    secondary(
                        "Today",
                        formatDashboardInteger(supplement.todaySessions()),
                        "first user message timestamp 落在当前自然日内的 session 数。"),
                    secondary(
                        "7d Avg",
                        formatDashboardCompact(supplement.avgDailySessions7d()),
                        "最近 7 个自然日每日 session 数的算术平均值。"),
                    secondary(
                        "Median Duration",
                        DisplayFormatters.formatDuration(supplement.medianDurationSeconds()),
                        "当前 scope 下 session duration 的中位数。"),
                    secondary(
                        "Avg Rounds",
                        String.format(java.util.Locale.ROOT, "%.1f", avgRounds),
                        "当前 scope 下每个 session 的 LLM round 数平均值。")))),
        kpi(
            new KpiCard(
                "Total Tokens",
                formatDashboardCompact(stats.totalTokens()),
                "Fresh + Cache Read + Cache Write + Output",
                "🧮",
                "orange",
                tokenBadge,
                tokenBadgeTone,
                List.of(
                    secondary(
                        "Fresh",
                        formatDashboardCompact(stats.totalFreshInputTokens()),
                        "互斥的新输入分段，已扣除 cache read 子集。"),
                    secondary(
                        "Cache Read",
                        formatDashboardCompact(stats.totalCacheReadTokens()),
                        "从缓存读取并计入输入侧的 token 数。"),
                    secondary(
                        "Cache Write",
                        formatDashboardCompact(stats.totalCacheWriteTokens()),
                        "写入缓存并计入输入侧的 token 数。"),
                    secondary(
                        "Output",
                        formatDashboardCompact(stats.totalOutputTokens()),
                        "模型输出 token 数。")))),
        kpi(
            new KpiCard(
                "Prompt Activity",
                formatDashboardInteger(totalUserMessages),
                "用户发起输入数量，按 user message 事件计数",
                "💬",
                "green",
                promptBadge,
                promptBadgeTone,
                List.of(
                    secondary(
                        "Assistant Turns",
                        formatDashboardInteger(totalAssistantMessages),
                        "assistant message 事件总数。"),
                    secondary(
                        "Tool Calls",
                        formatDashboardInteger(totalToolCalls),
                        "tool call 事件总数，不区分成功和失败。"),
                    secondary(
                        "Prompts / Session",
                        totalSessions > 0
                            ? String.format(java.util.Locale.ROOT, "%.1f", promptsPerSession)
                            : "N/A",
                        "User Prompts / Sessions；sessions 为 0 时显示 N/A。")))),
        kpi(
            new KpiCard(
                "Cache Read Ratio",
                cacheRatio != null
                    ? String.format(java.util.Locale.ROOT, "%.1f%%", cacheRatio * 100.0)
                    : "N/A",
                "Cache Read / 输入侧 token 总量",
                "⚡",
                "purple",
                cacheRatioBadge,
                cacheRatioBadgeTone,
                List.of(
                    secondary(
                        "Eligible Sessions",
                        formatDashboardInteger(supplement.eligibleSessions()),
                        "Input-side Tokens > 0 的 session 数，也是 Cache Read Ratio 可参与计算的分母样本。"),
                    secondary(
                        "P50 Session Ratio",
                        supplement.p50CacheRatio() != null
                            ? String.format(
                                java.util.Locale.ROOT, "%.1f%%", supplement.p50CacheRatio() * 100.0)
                            : "N/A",
                        "eligible sessions 的 per-session cache read ratio 中位数。"),
                    secondary(
                        "Low-read Sessions",
                        formatDashboardInteger(supplement.lowReadSessions()),
                        "eligible sessions 中 per-session cache read ratio 小于 20.0% 的 session 数。")))),
        kpi(
            new KpiCard(
                "Failed Tools",
                formatDashboardInteger(totalFailedTools),
                "failed tool result 总数",
                "⚠",
                "red",
                failedBadge,
                failedBadgeTone,
                List.of(
                    secondary(
                        "Failure Rate",
                        failureRate != null
                            ? String.format(java.util.Locale.ROOT, "%.1f%%", failureRate * 100.0)
                            : "N/A",
                        "Failed Tools / Tool Calls；tool calls 为 0 时显示 N/A。"),
                    secondary(
                        "Affected Sessions",
                        formatDashboardInteger(supplement.affectedFailureSessions()),
                        "failed tool result 数量大于 0 的 session 数。"),
                    secondary(
                        "Repeated Failure Sessions",
                        formatDashboardInteger(supplement.repeatedFailureSessions()),
                        "failed tool result 数量大于 1 的 session 数。")))));
  }

  private static Map<String, Object> kpi(KpiCard card) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("label", card.label());
    row.put("value", card.value());
    row.put("description", card.description());
    row.put("icon", card.icon());
    row.put("icon_color", card.iconColor());
    row.put("badge", card.badge());
    row.put("badge_tone", card.badgeTone() == null ? "neutral" : card.badgeTone());
    row.put("badge_description", card.badge() == null ? "" : card.description());
    row.put("secondary", card.secondary() == null ? List.of() : card.secondary());
    return row;
  }

  private static Map<String, Object> secondary(String label, Object value, String description) {
    return Map.of("label", label, "value", value, "description", description);
  }

  /**
   * Dashboard KPI 卡片输入。
   *
   * @param label 卡片标题
   * @param value 主指标展示值
   * @param description 指标说明
   * @param icon 展示图标
   * @param iconColor 图标颜色标识
   * @param badge 趋势徽标
   * @param badgeTone 趋势徽标语义色
   * @param secondary 二级指标列表
   */
  private record KpiCard(
      /* 卡片标题文本 */
      String label,
      /* 主指标展示值 */
      Object value,
      /* 指标说明文本 */
      String description,
      /* 图标名称标识 */
      String icon,
      /* 图标颜色标识 */
      String iconColor,
      /* 趋势徽标文本 */
      String badge,
      /* 趋势徽标色调 */
      String badgeTone,
      /* 二级指标列表 */
      List<Map<String, Object>> secondary) {}

  private static String formatDashboardInteger(Number value) {
    long n = value == null ? 0 : value.longValue();
    return String.format(java.util.Locale.ROOT, "%,d", n);
  }

  private static String formatDashboardCompact(Number value) {
    if (value == null || value.doubleValue() == 0.0) {
      return "0";
    }
    double n = value.doubleValue();
    if (n >= COMPACT_BILLION) {
      return String.format(java.util.Locale.ROOT, "%.1fB", n / COMPACT_BILLION);
    }
    if (n >= COMPACT_MILLION) {
      return String.format(java.util.Locale.ROOT, "%.1fM", n / COMPACT_MILLION);
    }
    if (n >= COMPACT_THOUSAND) {
      return String.format(java.util.Locale.ROOT, "%.1fK", n / COMPACT_THOUSAND);
    }
    return String.valueOf((long) n);
  }

  private static String formatDeltaBadge(long delta) {
    if (delta > 0) {
      return "+" + formatDashboardCompact(delta);
    }
    if (delta < 0) {
      return "-" + formatDashboardCompact(Math.abs(delta));
    }
    return "0";
  }

  private static List<Map<String, Object>> buildTrend(List<TrendDay> rows) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (TrendDay row : rows) {
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("date", row.date());
      map.put("claude_count", row.claudeCount());
      map.put("codex_count", row.codexCount());
      map.put("qoder_count", row.qoderCount());
      map.put("total_count", row.totalCount());
      map.put("claude_tokens", row.claudeTokens());
      map.put("codex_tokens", row.codexTokens());
      map.put("qoder_tokens", row.qoderTokens());
      map.put("total_tokens", row.totalTokens());
      map.put("fresh_input_tokens", row.freshInputTokens());
      map.put("cache_read_tokens", row.cacheReadTokens());
      map.put("cache_write_tokens", row.cacheWriteTokens());
      map.put("output_tokens", row.outputTokens());
      map.put("tool_calls", row.toolCalls());
      map.put("failed_tools", row.failedTools());
      result.add(map);
    }
    return result;
  }

  private static List<Map<String, Object>> buildPromptActivity(List<ActivityTrend> rows) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (ActivityTrend row : rows) {
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("date", row.date());
      map.put("claude_prompts", row.claudePrompts());
      map.put("codex_prompts", row.codexPrompts());
      map.put("qoder_prompts", row.qoderPrompts());
      map.put("total_prompts", row.totalPrompts());
      map.put("assistant_turns", row.assistantTurns());
      map.put("tool_calls", row.toolCalls());
      result.add(map);
    }
    return result;
  }

  private static Map<String, Object> buildCacheHealth(List<TrendDay> rows, String agentScope) {
    List<Map<String, Object>> series = new ArrayList<>();
    String scopedPrefix = scopeToCachePrefix(agentScope);
    Double latestRatio = null;
    Double lowestRatio = null;
    for (TrendDay row : rows) {
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("date", row.date());
      // Average = 所有 agent 输入侧 token 之和（与 Python 行为一致）
      map.put("average_fresh_input_tokens", row.freshInputTokens());
      map.put("average_cache_read_tokens", row.cacheReadTokens());
      map.put("average_cache_write_tokens", row.cacheWriteTokens());
      // Per-agent cache health 数据
      map.put("claude_code_fresh_input_tokens", row.claudeFreshInput());
      map.put("claude_code_cache_read_tokens", row.claudeCacheRead());
      map.put("claude_code_cache_write_tokens", row.claudeCacheWrite());
      map.put("qoder_fresh_input_tokens", row.qoderFreshInput());
      map.put("qoder_cache_read_tokens", row.qoderCacheRead());
      map.put("qoder_cache_write_tokens", row.qoderCacheWrite());
      map.put("codex_fresh_input_tokens", row.codexFreshInput());
      map.put("codex_cache_read_tokens", row.codexCacheRead());
      map.put("codex_cache_write_tokens", row.codexCacheWrite());
      map.put("qoder_unreported_input_side_tokens", 0);
      series.add(map);
      Double ratio = cacheRatioForPrefix(row, scopedPrefix);
      if (ratio != null) {
        latestRatio = ratio;
        lowestRatio = lowestRatio == null ? ratio : Math.min(lowestRatio, ratio);
      }
    }

    Map<String, Object> cacheHealth = new LinkedHashMap<>();
    cacheHealth.put("series", series);
    cacheHealth.put("latest_ratio", percentLabel(latestRatio));
    cacheHealth.put("lowest_ratio", percentLabel(lowestRatio));
    return cacheHealth;
  }

  /** 返回指定 prefix 对应的 cache read ratio，输入侧为 0 时返回 null。 */
  private static Double cacheRatioForPrefix(TrendDay row, String prefix) {
    long fresh;
    long read;
    long write;
    switch (prefix) {
      case "claude_code" -> {
        fresh = row.claudeFreshInput();
        read = row.claudeCacheRead();
        write = row.claudeCacheWrite();
      }
      case "qoder" -> {
        fresh = row.qoderFreshInput();
        read = row.qoderCacheRead();
        write = row.qoderCacheWrite();
      }
      case "codex" -> {
        fresh = row.codexFreshInput();
        read = row.codexCacheRead();
        write = row.codexCacheWrite();
      }
      default -> {
        fresh = row.freshInputTokens();
        read = row.cacheReadTokens();
        write = row.cacheWriteTokens();
      }
    }
    long inputSide = fresh + read + write;
    return inputSide > 0 ? (double) read / inputSide : null;
  }

  private static Map<String, Object> buildDashboardSummary(
      List<TrendDay> trendRows, List<ActivityTrend> activityRows, Map<String, Object> cacheHealth) {
    Map<String, Object> summary = new LinkedHashMap<>();
    long totalSessions = trendRows.stream().mapToLong(TrendDay::totalCount).sum();
    long totalTokens = trendRows.stream().mapToLong(TrendDay::totalTokens).sum();
    long totalPrompts = activityRows.stream().mapToLong(ActivityTrend::totalPrompts).sum();
    summary.put(
        "latest_sessions",
        trendRows.isEmpty() ? "—" : trendRows.get(trendRows.size() - 1).totalCount());
    summary.put("range_total_sessions", totalSessions);
    summary.put(
        "latest_tokens",
        trendRows.isEmpty()
            ? "0"
            : formatDashboardCompact(trendRows.get(trendRows.size() - 1).totalTokens()));
    summary.put("range_total_tokens", formatDashboardTrendTokens(totalTokens));
    summary.put(
        "latest_prompts",
        activityRows.isEmpty() ? "—" : activityRows.get(activityRows.size() - 1).totalPrompts());
    summary.put("range_total_prompts", totalPrompts);
    summary.put("latest_ratio", cacheHealth.get("latest_ratio"));
    summary.put("lowest_ratio", cacheHealth.get("lowest_ratio"));
    return summary;
  }

  private static Map<String, String> buildChartNotes() {
    Map<String, String> notes = new LinkedHashMap<>();
    notes.put("sessions", "按天新增的 session 总数,按照不同 agent 堆叠.");
    notes.put("prompts", "按天展示 user prompts 总数,并用折线显示每个 session 的平均 prompts.");
    notes.put("tokens", "按天展示 total tokens,按照 Fresh、Cache Read、Cache Write、Output 组成展示.");
    notes.put("cache_health", "按天展示整体和各 agent 的 Cache Read Ratio;Average 为全局平均.");
    notes.put("model_mix", "当前 Java index 暂未暴露完整模型占比图数据时显示明细表或空态。");
    notes.put("tool_dist", "当前 index 保存聚合工具调用数，不保存工具名称分布。");
    return notes;
  }

  private static Map<String, Object> buildAllAgentsBranch(
      DashboardStats stats,
      List<TrendDay> trendRows,
      List<ActivityTrend> activityRows,
      List<AgentEfficiency> efficiencyRows,
      List<AgentBreakdown> agentBreakdown) {

    // 说明: Contribution bars 与 All Agents 表均使用全量 indexed sessions。
    Map<String, AgentBreakdown> breakdownMap = new LinkedHashMap<>();
    for (AgentBreakdown row : agentBreakdown) {
      breakdownMap.put(row.agent(), row);
    }
    long totalSessionsAll = agentBreakdown.stream().mapToLong(AgentBreakdown::sessionCount).sum();
    long totalTokensAll = agentBreakdown.stream().mapToLong(AgentBreakdown::totalTokens).sum();
    long totalPromptsAll =
        agentBreakdown.stream().mapToLong(AgentBreakdown::totalUserMessages).sum();
    AgentContributionTotals totals =
        new AgentContributionTotals(totalSessionsAll, totalTokensAll, totalPromptsAll);

    // 说明: 按固定顺序构建 agent rows：Claude Code → Qoder → Codex
    List<Map<String, Object>> agentRows = new ArrayList<>();
    agentRows.add(
        buildAgentContributionRow(
            "claude_code", "Claude Code", breakdownMap.get("claude_code"), totals));
    agentRows.add(buildAgentContributionRow("qoder", "Qoder", breakdownMap.get("qoder"), totals));
    agentRows.add(buildAgentContributionRow("codex", "Codex", breakdownMap.get("codex"), totals));

    Map<String, Object> branch = new LinkedHashMap<>();
    branch.put("agent_rows", agentRows);
    branch.put("efficiency_rows", buildEfficiencyRows(efficiencyRows, null));
    branch.put("total_sessions_all", totalSessionsAll);
    branch.put("total_tokens_all", totalTokensAll);
    branch.put("total_prompts_all", totalPromptsAll);
    branch.put("session_leader", leaderBy(agentRows, "sessions_raw"));
    branch.put("token_leader", leaderBy(agentRows, "tokens_raw"));
    branch.put("prompt_leader", leaderBy(agentRows, "prompts_raw"));
    return branch;
  }

  /**
   * Agent 贡献表的总量分母。
   *
   * @param sessions session 总数
   * @param tokens token 总数
   * @param prompts prompt 总数
   */
  private record AgentContributionTotals(
      /* 会话总数量 */
      long sessions,
      /* 令牌总数量 */
      long tokens,
      /* 提示词总数量 */
      long prompts) {}

  /** 构建单个 agent 的贡献行，包含 contribution bar 数据（range）和 All Agents 表数据（全量）。 */
  private static Map<String, Object> buildAgentContributionRow(
      String dbAgent, String display, AgentBreakdown breakdown, AgentContributionTotals totals) {
    long rangeSessions = contributionSessions(breakdown);
    long rangeTokens = contributionTokens(breakdown);
    long rangePrompts = contributionPrompts(breakdown);
    long rangeTotalSessions = totals.sessions();
    long rangeTotalTokens = totals.tokens();
    long rangeTotalPrompts = totals.prompts();
    long totalSessionsAll = totals.sessions();
    long totalTokensAll = totals.tokens();
    long totalPromptsAll = totals.prompts();

    Map<String, Object> row = new LinkedHashMap<>();
    row.put("db_agent", dbAgent);
    row.put("display", display);

    // Contribution bar 数据——使用 range 范围数据
    row.put("sessions_raw", rangeSessions);
    row.put("sessions", rangeSessions);
    row.put("tokens_raw", rangeTokens);
    row.put("tokens", formatDashboardCompact(rangeTokens));
    row.put("prompts_raw", rangePrompts);
    row.put("prompts", rangePrompts);
    row.put(
        "session_share", DisplayFormatters.percentShareLabel(rangeSessions, rangeTotalSessions));
    row.put("token_share", DisplayFormatters.percentShareLabel(rangeTokens, rangeTotalTokens));
    row.put("prompt_share", DisplayFormatters.percentShareLabel(rangePrompts, rangeTotalPrompts));
    row.put(
        "session_share_value", DisplayFormatters.percentValue(rangeSessions, rangeTotalSessions));
    row.put("token_share_value", DisplayFormatters.percentValue(rangeTokens, rangeTotalTokens));
    row.put("prompt_share_value", DisplayFormatters.percentValue(rangePrompts, rangeTotalPrompts));

    // All Agents 表数据——使用全量 breakdown 数据
    if (breakdown != null) {
      // Token bar 分段数据
      long total = Math.max(1, breakdown.totalTokens());
      row.put("token_fresh", formatDashboardCompact(breakdown.freshInputTokens()));
      row.put("token_cache_read", formatDashboardCompact(breakdown.cacheReadTokens()));
      row.put("token_cache_write", formatDashboardCompact(breakdown.cacheWriteTokens()));
      row.put("token_output", formatDashboardCompact(breakdown.outputTokens()));
      row.put("fresh_pct", Math.round(breakdown.freshInputTokens() * 1000.0 / total) / 10.0);
      row.put("read_pct", Math.round(breakdown.cacheReadTokens() * 1000.0 / total) / 10.0);
      row.put("write_pct", Math.round(breakdown.cacheWriteTokens() * 1000.0 / total) / 10.0);
      row.put("output_pct", Math.round(breakdown.outputTokens() * 1000.0 / total) / 10.0);

      // 项目数
      row.put("projects", breakdown.projectCount());
      row.put("projects_raw", breakdown.projectCount());

      // 失败率
      long failureRate =
          breakdown.totalToolCalls() > 0
              ? Math.round(breakdown.totalFailedTools() * 1000.0 / breakdown.totalToolCalls()) / 10
              : 0;
      row.put("failed", breakdown.totalFailedTools());
      row.put("failed_raw", breakdown.totalFailedTools());
      row.put(
          "failure_rate",
          String.format(
              java.util.Locale.ROOT,
              "%,d · %.1f%%",
              breakdown.totalFailedTools(),
              breakdown.totalToolCalls() > 0
                  ? breakdown.totalFailedTools() * 100.0 / breakdown.totalToolCalls()
                  : 0.0));
      row.put("failure_rate_raw", failureRate / 10.0);

      // 最后活跃时间
      String lastActive = breakdown.lastActive();
      row.put("last_active", formatLastActive(lastActive));
      row.put("last_active_raw", lastActive);

      // 全量 sessions/tokens 用于表格排序
      row.put("sessions_full_raw", breakdown.sessionCount());
      row.put("sessions_full", breakdown.sessionCount());
      row.put(
          "session_full_share",
          DisplayFormatters.percentShareLabel(breakdown.sessionCount(), totalSessionsAll));
      row.put("tokens_full_raw", breakdown.totalTokens());
      row.put("tokens_full", formatDashboardCompact(breakdown.totalTokens()));
      row.put(
          "token_full_share",
          DisplayFormatters.percentShareLabel(breakdown.totalTokens(), totalTokensAll));
      row.put("prompts_full_raw", breakdown.totalUserMessages());
      row.put("prompts_full", formatDashboardCompact(breakdown.totalUserMessages()));
      row.put(
          "prompt_full_share",
          DisplayFormatters.percentShareLabel(breakdown.totalUserMessages(), totalPromptsAll));
    } else {
      row.put("token_fresh", "0");
      row.put("token_cache_read", "0");
      row.put("token_cache_write", "0");
      row.put("token_output", "0");
      row.put("fresh_pct", 0.0);
      row.put("read_pct", 0.0);
      row.put("write_pct", 0.0);
      row.put("output_pct", 0.0);
      row.put("projects", 0);
      row.put("projects_raw", 0);
      row.put("failed", 0);
      row.put("failed_raw", 0);
      row.put("failure_rate", "0 · 0.0%");
      row.put("failure_rate_raw", 0.0);
      row.put("last_active", "");
      row.put("last_active_raw", "");
      row.put("sessions_full_raw", 0);
      row.put("sessions_full", 0);
      row.put("session_full_share", "0.0%");
      row.put("tokens_full_raw", 0);
      row.put("tokens_full", "0");
      row.put("token_full_share", "0.0%");
      row.put("prompts_full_raw", 0);
      row.put("prompts_full", 0);
      row.put("prompt_full_share", "0.0%");
    }
    return row;
  }

  /** 格式化 last active 时间为相对时间。 */
  private static String formatLastActive(String timestamp) {
    if (timestamp == null || timestamp.isEmpty()) return "";
    try {
      // 解析 ISO timestamp 格式
      java.time.Instant instant;
      if (timestamp.endsWith("Z")) {
        instant = java.time.Instant.parse(timestamp);
      } else if (timestamp.contains("+") || timestamp.contains("T")) {
        instant = java.time.OffsetDateTime.parse(timestamp).toInstant();
      } else {
        instant =
            java.time.LocalDateTime.parse(timestamp)
                .atZone(java.time.ZoneId.systemDefault())
                .toInstant();
      }
      long diffSeconds = java.time.Instant.now().getEpochSecond() - instant.getEpochSecond();
      if (diffSeconds < 60) return "Just now";
      if (diffSeconds < 3600) return (diffSeconds / 60) + " min ago";
      if (diffSeconds < 86400) return (diffSeconds / 3600) + "h ago";
      return (diffSeconds / 86400) + "d ago";
    } catch (Exception e) {
      // 如果解析失败，返回前 10 个字符
      return timestamp.length() >= 10 ? timestamp.substring(0, 10) : timestamp;
    }
  }

  private static Map<String, Object> leaderBy(List<Map<String, Object>> rows, String key) {
    Map<String, Object> leader = null;
    long leaderValue = Long.MIN_VALUE;
    for (Map<String, Object> row : rows) {
      Object valueObj = row.get(key);
      long value = valueObj instanceof Number number ? number.longValue() : 0;
      if (leader == null || value > leaderValue) {
        leader = row;
        leaderValue = value;
      }
    }
    return leader == null ? Map.of() : leader;
  }

  private static Map<String, Object> buildSingleAgentBranch(
      String agentScope, List<AgentEfficiency> efficiencyRows) {
    if ("all".equals(agentScope)) {
      return Map.of();
    }
    String dbAgent = SCOPE_TO_DB.getOrDefault(agentScope, agentScope);
    List<Map<String, Object>> rows = buildEfficiencyRows(efficiencyRows, dbAgent);
    Map<String, Object> branch = new LinkedHashMap<>();
    branch.put("db_agent", dbAgent);
    branch.put("display_name", WebDisplayValues.agentDisplay(dbAgent));
    branch.put("efficiency_rows", rows);
    branch.put("model_rows", rows);
    branch.put("model_count", rows.size());
    return branch;
  }

  private static List<Map<String, Object>> buildEfficiencyRows(
      List<AgentEfficiency> rows, String agentFilter) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (AgentEfficiency row : rows) {
      if (agentFilter != null && !agentFilter.equals(row.agent())) {
        continue;
      }
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("db_agent", row.agent());
      map.put("agent", WebDisplayValues.agentDisplay(row.agent()));
      map.put("model", row.model());
      map.put("sessions_raw", row.sessionCount());
      map.put("sessions", row.sessionCount());
      map.put("tokens_per_session_raw", row.avgTotalTokens());
      map.put("tokens_per_session", formatDashboardCompact(row.avgTotalTokens()));
      map.put("avg_tokens", formatDashboardCompact(row.avgTotalTokens()));
      map.put("avg_process_time", DisplayFormatters.formatDuration(row.avgDuration()));
      map.put("cache_read_raw", row.cacheReuseRatio() == null ? -1 : row.cacheReuseRatio());
      map.put(
          "cache_read",
          row.cacheReuseRatio() == null ? "N/A" : percentLabel(row.cacheReuseRatio()));
      map.put("failure_raw", row.failedPerSession() == null ? 0.0 : row.failedPerSession());
      map.put(
          "failure",
          String.format(
              java.util.Locale.ROOT,
              "%.2f / session",
              row.failedPerSession() == null ? 0.0 : row.failedPerSession()));
      map.put(
          "tool_calls_per_session",
          row.avgTools() == 0.0
              ? "—"
              : String.format(java.util.Locale.ROOT, "%.1f", row.avgTools()));
      map.put("notes", row.cacheReuseRatio() == null ? "N/A" : "Provider reported");
      result.add(map);
    }
    return result;
  }

  private static long contributionSessions(AgentBreakdown row) {
    return row == null ? 0 : row.sessionCount();
  }

  private static long contributionTokens(AgentBreakdown row) {
    return row == null ? 0 : row.totalTokens();
  }

  private static long contributionPrompts(AgentBreakdown row) {
    return row == null ? 0 : row.totalUserMessages();
  }

  private static String formatDashboardTrendTokens(long value) {
    if (value <= 0) {
      return "0";
    }
    return String.format(java.util.Locale.ROOT, "%.1fM", value / COMPACT_MILLION);
  }

  private static String scopeToCachePrefix(String agentScope) {
    return switch (agentScope) {
      case "claude-code" -> "claude_code";
      case "qoder" -> "qoder";
      case "codex" -> "codex";
      default -> "average";
    };
  }

  private static String percentLabel(Double ratio) {
    if (ratio == null) {
      return "—";
    }
    return String.format("%.1f%%", ratio * 100.0);
  }
}
