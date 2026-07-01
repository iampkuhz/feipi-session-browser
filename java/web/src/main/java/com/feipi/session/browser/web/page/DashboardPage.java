package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.DashboardUseCase;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.sqlite.ActivityTrendRow;
import com.feipi.session.browser.index.sqlite.AgentEfficiencyRow;
import com.feipi.session.browser.index.sqlite.DashboardRow;
import com.feipi.session.browser.index.sqlite.KpiSupplementRow;
import com.feipi.session.browser.index.sqlite.TrendDayRow;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import com.feipi.session.browser.web.template.DisplayFormatters;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.sql.SQLException;
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
      DashboardRow stats = useCase.stats(agentFilter);
      KpiSupplementRow kpiSupplement = useCase.kpiSupplement(agentFilter);

      // 趋势数据
      int days = GRAIN_DAYS.getOrDefault(grain, 30);
      TrendFilter trendFilter = TrendFilter.ofDays(days);
      if (!agentFilter.isUnfiltered()) {
        trendFilter = trendFilter.withAgent(agentFilter);
      }
      List<TrendDayRow> trendRows = useCase.trendData(trendFilter);
      List<ActivityTrendRow> activityRows = useCase.activityTrend(trendFilter);
      List<AgentEfficiencyRow> efficiencyRows = useCase.agentEfficiency();

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
      Map<String, Object> cacheHealth = buildCacheHealth(trendRows, agentScope);
      context.put("cache_health", cacheHealth);
      context.put("chart_notes", buildChartNotes());
      context.put("dashboard_summary", buildDashboardSummary(trendRows, activityRows, cacheHealth));
      context.put("all_agents_branch", buildAllAgentsBranch(stats, trendRows, activityRows, efficiencyRows));
      context.put("single_agent_branch", buildSingleAgentBranch(agentScope, efficiencyRows));
      context.put("needs_attention", List.of());
      context.put("agent_sessions_total", stats.totalSessions());
      context.put("agent_sessions_page", 1);
      context.put("agent_sessions_total_pages", 1);
      context.put("agent_sessions_page_size", stats.totalSessions());

      String html = templates.render("dashboard.html", context);
      ctx.html(html);

    } catch (SQLException e) {
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
      DashboardRow stats,
      KpiSupplementRow supplement,
      List<TrendDayRow> trendRows,
      List<ActivityTrendRow> activityRows) {
    long inputSide =
        stats.totalFreshInputTokens() + stats.totalCacheReadTokens() + stats.totalCacheWriteTokens();
    long totalSessions = stats.totalSessions();
    long totalToolCalls = stats.totalToolCalls();
    long totalFailedTools = stats.totalFailedTools();
    long totalUserMessages = stats.totalUserMessages();
    long totalAssistantMessages = stats.totalAssistantMessages();

    // 说明:Badge 计算——对比当前可见窗口最后两个 range point
    long latestSessions = trendRows.isEmpty() ? 0 : trendRows.get(trendRows.size() - 1).totalCount();
    long prevSessions =
        trendRows.size() < 2 ? 0 : trendRows.get(trendRows.size() - 2).totalCount();
    long sessionDelta = latestSessions - prevSessions;

    long latestTokens =
        trendRows.isEmpty() ? 0 : trendRows.get(trendRows.size() - 1).totalTokens();
    long prevTokens =
        trendRows.size() < 2 ? 0 : trendRows.get(trendRows.size() - 2).totalTokens();

    long latestPrompts =
        activityRows.isEmpty() ? 0 : activityRows.get(activityRows.size() - 1).totalPrompts();
    long prevPrompts =
        activityRows.size() < 2 ? 0 : activityRows.get(activityRows.size() - 2).totalPrompts();
    long promptDelta = latestPrompts - prevPrompts;

    long latestFailed =
        trendRows.isEmpty() ? 0 : trendRows.get(trendRows.size() - 1).failedTools();
    long prevFailed =
        trendRows.size() < 2 ? 0 : trendRows.get(trendRows.size() - 2).failedTools();
    long failedDelta = latestFailed - prevFailed;

    // 说明:Cache Read Ratio badge——最后两个可计算点的百分点变化
    String cacheRatioBadge = null;
    String cacheRatioBadgeTone = "neutral";
    {
      Double latest = null;
      Double prev = null;
      for (int i = trendRows.size() - 1; i >= 0 && latest == null; i--) {
        TrendDayRow r = trendRows.get(i);
        long is = r.freshInputTokens() + r.cacheReadTokens() + r.cacheWriteTokens();
        if (is > 0) {
          latest = (double) r.cacheReadTokens() / is;
          for (int j = i - 1; j >= 0; j--) {
            TrendDayRow p = trendRows.get(j);
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
    String projectBadge =
        projectDelta >= 0 ? "+" + projectDelta : String.valueOf(projectDelta);
    String projectBadgeTone = projectDelta >= 0 ? "positive" : "negative";

    // 说明:Sessions badge
    String sessionBadge;
    String sessionBadgeTone;
    if (prevSessions > 0) {
      double pct = ((double) (latestSessions - prevSessions) / prevSessions) * 100.0;
      sessionBadge = String.format(java.util.Locale.ROOT, "%+.1f%%", pct);
    } else {
      sessionBadge = latestSessions > 0 ? "+" + latestSessions : "0";
    }
    sessionBadgeTone = sessionDelta >= 0 ? "positive" : "negative";

    // 说明:Prompt Activity badge
    String promptBadge;
    String promptBadgeTone;
    if (prevPrompts > 0) {
      double pct = ((double) (latestPrompts - prevPrompts) / prevPrompts) * 100.0;
      promptBadge = String.format(java.util.Locale.ROOT, "%+.1f%%", pct);
    } else {
      promptBadge = latestPrompts > 0 ? "+" + latestPrompts : "0";
    }
    promptBadgeTone = promptDelta >= 0 ? "positive" : "negative";

    // 说明:Failed Tools badge
    String failedBadge;
    String failedBadgeTone;
    if (prevFailed > 0) {
      double pct = ((double) (latestFailed - prevFailed) / prevFailed) * 100.0;
      failedBadge = String.format(java.util.Locale.ROOT, "%+.1f%%", pct);
    } else {
      failedBadge = latestFailed > 0 ? "+" + latestFailed : "0";
    }
    failedBadgeTone = failedDelta <= 0 ? "positive" : "negative";

    // 说明:二级指标计算
    double avgRounds =
        totalSessions > 0 ? (double) totalAssistantMessages / totalSessions : 0;
    double promptsPerSession =
        totalSessions > 0 ? (double) totalUserMessages / totalSessions : 0;
    Double cacheRatio = inputSide > 0 ? (double) stats.totalCacheReadTokens() / inputSide : null;
    Double failureRate =
        totalToolCalls > 0 ? (double) totalFailedTools / totalToolCalls : null;

    return List.of(
        kpi(
            "Projects",
            stats.projectCount(),
            "当前 scope 下出现过 session 的 project 数量",
            "🗂",
            "purple",
            projectBadge,
            projectBadgeTone,
            List.of(
                secondary(
                    "Active 24h",
                    supplement.activeProjects24h(),
                    "最近 24 小时内有 session event 的 project 去重数。"),
                secondary(
                    "Active 7d",
                    supplement.activeProjects7d(),
                    "最近 7 个自然日内有 session event 的 project 去重数。"),
                secondary(
                    "New 7d",
                    supplement.newProjects7d(),
                    "first seen timestamp 落在最近 7 个自然日内的 project 去重数。"))),
        kpi(
            "Sessions",
            totalSessions,
            "当前 scope 下已索引 session 总数",
            "🧵",
            "blue",
            sessionBadge,
            sessionBadgeTone,
            List.of(
                secondary(
                    "Today",
                    supplement.todaySessions(),
                    "first user message timestamp 落在当前自然日内的 session 数。"),
                secondary(
                    "7d Avg",
                    String.format(java.util.Locale.ROOT, "%.1f", supplement.avgDailySessions7d()),
                    "最近 7 个自然日每日 session 数的算术平均值。"),
                secondary(
                    "Median Duration",
                    DisplayFormatters.formatDuration(supplement.medianDurationSeconds()),
                    "当前 scope 下 session duration 的中位数。"),
                secondary(
                    "Avg Rounds",
                    String.format(java.util.Locale.ROOT, "%.1f", avgRounds),
                    "当前 scope 下每个 session 的 LLM round 数平均值。"))),
        kpi(
            "Total Tokens",
            DisplayFormatters.formatCompactToken(stats.totalTokens()),
            "Fresh + Cache Read + Cache Write + Output",
            "🧮",
            "orange",
            tokenBadge,
            tokenBadgeTone,
            List.of(
                secondary(
                    "Fresh",
                    DisplayFormatters.formatCompactToken(stats.totalFreshInputTokens()),
                    "互斥的新输入分段，已扣除 cache read 子集。"),
                secondary(
                    "Cache Read",
                    DisplayFormatters.formatCompactToken(stats.totalCacheReadTokens()),
                    "从缓存读取并计入输入侧的 token 数。"),
                secondary(
                    "Cache Write",
                    DisplayFormatters.formatCompactToken(stats.totalCacheWriteTokens()),
                    "写入缓存并计入输入侧的 token 数。"),
                secondary(
                    "Output",
                    DisplayFormatters.formatCompactToken(stats.totalOutputTokens()),
                    "模型输出 token 数。"))),
        kpi(
            "Prompt Activity",
            totalUserMessages,
            "用户发起输入数量，按 user message 事件计数",
            "💬",
            "green",
            promptBadge,
            promptBadgeTone,
            List.of(
                secondary(
                    "Assistant Turns",
                    totalAssistantMessages,
                    "assistant message 事件总数。"),
                secondary(
                    "Tool Calls",
                    totalToolCalls,
                    "tool call 事件总数，不区分成功和失败。"),
                secondary(
                    "Prompts / Session",
                    totalSessions > 0
                        ? String.format(java.util.Locale.ROOT, "%.1f", promptsPerSession)
                        : "N/A",
                    "User Prompts / Sessions；sessions 为 0 时显示 N/A。"))),
        kpi(
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
                    supplement.eligibleSessions(),
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
                    supplement.lowReadSessions(),
                    "eligible sessions 中 per-session cache read ratio 小于 20.0% 的 session 数。"))),
        kpi(
            "Failed Tools",
            totalFailedTools,
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
                    supplement.affectedFailureSessions(),
                    "failed tool result 数量大于 0 的 session 数。"),
                secondary(
                    "Repeated Failure Sessions",
                    supplement.repeatedFailureSessions(),
                    "failed tool result 数量大于 1 的 session 数。"))));
  }

  private static Map<String, Object> kpi(
      String label,
      Object value,
      String description,
      String icon,
      String iconColor,
      String badge,
      String badgeTone,
      List<Map<String, Object>> secondary) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("label", label);
    row.put("value", value);
    row.put("description", description);
    row.put("icon", icon);
    row.put("icon_color", iconColor);
    row.put("badge", badge);
    row.put("badge_tone", badgeTone == null ? "neutral" : badgeTone);
    row.put("badge_description", badge == null ? "" : description);
    row.put("secondary", secondary == null ? List.of() : secondary);
    return row;
  }

  private static Map<String, Object> secondary(String label, Object value, String description) {
    return Map.of("label", label, "value", value, "description", description);
  }

  private static List<Map<String, Object>> buildTrend(List<TrendDayRow> rows) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (TrendDayRow row : rows) {
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

  private static List<Map<String, Object>> buildPromptActivity(List<ActivityTrendRow> rows) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (ActivityTrendRow row : rows) {
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

  private static Map<String, Object> buildCacheHealth(List<TrendDayRow> rows, String agentScope) {
    List<Map<String, Object>> series = new ArrayList<>();
    String scopedPrefix = scopeToCachePrefix(agentScope);
    Double latestRatio = null;
    Double lowestRatio = null;
    for (TrendDayRow row : rows) {
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("date", row.date());
      map.put("average_fresh_input_tokens", row.freshInputTokens());
      map.put("average_cache_read_tokens", row.cacheReadTokens());
      map.put("average_cache_write_tokens", row.cacheWriteTokens());
      map.put("claude_code_fresh_input_tokens", 0);
      map.put("claude_code_cache_read_tokens", 0);
      map.put("claude_code_cache_write_tokens", 0);
      map.put("codex_fresh_input_tokens", 0);
      map.put("codex_cache_read_tokens", 0);
      map.put("codex_cache_write_tokens", 0);
      map.put("qoder_fresh_input_tokens", 0);
      map.put("qoder_cache_read_tokens", 0);
      map.put("qoder_cache_write_tokens", 0);
      map.put("qoder_unreported_input_side_tokens", 0);
      if (!"average".equals(scopedPrefix)) {
        map.put(scopedPrefix + "_fresh_input_tokens", row.freshInputTokens());
        map.put(scopedPrefix + "_cache_read_tokens", row.cacheReadTokens());
        map.put(scopedPrefix + "_cache_write_tokens", row.cacheWriteTokens());
      }
      series.add(map);
      Double ratio =
          ratio(row.cacheReadTokens(), row.freshInputTokens() + row.cacheReadTokens() + row.cacheWriteTokens());
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

  private static Map<String, Object> buildDashboardSummary(
      List<TrendDayRow> trendRows,
      List<ActivityTrendRow> activityRows,
      Map<String, Object> cacheHealth) {
    Map<String, Object> summary = new LinkedHashMap<>();
    long totalSessions = trendRows.stream().mapToLong(TrendDayRow::totalCount).sum();
    long totalTokens = trendRows.stream().mapToLong(TrendDayRow::totalTokens).sum();
    long totalPrompts = activityRows.stream().mapToLong(ActivityTrendRow::totalPrompts).sum();
    summary.put(
        "latest_sessions", trendRows.isEmpty() ? "—" : trendRows.get(trendRows.size() - 1).totalCount());
    summary.put("range_total_sessions", totalSessions);
    summary.put(
        "latest_tokens",
        trendRows.isEmpty()
            ? "0"
            : DisplayFormatters.formatCompactToken(trendRows.get(trendRows.size() - 1).totalTokens()));
    summary.put("range_total_tokens", DisplayFormatters.formatCompactToken(totalTokens));
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
    notes.put("sessions", "按所选时间粒度展示各 agent session 数。");
    notes.put("prompts", "按用户 prompt、助手轮次与工具调用展示活动趋势。");
    notes.put("tokens", "按 Fresh、Cache Read、Cache Write、Output 组件展示 token 趋势。");
    notes.put("cache_health", "展示缓存读取在输入侧 token 中的占比；缺失明细不以假数据补齐。");
    notes.put("model_mix", "当前 Java index 暂未暴露完整模型占比图数据时显示明细表或空态。");
    notes.put("tool_dist", "当前 index 保存聚合工具调用数，不保存工具名称分布。");
    return notes;
  }

  private static Map<String, Object> buildAllAgentsBranch(
      DashboardRow stats,
      List<TrendDayRow> trendRows,
      List<ActivityTrendRow> activityRows,
      List<AgentEfficiencyRow> efficiencyRows) {
    List<Map<String, Object>> agentRows = new ArrayList<>();
    long claudeTokens = trendRows.stream().mapToLong(TrendDayRow::claudeTokens).sum();
    long codexTokens = trendRows.stream().mapToLong(TrendDayRow::codexTokens).sum();
    long qoderTokens = trendRows.stream().mapToLong(TrendDayRow::qoderTokens).sum();
    long claudePrompts = activityRows.stream().mapToLong(ActivityTrendRow::claudePrompts).sum();
    long codexPrompts = activityRows.stream().mapToLong(ActivityTrendRow::codexPrompts).sum();
    long qoderPrompts = activityRows.stream().mapToLong(ActivityTrendRow::qoderPrompts).sum();

    agentRows.add(
        agentRow(
            "claude_code",
            "Claude Code",
            stats.claudeSessions(),
            claudeTokens,
            claudePrompts,
            stats.totalSessions(),
            stats.totalTokens(),
            stats.totalUserMessages()));
    agentRows.add(
        agentRow(
            "codex",
            "Codex",
            stats.codexSessions(),
            codexTokens,
            codexPrompts,
            stats.totalSessions(),
            stats.totalTokens(),
            stats.totalUserMessages()));
    agentRows.add(
        agentRow(
            "qoder",
            "Qoder",
            stats.qoderSessions(),
            qoderTokens,
            qoderPrompts,
            stats.totalSessions(),
            stats.totalTokens(),
            stats.totalUserMessages()));

    Map<String, Object> branch = new LinkedHashMap<>();
    branch.put("agent_rows", agentRows);
    branch.put("efficiency_rows", buildEfficiencyRows(efficiencyRows, null));
    branch.put("total_sessions_all", stats.totalSessions());
    branch.put("total_tokens_all", stats.totalTokens());
    branch.put("total_prompts_all", stats.totalUserMessages());
    branch.put("session_leader", leaderBy(agentRows, "sessions_raw"));
    branch.put("token_leader", leaderBy(agentRows, "tokens_raw"));
    branch.put("prompt_leader", leaderBy(agentRows, "prompts_raw"));
    return branch;
  }

  private static Map<String, Object> agentRow(
      String dbAgent,
      String display,
      long sessions,
      long tokens,
      long prompts,
      long totalSessions,
      long totalTokens,
      long totalPrompts) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("db_agent", dbAgent);
    row.put("display", display);
    row.put("sessions_raw", sessions);
    row.put("sessions", sessions);
    row.put("tokens_raw", tokens);
    row.put("tokens", DisplayFormatters.formatCompactToken(tokens));
    row.put("prompts_raw", prompts);
    row.put("prompts", prompts);
    row.put("session_share", ratioLabel(sessions, totalSessions));
    row.put("token_share", ratioLabel(tokens, totalTokens));
    row.put("prompt_share", ratioLabel(prompts, totalPrompts));
    row.put("session_share_value", DisplayFormatters.percentValue(sessions, totalSessions));
    row.put("token_share_value", DisplayFormatters.percentValue(tokens, totalTokens));
    row.put("prompt_share_value", DisplayFormatters.percentValue(prompts, totalPrompts));
    return row;
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
      String agentScope, List<AgentEfficiencyRow> efficiencyRows) {
    if ("all".equals(agentScope)) {
      return Map.of();
    }
    String dbAgent = SCOPE_TO_DB.getOrDefault(agentScope, agentScope);
    List<Map<String, Object>> rows = buildEfficiencyRows(efficiencyRows, dbAgent);
    Map<String, Object> branch = new LinkedHashMap<>();
    branch.put("db_agent", dbAgent);
    branch.put("display_name", agentDisplay(dbAgent));
    branch.put("efficiency_rows", rows);
    branch.put("model_rows", rows);
    branch.put("model_count", rows.size());
    return branch;
  }

  private static List<Map<String, Object>> buildEfficiencyRows(
      List<AgentEfficiencyRow> rows, String agentFilter) {
    List<Map<String, Object>> result = new ArrayList<>();
    for (AgentEfficiencyRow row : rows) {
      if (agentFilter != null && !agentFilter.equals(row.agent())) {
        continue;
      }
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("db_agent", row.agent());
      map.put("agent", agentDisplay(row.agent()));
      map.put("model", row.model());
      map.put("sessions_raw", row.sessionCount());
      map.put("sessions", row.sessionCount());
      map.put("tokens_per_session_raw", row.avgInputSide());
      map.put("tokens_per_session", DisplayFormatters.formatCompactToken(row.avgInputSide()));
      map.put("avg_tokens", DisplayFormatters.formatCompactToken(row.avgInputSide()));
      map.put("avg_process_time", DisplayFormatters.formatDuration(row.avgDuration()));
      map.put("cache_read_raw", row.cacheReuseRatio() == null ? 0 : row.cacheReuseRatio());
      map.put("cache_read", percentLabel(row.cacheReuseRatio()));
      map.put("failure_raw", row.failedPerSession() == null ? 0 : row.failedPerSession());
      map.put("failure", row.failedPerSession() == null ? "—" : String.format("%.2f", row.failedPerSession()));
      map.put(
          "tool_calls_per_session",
          row.avgTools() == 0.0 ? "—" : String.format("%.1f", row.avgTools()));
      map.put("notes", row.cacheReuseRatio() == null ? "No cache ratio" : "Provider reported");
      result.add(map);
    }
    return result;
  }

  private static String agentDisplay(String dbAgent) {
    return switch (dbAgent) {
      case "claude_code" -> "Claude Code";
      case "qoder" -> "Qoder";
      case "codex" -> "Codex";
      default -> dbAgent == null || dbAgent.isEmpty() ? "Unknown" : dbAgent;
    };
  }

  private static String scopeToCachePrefix(String agentScope) {
    return switch (agentScope) {
      case "claude-code" -> "claude_code";
      case "qoder" -> "qoder";
      case "codex" -> "codex";
      default -> "average";
    };
  }

  private static Double ratio(long numerator, long denominator) {
    if (denominator <= 0) {
      return null;
    }
    return (double) numerator / (double) denominator;
  }

  private static String ratioLabel(long numerator, long denominator) {
    return percentLabel(ratio(numerator, denominator));
  }

  private static String percentLabel(Double ratio) {
    if (ratio == null) {
      return "—";
    }
    return String.format("%.1f%%", ratio * 100.0);
  }
}
