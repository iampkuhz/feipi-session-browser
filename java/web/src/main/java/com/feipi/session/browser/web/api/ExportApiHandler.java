package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.web.api.ExportApiResponses.ExportDataBundleResponse;
import com.feipi.session.browser.web.api.ExportApiResponses.ExportFormatDto;
import com.feipi.session.browser.web.api.ExportApiResponses.ExportManifestResponse;
import com.feipi.session.browser.web.api.PageApiDtos.PageStateDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.PayloadIndexDto;
import com.feipi.session.browser.web.api.SessionDetailApiResponses.RoundIndexDto;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.sql.SQLException;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/** 提供导出 manifest 和 data-bundle 的资源 API。 */
public final class ExportApiHandler {

  private static final long MAX_EXPORT_BYTES = 50L * 1024 * 1024;

  private final QueryCompositionRoot queryRoot;

  /** 创建对应对象。 */
  public ExportApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
  }

  /** 处理 /api/export/session/{agent}/{sessionId}/manifest 的 GET 请求。 */
  public void handleManifest(Context ctx) throws SQLException {
    LoadedExport loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    ctx.json(
        new ExportManifestResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.agent(),
            loaded.sessionId(),
            detail.sessionRow().sessionKey(),
            loaded.visibilityValue(),
            MAX_EXPORT_BYTES,
            detail.hasArtifact(),
            detail.roundCount(),
            detail.payloadSourceCount(),
            formats(loaded.agent(), loaded.sessionId(), loaded.visibilityValue()),
            PageStateDto.ready()));
  }

  /** 处理 /api/export/session/{agent}/{sessionId}/data-bundle 的 GET 请求。 */
  public void handleDataBundle(Context ctx) throws SQLException {
    LoadedExport loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionRow row = detail.sessionRow();
    List<RoundIndexDto> rounds =
        detail.rounds().stream().map(round -> roundDto(round, row.totalTokens())).toList();
    List<PayloadIndexDto> payloads =
        detail.payloadSources().stream().map(ExportApiHandler::payloadDto).toList();
    ctx.json(
        new ExportDataBundleResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.agent(),
            loaded.sessionId(),
            row.sessionKey(),
            loaded.visibilityValue(),
            TokenSegments.of(
                row.freshInputTokens(),
                row.cacheReadTokens(),
                row.cacheWriteTokens(),
                row.outputTokens()),
            rounds.size(),
            payloads.size(),
            loaded.annotated().anomalies().anomalyCount(),
            rounds,
            payloads,
            PageStateDto.ready()));
  }

  private LoadedExport load(Context ctx) throws SQLException {
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
      return new LoadedExport(agent, sessionId, visibilityValue(visibility), detail.get());
    } catch (IOException e) {
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(
          new ApiResponses.ApiErrorResponse("artifact_error", "normalized artifact load failed"));
      return null;
    }
  }

  private static List<ExportFormatDto> formats(
      String agent, String sessionId, String visibilityValue) {
    String encodedAgent = ApiQueryParams.url(agent);
    String encodedSession = ApiQueryParams.url(sessionId);
    String visibility = "?visibility=" + ApiQueryParams.url(visibilityValue);
    return List.of(
        new ExportFormatDto(
            "html",
            "/sessions/" + encodedAgent + "/" + encodedSession + "/export.html" + visibility,
            "GET",
            "text/html; charset=utf-8",
            true),
        new ExportFormatDto(
            "mhtml",
            "/export/mhtml?agent="
                + encodedAgent
                + "&session_id="
                + encodedSession
                + "&visibility="
                + ApiQueryParams.url(visibilityValue),
            "GET",
            "multipart/related",
            true));
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
   * 表示 LoadedExport 数据。
   *
   * @param agent agent 类型标识。
   * @param sessionId provider session 标识符。
   * @param visibilityValue 导出可见性策略值。
   * @param annotated 带注解的 session 数据。
   */
  private record LoadedExport(
      String agent,
      String sessionId,
      String visibilityValue,
      SessionDetailUseCase.AnnotatedDetail annotated) {}
}
