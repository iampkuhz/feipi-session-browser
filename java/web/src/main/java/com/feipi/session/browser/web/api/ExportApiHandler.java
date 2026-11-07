package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
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
import com.feipi.session.browser.web.export.ContentExportSnapshot;
import io.javalin.http.Context;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

/** 提供导出 manifest 和 data-bundle 的资源 API。 */
public final class ExportApiHandler {

  private static final long MAX_EXPORT_BYTES = 50L * 1024 * 1024;

  private final QueryCompositionRoot queryRoot;
  private final java.util.function.Function<Context, LoadedExport> loader;

  /** 创建对应对象。 */
  public ExportApiHandler(QueryCompositionRoot queryRoot) {
    this.queryRoot = Objects.requireNonNull(queryRoot, "queryRoot must not be null");
    this.loader = null;
  }

  ExportApiHandler(java.util.function.Function<Context, LoadedExport> loader) {
    this.queryRoot = null;
    this.loader = Objects.requireNonNull(loader);
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
    long estimatedSizeBytes;
    try {
      if (large(loaded)) {
        try (var snapshot =
            ContentExportSnapshot.html(
                loaded.annotated().content(),
                detail.sessionRow().userMessageCount(),
                loaded.annotated().detail().visibility(),
                maxBytes,
                detail.sessionRow().sessionKey())) {
          estimatedSizeBytes = snapshot.size() + ("html".equals(requestedFormat) ? 0 : 1024);
        }
      } else {
        estimatedSizeBytes = estimateSizeBytes(detail);
      }
    } catch (ContentExportSnapshot.LimitExceededException e) {
      estimatedSizeBytes = maxBytes + 1;
    } catch (IOException e) {
      exportError(ctx, HttpStatus.INTERNAL_SERVER_ERROR, "export_failed");
      return;
    }
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
    if (large(loaded)) {
      writeContentBundle(ctx, loaded);
      return;
    }
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
                row.outputTokens(),
                row.tokenProvenance()),
            rounds.size(),
            payloads.size(),
            loaded.annotated().anomalies().anomalyCount(),
            rounds,
            payloads,
            PageStateDto.ready()));
  }

  private static boolean large(LoadedExport loaded) {
    return loaded.annotated().content() != null && loaded.annotated().artifact() == null;
  }

  /** 先将完整成员写入受大小限制的私有文件，成功后才提交 HTTP 响应。 */
  private static void writeContentBundle(Context ctx, LoadedExport loaded) {
    var detail = loaded.annotated().detail();
    var content = loaded.annotated().content();
    try {
      var reader = new SessionContentReader(content, detail.sessionRow().userMessageCount());
      try (var snapshot =
          ContentExportSnapshot.create(
              parseMaxBytes(ctx),
              output -> {
                var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                try (var json = mapper.getFactory().createGenerator(output)) {
                  json.writeStartObject();
                  json.writeStringField("schemaVersion", ApiResponses.SCHEMA_VERSION);
                  json.writeStringField("agent", loaded.agent());
                  json.writeStringField("sessionId", loaded.sessionId());
                  json.writeStringField("sessionKey", detail.sessionRow().sessionKey());
                  json.writeStringField("visibility", loaded.visibilityValue());
                  json.writeObjectField(
                      "tokens",
                      TokenSegments.of(
                          detail.sessionRow().freshInputTokens(),
                          detail.sessionRow().cacheReadTokens(),
                          detail.sessionRow().cacheWriteTokens(),
                          detail.sessionRow().outputTokens(),
                          detail.sessionRow().tokenProvenance()));
                  json.writeNumberField("roundCount", detail.roundCount());
                  json.writeNumberField("payloadCount", detail.payloadSourceCount());
                  json.writeNumberField(
                      "anomalyCount", loaded.annotated().anomalies().anomalyCount());
                  json.writeObjectField("rounds", SessionContentProjection.rounds(detail, content));
                  json.writeArrayFieldStart("payloads");
                  Long next = 0L;
                  do {
                    var page = reader.payloadSources(detail.visibility(), next, 500);
                    for (var source : page.items()) {
                      json.writeObject(
                          SessionDetailApiResponses.payloadIndexDto(
                              source, loaded.agent(), loaded.sessionId()));
                    }
                    next = page.nextCursor();
                  } while (next != null);
                  json.writeEndArray();
                  json.writeArrayFieldStart("calls");
                  try (var cursor = content.openCursor()) {
                    while (cursor.hasNext()) {
                      for (var call : cursor.next().calls()) {
                        json.writeStartObject();
                        json.writeStringField(
                            "callId", ContentExportSnapshot.safeText(call.callId()));
                        json.writeNumberField("callIndex", call.callIndex());
                        json.writeNumberField(
                            "roundIndex",
                            reader.roundIndex().roundIndexForCall(call.callId()).orElseThrow());
                        json.writeNumberField("totalTokens", call.usage().total());
                        json.writeStringField(
                            "request",
                            ContentExportSnapshot.safeText(
                                reader.payload(call, true, detail.visibility()).content()));
                        json.writeStringField(
                            "response",
                            ContentExportSnapshot.safeText(
                                reader.payload(call, false, detail.visibility()).content()));
                        json.writeEndObject();
                      }
                    }
                  }
                  json.writeEndArray();
                  json.writeArrayFieldStart("tools");
                  try (var cursor = content.openCursor()) {
                    while (cursor.hasNext()) {
                      for (var tool : cursor.next().toolExecutions()) {
                        json.writeStartObject();
                        json.writeStringField(
                            "toolCallId", ContentExportSnapshot.safeText(tool.toolCallId()));
                        json.writeStringField(
                            "declaredByCallId",
                            ContentExportSnapshot.safeText(tool.declaredByCallId()));
                        json.writeStringField("name", ContentExportSnapshot.safeText(tool.name()));
                        for (String kind : new String[] {"input", "result"}) {
                          var payload =
                              reader.payload(
                                  "tool:" + kind + ":" + tool.toolCallId(), detail.visibility());
                          if (payload.isEmpty())
                            throw new IOException("Export tool payload unavailable");
                          json.writeStringField(
                              kind, ContentExportSnapshot.safeText(payload.get().content()));
                        }
                        json.writeEndObject();
                      }
                    }
                  }
                  json.writeEndArray();
                  json.writeObjectField("state", PageStateDto.ready());
                  json.writeEndObject();
                }
              })) {
        ctx.contentType("application/json; charset=utf-8");
        snapshot.copyTo(ctx.outputStream());
      }
    } catch (ContentExportSnapshot.LimitExceededException e) {
      exportError(ctx, HttpStatus.CONTENT_TOO_LARGE, "export_too_large");
    } catch (IOException e) {
      exportError(ctx, HttpStatus.INTERNAL_SERVER_ERROR, "export_failed");
    }
  }

  private static void exportError(Context ctx, HttpStatus status, String code) {
    ctx.status(status);
    ctx.json(new ApiResponses.ApiErrorResponse(code, "Export could not be completed"));
  }

  private LoadedExport load(Context ctx) {
    if (loader != null) return loader.apply(ctx);
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
      return parsed > 0 ? Math.min(parsed, MAX_EXPORT_BYTES) : MAX_EXPORT_BYTES;
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
  record LoadedExport(
      String agent,
      String sessionId,
      String visibilityValue,
      SessionDetailUseCase.AnnotatedDetailContext annotated) {}
}
