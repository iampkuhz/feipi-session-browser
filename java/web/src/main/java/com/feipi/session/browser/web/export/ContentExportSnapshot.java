package com.feipi.session.browser.web.export;

import com.feipi.session.browser.application.sessiondetail.PayloadLookup;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

/** 收集完整离线快照并限制编码后的大小；仅在全部收集成功后发布。 */
public final class ContentExportSnapshot implements AutoCloseable {
  private final Path path;

  private ContentExportSnapshot(Path path) {
    this.path = path;
  }

  /** 将快照写入私有临时文件；任何收集失败都会删除临时文件。 */
  public static ContentExportSnapshot create(long maxBytes, ContentWriter writer)
      throws IOException {
    return create(maxBytes, null, writer);
  }

  private static ContentExportSnapshot create(long maxBytes, Path directory, ContentWriter writer)
      throws IOException {
    var permissions =
        PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------"));
    Path file =
        directory == null
            ? Files.createTempFile("feipi-export-", ".tmp", permissions)
            : Files.createTempFile(directory, "feipi-export-", ".tmp", permissions);
    boolean complete = false;
    try {
      try (var output = new LimitedOutput(Files.newOutputStream(file), maxBytes)) {
        writer.write(output);
      }
      complete = true;
      return new ContentExportSnapshot(file);
    } catch (IOException e) {
      for (Throwable cause = e; cause != null; cause = cause.getCause()) {
        if (cause instanceof LimitExceededException) throw new LimitExceededException(e);
      }
      throw e;
    } finally {
      if (!complete) Files.deleteIfExists(file);
    }
  }

  /** 从不可变的已发布内容收集全部调用与工具，不受页面当前窗口限制。 */
  public static ContentExportSnapshot html(
      NormalizedSessionContent content,
      long observedUsers,
      PayloadVisibility visibility,
      long maxBytes)
      throws IOException {
    return html(content, observedUsers, visibility, maxBytes, content.header().agent().toString());
  }

