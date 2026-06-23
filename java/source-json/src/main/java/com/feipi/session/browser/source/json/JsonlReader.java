package com.feipi.session.browser.source.json;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;

/**
 * 容错 JSONL 读取器。
 *
 * <p>支持美化打印、{@code }{}{ } 拼接、坏行跳过和 BOM 处理。逐行读取文件， 通过深度追踪将多行 JSON 累积为完整对象后解析。解析结果通过 {@link
 * JsonlReaderResult} 返回。
 *
 * <p>该类是不可变的，线程安全（{@link ObjectMapper} 实例由 Jackson 保证线程安全）。
 */
public final class JsonlReader {

  private final JsonlReaderConfig config;
  private final ObjectMapper mapper;

  /** 使用默认配置创建读取器。 */
  public JsonlReader() {
    this(JsonlReaderConfig.DEFAULT);
  }

  /**
   * 使用自定义配置创建读取器。
   *
   * @param config 读取器配置，不得为 null
   */
  public JsonlReader(JsonlReaderConfig config) {
    Objects.requireNonNull(config, "config 不得为 null");
    this.config = config;
    this.mapper = new ObjectMapper();
    // 检测拼接对象（如 }{），防止 Jackson 静默忽略尾部内容
    this.mapper.enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
  }

  /**
   * 读取并解析指定路径的 JSONL 文件。
   *
   * <p>逐行读取文件，跳过空行和 BOM，追踪 JSON 深度以支持美化打印和拼接对象。 解析结果包含成功的事件列表、诊断信息和统计数据。
   *
   * @param path JSONL 文件路径
   * @return 解析结果
   * @throws IOException 当文件读取失败时
   */
  public JsonlReaderResult read(Path path) throws IOException {
    Objects.requireNonNull(path, "path 不得为 null");

    List<JsonNode> events = new ArrayList<>();
    List<SourceDiagnostic> diagnostics = new ArrayList<>();
    List<String> currentLines = new ArrayList<>();
    int depth = 0;
    int totalLines = 0;
    int nonEmptyLines = 0;
    int bufferChars = 0;

    try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
      String line;
      boolean firstLine = true;

      while ((line = reader.readLine()) != null) {
        totalLines++;

        // 跳过 UTF-8 BOM（仅第一个字符）
        if (firstLine && !line.isEmpty() && line.charAt(0) == JsonlConstants.BOM) {
          line = line.substring(1);
        }
        firstLine = false;

        String stripped = stripTrailingChars(line);
        if (stripped.isEmpty()) {
          continue;
        }
        nonEmptyLines++;

        // 追踪 JSON 深度
        String braceChars = braceCharsOutsideStrings(stripped);
        for (int i = 0; i < braceChars.length(); i++) {
          char ch = braceChars.charAt(i);
          if (ch == '{' || ch == '[') {
            depth++;
          } else if (ch == '}' || ch == ']') {
            depth--;
          }
        }

        // 累积缓冲区
        if (bufferChars > 0) {
          bufferChars++; // 行分隔符
        }
        bufferChars += stripped.length();
        currentLines.add(stripped);

        // 缓冲区超限：强制刷新并报告错误
        if (bufferChars > config.maxBufferChars()) {
          String full = String.join("\n", currentLines).strip();
          diagnostics.add(buildBadJsonDiagnostic(totalLines, full));
          currentLines.clear();
          bufferChars = 0;
          depth = 0;
          continue;
        }

        if (depth == 0) {
          String full = String.join("\n", currentLines).strip();
          currentLines.clear();
          bufferChars = 0;

          if (events.size() < config.maxRecords()) {
            tryParseJson(full, totalLines, events, diagnostics);
          }
        }
      }
    }

    // EOF 时仍有未终止的 JSON（括号深度大于零，对象未闭合）
    if (!currentLines.isEmpty()) {
      String full = String.join("\n", currentLines).strip();
      diagnostics.add(buildBadJsonDiagnostic(totalLines, full));
    }

