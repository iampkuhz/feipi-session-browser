package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.api.query.ActivityTrend;
import com.feipi.session.browser.index.api.query.AgentBreakdown;
import com.feipi.session.browser.index.api.query.AgentEfficiency;
import com.feipi.session.browser.index.api.query.DashboardStats;
import com.feipi.session.browser.index.api.query.TrendDay;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import com.feipi.session.browser.web.api.DashboardApiResponses.AgentContributionDto;
import com.feipi.session.browser.web.api.DashboardApiResponses.AgentCounts;
import com.feipi.session.browser.web.api.DashboardApiResponses.AgentEfficiencyDto;
import com.feipi.session.browser.web.api.DashboardApiResponses.AgentsContributionResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.AgentsEfficiencyResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.CacheHealthPoint;
import com.feipi.session.browser.web.api.DashboardApiResponses.CacheInputDto;
import com.feipi.session.browser.web.api.DashboardApiResponses.DashboardCacheHealthResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.DashboardFilterEcho;
import com.feipi.session.browser.web.api.DashboardApiResponses.DashboardPromptTrendResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.DashboardSessionsTrendResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.DashboardSummaryResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.DashboardTokenTrendResponse;
import com.feipi.session.browser.web.api.DashboardApiResponses.PromptTrendPoint;
import com.feipi.session.browser.web.api.DashboardApiResponses.RatioDto;
import com.feipi.session.browser.web.api.DashboardApiResponses.SessionTrendPoint;
import com.feipi.session.browser.web.api.DashboardApiResponses.TokenTrendPoint;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.model.WebDisplayValues;
import io.javalin.http.Context;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Dashboard 页面的资源 API。 */
public final class DashboardApiHandler {

  private static final Set<String> VALID_AGENT_SCOPES =
      Set.of("all", "claude-code", "qoder", "codex");
  private static final Set<String> VALID_GRAINS = Set.of("day", "week", "month");
  private static final Map<String, String> SCOPE_TO_DB =
      Map.of("claude-code", "claude_code", "qoder", "qoder", "codex", "codex");
  private static final Map<String, Integer> GRAIN_DAYS =
      Map.of("day", 30, "week", 140, "month", 360);

  private final QueryCompositionRoot queryRoot;