  /** 补充可公开的会话身份，不导出本机元数据或原始来源路径。 */
  public static ContentExportSnapshot html(
      NormalizedSessionContent content,
      long observedUsers,
      PayloadVisibility visibility,
      long maxBytes,
      String sessionKey)
      throws IOException {
    var reader = new SessionContentReader(content, observedUsers);
    var payloads = reader.exportPayloads();
    var agent = content.header().agent();
    return createClosing(
        null,
        maxBytes,
        output -> {
          var writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);
          writer.write(
              "<!DOCTYPE html><!-- Feipi offline export v1; generated "
                  + new java.time.format.DateTimeFormatterBuilder()
                      .appendInstant(9)
                      .toFormatter()
                      .format(java.time.Instant.now())
                  + " --><html><head><meta charset=\"utf-8\"><title>Session"
                  + " export</title><style>body{font:16px system-ui;max-width:80em;margin:2em"
                  + " auto;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{border:1px"
                  + " solid #888;padding:.5em;margin:.5em}</style></head><body><h1>Session"
                  + " export</h1><p>");
          text(writer, sessionKey);
          writer.write("</p><p>Trace rows: ");
          writer.write(Integer.toString(reader.roundIndex().roundCount()));
          writer.write(
              " · Call records: "
                  + content.header().totals().get("calls")
                  + "</p><p>R = confirmed model call; G = logical record group without a confirmed"
                  + " model-call boundary. Record and row totals are not model API call counts.</p>");
          writer.write(
              "<p>需要从工具定位到声明记录的模型输入/输出时，优先使用 HTML。部分浏览器打开 MHTML" + " 时页内跳转可能不可用，可展开对应声明记录查看。</p>");
          writer.write("<p>本档案仅提供原生折叠和已收录片段，不包含在线 modal 往返或在线协作交互。</p>");
          writer.write("<p>模型耗时未测量。工具时长仅使用来源观测；— 为未知，不是零。工具工作量不能当作墙钟、重叠或关键路径。</p>");
          long tokens = 0;
          var provenance = TokenProvenance.empty();
          try (var cursor = content.openCursor()) {
            while (cursor.hasNext()) {
              var unit = cursor.next();
              for (var call : unit.calls()) {
                tokens = Math.addExact(tokens, call.usage().total());
                var precision = callPrecision(call);
                provenance = provenance.plus(precision);
                String rowType =
                    ContentRoundIndex.modelCallEvidence(agent, call).isEmpty() ? "G" : "R";
                writer.write(
                    "<details id=\"call-"
                        + anchor(call.callId())
                        + "\"><summary>"
                        + rowType
                        + reader.roundIndex().roundIndexForCall(call.callId()).orElseThrow()
                        + " · ");
                text(writer, call.callId());
                writer.write(" · tokens ");
                text(writer, usageLabel(call.usage().total(), precision));
                writer.write("</summary>");
                field(writer, "scope", call.scope().getValue());
                field(writer, "parentCallId", call.parentCallId().orElse(""));
                field(writer, "parentToolCallId", call.parentToolCallId().orElse(""));
                field(writer, "subagentId", call.subagentId().orElse(""));
                field(writer, "parentToolName", call.parentToolName().orElse(""));
                field(
                    writer,
                    "freshInputTokens",
                    componentLabel(call.usage().fresh(), precision.freshInput()));
                field(
                    writer,
                    "cacheReadTokens",
                    componentLabel(call.usage().cacheRead(), precision.cacheRead()));
                field(
                    writer,
                    "cacheWriteTokens",
                    componentLabel(call.usage().cacheWrite(), precision.cacheWrite()));
                field(
                    writer,
                    "outputTokens",
                    componentLabel(call.usage().output(), precision.output()));
                field(writer, "freshInputTokenPrecision", precision.freshInput());
                field(writer, "cacheReadTokenPrecision", precision.cacheRead());
                field(writer, "cacheWriteTokenPrecision", precision.cacheWrite());
                field(writer, "outputTokenPrecision", precision.output());
                field(writer, "tokenEstimationMethod", precision.estimationMethod());
                for (boolean request : new boolean[] {true, false}) {
                  var payload = payloads.payload(call, request, visibility);
                  field(writer, "payloadId", payload.payloadId());
                  writer.write(
                      "<h3 id=\""
                          + (request ? "input-" : "output-")
                          + anchor(call.callId())
                          + "\">");
                  writer.write(request ? "模型输入 · Request（本地来源/重建）</h3>" : "模型输出 · Response</h3>");
                  if (request) {
                    writer.write("<h4>输入正文</h4>");
                    if (payload.reading().isEmpty())
                      writer.write("<p>未单列输入正文；本地工具结果和原始请求仍可审查。</p>");
                    for (var block : payload.reading()) pre(writer, block.text());
                    if (payload.unconfirmedContext()) writer.write("<p>原始请求含归属未确认的上下文。</p>");
                    inputResults(writer, payloads, payload.payloadId(), visibility);
                    writer.write("<details><summary>原始请求全文</summary>");
                    pre(writer, payload.content());
                    writer.write("</details>");
                  } else pre(writer, payload.content());
                }
                writer.write("</details>");
              }
              for (var tool : unit.toolExecutions()) {
                writer.write(
                    "<details id=\"tool-" + anchor(tool.toolCallId()) + "\"><summary>Tool ");
                text(writer, tool.toolCallId());
                writer.write(" · ");
                text(writer, tool.name());
                writer.write(" · ");
                String duration = tool.durationMs() == null ? "— · 未测量" : tool.durationMs() + "ms";
                if (Long.valueOf(0).equals(tool.durationMs())
                    && tool.observation().isPresent()
                    && tool.observation().get().durationNanos() != null
                    && tool.observation().get().durationNanos() > 0) duration = "<1ms";
                text(writer, duration);
                writer.write(" · ");
                text(writer, tool.exitCode().map(code -> "退出码 " + code).orElse("退出未知"));
                writer.write("</summary>");
                if (reader.roundIndex().roundIndexForCall(tool.declaredByCallId()).isPresent()) {
                  writer.write(
                      "<p>来源：<a href=\"#input-"
                          + anchor(tool.declaredByCallId())
                          + "\">模型输入</a> · <a href=\"#output-"
                          + anchor(tool.declaredByCallId())
                          + "\">模型输出</a></p>");
                } else {
                  writer.write("<p>来源未确认：无法关联到模型输入或模型输出。</p>");
                }
                field(writer, "scope", tool.scope().getValue());
                field(writer, "declaredByCallId", tool.declaredByCallId());
                field(writer, "resultConsumedByCallId", tool.resultConsumedByCallId().orElse(""));
                field(writer, "subagentId", tool.subagentId().orElse(""));
                if (tool.observation().isPresent()) {
                  var observation = tool.observation().get();
                  field(writer, "observationSource", observation.source());
                  field(writer, "observationKind", observation.kind());
                  field(writer, "observationStatus", observation.status());
                  field(writer, "observationIssue", observation.issue());
                }
                for (String kind : new String[] {"input", "result"}) {
                  var payload =
                      payloads.payload("tool:" + kind + ":" + tool.toolCallId(), visibility);
                  if (payload.isEmpty()) throw new IOException("Export tool payload unavailable");
                  field(writer, "payloadId", payload.get().payloadId());
                  if ("result".equals(kind)) {
                    toolResults(
                        writer,
                        payloads,
                        payload.get().payloadId(),
                        visibility,
                        reader.roundIndex());
                    writer.write("<details><summary>工具结果全文</summary>");
                    pre(writer, payload.get().content());
                    writer.write("</details>");
                  } else {
                    writer.write("<h3>命令或参数</h3>");
                    pre(writer, payload.get().content());
                  }
                }
                writer.write("</details>");
              }
            }
          }
          writer.write("<p>Total tokens: ");
          text(writer, usageLabel(tokens, provenance));
          writer.write("</p></body></html>");
          writer.flush();
        },
        payloads::close);
  }

  private static void inputResults(
      Writer writer,
      SessionContentReader.ExportPayloads payloads,
      String payloadId,
      PayloadVisibility visibility)
      throws IOException {
    writer.write("<h4>本地记录中的工具结果</h4>");
    long cursor = 0;
    do {
      var page = payloads.localResults(payloadId, cursor, 20, null, visibility);
      if (cursor == 0) coverage(writer, page.coverage(), page.reason());
      if (cursor == 0 && page.references().isEmpty())
        writer.write(
            "complete".equals(page.coverage())
                ? "<p>当前未记录工具结果引用。</p>"
                : "<p>尚未能单列工具结果引用；不能据此确认没有引用。</p>");
      for (var reference : page.references()) {
        writer.write(
            "<details id=\"reference-" + anchor(reference.referenceId()) + "\"><summary>本地工具结果 · ");
        text(writer, reference.toolName());
        writer.write("</summary>");
        identity(writer, reference.identity());
        resultText(writer, reference.content());
        writer.write("</details>");
      }
      if (page.nextCursor() == null) break;
      cursor = page.nextCursor();
    } while (true);
  }

  private static void toolResults(
      Writer writer,
      SessionContentReader.ExportPayloads payloads,
      String payloadId,
      PayloadVisibility visibility,
      ContentRoundIndex index)
      throws IOException {
    writer.write("<h3>执行结果</h3>");
    long cursor = 0;
    do {
      var page = payloads.localResults(payloadId, cursor, 20, null, visibility);
      if (cursor == 0) coverage(writer, page.coverage(), page.reason());
      if (cursor == 0 && page.occurrences().isEmpty())
        writer.write(
            "complete".equals(page.coverage())
                ? "<p>当前未记录结果分项，工具结果全文仍可审查。</p>"
                : "<p>尚未能单列结果分项，工具结果全文仍可审查。</p>");
      for (var occurrence : page.occurrences()) {
        writer.write("<details><summary>Result · ");
        text(writer, occurrence.toolName());
        writer.write(" · " + (occurrence.order() + 1) + "</summary>");
        identity(writer, occurrence.identity());
        resultText(writer, occurrence.content());
        writer.write("<h4>包含此结果的本地输入</h4><p>仅证明本地记录包含，不代表 provider 采用或任务成功。</p>");
        long relationCursor = 0;
        do {
          var relations =
              payloads.localResultRelations(occurrence.occurrenceId(), relationCursor, 20, null);
          if (relationCursor == 0) coverage(writer, relations.coverage(), relations.reason());
          if (relationCursor == 0 && relations.targets().isEmpty()) {
            writer.write(
                "complete".equals(relations.coverage()) && "confirmed".equals(relations.identity())
                    ? "<p>本地未记录包含此结果的输入。</p>"
                    : "<p>尚不能确认包含此结果的输入；不是已确认零目标。</p>");
          }
          for (var target : relations.targets()) {
            boolean captured =
                "confirmed".equals(relations.identity())
                    && index.roundIndexForCall(target.callId()).isPresent();
            writer.write("<p>");
            if (captured)
              writer.write("<a href=\"#reference-" + anchor(target.referenceId()) + "\">");
            text(
                writer,
                "本地记录#"
                    + (target.recordIndex() == null ? "未知" : target.recordIndex())
                    + " · "
                    + ("subagent".equals(target.scope()) ? "子上下文" : "主上下文"));
            writer.write(captured ? "</a>" : " · 未收录或身份未确认，不能离线到达");
            writer.write("</p>");
          }
          if (relations.nextCursor() == null) break;
          relationCursor = relations.nextCursor();
        } while (true);
        writer.write("</details>");
      }
      if (page.nextCursor() == null) break;
      cursor = page.nextCursor();
    } while (true);
  }

  private static void coverage(Writer writer, String coverage, String reason) throws IOException {
    if ("partial".equals(coverage)) writer.write("<p>当前已确认的输入不代表完整集合，仍有记录无法核对。</p>");
    else if (!"complete".equals(coverage)) writer.write("<p>尚不能确认记录是否完整，不能据此判断全部包含关系。</p>");
    if (!reason.isEmpty()) {
      writer.write("<details><summary>关系范围说明</summary><p>以下为审查用的内部原因标记，不代表任务执行结果。</p><pre>");
      text(writer, reason);
      writer.write("</pre></details>");
    }
  }

  private static void identity(Writer writer, String identity) throws IOException {
    if ("ambiguous".equals(identity)) writer.write("<p>来源记录存在冲突，无法唯一确认结果身份。</p>");
    else if (!"confirmed".equals(identity)) writer.write("<p>结果的来源身份尚未确认，不能据此建立准确的包含关系。</p>");
  }

  private static void resultText(Writer writer, PayloadLookup.ResultContent content)
      throws IOException {
    if ("missing".equals(content.state())) writer.write("<p>结果正文缺失。</p>");
    else if (content.text().isEmpty()) writer.write("<p>显式空结果。</p>");
    else pre(writer, content.text());
    if (content.truncated()) writer.write("<p>此结果正文已裁剪；工具结果全文仍可审查。</p>");
  }

  private static void pre(Writer writer, String value) throws IOException {
    writer.write("<pre>");
    text(writer, value);
    writer.write("</pre>");
  }

  private static String anchor(String id) {
    try {
      return java.util.HexFormat.of()
          .formatHex(
              java.security.MessageDigest.getInstance("SHA-256")
                  .digest(id.getBytes(StandardCharsets.UTF_8)));
    } catch (java.security.NoSuchAlgorithmException exception) {
      throw new IllegalStateException("SHA-256 unavailable", exception);
    }
  }

  /** 关闭收集器成功后才移交快照；关闭失败时仍由本方法清理已构造的文件。 */
  static ContentExportSnapshot createClosing(
      Path directory, long maxBytes, ContentWriter writer, CloseAction close) throws IOException {
    ContentExportSnapshot snapshot = null;
    try (close) {
      snapshot = create(maxBytes, directory, writer);
    } catch (IOException | RuntimeException | Error failure) {
      if (snapshot != null) {
        try {
          snapshot.close();
        } catch (IOException cleanup) {
          failure.addSuppressed(cleanup);
        }
      }
      throw failure;
    }
    return snapshot;
  }

  /** 仅用于收集器生命周期的可抛出关闭操作，不提供运行时配置。 */
  @FunctionalInterface
  interface CloseAction extends AutoCloseable {
    @Override
    void close() throws IOException;
  }

  /** 即使选择完整可见性，仍执行导出的最低安全脱敏要求。 */
  public static String safeText(String value) {
    if (value == null) return "";
    return SensitiveFieldPolicy.DEFAULT
        .applyMasking(value)
        .replaceAll(
            "(?i)(?:[A-Z]:\\\\Users\\\\[^\\s\"<>]+|/(?:Users|home)/[^\\s\"<>]+)", "[LOCAL_PATH]")
        .replaceAll("(?i)(Bearer\\s+)[A-Za-z0-9._~+/-]+=*", "$1[REDACTED]")
        .replaceAll(
            "(?i)(\"(?:cookie|x-api-key)\"\\s*:\\s*\")(?:\\\\.|[^\"\\\\])*(\")", "$1[REDACTED]$2")
        .replaceAll("(?i)((?:cookie|x-api-key)\\s*[:=]\\s*)[^\\r\\n]+", "$1[REDACTED]");
  }

  private static TokenProvenance callPrecision(NormalizedCall call) {
    var metadata = new java.util.LinkedHashMap<String, Object>(call.attributionCandidates());
    metadata.putAll(call.usageSource());
    return TokenProvenance.fromMetadata(metadata);
  }

  private static String usageLabel(long tokens, TokenProvenance precision) {
    boolean missing =
        precision.unknownSessionCount() > 0 || precision.unavailableSessionCount() > 0;
    boolean estimated = precision.estimatedSessionCount() > 0;
    String states =
        String.join(
            ",",
            precision.freshInput(),
            precision.cacheRead(),
            precision.cacheWrite(),
            precision.output());
    if (missing || states.contains("mixed"))
      return "N/A · Partial (stored sum "
          + tokens
          + ")"
          + (estimated ? " · Estimated" : "")
          + " · "
          + states;
    return tokens + (estimated ? " · Estimated" : " · provider_reported");
  }

  private static String componentLabel(long tokens, String precision) {
    return switch (precision) {
      case "provider_reported" -> Long.toString(tokens);
      case "estimated" -> tokens + " · Estimated";
      case "mixed" -> tokens + " · Partial";
      default -> "N/A";
    };
  }

  private static void field(Writer writer, String name, String value) throws IOException {
    writer.write("<p>");
    text(writer, name);
    writer.write(": ");
    text(writer, value);
    writer.write("</p>");
  }

  private static void text(Writer writer, String value) throws IOException {
    String safe = safeText(value);
    for (int i = 0; i < safe.length(); i++) {
      switch (safe.charAt(i)) {
        case '&' -> writer.write("&amp;");
        case '<' -> writer.write("&lt;");
        case '>' -> writer.write("&gt;");
        case '"' -> writer.write("&quot;");
        default -> writer.write(safe.charAt(i));
      }
    }
  }

  /** 返回完整快照编码后的实际字节数。 */
  public long size() throws IOException {
    return Files.size(path);
  }

  /** 仅将已经完整收集成功的快照文件复制到响应输出流。 */
  public void copyTo(OutputStream output) throws IOException {
    Files.copy(path, output);
  }

  /** 无论导出成功还是失败，关闭时都删除私有快照文件。 */
  @Override
  public void close() throws IOException {
    Files.deleteIfExists(path);
  }

  /** 向受大小限制的文件写入内容；调用方不得持有传入的输出流。 */
  @FunctionalInterface
  public interface ContentWriter {
    /** 将完整导出内容写入受大小限制的输出流，超出限制时明确失败。 */
    void write(OutputStream output) throws IOException;
  }

  /** 收集阶段在响应发布前超过配置的字节限制，禁止发布不完整快照。 */
  public static final class LimitExceededException extends IOException {
    private static final long serialVersionUID = 1L;

    private LimitExceededException() {
      this(null);
    }

    private LimitExceededException(Throwable cause) {
      super("Export exceeds byte limit", cause);
    }
  }

  /** 写入前计算编码后的字节数，避免生成或发布超过大小限制的快照。 */
  private static final class LimitedOutput extends FilterOutputStream {
    private final long max;
    private long count;

    LimitedOutput(OutputStream output, long max) {
      super(output);
      this.max = max;
    }

    @Override
    public void write(int value) throws IOException {
      if (count >= max) throw new LimitExceededException();
      out.write(value);
      count++;
    }

    @Override
    public void write(byte[] values, int offset, int length) throws IOException {
      if (length > max - count) throw new LimitExceededException();
      out.write(values, offset, length);
      count += length;
    }
  }
}
