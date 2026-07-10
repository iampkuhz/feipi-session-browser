package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.index.api.query.SessionRecord;
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
  public void handleManifest(Context ctx) {
    String requestedFormat = normalizeFormat(ctx.queryParam("format"));
    if ("unsupported".equals(requestedFormat)) {
      ctx.status(HttpStatus.BAD_REQUEST);
      ctx.json(
          new ApiResponses.ApiErrorResponse("unsupported_format", "unsupported export format"));
      return;
    }
    LoadedExport loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    long maxBytes = parseMaxBytes(ctx);
    long estimatedSizeBytes = estimateSizeBytes(detail);
    boolean ready = estimatedSizeBytes <= maxBytes;
    List<ExportFormatDto> formatRows =
        ready
            ? formats(loaded.agent(), loaded.sessionId(), loaded.visibilityValue(), requestedFormat)
            : List.of();
    ctx.json(
        new ExportManifestResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.agent(),
            loaded.sessionId(),
            detail.sessionRow().sessionKey(),
            loaded.visibilityValue(),
            maxBytes,
            estimatedSizeBytes,
            maxBytes,
            detail.hasArtifact(),
            true,
            detail.hasArtifact(),
            detail.roundCount(),
            detail.payloadSourceCount(),
            formatRows,
            ready
                ? PageStateDto.ready()
                : new PageStateDto(
                    "too_large",
                    "export_size_limit_exceeded",
                    "Export bundle is too large",
                    "Estimated export size exceeds the configured max size.",
                    List.of())));
  }

  /** 处理 /api/export/session/{agent}/{sessionId}/data-bundle 的 GET 请求。 */
  public void handleDataBundle(Context ctx) {
    LoadedExport loaded = load(ctx);
    if (loaded == null) {
      return;
    }
    SessionDetail detail = loaded.annotated().detail();
    SessionRecord row = detail.sessionRow();
    List<RoundIndexDto> rounds =
        RoundIndexProjection.exportDtos(detail, loaded.annotated().artifact());
    List<PayloadIndexDto> payloads =
        detail.payloadSources().stream()
            .map(
                source ->
                    SessionDetailApiResponses.payloadIndexDto(
                        source, loaded.agent(), loaded.sessionId()))
            .toList();
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

  private LoadedExport load(Context ctx) {
    String agent =
        ApiQueryParams.canonicalAgent(ApiResponses.decodePathParam(ctx.pathParam("agent")));
    String sessionId = ApiResponses.decodePathParam(ctx.pathParam("sessionId"));
    PayloadVisibility visibility = ApiQueryParams.payloadVisibility(ctx);
    String sessionKey = agent + ":" + sessionId;
    Optional<SessionDetailUseCase.AnnotatedDetailContext> detail =
        ApiSessionDetails.loadAnnotatedDetailContext(ctx, queryRoot, sessionKey, visibility);
    return detail
        .map(annotated -> new LoadedExport(agent, sessionId, visibility.getValue(), annotated))
        .orElse(null);
  }

  private static List<ExportFormatDto> formats(
      String agent, String sessionId, String visibilityValue, String requestedFormat) {
    String encodedAgent = ApiQueryParams.url(agent);
    String encodedSession = ApiQueryParams.url(sessionId);
    String visibility = "?visibility=" + ApiQueryParams.url(visibilityValue);
    ExportFormatDto html =
        new ExportFormatDto(
            "html",
            "/sessions/" + encodedAgent + "/" + encodedSession + "/export.html" + visibility,
            "GET",
            "text/html; charset=utf-8",
            true);
    ExportFormatDto mhtml =
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
            true);
    return switch (requestedFormat) {
      case "html" -> List.of(html);
      case "mhtml" -> List.of(mhtml);
      default -> List.of(html, mhtml);
    };
  }

  private static String normalizeFormat(String value) {
    String normalized = ApiQueryParams.normalizeAll(value);
    if ("all".equals(normalized) || "html".equals(normalized) || "mhtml".equals(normalized)) {
      return normalized;
    }
    return "unsupported";
  }

  private static long parseMaxBytes(Context ctx) {
    String raw = ctx.queryParam("max_bytes");
    if (raw == null || raw.isBlank()) {
      return MAX_EXPORT_BYTES;
    }
    try {
      long parsed = Long.parseLong(raw);
      return parsed > 0 ? parsed : MAX_EXPORT_BYTES;
    } catch (NumberFormatException ignored) {
      return MAX_EXPORT_BYTES;
    }
  }

  private static long estimateSizeBytes(SessionDetail detail) {
    long base = 16L * 1024;
    long roundBytes = detail.roundCount() * 4096L;
    long payloadBytes = detail.payloadSourceCount() * 4096L;
    return base + roundBytes + payloadBytes;
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
      SessionDetailUseCase.AnnotatedDetailContext annotated) {}
}
