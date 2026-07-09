package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.index.api.query.ProjectListSummary;
import com.feipi.session.browser.index.api.query.ProjectStats;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.ProjectListFilter;
import com.feipi.session.browser.web.api.PageApiDtos.ActiveFilterDto;
import com.feipi.session.browser.web.api.PageApiDtos.ActiveFiltersResponse;
import com.feipi.session.browser.web.api.PageApiDtos.ApiLink;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.ProjectsApiResponses.ProjectAgentBadgeDto;
import com.feipi.session.browser.web.api.ProjectsApiResponses.ProjectRowDto;
import com.feipi.session.browser.web.api.ProjectsApiResponses.ProjectsFilterEcho;
import com.feipi.session.browser.web.api.ProjectsApiResponses.ProjectsRowsResponse;
import com.feipi.session.browser.web.api.ProjectsApiResponses.ProjectsSummaryResponse;
import com.feipi.session.browser.web.page.QueryParams;
import io.javalin.http.Context;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Projects list 页面的资源 API。 */
public final class ProjectsApiHandler {

  private final QueryCompositionRoot queryRoot;

  /** 创建对应对象。 */
  public ProjectsApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
  }

  /** 处理 /api/projects/summary 的 GET 请求。 */
  public void handleSummary(Context ctx) {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    ProjectListFilter filter = QueryParams.parseProjectListFilter(params);
    ProjectListSummary summary = queryRoot.projectList().summary(filter);
    ctx.json(
        new ProjectsSummaryResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(params),
            summary.projectCount(),
            summary.sessionCount(),
            TokenSegments.of(
                summary.freshInputTokens(),
                summary.cacheReadTokens(),
                summary.cacheWriteTokens(),
                summary.outputTokens()),
            summary.toolCallCount(),
            summary.failedToolCount(),
            summaryState(summary.projectCount(), hasUserFilter(params))));
  }

  /** 处理 /api/projects/rows 的 GET 请求。 */
  public void handleRows(Context ctx) {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    ProjectListFilter filter = QueryParams.parseProjectListFilter(params);
    PageResult<ProjectStats> page = queryRoot.projectList().list(filter);
    List<ProjectRowDto> rows = page.items().stream().map(ProjectsApiHandler::rowDto).toList();
    ctx.json(
        ApiPageRows.response(
            params,
            ProjectsApiHandler::echo,
            rows,
            page.totalCount(),
            rowsState(page.totalCount(), hasUserFilter(params)),
            ProjectsRowsResponse::new));
  }

  /** 处理 /api/projects/active-filters 的 GET 请求。 */
  public void handleActiveFilters(Context ctx) {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    String q = params.getOrDefault("q", "").trim();
    List<ActiveFilterDto> chips =
        q.isEmpty() ? List.of() : List.of(new ActiveFilterDto("q", "Search", q, "/projects"));
    ctx.json(
        new ActiveFiltersResponse(
            ApiResponses.SCHEMA_VERSION,
            chips,
            "/projects",
            chips.isEmpty()
                ? PageStateDto.empty("No active filters", "Projects list is using the full scope.")
                : PageStateDto.ready()));
  }

  private static ProjectRowDto rowDto(ProjectStats row) {
    return new ProjectRowDto(
        row.projectKey(),
        row.projectName(),
        row.totalSessions(),
        row.claudeSessions(),
        row.codexSessions(),
        row.qoderSessions(),
        List.of(
                new ProjectAgentBadgeDto("claude_code", "Claude Code", row.claudeSessions()),
                new ProjectAgentBadgeDto("qoder", "Qoder", row.qoderSessions()),
                new ProjectAgentBadgeDto("codex", "Codex", row.codexSessions()))
            .stream()
            .filter(agent -> agent.sessions() > 0)
            .toList(),
        TokenSegments.of(
            row.totalFreshInputTokens(),
            row.totalCacheReadTokens(),
            row.totalCacheWriteTokens(),
            row.totalOutputTokens()),
        row.totalToolCalls(),
        row.totalFailedTools(),
        row.totalUserMessages(),
        row.totalAssistantMessages(),
        row.firstSeen(),
        row.lastSeen(),
        "/projects/" + ApiQueryParams.url(row.projectKey()));
  }

  private static ProjectsFilterEcho echo(Map<String, String> params) {
    return new ProjectsFilterEcho(
        params.getOrDefault("q", ""),
        params.getOrDefault("sort", "last_active"),
        ApiQueryParams.normalizeDir(params.getOrDefault("dir", "desc")),
        QueryParams.parsePage(params),
        QueryParams.parsePageSize(params));
  }

  private static PageStateDto summaryState(long projectCount, boolean hasFilter) {
    if (projectCount > 0) {
      return PageStateDto.ready();
    }
    return hasFilter
        ? PageStateDto.noResults(
            "No projects match your current search",
            "Clear search or adjust your query.",
            List.of(ApiLink.get("clear_search", "/api/projects/summary")))
        : PageStateDto.empty("No projects indexed yet", "Run a scan before browsing projects.");
  }

  private static PageStateDto rowsState(long projectCount, boolean hasFilter) {
    if (projectCount > 0) {
      return PageStateDto.ready();
    }
    return hasFilter
        ? PageStateDto.noResults(
            "No projects match your current search",
            "Clear search or adjust your query.",
            List.of(ApiLink.get("clear_search", "/projects")))
        : PageStateDto.empty("No projects indexed yet", "Run a scan before browsing projects.");
  }

  private static boolean hasUserFilter(Map<String, String> params) {
    return !params.getOrDefault("q", "").trim().isEmpty();
  }
}
