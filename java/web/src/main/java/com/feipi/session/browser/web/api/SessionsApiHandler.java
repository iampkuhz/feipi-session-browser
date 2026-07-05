package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionListUseCase;
import com.feipi.session.browser.index.sqlite.ProjectOptionRow;
import com.feipi.session.browser.index.sqlite.SessionListSummaryRow;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.PageResult;
import com.feipi.session.browser.query.api.SessionListFilter;
import com.feipi.session.browser.web.api.PageApiDtos.ApiLink;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.PaginationDto;
import com.feipi.session.browser.web.api.PageApiDtos.SelectOptionDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionRowDto;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionsFilterEcho;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionsOptionsResponse;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionsRowsResponse;
import com.feipi.session.browser.web.api.SessionsApiResponses.SessionsSummaryResponse;
import com.feipi.session.browser.web.page.QueryParams;
import io.javalin.http.Context;
import java.sql.SQLException;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Sessions list 页面的资源 API。 */
public final class SessionsApiHandler {

  private final QueryCompositionRoot queryRoot;

  /** 创建对应对象。 */
  public SessionsApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
  }

  /** 处理 /api/sessions/summary 的 GET 请求。 */
  public void handleSummary(Context ctx) throws SQLException {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    SessionListFilter filter = QueryParams.parseSessionListFilter(params);
    SessionListSummaryRow summary = queryRoot.sessionList().summary(filter);
    SessionsSummaryResponse response =
        new SessionsSummaryResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(params),
            summary.sessionCount(),
            summary.projectCount(),
            TokenSegments.of(
                summary.freshInputTokens(),
                summary.cacheReadTokens(),
                summary.cacheWriteTokens(),
                summary.outputTokens()),
            summary.failedToolCount(),
            summaryState(summary.sessionCount(), hasUserFilter(params)));
    ctx.json(response);
  }

  /** 处理 /api/sessions/options 的 GET 请求。 */
  public void handleOptions(Context ctx) throws SQLException {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    SessionListFilter filter = QueryParams.parseSessionListFilter(params);
    SessionListUseCase useCase = queryRoot.sessionList();
    List<SelectOptionDto> modelOptions =
        useCase.modelOptions(filter).stream()
            .map(value -> new SelectOptionDto(value, value))
            .toList();
    List<SelectOptionDto> projectOptions =
        useCase.projectOptions(filter).stream().map(SessionsApiHandler::projectOption).toList();
    ctx.json(
        new SessionsOptionsResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(params),
            agentOptions(),
            modelOptions,
            projectOptions,
            statusOptions()));
  }

  /** 处理 /api/sessions/rows 的 GET 请求。 */
  public void handleRows(Context ctx) throws SQLException {
    Map<String, String> params = ApiQueryParams.flat(ctx);
    SessionListFilter filter = QueryParams.parseSessionListFilter(params);
    SessionListUseCase.AnnotatedPageResult result =
        queryRoot.sessionList().listWithAnomalies(filter);
    PageResult<SessionRow> page = result.page();
    int currentPage = QueryParams.parsePage(params);
    int pageSize = QueryParams.parsePageSize(params);
    List<SessionRowDto> rows = page.items().stream().map(SessionsApiHandler::rowDto).toList();
    ctx.json(
        new SessionsRowsResponse(
            ApiResponses.SCHEMA_VERSION,
            echo(params),
            rows,
            PaginationDto.of(currentPage, pageSize, page.totalCount()),
            rowsState(page.totalCount(), hasUserFilter(params))));
  }

  static SessionRowDto rowDto(SessionRow row) {
    return new SessionRowDto(
        row.sessionKey(),
        row.sessionId(),
        row.title(),
        row.projectKey(),
        row.projectName(),
        row.cwd(),
        row.agent(),
        row.model(),
        TokenSegments.of(
            row.freshInputTokens(),
            row.cacheReadTokens(),
            row.cacheWriteTokens(),
            row.outputTokens()),
        row.assistantMessageCount(),
        row.toolCallCount(),
        row.subagentInstanceCount(),
        row.durationSeconds(),
        row.modelExecutionSeconds() + row.toolExecutionSeconds(),
        row.failedToolCount(),
        row.startedAt(),
        row.endedAt(),
        "/sessions/" + ApiQueryParams.url(row.agent()) + "/" + ApiQueryParams.url(row.sessionId()),
        "/projects/" + ApiQueryParams.url(row.projectKey()));
  }

  private static SessionsFilterEcho echo(Map<String, String> params) {
    return new SessionsFilterEcho(
        QueryParams.normalizeSessionAgent(params.getOrDefault("agent", "")),
        params.getOrDefault("model", ""),
        params.getOrDefault("project", ""),
        params.getOrDefault("status", ""),
        params.getOrDefault("q", ""),
        QueryParams.uiSortKey(params),
        ApiQueryParams.normalizeDir(params.getOrDefault("dir", "desc")),
        QueryParams.parsePage(params),
        QueryParams.parsePageSize(params));
  }

  private static PageStateDto summaryState(long totalCount, boolean hasFilter) {
    if (totalCount > 0) {
      return PageStateDto.ready();
    }
    return hasFilter
        ? PageStateDto.noResults(
            "No sessions match your current filters",
            "Clear filters or adjust your search.",
            List.of(ApiLink.get("clear_all_filters", "/api/sessions/summary")))
        : PageStateDto.empty("No sessions indexed yet", "Run a scan before browsing sessions.");
  }

  private static PageStateDto rowsState(long totalCount, boolean hasFilter) {
    if (totalCount > 0) {
      return PageStateDto.ready();
    }
    return hasFilter
        ? PageStateDto.noResults(
            "No sessions match your current filters",
            "Clear filters or adjust your search.",
            List.of(ApiLink.get("clear_all_filters", "/sessions")))
        : PageStateDto.empty("No sessions indexed yet", "Run a scan before browsing sessions.");
  }

  private static List<SelectOptionDto> agentOptions() {
    return List.of(
        new SelectOptionDto("all", "All Agents"),
        new SelectOptionDto("claude_code", "Claude Code"),
        new SelectOptionDto("qoder", "Qoder"),
        new SelectOptionDto("codex", "Codex"));
  }

  private static List<SelectOptionDto> statusOptions() {
    return List.of(
        new SelectOptionDto("", "All"),
        new SelectOptionDto("failed", "Failed"),
        new SelectOptionDto("no-failures", "No failures"));
  }

  private static SelectOptionDto projectOption(ProjectOptionRow row) {
    String label = row.projectName().isBlank() ? row.projectKey() : row.projectName();
    return new SelectOptionDto(row.projectKey(), label);
  }

  private static boolean hasUserFilter(Map<String, String> params) {
    for (String key : List.of("agent", "model", "project", "status", "q")) {
      String value = params.getOrDefault(key, "").trim();
      if (!value.isEmpty() && !("agent".equals(key) && "all".equalsIgnoreCase(value))) {
        return true;
      }
    }
    return false;
  }
}