    int eventsSkipped = countSkippedEvents(diagnostics);
    JsonlStats stats = new JsonlStats(totalLines, nonEmptyLines, events.size(), eventsSkipped);
    return new JsonlReaderResult(events, diagnostics, stats);
  }

  /**
   * 提取字符串外的花括号字符序列。
   *
   * <p>状态机遍历输入文本，跳过字符串内的字符（处理转义）， 仅收集不在双引号字符串内的 {@code {}{ }} 字符。
   *
   * @param text 输入文本
   * @return 仅包含字符串外花括号的字符序列
   */
  static String braceCharsOutsideStrings(String text) {
    StringBuilder result = new StringBuilder();
    boolean inString = false;
    boolean escaped = false;

    for (int i = 0; i < text.length(); i++) {
      char ch = text.charAt(i);
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch == '\\') {
        escaped = true;
        continue;
      }
      if (ch == '"') {
        inString = !inString;
        continue;
      }
      if (!inString && (ch == '{' || ch == '}' || ch == '[' || ch == ']')) {
        result.append(ch);
      }
    }
    return result.toString();
  }

  /**
   * 在顶层 {@code }{}{ } 边界拆分文本。
   *
   * <p>追踪花括号深度，当深度回到 0 且下一个字符是 {@code &#123;} 时切割。 如果从未发生切割（文本为单个对象），返回包含原文本的列表。
   *
   * @param text 输入文本
   * @return 拆分后的文本段列表
   */
  static List<String> splitAtDepth0(String text) {
    List<String> parts = new ArrayList<>();
    int currentStart = 0;
    int depth = 0;
    boolean inString = false;
    boolean escaped = false;

    for (int i = 0; i < text.length(); i++) {
      char ch = text.charAt(i);
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch == '\\') {
        escaped = true;
        continue;
      }
      if (ch == '"') {
        inString = !inString;
        continue;
      }
      if (inString) {
        continue;
      }
      if (ch == '{') {
        depth++;
      } else if (ch == '}') {
        depth--;
        if (depth == 0 && i + 1 < text.length() && text.charAt(i + 1) == '{') {
          String candidate = text.substring(currentStart, i + 1).strip();
          if (!candidate.isEmpty()) {
            parts.add(candidate);
          }
          currentStart = i + 1;
        }
      }
    }

    if (currentStart == 0) {
      return List.of(text);
    }

    String tail = text.substring(currentStart).strip();
    if (!tail.isEmpty()) {
      parts.add(tail);
    }
    return parts.isEmpty() ? List.of(text) : parts;
  }

  /**
   * 尝试解析 JSON 文本，失败时尝试拆分拼接对象。
   *
   * @param text 待解析文本
   * @param lineNo 问题所在的源文件行号（从 1 开始计数）
   * @param events 成功解析的事件列表
   * @param diagnostics 诊断信息列表
   */
  private void tryParseJson(
      String text, int lineNo, List<JsonNode> events, List<SourceDiagnostic> diagnostics) {
    try {
      JsonNode node = mapper.readTree(text);
      if (node.isObject()) {
        events.add(node);
      } else {
        String typeName = typeNameFor(node);
        diagnostics.add(buildNonObjectDiagnostic(lineNo, typeName, text));
      }
      return;
    } catch (JsonProcessingException e) {
      // 首次解析失败，尝试拆分
    }

    List<String> parts = splitAtDepth0(text);
    if (parts.size() > 1) {
      for (String part : parts) {
        try {
          JsonNode node = mapper.readTree(part);
          if (node.isObject()) {
            events.add(node);
          } else {
            String typeName = typeNameFor(node);
            diagnostics.add(buildNonObjectDiagnostic(lineNo, typeName, part));
          }
        } catch (JsonProcessingException e2) {
          diagnostics.add(buildBadJsonDiagnostic(lineNo, part));
        }
      }
    } else {
      diagnostics.add(buildBadJsonDiagnostic(lineNo, text));
    }
  }

  /** 构建 BAD_JSON 诊断信息。 */
  private SourceDiagnostic buildBadJsonDiagnostic(int lineNo, String text) {
    String preview = config.truncatePreview(text);
    return new SourceDiagnostic(
        ParseSeverity.ERROR,
        ParseIssueType.BAD_JSON,
        "Unparseable JSON at line " + lineNo,
        lineNo,
        Optional.of(preview),
        ParseIssueType.BAD_JSON.name(),
        "",
        OptionalInt.empty(),
        OptionalInt.empty(),
        OptionalInt.empty());
  }

  /** 构建 NON_OBJECT_SKIPPED 诊断信息。 */
  private SourceDiagnostic buildNonObjectDiagnostic(int lineNo, String typeName, String text) {
    String preview = config.truncatePreview(text);
    return new SourceDiagnostic(
        ParseSeverity.WARNING,
        ParseIssueType.NON_OBJECT_SKIPPED,
        "Non-dict JSON value skipped: " + typeName,
        lineNo,
        Optional.of(preview),
        ParseIssueType.NON_OBJECT_SKIPPED.name(),
        "",
        OptionalInt.empty(),
        OptionalInt.empty(),
        OptionalInt.empty());
  }

  /** 获取 JsonNode 的类型名称（用于诊断消息）。 */
  private static String typeNameFor(JsonNode node) {
    return node.getNodeType().name().toLowerCase();
  }

  /** 统计诊断中的跳过事件数量（BAD_JSON + NON_OBJECT_SKIPPED）。 */
  private static int countSkippedEvents(List<SourceDiagnostic> diagnostics) {
    int count = 0;
    for (SourceDiagnostic d : diagnostics) {
      if (d.issueType() == ParseIssueType.BAD_JSON
          || d.issueType() == ParseIssueType.NON_OBJECT_SKIPPED) {
        count++;
      }
    }
    return count;
  }

  /** 去除尾部空白字符（与 Python {@code rstrip()} 行为一致）。 */
  private static String stripTrailingChars(String text) {
    int end = text.length();
    while (end > 0 && Character.isWhitespace(text.charAt(end - 1))) {
      end--;
    }
    return text.substring(0, end);
  }
}
