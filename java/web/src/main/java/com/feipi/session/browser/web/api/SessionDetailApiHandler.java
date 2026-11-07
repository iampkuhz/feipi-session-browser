package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.AnomalyDto;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.PayloadIndexDto;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.RoundIndexDto;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionDetailFilterEcho;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionDiagnosticsResponse;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionMetaResponse;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionMetricsResponse;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionPayloadsResponse;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.SessionRoundsResponse;
import io.javalin.http.BadRequestResponse;
import io.javalin.http.Context;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

/** Session Detail 页面的资源 API。 */
public final class SessionDetailApiHandler {

  private final Function<Context, LoadedDetail> detailLoader;

  /** 创建对应对象。 */
  public SessionDetailApiHandler(QueryCompositionRoot queryRoot) {
    Objects.requireNonNull(queryRoot, "queryRoot must not be null");
    this.detailLoader = ctx -> loadPersonal(ctx, queryRoot);
  }

  /**
   * 使用当前分析范围的加载器创建资源处理器。
   *
   * @param detailLoader 不访问其他范围的详情加载器
   */
  public SessionDetailApiHandler(Function<Context, LoadedDetail> detailLoader) {
    this.detailLoader = Objects.requireNonNull(detailLoader, "detailLoader 不得为 null");
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/meta 的 GET 请求。 */
  public void handleMeta(Context ctx) {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionRecord row = detail.sessionRow();
    SessionDetailParityAnalyzer.Result parity =
        SessionDetailParityAnalyzer.analyze(
            detail,
            loaded.annotated().artifact(),
            loaded.annotated().content(),
            loaded.allowSourceFiles());
    ctx.json(
        new SessionMetaResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo(),
            row.sessionKey(),
            row.title(),
            row.projectKey(),
            row.projectName(),
            row.cwd(),
            row.model(),
            row.startedAt(),
            row.endedAt(),
            row.gitBranch(),
            row.source(),
            detail.hasArtifact(),
            detail.artifactSchemaVersion(),
            detail.cacheKey(),
            parity.meta,
            PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/metrics 的 GET 请求。 */
  public void handleMetrics(Context ctx) {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionRecord row = detail.sessionRow();
    SessionDetailParityAnalyzer.Result parity =
        SessionDetailParityAnalyzer.analyze(
            detail,
            loaded.annotated().artifact(),
            loaded.annotated().content(),
            loaded.allowSourceFiles());
    Map<String, Object> parityMetrics = parity.metrics;
    ctx.json(
        new SessionMetricsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo(),
            TokenSegments.of(
                row.freshInputTokens(),
                row.cacheReadTokens(),
                row.cacheWriteTokens(),
                row.outputTokens(),
                row.tokenProvenance()),
            row.userMessageCount(),
            row.assistantMessageCount(),
            longMetric(parityMetrics, "toolCalls", row.toolCallCount()),
            longMetric(parityMetrics, "failedTools", row.failedToolCount()),
            longMetric(parityMetrics, "subagentRuns", row.subagentInstanceCount()),
            row.durationSeconds(),
            ApiSessionTimings.available(
                row.timing().modelExecutionSeconds(), row.timing().modelExecutionPrecision()),
            ApiSessionTimings.available(
                row.timing().toolExecutionSeconds(), row.timing().toolExecutionPrecision()),
            row.timing(),
            detail.roundCount(),
            detail.payloadSourceCount(),
            parity.metrics,
            PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/diagnostics 的 GET 请求。 */
  public void handleDiagnostics(Context ctx) {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionAnomalySummary anomalies = loaded.annotated().anomalies();
    SessionDetailParityAnalyzer.Result parity =
        SessionDetailParityAnalyzer.analyze(
            loaded.annotated().detail(),
            loaded.annotated().artifact(),
            loaded.annotated().content(),
            loaded.allowSourceFiles());
    List<AnomalyDto> rows =
        anomalies.anomalies().stream().map(SessionDetailApiHandler::anomaly).toList();
    ctx.json(
        new SessionDiagnosticsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo(),
            anomalies.anomalyCount(),
            anomalies.maxSeverity().getValue(),
            anomalies.mainReason(),
            rows,
            parity.diagnostics,
            rows.isEmpty()
                ? Boolean.TRUE.equals(parity.diagnostics.get("contentMeasured"))
                    ? PageStateDto.empty(
                        "No issue signals detected",
                        "No anomalies were detected in observed indexed content; this does not"
                            + " establish task completion or complete log coverage.")
                    : PageStateDto.empty(
                        "Diagnostics coverage unknown",
                        "Session content is unavailable; absence of detected anomalies is not"
                            + " evidence of a clean run.")
                : PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/rounds 的 GET 请求。 */
  public void handleRounds(Context ctx) {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionDetailParityAnalyzer.Result parity =
        SessionDetailParityAnalyzer.analyze(
            detail,
            loaded.annotated().artifact(),
            loaded.annotated().content(),
            loaded.allowSourceFiles());
    String traceStatus = ApiQueryParams.normalizeAll(ctx.queryParam("trace_status"));
    List<RoundIndexDto> rows =
        roundRows(loaded, parity).stream()
            .filter(round -> statusMatches(traceStatus, round))
            .toList();
    if (paged(ctx, loaded)) {
      sendWindow(ctx, loaded, rows, "rounds", traceStatus);
      return;
    }
    ctx.json(
        new SessionRoundsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo().withTraceStatus(traceStatus),
            rows.size(),
            rows,
            roundState(rows.size(), traceStatus)));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/payloads 的 GET 请求。 */
  public void handlePayloads(Context ctx) {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    String payloadStatus = ApiQueryParams.normalizeAll(ctx.queryParam("status"));
    if (loaded.annotated().artifact() == null && loaded.annotated().content() != null) {
      sendContentPayloads(ctx, loaded, payloadStatus);
      return;
    }
    List<PayloadIndexDto> rows =
        loaded.annotated().detail().payloadSources().stream()
            .map(source -> SessionDetailApiResponses.payloadIndexDto(source, loaded.apiBase()))
            .filter(payload -> payloadStatusMatches(payloadStatus, payload.status()))
            .toList();
    if (paged(ctx, loaded)) {
      sendWindow(ctx, loaded, rows, "payloads", payloadStatus);
      return;
    }
    ctx.json(
        new SessionPayloadsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo().withPayloadStatus(payloadStatus),
            rows.size(),
            rows,
            payloadState(rows.size(), payloadStatus)));
  }

  private static List<RoundIndexDto> roundRows(
      LoadedDetail loaded, SessionDetailParityAnalyzer.Result parity) {
    if (loaded.annotated().artifact() != null || loaded.annotated().content() == null) {
      return RoundIndexProjection.pageDtos(
          loaded.annotated().detail(), loaded.annotated().artifact(), parity);
    }
    try {
      return SessionContentProjection.rounds(
          loaded.annotated().detail(), loaded.annotated().content());
    } catch (IOException exception) {
      throw (io.javalin.http.InternalServerErrorResponse)
          new io.javalin.http.InternalServerErrorResponse("normalized content read failed")
              .initCause(exception);
    }
  }

  private static boolean paged(Context ctx, LoadedDetail loaded) {
    return ctx.queryParam("cursor") != null
        || ctx.queryParam("limit") != null
        || (loaded.annotated().artifact() == null && loaded.annotated().content() != null);
  }

  private static int windowLimit(Context ctx) {
    try {
      int limit = ctx.queryParam("limit") == null ? 100 : Integer.parseInt(ctx.queryParam("limit"));
      if (limit < 1 || limit > 500) throw new NumberFormatException();
      return limit;
    } catch (NumberFormatException exception) {
      throw (BadRequestResponse)
          new BadRequestResponse("limit must be within 1..500").initCause(exception);
    }
  }

  private static String cursorScope(
      Context ctx, LoadedDetail loaded, String section, String filter) {
    return loaded.annotated().detail().cacheKey()
        + "|"
        + ctx.res().getHeader("X-Session-Index-Generation")
        + "|"
        + loaded.apiBase()
        + "|"
        + loaded.echo().visibility()
        + "|"
        + section
        + "|"
        + filter;
  }

  private static long windowOffset(Context ctx, String scope) {
    if (ctx.queryParam("cursor") == null) return 0;
    try {
      return SessionContentCursor.decode(ctx.queryParam("cursor"), scope);
    } catch (IllegalArgumentException exception) {
      throw (BadRequestResponse)
          new BadRequestResponse("invalid cursor for this snapshot and filter")
              .initCause(exception);
    }
  }

  private static <T> void sendWindow(
      Context ctx, LoadedDetail loaded, List<T> rows, String section, String filter) {
    int limit = windowLimit(ctx);
    String scope = cursorScope(ctx, loaded, section, filter);
    long offset = windowOffset(ctx, scope);
    if (offset > rows.size()) throw new BadRequestResponse("cursor exceeds section total");
    int end = (int) Math.min(rows.size(), offset + limit);
    sendPage(
        ctx,
        loaded,
        section,
        filter,
        rows.subList((int) offset, end),
        rows.size(),
        end < rows.size() ? SessionContentCursor.encode(scope, end) : null);
  }

  private static void sendPage(
      Context ctx,
      LoadedDetail loaded,
      String section,
      String filter,
      List<?> rows,
      long total,
      String next) {
    Map<String, Object> response = new LinkedHashMap<>();
    response.put("schemaVersion", ApiResponses.SCHEMA_VERSION);
    response.put(
        "filters",
        "rounds".equals(section)
            ? loaded.echo().withTraceStatus(filter)
            : loaded.echo().withPayloadStatus(filter));
    response.put("rounds".equals(section) ? "roundCount" : "payloadCount", total);
    response.put("total", total);
    response.put(section, rows);
    response.put("nextCursor", next);
    response.put(
        "state",
        "rounds".equals(section) ? roundState(total, filter) : payloadState(total, filter));
    ctx.json(response);
  }

  private static void sendContentPayloads(Context ctx, LoadedDetail loaded, String filter) {
    int limit = windowLimit(ctx);
    String scope = cursorScope(ctx, loaded, "payloads", filter);
    long offset = windowOffset(ctx, scope);
    var items = new ArrayList<PayloadIndexDto>();
    long total = 0;
    try (var cursor = loaded.annotated().content().openCursor()) {
      while (cursor.hasNext()) {
        for (var call : cursor.next().calls()) {
          boolean child = call.scope() == com.feipi.session.browser.domain.enums.CallScope.SUBAGENT;
          for (boolean request : new boolean[] {true, false}) {
            String kind =
                child
                    ? (request ? "subagent_request" : "subagent_response")
                    : (request ? "llm_request" : "llm_response");
            String id = (child ? "sa:" : "main:") + (request ? "req:" : "resp:") + call.callId();
            var item =
                new PayloadIndexDto(
                    id,
                    kind,
                    call.callId(),
                    (request ? "Request " : "Response ") + call.callKey(),
                    false,
                    "available",
                    loaded.apiBase() + "/payload/" + ApiQueryParams.url(id));
            if (!payloadStatusMatches(filter, item.status())) continue;
            if (total >= offset && items.size() < limit) items.add(item);
            total++;
          }
        }
      }
    } catch (IOException exception) {
      throw (io.javalin.http.InternalServerErrorResponse)
          new io.javalin.http.InternalServerErrorResponse("normalized content read failed")
              .initCause(exception);
    }
    if (offset > total) throw new BadRequestResponse("cursor exceeds section total");
    long end = offset + items.size();
    sendPage(
        ctx,
        loaded,
        "payloads",
        filter,
        items,
        total,
        end < total ? SessionContentCursor.encode(scope, end) : null);
  }

  private LoadedDetail load(Context ctx) {
    return detailLoader.apply(ctx);
  }

  private static LoadedDetail loadPersonal(Context ctx, QueryCompositionRoot queryRoot) {
    String agent =
        ApiQueryParams.canonicalAgent(ApiResponses.decodePathParam(ctx.pathParam("agent")));
    String sessionId = ApiResponses.decodePathParam(ctx.pathParam("sessionId"));
    var visibility = ApiQueryParams.payloadVisibility(ctx);
    String sessionKey = agent + ":" + sessionId;
    Optional<SessionDetailUseCase.AnnotatedDetailContext> detail =
        ApiSessionDetails.loadAnnotatedDetailContext(ctx, queryRoot, sessionKey, visibility);
    return detail
        .map(
            annotated ->
                new LoadedDetail(
                    new SessionDetailFilterEcho(agent, sessionId, visibility.getValue(), "", ""),
                    annotated,
                    "/api/sessions/"
                        + ApiQueryParams.url(agent)
                        + "/"
                        + ApiQueryParams.url(sessionId),
                    // 无冻结制品的兼容行不能从持续变化的源补出未发布计数。
                    annotated.artifact() != null))
        .orElse(null);
  }

  private static AnomalyDto anomaly(DetectedAnomaly anomaly) {
    return new AnomalyDto(
        anomaly.type().getValue(), anomaly.severity().getValue(), anomaly.reason());
  }

  private static boolean statusMatches(String filter, RoundIndexDto round) {
    if ("all".equals(filter)) {
      return true;
    }
    if ("failed".equals(filter)) {
      return "failed".equals(round.status())
          || Boolean.TRUE.equals(round.parity().get("hasIssues"));
    }
    if ("low-cache".equals(filter)) {
      return Boolean.TRUE.equals(round.parity().get("isLowCache"));
    }
    return filter.equals(round.status());
  }

  private static boolean payloadStatusMatches(String filter, String status) {
    if ("failed".equals(filter)) {
      return List.of("failed", "missing", "error").contains(status);
    }
    return "all".equals(filter) || filter.equals(status);
  }

  private static long longMetric(Map<String, Object> values, String key, long fallback) {
    Object value = values.get(key);
    return value instanceof Number number ? number.longValue() : fallback;
  }

  private static PageStateDto roundState(long count, String filter) {
    return emptyOrFilteredState(
        count,
        filter,
        "No round artifact",
        "No normalized round data is available.",
        "No rounds match the selected trace status",
        "Clear the trace status filter or inspect all rounds.");
  }

  private static PageStateDto payloadState(long count, String filter) {
    return emptyOrFilteredState(
        count,
        filter,
        "No payload index",
        "No normalized payload data is available.",
        "No payloads match the selected status",
        "Clear the payload status filter or inspect all payloads.");
  }

  private static PageStateDto emptyOrFilteredState(
      long count,
      String filter,
      String emptyTitle,
      String emptyMessage,
      String noResultsTitle,
      String noResultsMessage) {
    if (count > 0) {
      return PageStateDto.ready();
    }
    return "all".equals(filter)
        ? PageStateDto.empty(emptyTitle, emptyMessage)
        : PageStateDto.noResults(noResultsTitle, noResultsMessage, List.of());
  }

  /**
   * 表示 LoadedDetail 数据。
   *
   * @param echo 该字段在 API 响应中的业务值。
   * @param annotated 带注解的 session 数据。
   * @param apiBase 当前分析范围的 API 基址。
   * @param allowSourceFiles 是否允许个人会话的本机源文件补充分析。
   */
  public record LoadedDetail(
      SessionDetailFilterEcho echo,
      SessionDetailUseCase.AnnotatedDetailContext annotated,
      String apiBase,
      boolean allowSourceFiles) {}
}
