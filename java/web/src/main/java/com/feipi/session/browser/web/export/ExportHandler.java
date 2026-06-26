package com.feipi.session.browser.web.export;

import com.feipi.session.browser.application.QueryCompositionRoot;
import com.feipi.session.browser.application.SessionDetailUseCase;
import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.PayloadSource;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.Header;
import io.javalin.http.HttpStatus;
import java.io.IOException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 会话导出端点处理器。
 *
 * <p>支持将会话页面导出为 MHTML 或独立 HTML 格式，便于离线浏览和存档。
 *
 * <p>安全措施：
 *
 * <ul>
 *   <li>响应体大小限制（{@value #MAX_EXPORT_BYTES} 字节），超限返回 413
 *   <li>明确的 Content-Type 和 charset，禁止浏览器推测内容类型
 *   <li>Content-Disposition 包含文件名，阻止浏览器内联渲染
 *   <li>导出内容不包含本地绝对路径，只使用相对引用
 * </ul>
 *
 * <p>校验放置：导出格式、大小限制在 HTTP adapter 入口校验，下游渲染信任已验证的参数。
 */
public final class ExportHandler {

  private static final Logger LOG = LoggerFactory.getLogger(ExportHandler.class);

  /** 导出响应体最大字节数（50 MB）。 */
  static final long MAX_EXPORT_BYTES = 50L * 1024 * 1024;

  /** 多部分关联内容类型，用于 MHTML 导出。 */
  static final String MHTML_CONTENT_TYPE = "multipart/related";

  /** 独立页面内容类型，用于 HTML 导出。 */
  static final String HTML_CONTENT_TYPE = "text/html; charset=utf-8";

  private final PebbleEnvironment templates;
  private final QueryCompositionRoot queryRoot;

  /**
   * 创建导出处理器（无查询能力，仅支持占位导出）。
   *
   * @param templates Pebble 模板环境
   */
  public ExportHandler(PebbleEnvironment templates) {
    this(templates, null);
  }

  /**
   * 创建导出处理器。
   *
   * @param templates Pebble 模板环境
   * @param queryRoot 查询 composition root，提供 session detail use case；null 时不支持完整导出
   */
  public ExportHandler(PebbleEnvironment templates, QueryCompositionRoot queryRoot) {
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
    this.queryRoot = queryRoot;
  }

  /**
   * 处理导出请求。
   *
   * <p>路径格式：{@code GET /export/{format}?agent=...&session_id=...}
   *
   * @param ctx Javalin 请求上下文
   */
  public void handleExport(Context ctx) {
    String format = ctx.pathParam("format");
    String agent = ctx.queryParam("agent");
    String sessionId = ctx.queryParam("session_id");

    if (agent == null || agent.isBlank() || sessionId == null || sessionId.isBlank()) {
      ctx.status(HttpStatus.BAD_REQUEST);
      ctx.json(Map.of("error", "missing_params", "message", "缺少 agent 或 session_id 参数"));
      return;
    }

    if (!"html".equals(format) && !"mhtml".equals(format)) {
      ctx.status(HttpStatus.BAD_REQUEST);
      ctx.json(Map.of("error", "unsupported_format", "message", "不支持的导出格式: " + format));
      return;
    }

    try {
      if ("html".equals(format)) {
        exportHtml(ctx, agent, sessionId);
      } else {
        exportMhtml(ctx, agent, sessionId);
      }
    } catch (ExportSizeExceededException e) {
      LOG.warn("导出内容超限: agent={}, session={}", agent, sessionId);
      ctx.status(HttpStatus.CONTENT_TOO_LARGE);
      ctx.json(Map.of("error", "export_too_large", "message", "导出内容超过大小限制"));
    } catch (Exception e) {
      LOG.error("导出失败: agent={}, session={}", agent, sessionId, e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(Map.of("error", "export_failed", "message", "导出失败"));
    }
  }

  /**
   * 处理 session 详情页导出请求。
   *
   * <p>路径格式：{@code GET /sessions/{agent}/{sessionId}/export.html}
   *
   * @param ctx Javalin 请求上下文
   * @param agent URL 中的 agent 标识（已 URL 编码）
   * @param sessionId URL 中的会话标识（已 URL 编码）
   */
  public void exportSessionHtml(Context ctx, String agent, String sessionId) {
    if (queryRoot == null) {
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(Map.of("error", "export_not_available", "message", "导出功能不可用"));
      return;
    }

    String decodedAgent = URLDecoder.decode(agent, StandardCharsets.UTF_8);
    String decodedSessionId = URLDecoder.decode(sessionId, StandardCharsets.UTF_8);
    String sessionKey = decodedAgent + ":" + decodedSessionId;
    PayloadVisibility visibility = parseVisibility(ctx);

    try {
      SessionDetailUseCase useCase = queryRoot.sessionDetail();
      Optional<SessionDetailUseCase.AnnotatedDetail> resultOpt =
          useCase.getDetailWithAnomalies(sessionKey, visibility);

      if (resultOpt.isEmpty()) {
        ctx.status(HttpStatus.NOT_FOUND);
        ctx.json(Map.of("error", "session_not_found", "message", "会话不存在: " + sessionKey));
        return;
      }

      SessionDetailUseCase.AnnotatedDetail annotated = resultOpt.get();
      SessionDetail detail = annotated.detail();
      SessionAnomalySummary anomalies = annotated.anomalies();

      Map<String, Object> context =
          buildExportContext(detail, anomalies, decodedAgent, decodedSessionId, visibility);
      String html = templates.render("export-session.html", context);
      byte[] bytes = html.getBytes(StandardCharsets.UTF_8);

      if (bytes.length > MAX_EXPORT_BYTES) {
        throw new ExportSizeExceededException(bytes.length, MAX_EXPORT_BYTES);
      }

      String fileName = "session-" + sanitizeFileName(decodedSessionId) + ".html";
      ctx.contentType(HTML_CONTENT_TYPE);
      ctx.header(Header.CONTENT_DISPOSITION, "attachment; filename=\"" + fileName + "\"");
      ctx.result(bytes);

    } catch (SQLException e) {
      LOG.error("导出查询失败: {}", sessionKey, e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(Map.of("error", "export_query_failed", "message", "导出查询失败"));
    } catch (IOException e) {
      LOG.error("导出制品读取失败: {}", sessionKey, e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(Map.of("error", "export_artifact_failed", "message", "制品读取失败"));
    } catch (ExportSizeExceededException e) {
      LOG.warn("导出内容超限: {}", sessionKey);
      ctx.status(HttpStatus.CONTENT_TOO_LARGE);
      ctx.json(Map.of("error", "export_too_large", "message", "导出内容超过大小限制"));
    } catch (Exception e) {
      LOG.error("导出失败: {}", sessionKey, e);
      ctx.status(HttpStatus.INTERNAL_SERVER_ERROR);
      ctx.json(Map.of("error", "export_failed", "message", "导出失败"));
    }
  }

  /** 构建导出模板上下文。 */
  private static Map<String, Object> buildExportContext(
      SessionDetail detail,
      SessionAnomalySummary anomalies,
      String agent,
      String sessionId,
      PayloadVisibility visibility) {

    SessionRow row = detail.sessionRow();
    List<CallRound> rounds = detail.rounds();
    List<PayloadSource> payloadSources = detail.payloadSources();

    Map<String, Object> context = new HashMap<>();

    // Session 基本信息
    context.put("session", row);
    context.put("current_agent", agent);
    context.put("session_id", sessionId);
    context.put("session_key", row.sessionKey());
    context.put("export_timestamp", currentTimestamp());
    context.put("active_page", "export");

    // 可见性
    context.put("visibility", visibility.name().toLowerCase());
    context.put("payload_hidden", visibility == PayloadVisibility.STANDARD);
    context.put("has_artifact", detail.hasArtifact());

    // 异常检测
    context.put("anomalies", anomalies);
    context.put("anomaly_count", anomalies.anomalyCount());
    context.put("has_anomalies", anomalies.anomalyCount() > 0);
    context.put("anomaly_list", buildAnomalyDisplayList(anomalies));

    // Rounds — 完整导出所有 round，不做截断
    context.put("rounds", buildExportRoundList(rounds));
    context.put("round_count", rounds.size());
    context.put("has_rounds", !rounds.isEmpty());

    // Payload 来源摘要
    context.put("payload_sources", buildPayloadSourceSummary(payloadSources));
    context.put("payload_source_count", payloadSources.size());

    // Session 指标
    context.put("session_metrics", buildSessionMetrics(row));

    return context;
  }

  /** 解析 payload 可见性查询参数。 */
  private static PayloadVisibility parseVisibility(Context ctx) {
    String visParam = ctx.queryParam("visibility");
    if ("full".equalsIgnoreCase(visParam)) {
      return PayloadVisibility.FULL;
    }
    return PayloadVisibility.STANDARD;
  }

  /** 生成独立 HTML 导出（占位模式，无完整数据）。 */
  private void exportHtml(Context ctx, String agent, String sessionId) {
    // 模板上下文使用原始字符串，Pebble auto-escaping 负责 XSS 防护
    Map<String, Object> context = new HashMap<>();
    context.put("agent", agent);
    context.put("session_id", sessionId);
    context.put("export_timestamp", currentTimestamp());
    context.put("active_page", "export");

    String html = templates.render("export.html", context);
    byte[] bytes = html.getBytes(StandardCharsets.UTF_8);

    if (bytes.length > MAX_EXPORT_BYTES) {
      throw new ExportSizeExceededException(bytes.length, MAX_EXPORT_BYTES);
    }

    String fileName = "session-" + sanitizeFileName(sessionId) + ".html";
    ctx.contentType(HTML_CONTENT_TYPE);
    ctx.header(Header.CONTENT_DISPOSITION, "attachment; filename=\"" + fileName + "\"");
    ctx.result(bytes);
  }

  /** 生成 MHTML 导出。 */
  private void exportMhtml(Context ctx, String agent, String sessionId) {
    Map<String, Object> context = new HashMap<>();
    context.put("agent", agent);
    context.put("session_id", sessionId);
    context.put("export_timestamp", currentTimestamp());
    context.put("active_page", "export");

    String html = templates.render("export.html", context);
    String boundary = "----=_Part_FeiPi_Export_" + System.currentTimeMillis();
    String mhtml = buildMhtmlEnvelope(html, boundary);

    byte[] bytes = mhtml.getBytes(StandardCharsets.UTF_8);
    if (bytes.length > MAX_EXPORT_BYTES) {
      throw new ExportSizeExceededException(bytes.length, MAX_EXPORT_BYTES);
    }

    String fileName = "session-" + sanitizeFileName(sessionId) + ".mhtml";
    ctx.contentType(MHTML_CONTENT_TYPE + "; boundary=\"" + boundary + "\"");
    ctx.header(Header.CONTENT_DISPOSITION, "attachment; filename=\"" + fileName + "\"");
    ctx.result(bytes);
  }

  /** 构建 MHTML 信封。 */
  private static String buildMhtmlEnvelope(String html, String boundary) {
    StringBuilder sb = new StringBuilder(html.length() + 256);
    sb.append("MIME-Version: 1.0\r\n");
    sb.append("Content-Type: multipart/related; boundary=\"").append(boundary).append("\"\r\n\r\n");
    sb.append("--").append(boundary).append("\r\n");
    sb.append("Content-Type: text/html; charset=utf-8\r\n");
    sb.append("Content-Transfer-Encoding: quoted-printable\r\n\r\n");
    sb.append(html);
    sb.append("\r\n--").append(boundary).append("--\r\n");
    return sb.toString();
  }

  /** 返回 RFC 1123 格式时间戳。 */
  private static String currentTimestamp() {
    return ZonedDateTime.now(ZoneOffset.UTC).format(DateTimeFormatter.RFC_1123_DATE_TIME);
  }

  /** 清理文件名，移除非字母数字字符。 */
  static String sanitizeFileName(String raw) {
    StringBuilder sb = new StringBuilder(raw.length());
    for (int i = 0; i < raw.length(); i++) {
      char c = raw.charAt(i);
      if (Character.isLetterOrDigit(c) || c == '-' || c == '_') {
        sb.append(c);
      }
    }
    String result = sb.toString();
    if (result.isEmpty()) {
      return "export";
    }
    if (result.length() > 100) {
      result = result.substring(0, 100);
    }
    return result;
  }

  /** 构建异常展示列表。 */
  private static List<Map<String, String>> buildAnomalyDisplayList(
      SessionAnomalySummary anomalies) {
    List<Map<String, String>> result = new ArrayList<>();
    for (DetectedAnomaly anomaly : anomalies.anomalies()) {
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("type", anomaly.type().getValue());
      entry.put("severity", anomaly.severity().name().toLowerCase());
      entry.put("reason", anomaly.reason());
      entry.put("tone", anomaly.severity().getValue());
      result.add(entry);
    }
    return result;
  }

  /** 构建 export 用 round 列表（包含全部 rounds，不截断）。 */
  private static List<Map<String, Object>> buildExportRoundList(List<CallRound> rounds) {
    List<Map<String, Object>> result = new ArrayList<>(rounds.size());
    for (CallRound round : rounds) {
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put("round_index", round.roundIndex());
      entry.put("call_count", round.callCount());
      entry.put("tool_call_count", round.toolCallCount());
      entry.put("is_subagent", !round.parentCallId().isEmpty());
      entry.put("parent_call_id", round.parentCallId());
      entry.put("calls", round.calls());
      entry.put("tool_call_ids", round.toolCallIds());
      entry.put("is_empty", round.isEmpty());
      result.add(entry);
    }
    return result;
  }

  /** 构建 payload 来源摘要列表。 */
  private static List<Map<String, String>> buildPayloadSourceSummary(List<PayloadSource> sources) {
    List<Map<String, String>> result = new ArrayList<>(sources.size());
    for (PayloadSource source : sources) {
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("payload_id", source.payloadId());
      entry.put("kind", source.kind().name().toLowerCase());
      entry.put("call_id", source.callId());
      entry.put("title", source.title());
      entry.put("truncated", source.truncated() ? "true" : "false");
      entry.put("status", source.truncated() ? "truncated" : "available");
      result.add(entry);
    }
    return result;
  }

  /** 构建 session 指标 map。 */
  private static Map<String, Object> buildSessionMetrics(SessionRow row) {
    Map<String, Object> metrics = new LinkedHashMap<>();
    metrics.put("total_tokens", row.totalTokens());
    metrics.put("output_tokens", row.outputTokens());
    metrics.put("fresh_input_tokens", row.freshInputTokens());
    metrics.put("cache_read_tokens", row.cacheReadTokens());
    metrics.put("cache_write_tokens", row.cacheWriteTokens());
    metrics.put("duration_seconds", row.durationSeconds());
    metrics.put("model_execution_seconds", row.modelExecutionSeconds());
    metrics.put("tool_execution_seconds", row.toolExecutionSeconds());
    metrics.put("tool_call_count", row.toolCallCount());
    metrics.put("failed_tool_count", row.failedToolCount());
    metrics.put("user_message_count", row.userMessageCount());
    metrics.put("assistant_message_count", row.assistantMessageCount());
    metrics.put("subagent_instance_count", row.subagentInstanceCount());
    return metrics;
  }

  /** 导出内容超过大小限制时抛出的异常。 */
  static final class ExportSizeExceededException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    ExportSizeExceededException(long actual, long limit) {
      super("导出内容 " + actual + " 字节超过限制 " + limit + " 字节");
    }
  }
}
