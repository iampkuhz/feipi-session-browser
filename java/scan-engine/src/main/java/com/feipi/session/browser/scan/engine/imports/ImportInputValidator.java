package com.feipi.session.browser.scan.engine.imports;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
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
  private static final Set<String> CODEX_TYPES =
      Set.of("session_meta", "response_item", "event_msg", "turn_context", "token_usage_record");
  private static final Set<String> MESSAGE_TYPES = Set.of("user", "assistant");
  private static final Set<String> AUXILIARY_TYPES =
      Set.of(
          "system",
          "summary",
          "progress",
          "file-history-snapshot",
          "queue-operation",
          "last-prompt",
          "custom-title",
          "tag",
          "agent-name",
          "pr-link",
          "mode",
          "permission-mode",
          "attachment");

  private ImportInputValidator() {}

  static String validate(Path file, NormalizedAgent source, ImportLimits limits)
      throws IOException {
    var decoder =
        StandardCharsets.UTF_8
            .newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT);
    Set<String> sessionIds = new HashSet<>();
    int count = 0;
    boolean transcript = false;
    try (var reader =
        new BufferedReader(new InputStreamReader(Files.newInputStream(file), decoder))) {
      String line;
      while ((line = readLine(reader, limits.maxRecordChars())) != null) {
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
        transcript |= checkSource(record, source);
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
    return sessionIds.stream().findFirst().orElse("");
  }

  private static String readLine(BufferedReader reader, int maxChars) throws IOException {
    StringBuilder line = new StringBuilder();
    int value;
    while ((value = reader.read()) != -1) {
      if (value == '\n') {
        return line.toString();
      }
      if (line.length() == maxChars) {
        throw failure("record_too_large");
      }
      line.append((char) value);
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

  private static boolean checkSource(JsonNode record, NormalizedAgent source) throws IOException {
    String type = record.path("type").asText();
    if (CODEX_TYPES.contains(type)) {
      if (source != NormalizedAgent.CODEX) {
        throw failure("source_mismatch");
      }
      return true;
    }
    if (MESSAGE_TYPES.contains(type)) {
      if (source == NormalizedAgent.CODEX) {
        throw failure("source_mismatch");
      }
      return true;
    }
    if (type.isEmpty() && MESSAGE_TYPES.contains(record.path("role").asText())) {
      if (source != NormalizedAgent.QODER) {
        throw failure("source_mismatch");
      }
      return true;
    }
    if (!AUXILIARY_TYPES.contains(type) || source == NormalizedAgent.CODEX) {
      throw failure("unsupported_format");
    }
    return false;
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
