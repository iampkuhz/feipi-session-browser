package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadVisibility;
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
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.sql.SQLException;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/** Session Detail 页面的资源 API。 */
public final class SessionDetailApiHandler {

  private final QueryCompositionRoot queryRoot;

  /** 创建对应对象。 */
  public SessionDetailApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/meta 的 GET 请求。 */
  public void handleMeta(Context ctx) throws SQLException {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionRow row = detail.sessionRow();
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
            PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/metrics 的 GET 请求。 */
  public void handleMetrics(Context ctx) throws SQLException {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionRow row = detail.sessionRow();
    ctx.json(
        new SessionMetricsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo(),
            TokenSegments.of(
                row.freshInputTokens(),
                row.cacheReadTokens(),
                row.cacheWriteTokens(),
                row.outputTokens()),
            row.userMessageCount(),
            row.assistantMessageCount(),
            row.toolCallCount(),
            row.failedToolCount(),
            row.subagentInstanceCount(),
            row.durationSeconds(),
            row.modelExecutionSeconds(),
            row.toolExecutionSeconds(),
            detail.roundCount(),
            detail.payloadSourceCount(),
            PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/diagnostics 的 GET 请求。 */
  public void handleDiagnostics(Context ctx) throws SQLException {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionAnomalySummary anomalies = loaded.annotated().anomalies();
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
            rows.isEmpty()
                ? PageStateDto.empty("No diagnostics triggered", "This session has no anomalies.")
                : PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/rounds 的 GET 请求。 */
  public void handleRounds(Context ctx) throws SQLException {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    long sessionTokens = detail.sessionRow().totalTokens();
    List<RoundIndexDto> rows =
        detail.rounds().stream().map(round -> roundDto(round, sessionTokens)).toList();
    ctx.json(
        new SessionRoundsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo(),
            rows.size(),
            rows,
            rows.isEmpty()
                ? PageStateDto.empty("No round artifact", "No normalized round data is available.")
                : PageStateDto.ready()));
  }

  /** 处理 /api/sessions/{agent}/{sessionId}/payloads 的 GET 请求。 */
  public void handlePayloads(Context ctx) throws SQLException {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    List<PayloadIndexDto> rows =
        loaded.annotated().detail().payloadSources().stream()
            .map(SessionDetailApiHandler::payloadDto)
            .toList();
    ctx.json(
        new SessionPayloadsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo(),
            rows.size(),
            rows,
            rows.isEmpty()
                ? PageStateDto.empty("No payload index", "No normalized payload data is available.")
                : PageStateDto.ready()));
  }

  private LoadedDetail load(Context ctx) throws SQLException {
    String agent = canonicalAgent(ApiResponses.decodePathParam(ctx.pathParam("agent")));
    String sessionId = ApiResponses.decodePathParam(ctx.pathParam("sessionId"));
    PayloadVisibility visibility = parseVisibility(ctx);
    String sessionKey = agent + ":" + sessionId;
    try {
      Optional<SessionDetailUseCase.AnnotatedDetail> detail =
          queryRoot.sessionDetail().getDetailWithAnomalies(sessionKey, visibility);
      if (detail.isEmpty()) {
        ctx.status(HttpStatus.NOT_FOUND);
        ctx.json(new ApiResponses.ApiErrorResponse("not_found", "session not found"));
        return null;
      }
      return new LoadedDetail(
          new SessionDetailFilterEcho(agent, sessionId, visibilityValue(visibility)), detail.get());
    } catch (IOException e) {
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(
          new ApiResponses.ApiErrorResponse("artifact_error", "normalized artifact load failed"));
      return null;
    }
  }

  private static RoundIndexDto roundDto(CallRound round, long sessionTokens) {
    Double tokenShare = sessionTokens > 0 ? round.totalTokens() / (double) sessionTokens : null;
    return new RoundIndexDto(
        round.roundIndex(),
        round.calls(),
        round.toolCallIds(),
        round.parentCallId(),
        TokenSegments.of(
            round.freshInputTokens(),
            round.cacheReadTokens(),
            round.cacheWriteTokens(),
            round.outputTokens()),
        round.callCount(),
        round.toolCallCount(),
        tokenShare);
  }

  private static PayloadIndexDto payloadDto(PayloadSource source) {
    return new PayloadIndexDto(
        source.payloadId(),
        source.kind().getValue(),
        source.callId(),
        source.title(),
        source.truncated());
  }

  private static AnomalyDto anomaly(DetectedAnomaly anomaly) {
    return new AnomalyDto(
        anomaly.type().getValue(), anomaly.severity().getValue(), anomaly.reason());
  }

  private static PayloadVisibility parseVisibility(Context ctx) {
    return "full".equalsIgnoreCase(ctx.queryParam("visibility"))
        ? PayloadVisibility.FULL
        : PayloadVisibility.STANDARD;
  }

  private static String visibilityValue(PayloadVisibility visibility) {
    return visibility == PayloadVisibility.FULL ? "full" : "standard";
  }

  private static String canonicalAgent(String agent) {
    return "claude-code".equals(agent) ? "claude_code" : agent;
  }

  /**
   * 表示 LoadedDetail 数据。
   *
   * @param echo 该字段在 API 响应中的业务值。
   * @param annotated 带注解的 session 数据。
   */
  private record LoadedDetail(
      SessionDetailFilterEcho echo, SessionDetailUseCase.AnnotatedDetail annotated) {}
}
