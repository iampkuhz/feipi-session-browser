package com.feipi.session.browser.web.export;

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
                  + java.time.Instant.now()
                  + " --><html><head><meta charset=\"utf-8\"><title>Session"
                  + " export</title><style>body{font:16px system-ui;max-width:80em;margin:2em"
                  + " auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{border:1px"
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
                    "<details><summary>"
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
                  writer.write(request ? "<h3>Request</h3><pre>" : "<h3>Response</h3><pre>");
                  text(writer, payload.content());
                  writer.write("</pre>");
                }
                writer.write("</details>");
              }
              for (var tool : unit.toolExecutions()) {
                writer.write("<details><summary>Tool ");
                text(writer, tool.toolCallId());
                writer.write(" · ");
                text(writer, tool.name());
                writer.write("</summary>");
                field(writer, "scope", tool.scope().getValue());
                field(writer, "declaredByCallId", tool.declaredByCallId());
                field(writer, "resultConsumedByCallId", tool.resultConsumedByCallId().orElse(""));
                field(writer, "subagentId", tool.subagentId().orElse(""));
                for (String kind : new String[] {"input", "result"}) {
                  var payload =
                      payloads.payload("tool:" + kind + ":" + tool.toolCallId(), visibility);
                  if (payload.isEmpty()) throw new IOException("Export tool payload unavailable");
                  field(writer, "payloadId", payload.get().payloadId());
                  writer.write("<pre>");
                  text(writer, payload.get().content());
                  writer.write("</pre>");
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
