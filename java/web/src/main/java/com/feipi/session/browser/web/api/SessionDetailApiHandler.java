package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
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
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
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
            readingMeta(loaded, parity.meta),
            PageStateDto.ready()));
  }

  private static Map<String, Object> readingMeta(LoadedDetail loaded, Map<String, Object> base) {
    var meta = new LinkedHashMap<>(base);
    try {
      var content = readingContent(loaded);
      if (content == null) return meta;
      if (content.header().totals().getOrDefault("calls", 0L) == 0) {
        var reader =
            new SessionContentReader(
                content, loaded.annotated().detail().sessionRow().userMessageCount());
        String observed = reader.observedInputPreview();
        if (!observed.isBlank()) addFirstUserPrompt(meta, observed, "round:req:1");
        return meta;
      }
      var previews = SessionContentPreviews.read(content);
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          for (var call : cursor.next().calls()) {
            if (call.scope() != CallScope.MAIN) continue;
            String text = previews.userText(call, 1);
            if (text.isBlank()) continue;
            addFirstUserPrompt(meta, text, "main:req:" + call.callId());
            return meta;
          }
        }
      }
      return meta;
    } catch (IOException exception) {
      throw new IllegalStateException("无法读取已验证的首问预览", exception);
    }
  }

  private static void addFirstUserPrompt(Map<String, Object> meta, String text, String payloadId) {
    meta.put("firstUserPrompt", text);
    meta.put("firstUserPromptPayloadId", payloadId);
  }

  private static NormalizedSessionContent readingContent(LoadedDetail loaded) throws IOException {
    var content = loaded.annotated().content();
    return content != null || loaded.annotated().artifact() == null
        ? content
        : NormalizedSessionContent.fromArtifact(loaded.annotated().artifact());
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
    var counts = RoundCounts.from(rows);
    String target = ctx.queryParam("target");
    if (paged(ctx, loaded) || target != null) {
      if (target != null && ctx.queryParam("cursor") != null)
        throw new BadRequestResponse("choose target or cursor");
      sendWindow(
          ctx,
          loaded,
          rows,
          "rounds",
          traceStatus,
          counts,
          target == null ? -1 : RoundTarget.rowOffset(rows, target));
      return;
    }
    ctx.json(
        new SessionRoundsResponse(
            ApiResponses.SCHEMA_VERSION,
            loaded.echo().withTraceStatus(traceStatus),
            rows.size(),
            counts.confirmed(),
            counts.unconfirmedRounds(),
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
            .toList();
    rows =
        payloadMetadata(loaded, rows).stream()
            .filter(payload -> payloadStatusMatches(payloadStatus, payload.status()))
            .toList();
    if (paged(ctx, loaded)) {
      sendWindow(ctx, loaded, rows, "payloads", payloadStatus, null, -1);
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
      Context ctx,
      LoadedDetail loaded,
      List<T> rows,
      String section,
      String filter,
      RoundCounts roundCounts,
      long targetOffset) {
    int limit = windowLimit(ctx);
    String scope = cursorScope(ctx, loaded, section, filter);
    long offset = targetOffset < 0 ? windowOffset(ctx, scope) : targetOffset;
    if (offset > rows.size()) throw new BadRequestResponse("cursor exceeds section total");
    int end = (int) Math.min(rows.size(), offset + limit);
    sendPage(
        ctx,
        loaded,
        section,
        filter,
        new PageWindow(
            rows.subList((int) offset, end),
            rows.size(),
            offset,
            end < rows.size() ? SessionContentCursor.encode(scope, end) : null,
            roundCounts));
  }

  private static void sendPage(
      Context ctx, LoadedDetail loaded, String section, String filter, PageWindow window) {
    Map<String, Object> response = new LinkedHashMap<>();
    response.put("schemaVersion", ApiResponses.SCHEMA_VERSION);
    response.put(
        "filters",
        "rounds".equals(section)
            ? loaded.echo().withTraceStatus(filter)
            : loaded.echo().withPayloadStatus(filter));
    boolean rounds = "rounds".equals(section);
    response.put(rounds ? "roundCount" : "payloadCount", window.total());
    response.put("total", window.total());
    response.put("offset", window.offset());
    if (window.roundCounts() != null) {
      response.put("modelCallCount", window.roundCounts().confirmed());
      response.put("recordGroupCount", window.roundCounts().unconfirmedRounds());
    }
    response.put(section, window.rows());
    response.put("nextCursor", window.next());
    response.put(
        "state",
        rounds ? roundState(window.total(), filter) : payloadState(window.total(), filter));
    ctx.json(response);
  }

  private static List<PayloadIndexDto> payloadMetadata(
      LoadedDetail loaded, List<PayloadIndexDto> rows) {
    try {
      var content = readingContent(loaded);
      if (content == null) return rows;
      var index = ContentRoundIndex.build(content, 0);
      var previews = SessionContentPreviews.read(content);
      var labels = SessionContentPreviews.roundLabels(content, index);
      var calls = new HashMap<String, NormalizedCall>();
      for (var call : loaded.annotated().artifact().calls()) calls.put(call.callId(), call);
      return rows.stream()
          .map(
              row -> {
                var call = calls.get(row.callId());
                if (call == null) return row;
                int round = index.roundIndexForCall(call.callId()).orElse(0);
                String label = labels.getOrDefault(round, "");
                return new PayloadIndexDto(
                    row.payloadId(),
                    row.kind(),
                    row.callId(),
                    row.title(),
                    row.truncated(),
                    payloadReadingStatus(row, previews, call),
                    row.apiUrl(),
                    round,
                    label,
                    call.scope().name().toLowerCase(Locale.ROOT),
                    call.subagentId().orElse(""),
                    call.callKey(),
                    previews.text(call, row.kind().endsWith("request")),
                    previews.timestamp(call));
              })
          .toList();
    } catch (IOException exception) {
      throw new IllegalStateException("无法读取已验证的原文索引元数据", exception);
    }
  }

  private static String payloadReadingStatus(
      PayloadIndexDto row, SessionContentPreviews previews, NormalizedCall call) {
    if ((row.kind().endsWith("_request") || row.kind().endsWith("_response"))
        && "available".equals(row.status())
        && !previews.hasPayload(call, row.kind().endsWith("_request"))) return "missing";
    return row.status();
  }

  private static void sendContentPayloads(Context ctx, LoadedDetail loaded, String filter) {
    int limit = windowLimit(ctx);
    String scope = cursorScope(ctx, loaded, "payloads", filter);
    long offset = windowOffset(ctx, scope);
    var items = new ArrayList<PayloadIndexDto>();
    long total = 0;
    try {
      var content = readingContent(loaded);
      var index = ContentRoundIndex.build(content, 0);
      var previews = SessionContentPreviews.read(content);
      var labels = SessionContentPreviews.roundLabels(content, index);
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          for (var call : cursor.next().calls()) {
            boolean child = call.scope() == CallScope.SUBAGENT;
            for (boolean request : new boolean[] {true, false}) {
              String status = previews.hasPayload(call, request) ? "available" : "missing";
              if (!payloadStatusMatches(filter, status)) continue;
              if (total++ < offset || items.size() >= limit) continue;
              int round = index.roundIndexForCall(call.callId()).orElse(0);
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
                      status,
                      loaded.apiBase() + "/payload/" + ApiQueryParams.url(id),
                      round,
                      labels.getOrDefault(round, ""),
                      call.scope().name().toLowerCase(Locale.ROOT),
                      call.subagentId().orElse(""),
                      call.callKey(),
                      previews.text(call, request),
                      previews.timestamp(call));
              items.add(item);
            }
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
        new PageWindow(
            items,
            total,
            offset,
            end < total ? SessionContentCursor.encode(scope, end) : null,
            null));
  }

  private LoadedDetail load(Context ctx) {
    return detailLoader.apply(ctx);
  }

  /** 返回有界执行摘要；全量诊断与目标定位均由同范围的冻结内容计算。 */
  public void handleExecution(Context ctx) {
    LoadedDetail loaded = load(ctx);
    if (loaded == null) return;
    int limit = 20;
    try {
      if (ctx.queryParam("limit") != null) limit = Integer.parseInt(ctx.queryParam("limit"));
      if (limit < 1 || limit > 100) throw new NumberFormatException();
    } catch (NumberFormatException exception) {
      throw (BadRequestResponse)
          new BadRequestResponse("limit must be between 1 and 100").initCause(exception);
    }
    String filter = Optional.ofNullable(ctx.queryParam("status")).orElse("all");
    if (!List.of("all", "failed").contains(filter))
      throw new BadRequestResponse("invalid execution status");
    String scope = cursorScope(ctx, loaded, "execution", filter + ":" + limit);
    var content = loaded.annotated().content();
    if (content == null && loaded.annotated().artifact() != null) {
      content =
          com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
              loaded.annotated().artifact());
    }
    try {
      if (content == null) {
        if (ctx.queryParam("cursor") != null || ctx.queryParam("target") != null)
          throw new BadRequestResponse("no execution content");
        ctx.json(
            new SessionExecutionProjection.Page(
                ApiResponses.SCHEMA_VERSION,
                List.of(),
                0,
                0,
                null,
                new SessionExecutionProjection.Diagnostics(0, 0, 0, 0, "", List.of(), 0, null)));
        return;
      }
      if ("1".equals(ctx.queryParam("summary"))) {
        ctx.json(
            new SessionExecutionProjection.Page(
                ApiResponses.SCHEMA_VERSION,
                List.of(),
                0,
                0,
                null,
                SessionExecutionProjection.diagnostics(content)));
        return;
      }
      var page =
          SessionExecutionProjection.read(
              content, scope, ctx.queryParam("cursor"), limit, ctx.queryParam("target"), filter);
      if (page.total() == 0
          && "all".equals(filter)
          && loaded.annotated().detail().sessionRow().userMessageCount() > 0) {
        var reader =
            new com.feipi.session.browser.application.sessiondetail.SessionContentReader(
                content, loaded.annotated().detail().sessionRow().userMessageCount());
        if (reader.hasObservedInput()) {
          var input =
              new SessionExecutionProjection.Group(
                  "observed-input:1",
                  1,
                  1,
                  "用户输入记录",
                  "main",
                  "",
                  "",
                  reader.observedInputPreview(),
                  0,
                  false,
                  "",
                  true,
                  false);
          page =
              new SessionExecutionProjection.Page(
                  page.schemaVersion(),
                  List.of(new SessionExecutionProjection.Item(input, null, 0)),
                  1,
                  0,
                  null,
                  null);
        }
      }
      ctx.json(
          new SessionExecutionProjection.Page(
              page.schemaVersion(),
              page.items(),
              page.total(),
              page.offset(),
              page.nextCursor(),
              SessionExecutionProjection.diagnostics(content)));
    } catch (IllegalArgumentException exception) {
      throw (BadRequestResponse)
          new BadRequestResponse("invalid execution cursor").initCause(exception);
    } catch (IOException exception) {
      throw (io.javalin.http.InternalServerErrorResponse)
          new io.javalin.http.InternalServerErrorResponse("normalized content read failed")
              .initCause(exception);
    }
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

  /**
   * 当前筛选范围内的一页记录及其全量计数。
   *
   * @param rows 当前页记录
   * @param total 筛选后的全量记录数
   * @param offset 当前页在筛选结果中的起始偏移
   * @param next 下一页游标，末页为空
   * @param roundCounts 已确认调用和未确认记录组数量，非 Trace 资源为空
   */
  private record PageWindow(
      List<?> rows, long total, long offset, String next, RoundCounts roundCounts) {}

  /**
   * 两种计数单位不可相减：一个任务轮可以包含多个已确认调用。
   *
   * @param confirmed 筛选范围内已确认的调用数
   * @param unconfirmedRounds 筛选范围内没有已确认调用的轮次数
   */
  private record RoundCounts(long confirmed, long unconfirmedRounds) {
    private static RoundCounts from(List<RoundIndexDto> rows) {
      long calls = 0;
      long groups = 0;
      for (var row : rows) {
        Object count = row.parity().get("confirmedCallCount");
        long observed =
            count instanceof Number number
                ? number.longValue()
                : row.parity().get("modelCallEvidence") instanceof String evidence
                        && !evidence.isEmpty()
                    ? 1
                    : 0;
        calls += observed;
        if (observed == 0) groups++;
      }
      return new RoundCounts(calls, groups);
    }
  }
}
