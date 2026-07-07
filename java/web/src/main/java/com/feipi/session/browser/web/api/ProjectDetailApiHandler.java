package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.ProjectStatsRow;
import com.feipi.session.browser.index.sqlite.SessionListSummaryRow;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.PageRequest;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectFilter;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.query.api.Sort;
import com.feipi.session.browser.web.api.PageApiDtos.ApiLink;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.PaginationDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectAgentMixResponse;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectAgentMixRow;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectDetailFilterEcho;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectDetailSummaryResponse;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectTokenTrendPoint;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectTokenTrendResponse;
import com.feipi.session.browser.web.api.ProjectDetailApiResponses.ProjectToolHotspotsResponse;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionsRowsResponse;
import com.feipi.session.browser.web.model.TokenTrendBuckets;
import com.feipi.session.browser.web.model.WebDisplayValues;
import com.feipi.session.browser.web.page.QueryParams;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Project Detail 页面的资源 API。 */
public final class ProjectDetailApiHandler {

  private final QueryCompositionRoot queryRoot;

  /** 创建对应对象。 */
  public ProjectDetailApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
  }

  /** 处理 /api/projects/{projectKey}/summary 的 GET 请求。 */
  public void handleSummary(Context ctx) throws SQLException {
    String projectKey = projectKey(ctx);
    ProjectStatsRow project = findProjectOr404(ctx, projectKey);
    if (project == null) {
      return;
    }
    ctx.json(
        new ProjectDetailSummaryResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(ctx, projectKey),
            project.projectName(),
            project.totalSessions(),
            project.claudeSessions(),
            project.codexSessions(),
            project.qoderSessions(),
            projectTokens(project),
            project.totalToolCalls(),
            project.totalFailedTools(),
            project.totalUserMessages(),
            project.totalAssistantMessages(),
            project.firstSeen(),
            project.lastSeen(),
            PageStateDto.ready()));
  }

  /** 处理 /api/projects/{projectKey}/token-trend 的 GET 请求。 */
  public void handleTokenTrend(Context ctx) throws SQLException {
    String projectKey = projectKey(ctx);
    ProjectStatsRow project = findProjectOr404(ctx, projectKey);
    if (project == null) {
      return;
    }
    List<SessionRow> sessions = allProjectSessions(projectKey, project);
    List<ProjectTokenTrendPoint> points = tokenTrendPoints(sessions, grain(ctx));
    ctx.json(
        new ProjectTokenTrendResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(ctx, projectKey),
            projectTokens(project),
            points,
            points.isEmpty()
                ? PageStateDto.empty("No project token trend data", "No dated sessions exist.")
                : PageStateDto.ready()));
  }

  /** 处理 /api/projects/{projectKey}/agent-mix 的 GET 请求。 */
  public void handleAgentMix(Context ctx) throws SQLException {
    String projectKey = projectKey(ctx);
    ProjectStatsRow project = findProjectOr404(ctx, projectKey);
    if (project == null) {
      return;
    }
    List<SessionRow> sessions = allProjectSessions(projectKey, project);
    ctx.json(
        new ProjectAgentMixResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(ctx, projectKey),
            project.totalSessions(),
            projectTokens(project),
            agentMixRows(project, sessions),
            PageStateDto.ready()));
  }

  /** 处理 /api/projects/{projectKey}/tool-hotspots 的 GET 请求。 */
  public void handleToolHotspots(Context ctx) throws SQLException {
    String projectKey = projectKey(ctx);
    ProjectStatsRow project = findProjectOr404(ctx, projectKey);
    if (project == null) {
      return;
    }
    String reason = "tool_name_breakdown_not_indexed";
    ctx.json(
        new ProjectToolHotspotsResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(ctx, projectKey),
            false,
            reason,
            List.of(),
            PageStateDto.noResults(
                "Tool hotspots unavailable",
                "Current index stores aggregate tool counts but not tool names.",
                List.of(
                    ApiLink.get(
                        "project_summary",
                        "/api/projects/" + ApiQueryParams.url(projectKey) + "/summary")))));
  }

  /** 处理 /api/projects/{projectKey}/sessions/summary 的 GET 请求。 */
  public void handleSessionsSummary(Context ctx) throws SQLException {
    String projectKey = projectKey(ctx);
    ProjectStatsRow project = findProjectOr404(ctx, projectKey);
    if (project == null) {
      return;
    }
    Map<String, String> params = sessionParams(ctx, projectKey);
    SessionListFilter filter = QueryParams.parseSessionListFilter(params);
    SessionListSummaryRow summary = queryRoot.sessionList().summary(filter);
    ctx.json(
        ApiSessionSummaries.response(
            params,
            summary,
            sessionsState(summary.sessionCount(), hasSessionFilter(params), projectKey)));
  }

  /** 处理 /api/projects/{projectKey}/sessions/rows 的 GET 请求。 */
  public void handleSessionsRows(Context ctx) throws SQLException {
    String projectKey = projectKey(ctx);
    ProjectStatsRow project = findProjectOr404(ctx, projectKey);
    if (project == null) {
      return;
    }
    Map<String, String> params = sessionParams(ctx, projectKey);
    SessionListFilter filter = QueryParams.parseSessionListFilter(params);
    SessionListUseCase.AnnotatedPageResult result =
        queryRoot.sessionList().listWithAnomalies(filter);
    PageResult<SessionRow> page = result.page();
    int currentPage = QueryParams.parsePage(params);
    int pageSize = QueryParams.parsePageSize(params);
    ctx.json(
        new SessionsRowsResponse(
            ApiResponses.SCHEMA_VERSION,
            ApiQueryParams.sessionsFilterEcho(params),
            page.items().stream().map(SessionsApiHandler::rowDto).toList(),
            PaginationDto.of(currentPage, pageSize, page.totalCount()),
            sessionsState(page.totalCount(), hasSessionFilter(params), projectKey)));
  }

  private ProjectStatsRow findProjectOr404(Context ctx, String projectKey) throws SQLException {
    ProjectStatsRow project = queryRoot.projectList().stats(projectKey);
    if (project.totalSessions() == 0 && project.projectName().isEmpty()) {
      ctx.status(HttpStatus.NOT_FOUND);
      ctx.json(new ApiResponses.ApiErrorResponse("not_found", "project not found"));
      return null;
    }
    return project;
  }

  private List<SessionRow> allProjectSessions(String projectKey, ProjectStatsRow project)
      throws SQLException {
    int limit = (int) Math.max(1, Math.min(PageRequest.MAX_LIMIT, project.totalSessions()));
    SessionListFilter filter =
        SessionListFilter.defaults()
            .withProject(ProjectFilter.of(projectKey))
            .withSort(Sort.ofSession("started_at", "asc"))
            .withPage(PageRequest.ofOffset(0, limit));
    return queryRoot.sessionList().listWithAnomalies(filter).page().items();
  }

  private static List<ProjectTokenTrendPoint> tokenTrendPoints(
      List<SessionRow> sessions, String grain) {
    List<ProjectTokenTrendPoint> points = new ArrayList<>();
    for (TokenTrendBuckets.Point point : TokenTrendBuckets.fromSessions(sessions, grain)) {
      points.add(
          new ProjectTokenTrendPoint(
              point.label(),
              TokenSegments.of(
                  point.fresh(), point.cacheRead(), point.cacheWrite(), point.output())));
    }
    return points;
  }

  private static List<ProjectAgentMixRow> agentMixRows(
      ProjectStatsRow project, List<SessionRow> sessions) {
    List<ProjectAgentMixRow> rows = new ArrayList<>();
    for (String agent : List.of("claude_code", "qoder", "codex")) {
      long sessionCount = 0;
      long fresh = 0;
      long cacheRead = 0;
      long cacheWrite = 0;
      long output = 0;
      long failed = 0;
      for (SessionRow session : sessions) {
        if (!agent.equals(session.agent())) {
          continue;
        }
        sessionCount++;
        fresh += session.freshInputTokens();
        cacheRead += session.cacheReadTokens();
        cacheWrite += session.cacheWriteTokens();
        output += session.outputTokens();
        failed += session.failedToolCount();
      }
      long tokenTotal = fresh + cacheRead + cacheWrite + output;
      rows.add(
          new ProjectAgentMixRow(
              agent,
              WebDisplayValues.agentDisplay(agent),
              sessionCount,
              TokenSegments.of(fresh, cacheRead, cacheWrite, output),
              failed,
              WebDisplayValues.share(sessionCount, project.totalSessions()),
              WebDisplayValues.share(tokenTotal, project.totalTokens()),
              ratio(sessionCount, project.totalSessions()),
              ratio(tokenTotal, project.totalTokens())));
    }
    return rows;
  }

  private static TokenSegments projectTokens(ProjectStatsRow project) {
    return TokenSegments.of(
        project.totalFreshInputTokens(),
        project.totalCacheReadTokens(),
        project.totalCacheWriteTokens(),
        project.totalOutputTokens());
  }

  private static PageStateDto sessionsState(long totalCount, boolean hasFilter, String projectKey) {
    if (totalCount > 0) {
      return PageStateDto.ready();
    }
    return hasFilter
        ? PageStateDto.noResults(
            "No project sessions match your filters",
            "Clear filters or adjust your search.",
            List.of(
                ApiLink.get(
                    "clear_project_session_filters",
                    "/projects/" + ApiQueryParams.url(projectKey))))
        : PageStateDto.empty("No sessions in this project", "Run a scan before browsing sessions.");
  }

  private static boolean hasSessionFilter(Map<String, String> params) {
    for (String key : List.of("agent", "model", "status", "q")) {
      String value = params.getOrDefault(key, "").trim();
      if (!value.isEmpty() && !("agent".equals(key) && "all".equalsIgnoreCase(value))) {
        return true;
      }
    }
    return false;
  }

  private static Map<String, String> sessionParams(Context ctx, String projectKey) {
    Map<String, String> params = new java.util.HashMap<>(ApiQueryParams.flat(ctx));
    params.put("project", projectKey);
    return params;
  }

  private static ProjectDetailFilterEcho echo(Context ctx, String projectKey) {
    return new ProjectDetailFilterEcho(projectKey, grain(ctx));
  }

  private static String projectKey(Context ctx) {
    return ApiResponses.decodePathParam(ctx.pathParam("projectKey"));
  }

  private static String grain(Context ctx) {
    String raw = ApiQueryParams.flat(ctx).getOrDefault("grain", "day").trim().toLowerCase();
    return switch (raw) {
      case "week", "month" -> raw;
      default -> "day";
    };
  }

  private static double ratio(long value, long total) {
    return total <= 0 ? 0.0 : value / (double) total;
  }
}
