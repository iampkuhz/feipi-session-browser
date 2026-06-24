package com.feipi.session.browser.web.export;

import com.feipi.session.browser.web.template.PebbleEnvironment;
import io.javalin.http.Context;
import io.javalin.http.Header;
import io.javalin.http.HttpStatus;
import java.nio.charset.StandardCharsets;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
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

  /**
   * 创建导出处理器。
   *
   * @param templates Pebble 模板环境
   */
  public ExportHandler(PebbleEnvironment templates) {
    this.templates = Objects.requireNonNull(templates, "templates 不得为 null");
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

  /** 生成独立 HTML 导出。 */
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
  private static String sanitizeFileName(String raw) {
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

  /** 导出内容超过大小限制时抛出的异常。 */
  static final class ExportSizeExceededException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    ExportSizeExceededException(long actual, long limit) {
      super("导出内容 " + actual + " 字节超过限制 " + limit + " 字节");
    }
  }
}