  /** 创建对应对象。 */
  public DashboardApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
  }

  /** 处理 /api/dashboard/summary 的 GET 请求。 */
  public void handleSummary(Context ctx) {
    DashboardRequest request = request(ctx);
    DashboardStats stats = queryRoot.dashboard().stats(request.agentFilter());
    long inputSide =
        stats.totalFreshInputTokens()
            + stats.totalCacheReadTokens()
            + stats.totalCacheWriteTokens();
    Double cacheReadRatio =
        inputSide > 0 ? stats.totalCacheReadTokens() / (double) inputSide : null;
    ctx.json(
        new DashboardSummaryResponse(
            ApiResponses.SCHEMA_VERSION,
            request.echo(),
            stats.totalSessions(),
            stats.projectCount(),
            new AgentCounts(
                stats.claudeSessions(),
                stats.codexSessions(),
                stats.qoderSessions(),
                stats.totalSessions()),
            TokenSegments.of(
                stats.totalFreshInputTokens(),
                stats.totalCacheReadTokens(),
                stats.totalCacheWriteTokens(),
                stats.totalOutputTokens()),
            stats.totalToolCalls(),
            stats.totalFailedTools(),
            stats.totalUserMessages(),
            stats.totalAssistantMessages(),
            RatioDto.of(cacheReadRatio),
            readyOrEmpty(stats.totalSessions(), "No dashboard data yet")));
  }

  /** 处理 /api/dashboard/trends/sessions 的 GET 请求。 */
  public void handleSessionsTrend(Context ctx) {
    DashboardRequest request = request(ctx);
    List<TrendDay> rows = queryRoot.dashboard().trendData(request.trendFilter());
    List<SessionTrendPoint> points =
        rows.stream().map(DashboardApiHandler::sessionTrendPoint).toList();
    long rangeTotal = points.stream().mapToLong(SessionTrendPoint::totalCount).sum();
    ctx.json(
        new DashboardSessionsTrendResponse(
            ApiResponses.SCHEMA_VERSION,
            request.echo(),
            rangeTotal,
            points,
            readyOrEmpty(rangeTotal, "No session trend data in the selected range")));
  }

  /** 处理 /api/dashboard/trends/tokens 的 GET 请求。 */
  public void handleTokenTrend(Context ctx) {
    DashboardRequest request = request(ctx);
    List<TrendDay> rows = queryRoot.dashboard().trendData(request.trendFilter());
    List<TokenTrendPoint> points = rows.stream().map(DashboardApiHandler::tokenTrendPoint).toList();
    long fresh = rows.stream().mapToLong(TrendDay::freshInputTokens).sum();
    long cacheRead = rows.stream().mapToLong(TrendDay::cacheReadTokens).sum();
    long cacheWrite = rows.stream().mapToLong(TrendDay::cacheWriteTokens).sum();
    long output = rows.stream().mapToLong(TrendDay::outputTokens).sum();
    ctx.json(
        new DashboardTokenTrendResponse(
            ApiResponses.SCHEMA_VERSION,
            request.echo(),
            TokenSegments.of(fresh, cacheRead, cacheWrite, output),
            points,
            readyOrEmpty(fresh + cacheRead + cacheWrite + output, "No token trend data")));
  }

  /** 处理 /api/dashboard/trends/prompts 的 GET 请求。 */
  public void handlePromptTrend(Context ctx) {
    DashboardRequest request = request(ctx);
    List<ActivityTrend> rows = queryRoot.dashboard().activityTrend(request.trendFilter());
    List<PromptTrendPoint> points =
        rows.stream().map(DashboardApiHandler::promptTrendPoint).toList();
    long rangeTotal = points.stream().mapToLong(PromptTrendPoint::totalPrompts).sum();
    ctx.json(
        new DashboardPromptTrendResponse(
            ApiResponses.SCHEMA_VERSION,
            request.echo(),
            rangeTotal,
            points,
            readyOrEmpty(rangeTotal, "No prompt trend data in the selected range")));
  }

  /** 处理 /api/dashboard/trends/cache-health 的 GET 请求。 */
  public void handleCacheHealth(Context ctx) {
    DashboardRequest request = request(ctx);
    List<TrendDay> rows = queryRoot.dashboard().trendData(request.trendFilter());
    List<CacheHealthPoint> points =
        rows.stream().map(DashboardApiHandler::cacheHealthPoint).toList();
    List<Double> ratios =
        points.stream()
            .map(point -> point.average().ratio().value())
            .filter(Objects::nonNull)
            .toList();
    Double latest = ratios.isEmpty() ? null : ratios.get(ratios.size() - 1);
    Double lowest = ratios.stream().min(Comparator.naturalOrder()).orElse(null);
    ctx.json(
        new DashboardCacheHealthResponse(
            ApiResponses.SCHEMA_VERSION,
            request.echo(),
            RatioDto.of(latest),
            RatioDto.of(lowest),
            points,
            readyOrEmpty(points.size(), "No cache health data in the selected range")));
  }

  /** 处理 /api/dashboard/agents/contribution 的 GET 请求。 */
  public void handleAgentContribution(Context ctx) {
    DashboardRequest request = request(ctx);
    List<AgentBreakdown> breakdown = queryRoot.dashboard().agentBreakdown();
    TokenSegments totals =
        TokenSegments.of(
            breakdown.stream().mapToLong(AgentBreakdown::freshInputTokens).sum(),
            breakdown.stream().mapToLong(AgentBreakdown::cacheReadTokens).sum(),
            breakdown.stream().mapToLong(AgentBreakdown::cacheWriteTokens).sum(),
            breakdown.stream().mapToLong(AgentBreakdown::outputTokens).sum());
    long totalSessions = breakdown.stream().mapToLong(AgentBreakdown::sessionCount).sum();
    long totalPrompts = breakdown.stream().mapToLong(AgentBreakdown::totalUserMessages).sum();
    Map<String, AgentBreakdown> breakdownByAgent = new LinkedHashMap<>();
    breakdown.forEach(row -> breakdownByAgent.put(row.agent(), row));
    List<AgentContributionDto> rows =
        List.of("claude_code", "qoder", "codex").stream()
            .map(
                agent ->
                    contributionRow(
                        agent,
                        breakdownByAgent.get(agent),
                        totalSessions,
                        totals.total(),
                        totalPrompts))
            .toList();
    ctx.json(
        new AgentsContributionResponse(
            ApiResponses.SCHEMA_VERSION,
            request.echo(),
            totalSessions,
            totals,
            totalPrompts,
            rows,
            readyOrEmpty(totalSessions, "No agent contribution data yet")));
  }

  /** 处理 /api/dashboard/agents/efficiency 的 GET 请求。 */
  public void handleAgentEfficiency(Context ctx) {
    DashboardRequest request = request(ctx);
    ctx.json(efficiencyResponse(request, AgentFilter.NONE));
  }

  /** 处理 /api/dashboard/agents/{agent}/deep-dive 的 GET 请求。 */
  public void handleAgentDeepDive(Context ctx) {
    String scope = normalizeAgentScope(ctx.pathParam("agent"));
    DashboardRequest request = request(ctx, scope);
    ctx.json(efficiencyResponse(request, request.agentFilter()));
  }

  private AgentsEfficiencyResponse efficiencyResponse(
      DashboardRequest request, AgentFilter agentFilter) {
    List<AgentEfficiencyDto> rows =
        queryRoot.dashboard().agentEfficiency().stream()
            .filter(row -> agentFilter.isUnfiltered() || agentFilter.agent().equals(row.agent()))
            .map(DashboardApiHandler::efficiencyRow)
            .toList();
    return new AgentsEfficiencyResponse(
        ApiResponses.SCHEMA_VERSION,
        request.echo(),
        rows,
        rows.isEmpty()
            ? PageStateDto.empty("No efficiency data yet", "No model rows are available.")
            : PageStateDto.ready());
  }

  private DashboardRequest request(Context ctx) {
    return request(ctx, normalizeAgentScope(ApiQueryParams.flat(ctx).getOrDefault("agent", "all")));
  }

  private DashboardRequest request(Context ctx, String agentScope) {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    String grain = normalizeGrain(params.getOrDefault("grain", "day"));
    int days = GRAIN_DAYS.getOrDefault(grain, 30);
    AgentFilter agentFilter = buildAgentFilter(agentScope);
    TrendFilter trendFilter = TrendFilter.ofDays(days);
    if (!agentFilter.isUnfiltered()) {
      trendFilter = trendFilter.withAgent(agentFilter);
    }
    return new DashboardRequest(
        new DashboardFilterEcho(agentScope, grain, days), agentFilter, trendFilter);
  }

  private static SessionTrendPoint sessionTrendPoint(TrendDay row) {
    return new SessionTrendPoint(
        row.date(),
        row.totalCount(),
        row.claudeCount(),
        row.codexCount(),
        row.qoderCount(),
        row.toolCalls(),
        row.failedTools());
  }

  private static TokenTrendPoint tokenTrendPoint(TrendDay row) {
    return new TokenTrendPoint(
        row.date(),
        TokenSegments.of(
            row.freshInputTokens(),
            row.cacheReadTokens(),
            row.cacheWriteTokens(),
            row.outputTokens()),
        row.claudeTokens(),
        row.codexTokens(),
        row.qoderTokens());
  }

  private static PromptTrendPoint promptTrendPoint(ActivityTrend row) {
    return new PromptTrendPoint(
        row.date(),
        row.totalPrompts(),
        row.claudePrompts(),
        row.codexPrompts(),
        row.qoderPrompts(),
        row.assistantTurns(),
        row.toolCalls());
  }

  private static CacheHealthPoint cacheHealthPoint(TrendDay row) {
    return new CacheHealthPoint(
        row.date(),
        CacheInputDto.of(row.freshInputTokens(), row.cacheReadTokens(), row.cacheWriteTokens()),
        CacheInputDto.of(row.claudeFreshInput(), row.claudeCacheRead(), row.claudeCacheWrite()),
        CacheInputDto.of(row.codexFreshInput(), row.codexCacheRead(), row.codexCacheWrite()),
        CacheInputDto.of(row.qoderFreshInput(), row.qoderCacheRead(), row.qoderCacheWrite()));
  }

  private static AgentContributionDto contributionRow(
      String agent,
      AgentBreakdown row,
      long totalSessions,
      long totalTokens,
      long totalPrompts) {
    if (row == null) {
      return new AgentContributionDto(
          agent,
          WebDisplayValues.agentDisplay(agent),
          0,
          TokenSegments.of(0, 0, 0, 0),
          0,
          0,
          0,
          0,
          0.0,
          0.0,
          0.0);
    }
    return new AgentContributionDto(
        row.agent(),
        WebDisplayValues.agentDisplay(row.agent()),
        row.sessionCount(),
        TokenSegments.of(
            row.freshInputTokens(),
            row.cacheReadTokens(),
            row.cacheWriteTokens(),
            row.outputTokens()),
        row.totalUserMessages(),
        row.projectCount(),
        row.totalToolCalls(),
        row.totalFailedTools(),
        WebDisplayValues.share(row.sessionCount(), totalSessions),
        WebDisplayValues.share(row.totalTokens(), totalTokens),
        WebDisplayValues.share(row.totalUserMessages(), totalPrompts));
  }

  private static AgentEfficiencyDto efficiencyRow(AgentEfficiency row) {
    return new AgentEfficiencyDto(
        row.agent(),
        row.model(),
        row.sessionCount(),
        row.avgDuration(),
        row.p95Duration(),
        row.avgTotalTokens(),
        row.avgTools(),
        row.toolsPerRound(),
        row.cacheReuseRatio(),
        row.failedPerSession());
  }

  private static PageStateDto readyOrEmpty(long count, String emptyTitle) {
    return count > 0
        ? PageStateDto.ready()
        : PageStateDto.empty(emptyTitle, "Run a scan before opening this Dashboard resource.");
  }

  private static String normalizeAgentScope(String value) {
    return value == null || !VALID_AGENT_SCOPES.contains(value) ? "all" : value;
  }

  private static String normalizeGrain(String value) {
    return value == null || !VALID_GRAINS.contains(value) ? "day" : value;
  }

  private static AgentFilter buildAgentFilter(String agentScope) {
    if ("all".equals(agentScope)) {
      return AgentFilter.NONE;
    }
    String dbAgent = SCOPE_TO_DB.getOrDefault(agentScope, "");
    return dbAgent.isEmpty() ? AgentFilter.NONE : AgentFilter.of(dbAgent);
  }

  /**
   * 表示 DashboardRequest 数据。
   *
   * @param echo 该字段在 API 响应中的业务值。
   * @param agentFilter 该字段在 API 响应中的业务值。
   * @param trendFilter 该字段在 API 响应中的业务值。
   */
  private record DashboardRequest(
      DashboardFilterEcho echo, AgentFilter agentFilter, TrendFilter trendFilter) {}
}
