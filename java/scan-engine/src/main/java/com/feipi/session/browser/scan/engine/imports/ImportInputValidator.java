package com.feipi.session.browser.scan.engine.imports;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.source.spi.SourceAdapter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PushbackReader;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.Set;

/** 在宽容的来源解析器前执行严格、有界的单文件契约检查。 */
final class ImportInputValidator {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final int LINE_BUFFER_CHARS = 8192;

  private ImportInputValidator() {}

  /**
   * 已通过单文件校验的导入输入。
   *
   * @param sessionId 原始会话标识；未提供时为空字符串
   * @param analysisFile 用于分析的私有文件路径，不包含需忽略的元数据
   */
  record ValidatedInput(String sessionId, Path analysisFile) {}

  static ValidatedInput validate(Path file, SourceAdapter adapter, ImportLimits limits)
      throws IOException {
    Set<String> sessionIds = new HashSet<>();
    Set<Integer> ignoredLines = new HashSet<>();
    int count = 0;
    int lineNo = 0;
    boolean transcript = false;
    try (var reader = openReader(file)) {
      char[] lineBuffer = new char[LINE_BUFFER_CHARS];
      String line;
      while ((line = readLine(reader, limits.maxRecordChars(), lineBuffer)) != null) {
        lineNo++;
        if (count == 0 && line.startsWith("\uFEFF")) {
          line = line.substring(1);
        }
        if (line.isBlank()) {
          continue;
        }
        if (++count > limits.maxRecords()) {
          throw failure("too_many_records");
        }
        JsonNode record = parseObject(line);
        var kind =
            adapter.classifyRecord(
                text(record.path("type")),
                text(record.path("role")),
                text(record.path("message").path("role")));
        switch (kind) {
          case TRANSCRIPT -> transcript = true;
          case IGNORED_METADATA -> ignoredLines.add(lineNo);
          case AUXILIARY -> {
            /* 辅助记录仍受单会话及资源校验。 */
          }
          case FOREIGN -> throw failure("source_mismatch");
          case UNKNOWN -> throw failure("unsupported_format");
        }
        addId(sessionIds, record.path("sessionId"));
        addId(sessionIds, record.path("session_id"));
        if ("session_meta".equals(record.path("type").asText())) {
          addId(sessionIds, record.path("payload").path("id"));
          addId(sessionIds, record.path("payload").path("session_id"));
        }
        if (sessionIds.size() > 1) {
          throw failure("multiple_sessions");
        }
      }
    } catch (CharacterCodingException exception) {
      throw failure("invalid_utf8", exception);
    }
    if (count == 0) {
      throw failure("empty_input");
    }
    if (!transcript) {
      throw failure("unsupported_format");
    }
    return new ValidatedInput(
        sessionIds.stream().findFirst().orElse(""),
        ignoredLines.isEmpty() ? file : filterMetadata(file, limits, ignoredLines));
  }

  private static PushbackReader openReader(Path file) throws IOException {
    var decoder =
        StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    return new PushbackReader(
        new InputStreamReader(Files.newInputStream(file), decoder), LINE_BUFFER_CHARS);
  }

  /** 只在确有兼容元数据时生成分析副本，不让元数据字段进入解析器或原始事件目录。 */
  private static Path filterMetadata(Path file, ImportLimits limits, Set<Integer> ignoredLines)
      throws IOException {
    Path filtered = file.resolveSibling("analysis.jsonl");
    try (var reader = openReader(file);
        var writer = Files.newBufferedWriter(filtered, StandardCharsets.UTF_8)) {
      char[] buffer = new char[LINE_BUFFER_CHARS];
      int lineNo = 0;
      String line;
      while ((line = readLine(reader, limits.maxRecordChars(), buffer)) != null) {
        if (!ignoredLines.contains(++lineNo)) writer.append(line).append('\n');
      }
    }
    return filtered;
  }

  private static String readLine(PushbackReader reader, int maxChars, char[] buffer)
      throws IOException {
    StringBuilder line = new StringBuilder(Math.min(256, maxChars));
    int count;
    while ((count = reader.read(buffer, 0, buffer.length)) != -1) {
      int newline = 0;
      while (newline < count && buffer[newline] != '\n') newline++;
      int append = newline;
      if (line.length() > maxChars - append) throw failure("record_too_large");
      line.append(buffer, 0, append);
      if (newline < count) {
        int remaining = count - newline - 1;
        if (remaining > 0) reader.unread(buffer, newline + 1, remaining);
        return line.toString();
      }
    }
    return line.isEmpty() ? null : line.toString();
  }

  private static JsonNode parseObject(String line) throws IOException {
    try (JsonParser parser = MAPPER.createParser(line)) {
      parser.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);
      JsonNode node = MAPPER.readTree(parser);
      if (node == null || !node.isObject() || parser.nextToken() != null) {
        throw failure("invalid_jsonl");
      }
      return node;
    } catch (SessionImportException exception) {
      throw exception;
    } catch (IOException exception) {
      throw failure("invalid_jsonl", exception);
    }
  }

  private static String text(JsonNode value) {
    return value.isTextual() ? value.textValue() : "";
  }

  private static void addId(Set<String> ids, JsonNode value) throws IOException {
    if (value.isMissingNode() || value.isNull()) {
      return;
    }
    if (!value.isTextual() || value.asText().length() > 256) {
      throw failure("invalid_jsonl");
    }
    if (!value.asText().isBlank()) {
      ids.add(value.asText());
    }
  }

  static SessionImportException failure(String code) {
    return new SessionImportException(code, "独立 JSONL 分析失败（" + code + "）");
  }

  static SessionImportException failure(String code, Exception cause) {
    // 保留失败位置而不保留可能含上传正文或服务器路径的异常消息/因果链。
    SessionImportException failure = failure(code);
    failure.setStackTrace(cause.getStackTrace());
    return failure;
  }
}
