package com.feipi.session.browser.web.page;

import com.feipi.session.browser.application.ProjectListUseCase;
import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.ProjectStatsRow;
import com.feipi.session.browser.index.sqlite.SessionListAggregate;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.ProjectFilter;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.query.api.TitleFilter;
import com.feipi.session.browser.web.model.PaginationModel;
import com.feipi.session.browser.web.template.DisplayFormatters;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Projects 页面路由处理器。
 *
 * <p>处理两个路由：
 *
 * <ul>
 *   <li>{@code GET /projects} — 项目列表页
 *   <li>{@code GET /projects/{key}} — 项目详情页（包含该项目的会话列表）
 * </ul>
 *
 * <p>路由只负责 HTTP input 解析和 output 渲染，数据查询委托给 use case。
 */
public final class ProjectsPage {

  private static final Logger LOG = LoggerFactory.getLogger(ProjectsPage.class);

  private final QueryCompositionRoot queryRoot;
  private final PebbleEnvironment templates;

  /**
   * 创建 Projects 页面处理器。
   *
   * @param queryRoot 查询 composition root
   * @param templates Pebble 模板环境
   */
  public ProjectsPage(QueryCompositionRoot queryRoot, PebbleEnvironment templates) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot 不得为 null");
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
  }

  /**
   * 处理 GET /projects 列表请求。
   *
   * @param ctx Javalin 请求上下文
   */
  public void handleList(Context ctx) {
    Map<String, String> params = SessionsPage.flatQueryParams(ctx);
    ProjectListFilter filter = QueryParams.parseProjectListFilter(params);

    try {
      ProjectListUseCase useCase = queryRoot.projectList();
      long totalCount = useCase.count(filter);
      var pageResult = useCase.list(filter);

      int currentPage = QueryParams.parsePage(params);
      int pageSize = QueryParams.parsePageSize(params);
      PaginationModel pagination = PaginationModel.of(currentPage, pageSize, (int) totalCount);

      Map<String, Object> context = new HashMap<>();
      context.put("projects", pageResult.items());
      context.put("total_count", totalCount);
      context.putAll(pagination.toTemplateContext());
      context.put("filter_q", params.getOrDefault("q", ""));
      context.put("sort_by", params.getOrDefault("sort", "last_active"));
      context.put("sort_dir", params.getOrDefault("dir", "desc"));
      context.put("active_page", "projects");

      String html = templates.render("projects.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Projects 列表查询失败", e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(
          templates.render("error.html", Map.of("error", "查询项目列表失败", "active_page", "projects")));
    }
  }

  /**
   * 处理 GET /projects/{key} 详情请求。
   *
   * @param ctx Javalin 请求上下文
   * @param projectKey URL 中的项目键
   */
  public void handleDetail(Context ctx, String projectKey) {
    String decodedKey = URLDecoder.decode(projectKey, StandardCharsets.UTF_8);
    Map<String, String> params = SessionsPage.flatQueryParams(ctx);

    try {
      ProjectListUseCase projectUseCase = queryRoot.projectList();
      ProjectStatsRow project = projectUseCase.stats(decodedKey);

      // 项目不存在时返回 404
      if (project.totalSessions() == 0
          && (project.projectName() == null || project.projectName().isEmpty())) {
        ctx.status(HttpStatus.NOT_FOUND);
        ctx.html(
            templates.render("error.html", Map.of("error", "项目不存在", "active_page", "projects")));
        return;
      }

      // 查询该项目下的会话列表
      SessionListFilter sessionFilter = buildProjectSessionFilter(decodedKey, params);
      SessionListUseCase sessionUseCase = queryRoot.sessionList();
      long totalCount = sessionUseCase.count(sessionFilter);
      SessionListUseCase.AnnotatedPageResult result =
          sessionUseCase.listWithAnomalies(sessionFilter);
      SessionListAggregate aggregate = sessionUseCase.aggregate(sessionFilter);
      List<SessionRow> allProjectSessions =
          sessionUseCase
              .listWithAnomalies(buildAllProjectSessionsFilter(decodedKey, project))
              .page()
              .items();

      int currentPage = QueryParams.parsePage(params);
      int pageSize = QueryParams.parsePageSize(params);
      PaginationModel pagination = PaginationModel.of(currentPage, pageSize, (int) totalCount);
      String trendGrain = normalizeTrendGrain(params.getOrDefault("grain", "day"));

      Map<String, Object> context = new HashMap<>();
      context.put("project", project);
      context.put("sessions", result.page().items());
      context.put("anomalies", result.anomalies());
      context.put("sessions_aggregate", aggregate);
      context.put("project_detail", buildProjectDetail(project, allProjectSessions, trendGrain));
      context.put("project_key", decodedKey);
      context.put("total_count", totalCount);
      context.putAll(pagination.toTemplateContext());
      context.put("filter_q", params.getOrDefault("q", ""));
      context.put("sort_by", QueryParams.uiSortKey(params));
      context.put("sort_dir", params.getOrDefault("dir", "desc"));
      context.put("trend_grain", trendGrain);
      context.put("active_page", "projects");

      String html = templates.render("project.html", context);
      ctx.html(html);

    } catch (SQLException e) {
      LOG.error("Project 详情查询失败: {}", decodedKey, e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.html(
          templates.render("error.html", Map.of("error", "查询项目详情失败", "active_page", "projects")));
    }
  }

  /**
   * 构建项目详情页的会话列表过滤器。
   *
   * @param projectKey 项目键
   * @param params 查询参数
   * @return 限定到指定项目的会话列表过滤器
   */
  private static SessionListFilter buildProjectSessionFilter(
      String projectKey, Map<String, String> params) {
    SessionListFilter filter = SessionListFilter.defaults();
    filter = filter.withProject(ProjectFilter.of(projectKey));

    String q = params.getOrDefault("q", "").trim();
    if (!q.isEmpty()) {
      filter = filter.withTitle(TitleFilter.of(q));
    }

    // 项目详情页的排序默认按 ended_at DESC
    String rawSort = params.getOrDefault("sort", "").trim().toLowerCase();
    String rawDir = params.getOrDefault("dir", "desc").trim().toLowerCase();
    String dir = ("asc".equals(rawDir)) ? "asc" : "desc";
    if (!rawSort.isEmpty()) {
      String dbField = QueryParams.resolveSessionSortField(rawSort, "ended_at");
      filter = filter.withSort(Sort.ofSession(dbField, dir));
    }

    int page = QueryParams.parsePage(params);
    int pageSize = QueryParams.parsePageSize(params);
    int offset = (page - 1) * pageSize;
    filter = filter.withPage(PageRequest.ofOffset(offset, pageSize));

    return filter;
  }

  private static SessionListFilter buildAllProjectSessionsFilter(
      String projectKey, ProjectStatsRow project) {
    int limit = (int) Math.max(1, Math.min(Integer.MAX_VALUE, project.totalSessions()));
    return SessionListFilter.defaults()
        .withProject(ProjectFilter.of(projectKey))
        .withSort(Sort.ofSession("started_at", "asc"))
        .withPage(PageRequest.ofOffset(0, limit));
  }

  private static String normalizeTrendGrain(String raw) {
    String value = raw == null ? "" : raw.trim().toLowerCase();
    return switch (value) {
      case "week", "month" -> value;
      default -> "day";
    };
  }

  private static Map<String, Object> buildProjectDetail(
      ProjectStatsRow project, List<SessionRow> sessions, String grain) {
    Map<String, Object> detail = new LinkedHashMap<>();
    detail.put(
        "active_period",
        "Active: " + dateLabel(project.firstSeen()) + " to " + dateLabel(project.lastSeen()));
    detail.put("sessions_kpi", buildSessionsKpi(sessions));
    detail.put("agents_kpi", buildAgentsKpi(sessions));
    detail.put("tokens_kpi", buildTokensKpi(project));
    detail.put("cache_kpi", buildCacheKpi(project, sessions));
    detail.put("failure_kpi", buildFailureKpi(project, sessions));
    detail.put("agent_mix", buildAgentMix(project, sessions));
    detail.put("token_trend", buildTokenTrend(sessions, grain));
    detail.put(
        "tool_hotspots_reason", "Tool name breakdown is not stored in the current session index.");
    return detail;
  }

  private static Map<String, Object> buildSessionsKpi(List<SessionRow> sessions) {
    LocalDate today = LocalDate.now();
    LocalDate sevenDayStart = today.minusDays(6);
    List<LocalDate> startedDates =
        sessions.stream()
            .map(SessionRow::startedAt)
            .map(ProjectsPage::parseDate)
            .filter(Objects::nonNull)
            .toList();
    long todayCount = startedDates.stream().filter(today::equals).count();
    long lastSevenDays =
        startedDates.stream()
            .filter(date -> !date.isBefore(sevenDayStart) && !date.isAfter(today))
            .count();
    List<Double> durations =
        sessions.stream()
            .mapToDouble(SessionRow::durationSeconds)
            .filter(v -> v > 0)
            .boxed()
            .toList();
    List<Double> processTimes =
        sessions.stream()
            .mapToDouble(
                session -> session.modelExecutionSeconds() + session.toolExecutionSeconds())
            .filter(v -> v > 0)
            .boxed()
            .toList();
    return orderedMap(
        "today",
        todayCount,
        "avg_7d",
        lastSevenDays / 7.0,
        "median_duration",
        formatSeconds(median(durations)),
        "median_process_time",
        formatSeconds(median(processTimes)));
  }

  private static Map<String, Object> buildAgentsKpi(List<SessionRow> sessions) {
    long claude = sessions.stream().filter(s -> "claude_code".equals(s.agent())).count();
    long qoder = sessions.stream().filter(s -> "qoder".equals(s.agent())).count();
    long codex = sessions.stream().filter(s -> "codex".equals(s.agent())).count();
    return orderedMap(
        "count",
        (claude > 0 ? 1 : 0) + (qoder > 0 ? 1 : 0) + (codex > 0 ? 1 : 0),
        "claude_code",
        claude,
        "qoder",
        qoder,
        "codex",
        codex);
  }

  private static Map<String, Object> buildTokensKpi(ProjectStatsRow project) {
    return orderedMap(
        "total",
        project.totalTokens(),
        "fresh",
        project.totalFreshInputTokens(),
        "cache_read",
        project.totalCacheReadTokens(),
        "cache_write",
        project.totalCacheWriteTokens(),
        "output",
        project.totalOutputTokens());
  }

  private static Map<String, Object> buildCacheKpi(
      ProjectStatsRow project, List<SessionRow> sessions) {
    long inputSide =
        project.totalFreshInputTokens()
            + project.totalCacheReadTokens()
            + project.totalCacheWriteTokens();
    long eligible = 0;
    long lowRead = 0;
    for (SessionRow session : sessions) {
      long sessionInput =
          session.freshInputTokens() + session.cacheReadTokens() + session.cacheWriteTokens();
      if (sessionInput <= 0) {
        continue;
      }
      eligible++;
      if (session.cacheReadTokens() / (double) sessionInput < 0.2) {
        lowRead++;
      }
    }
    return orderedMap(
        "ratio",
        DisplayFormatters.percentLabel(project.totalCacheReadTokens(), inputSide),
        "eligible_sessions",
        eligible,
        "low_read_sessions",
        lowRead);
  }

  private static Map<String, Object> buildFailureKpi(
      ProjectStatsRow project, List<SessionRow> sessions) {
    long affected = sessions.stream().filter(s -> s.failedToolCount() > 0).count();
    long repeated = sessions.stream().filter(s -> s.failedToolCount() > 1).count();
    return orderedMap(
        "failed_tools",
        project.totalFailedTools(),
        "failure_rate",
        DisplayFormatters.percentLabel(project.totalFailedTools(), project.totalToolCalls()),
        "affected_sessions",
        affected,
        "repeated_failure_sessions",
        repeated);
  }

  private static List<Map<String, Object>> buildAgentMix(
      ProjectStatsRow project, List<SessionRow> sessions) {
    List<Map<String, Object>> rows = new ArrayList<>();
    long totalTokens = Math.max(0, project.totalTokens());
    addAgentMix(
        rows,
        "claude_code",
        "Claude Code",
        "claude",
        project.totalSessions(),
        totalTokens,
        sessions);
    addAgentMix(rows, "qoder", "Qoder", "qoder", project.totalSessions(), totalTokens, sessions);
    addAgentMix(rows, "codex", "Codex", "codex", project.totalSessions(), totalTokens, sessions);
    return rows;
  }

  private static void addAgentMix(
      List<Map<String, Object>> rows,
      String key,
      String label,
      String scope,
      long totalSessions,
      long totalTokens,
      List<SessionRow> sessions) {
    long sessionCount = 0;
    long tokens = 0;
    long failed = 0;
    for (SessionRow session : sessions) {
      if (!key.equals(session.agent())) {
        continue;
      }
      sessionCount++;
      tokens += session.totalTokens();
      failed += session.failedToolCount();
    }
    rows.add(
        orderedMap(
            "key",
            key,
            "label",
            label,
            "scope",
            scope,
            "sessions",
            sessionCount,
            "tokens",
            tokens,
            "failed",
            failed,
            "session_share",
            totalSessions > 0 ? sessionCount * 100.0 / totalSessions : 0.0,
            "token_share",
            totalTokens > 0 ? tokens * 100.0 / totalTokens : 0.0));
  }

  private static Map<String, Object> buildTokenTrend(List<SessionRow> sessions, String grain) {
    Map<String, long[]> buckets = new LinkedHashMap<>();
    for (SessionRow session : sessions) {
      LocalDate date = parseDate(session.startedAt());
      if (date == null) {
        continue;
      }
      String key = bucketLabel(date, grain);
      long[] values = buckets.computeIfAbsent(key, ignored -> new long[5]);
      values[0] += session.freshInputTokens();
      values[1] += session.cacheReadTokens();
      values[2] += session.cacheWriteTokens();
      values[3] += session.outputTokens();
      values[4] += session.totalTokens();
    }

    List<Map<String, Object>> points = new ArrayList<>();
    long maxTotal = 0;
    for (Map.Entry<String, long[]> entry : buckets.entrySet()) {
      long[] values = entry.getValue();
      maxTotal = Math.max(maxTotal, values[4]);
      points.add(
          orderedMap(
              "label",
              entry.getKey(),
              "fresh",
              values[0],
              "cache_read",
              values[1],
              "cache_write",
              values[2],
              "output",
              values[3],
              "total",
              values[4]));
    }

    return orderedMap(
        "points",
        points,
        "layers",
        buildTrendLayers(points, maxTotal),
        "max_total",
        maxTotal,
        "has_data",
        maxTotal > 0 && !points.isEmpty());
  }

  private static List<Map<String, Object>> buildTrendLayers(
      List<Map<String, Object>> points, long maxTotal) {
    List<Map<String, Object>> layers = new ArrayList<>();
    if (points.isEmpty() || maxTotal <= 0) {
      return layers;
    }
    double[] lower = new double[points.size()];
    for (String key : List.of("fresh", "cache_read", "cache_write", "output")) {
      List<String> upper = new ArrayList<>();
      List<String> lowerPath = new ArrayList<>();
      for (int i = 0; i < points.size(); i++) {
        double x = points.size() == 1 ? 0.0 : i * 100.0 / (points.size() - 1);
        double low = lower[i];
        double high = low + ((Number) points.get(i).get(key)).doubleValue() * 100.0 / maxTotal;
        upper.add(String.format(java.util.Locale.ROOT, "%.2f,%.2f", x, 100 - high));
        lowerPath.add(String.format(java.util.Locale.ROOT, "%.2f,%.2f", x, 100 - low));
        lower[i] = high;
      }
      java.util.Collections.reverse(lowerPath);
      layers.add(
          orderedMap(
              "key",
              key,
              "path",
              "M " + String.join(" L ", upper) + " L " + String.join(" L ", lowerPath) + " Z"));
    }
    return layers;
  }

  private static String bucketLabel(LocalDate date, String grain) {
    if ("month".equals(grain)) {
      return date.getYear()
          + "-"
          + String.format(java.util.Locale.ROOT, "%02d", date.getMonthValue());
    }
    if ("week".equals(grain)) {
      return date.minusDays(date.getDayOfWeek().getValue() - 1L).toString();
    }
    return date.toString();
  }

  private static LocalDate parseDate(String value) {
    if (value == null || value.isEmpty()) {
      return null;
    }
    try {
      return Instant.parse(value.replace("Z", "+00:00"))
          .atZone(ZoneId.systemDefault())
          .toLocalDate();
    } catch (Exception ignored) {
      return null;
    }
  }

  private static String dateLabel(String value) {
    LocalDate date = parseDate(value);
    return date != null ? date.toString() : "N/A";
  }

  private static double median(List<Double> values) {
    return switch (values.size()) {
      case 0 -> 0.0;
      default -> medianOfSorted(values.stream().sorted().toList());
    };
  }

  private static double medianOfSorted(List<Double> ordered) {
    int size = ordered.size();
    int mid = size / 2;
    return (size & 1) == 1 ? ordered.get(mid) : (ordered.get(mid - 1) + ordered.get(mid)) * 0.5;
  }

  private static String formatSeconds(double value) {
    long seconds = Math.max(0, Math.round(value));
    return DisplayFormatters.formatDuration(seconds);
  }

  private static Map<String, Object> orderedMap(Object... pairs) {
    if ((pairs.length & 1) == 1) {
      throw new IllegalArgumentException("orderedMap requires key/value pairs");
    }
    Map<String, Object> values = new LinkedHashMap<>();
    for (int i = 0; i < pairs.length; i += 2) {
      values.put((String) pairs[i], pairs[i + 1]);
    }
    return values;
  }
}
