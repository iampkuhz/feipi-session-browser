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
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.regex.Pattern;

/**
 * 容错 JSONL 读取器。
 *
 * <p>支持美化打印、{@code }{}{ } 拼接、坏行跳过和 BOM 处理。逐行读取文件， 通过深度追踪将多行 JSON 累积为完整对象后解析。解析结果通过 {@link
 * JsonlReaderResult} 返回。
 *
 * <p>核心特性：
 *
 * <ul>
 *   <li>每条记录追踪起始/结束行号和字节范围
 *   <li>括号不匹配（类型错误、深度负数）产生专用诊断代码
 *   <li>达到 {@code maxRecords} 后返回明确的 {@code STOPPED_BY_LIMIT} 状态
 *   <li>读取前后检测文件 size/mtime，变化时返回 {@code RETRYABLE_INCOMPLETE}
 *   <li>超大记录不无界累积行数，缓冲区和行数均有上限
 *   <li>诊断预览文本经过脱敏处理且有大小限制
 * </ul>
 *
 * <p>该类是不可变的，线程安全（{@link ObjectMapper} 实例由 Jackson 保证线程安全）。
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类内部多个方法（braceCharsOutsideStrings、scanBracketContent、
 * splitAtDepth0 等）存在结构性相似（语句级 STATEMENT_DUPLICATE），原因：均为 JSON 文本解析工具方法，
 * 遵循相同的字符遍历和状态追踪模式。此重复是低层解析逻辑的固有特征，提取公共方法会引入不必要的间接层。
 */
public final class JsonlReader {

  private final JsonlReaderConfig config;
  private final ObjectMapper mapper;

  /** 用于预览脱敏的正则：匹配 JSON 字符串值中看起来像密钥/token 的内容。 */
  private static final Pattern SECRET_VALUE_PATTERN =
      Pattern.compile(
          "\"(?:password|passwd|secret|token|api[_-]?key|authorization|credential)\""
              + "\\s*:\\s*\"[^\"]*\"",
          Pattern.CASE_INSENSITIVE);

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
   * <p>逐行读取文件，跳过空行和 BOM，追踪 JSON 深度以支持美化打印和拼接对象。 解析前和解析后分别记录文件 size/mtime，如检测到文件在读取期间被修改， 返回 {@code
   * RETRYABLE_INCOMPLETE} 诊断。解析结果包含成功的事件列表、诊断信息和统计数据。
   *
   * @param path JSONL 文件路径
   * @return 解析结果
   * @throws IOException 当文件读取失败时
   */
  public JsonlReaderResult read(Path path) throws IOException {
    Objects.requireNonNull(path, "path 不得为 null");

    // 读取前快照：检测活跃写入
    long sizeBefore = Files.size(path);
    long mtimeBefore = Files.getLastModifiedTime(path).toMillis();

    // 检测行终止符字节长度（\n = 1, \r\n = 2），用于字节偏移估算
    int terminatorByteLen = detectLineTerminatorByteLen(path);

    List<JsonNode> events = new ArrayList<>();
    List<SourceDiagnostic> diagnostics = new ArrayList<>();
    List<String> currentLines = new ArrayList<>();
    int depth = 0;
    int curlyDepth = 0;
    int squareDepth = 0;
    int totalLines = 0;
    int nonEmptyLines = 0;
    int bufferChars = 0;
    long recordStartByteOffset = 0;
    int recordStartLine = 1;
    boolean stoppedByLimit = false;
    boolean stopped = false;
    boolean recordHasMismatch = false;

    try (BufferedReader reader =
        new BufferedReader(
            new InputStreamReader(Files.newInputStream(path), StandardCharsets.UTF_8))) {
      String line;
      boolean firstLine = true;
      long byteOffset = 0;

      while ((line = reader.readLine()) != null) {
        totalLines++;
        long lineStartByteOffset = byteOffset;

        // 跳过 UTF-8 BOM（仅第一个字符，3 字节 EF BB BF）
        if (firstLine && !line.isEmpty() && line.charAt(0) == JsonlConstants.BOM) {
          line = line.substring(1);
          byteOffset += 3; // UTF-8 BOM 占 3 字节
        }
        firstLine = false;

        String stripped = stripTrailingChars(line);
        if (stripped.isEmpty()) {
          // 空行仍消耗字节（行终止符）
          byteOffset += estimateUtf8ByteLength(line) + terminatorByteLen;
          continue;
        }
        nonEmptyLines++;

        // 达到 maxRecords 后，仅追踪深度以跳过当前记录，不做解析
        if (stopped) {
          for (int i = 0; i < stripped.length(); i++) {
            char ch = stripped.charAt(i);
            if (ch == '{') {
              depth++;
              curlyDepth++;
            } else if (ch == '}') {
              depth--;
              curlyDepth--;
            } else if (ch == '[') {
              depth++;
              squareDepth++;
            } else if (ch == ']') {
              depth--;
              squareDepth--;
            }
          }
          byteOffset += estimateUtf8ByteLength(stripped) + terminatorByteLen;
          // 深度回到 0 且括号平衡时，当前记录结束，解除 stopped
          if (depth <= 0 && curlyDepth <= 0 && squareDepth <= 0) {
            depth = 0;
            curlyDepth = 0;
            squareDepth = 0;
            stopped = false;
          }
          continue;
        }

        // 扫描括号：检测不匹配和深度变化
        BracketScanResult scan = scanBracketContent(stripped, curlyDepth, squareDepth);

        // 更新深度（scan 返回的是处理完本行后的绝对深度）
        curlyDepth = scan.curlyDepth;
        squareDepth = scan.squareDepth;
        depth = curlyDepth + squareDepth;

        // 追踪本记录内是否出现过括号不匹配
        if (scan.mismatch && !recordHasMismatch) {
          recordHasMismatch = true;
        }

        // 新记录开始时记录起始位置
        if (currentLines.isEmpty()) {
          recordStartByteOffset = lineStartByteOffset;
          recordStartLine = totalLines;
        }

        // 累积缓冲区
        if (bufferChars > 0) {
          bufferChars++; // 行分隔符
        }
        bufferChars += stripped.length();
        addLineIfRoom(currentLines, stripped);

        // 缓冲区超限：强制刷新并报告错误
        if (bufferChars > config.maxBufferSize()) {
          String full = String.join("\n", currentLines).strip();
          diagnostics.add(
              buildBadJsonDiagnostic(
                  recordStartLine,
                  full,
                  JsonlConstants.CODE_BUFFER_OVERFLOW,
                  recordStartByteOffset,
                  byteOffset + estimateUtf8ByteLength(stripped) + terminatorByteLen));
          currentLines.clear();
          bufferChars = 0;
          depth = 0;
          curlyDepth = 0;
          squareDepth = 0;
          recordHasMismatch = false;
          byteOffset += estimateUtf8ByteLength(stripped) + terminatorByteLen;
          continue;
        }

        // 深度变为负数：多余的闭合括号，立即刷新并报告
        if (depth < 0) {
          String full = String.join("\n", currentLines).strip();
          long recordEndByteOffset =
              byteOffset + estimateUtf8ByteLength(stripped) + terminatorByteLen;
          String code =
              recordHasMismatch
                  ? JsonlConstants.CODE_BRACKET_MISMATCH
                  : JsonlConstants.CODE_NEGATIVE_DEPTH;
          // 尝试解析缓冲区中可能已完成的有效内容
          if (!full.isEmpty()) {
            tryParseJson(
                full,
                recordStartLine,
                events,
                diagnostics,
                recordStartByteOffset,
                recordEndByteOffset);
          }
          // 报告多余括号
          diagnostics.add(
              buildBadJsonDiagnostic(
                  totalLines, stripped, code, recordEndByteOffset, recordEndByteOffset));
          currentLines.clear();
          bufferChars = 0;
          depth = 0;
          curlyDepth = 0;
          squareDepth = 0;
          recordHasMismatch = false;
          byteOffset += estimateUtf8ByteLength(stripped) + terminatorByteLen;
          continue;
        }

        if (depth <= 0) {
          // 总深度回到零或以下：当前记录结束
          // 注意：curlyDepth/squareDepth 可能各自不为零（如 {"a":] 中 curly=1,square=-1），
          // 但深度之和为零即表示所有括号已闭合或多余
          String full = String.join("\n", currentLines).strip();
          long recordEndByteOffset =
              byteOffset + estimateUtf8ByteLength(stripped) + terminatorByteLen;
          currentLines.clear();
          bufferChars = 0;

          if (events.size() >= config.maxRecords()) {
            // 达到最大记录数：标记停止
            stoppedByLimit = true;
            stopped = true;
            diagnostics.add(
                buildInfoDiagnostic(
                    recordStartLine,
                    JsonlConstants.CODE_STOPPED_BY_LIMIT,
                    "Stopped after reaching maxRecords limit (" + config.maxRecords() + ")",
                    recordStartByteOffset,
                    recordEndByteOffset));
          } else if (recordHasMismatch || depth < 0) {
            // 括号类型不匹配或深度负数，不尝试解析
            String code =
                recordHasMismatch
                    ? JsonlConstants.CODE_BRACKET_MISMATCH
                    : JsonlConstants.CODE_NEGATIVE_DEPTH;
            diagnostics.add(
                buildBadJsonDiagnostic(
                    recordStartLine, full, code, recordStartByteOffset, recordEndByteOffset));
          } else {
            tryParseJson(
                full,
                recordStartLine,
                events,
                diagnostics,
                recordStartByteOffset,
                recordEndByteOffset);
          }
          depth = 0;
          curlyDepth = 0;
          squareDepth = 0;
          recordHasMismatch = false;
        }

        byteOffset += estimateUtf8ByteLength(stripped) + terminatorByteLen;
      }
    }

    // EOF 时仍有未终止的 JSON（括号深度大于零，对象未闭合）
    if (!currentLines.isEmpty()) {
      String full = String.join("\n", currentLines).strip();
      diagnostics.add(
          buildBadJsonDiagnostic(
              recordStartLine,
              full,
              ParseIssueType.BAD_JSON.name(),
              recordStartByteOffset,
              -1 // EOF，结束位置未知
              ));
    }

    // 读取后快照：检测活跃写入
    long sizeAfter = Files.size(path);
    long mtimeAfter = Files.getLastModifiedTime(path).toMillis();
    if (sizeAfter != sizeBefore || mtimeAfter != mtimeBefore) {
      // 文件在读取期间被修改，数据可能不完整
      diagnostics.add(
          buildWarnDiagnostic(
              Math.max(1, totalLines),
              JsonlConstants.CODE_RETRYABLE_INCOMPLETE,
              "File modified during read; results may be incomplete",
              -1));
      return new JsonlReaderResult(
          events,
          diagnostics,
          new JsonlStats(totalLines, nonEmptyLines, events.size(), countSkippedEvents(diagnostics)),
          stoppedByLimit);
    }

    int eventsSkipped = countSkippedEvents(diagnostics);
    JsonlStats stats = new JsonlStats(totalLines, nonEmptyLines, events.size(), eventsSkipped);
    return new JsonlReaderResult(events, diagnostics, stats, stoppedByLimit);
  }

  // ─── 括号扫描 ──────────────────────────────────────────────────────────

  /**
   * 括号扫描结果。
   *
   * @param curlyDepth 处理完本行后的花括号绝对深度
   * @param squareDepth 处理完本行后的方括号绝对深度
   * @param mismatch 是否检测到括号类型不匹配或深度负数
   */
  private record BracketScanResult(int curlyDepth, int squareDepth, boolean mismatch) {}

  /**
   * 扫描文本中的括号，分别追踪花括号和方括号深度。
   *
   * <p>从给定的累积深度开始追踪，检测两类异常：
   *
   * <ul>
   *   <li>括号深度变为负数（多余的闭合括号）
   *   <li>括号类型不匹配（如 {@code {}]} —— 花括号开后用方括号关闭）
   * </ul>
   *
   * @param text 输入文本
   * @param initialCurlyDepth 进入本行之前的花括号累积深度
   * @param initialSquareDepth 进入本行之前的方括号累积深度
   * @return 扫描结果，包含处理后的绝对深度和匹配状态
   */
  static BracketScanResult scanBracketContent(
      String text, int initialCurlyDepth, int initialSquareDepth) {
    int cDepth = initialCurlyDepth;
    int sDepth = initialSquareDepth;
    boolean inString = false;
    boolean escaped = false;
    boolean mismatch = false;

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

      switch (ch) {
        case '{' -> cDepth++;
        case '}' -> {
          cDepth--;
          if (cDepth < 0 && !mismatch) {
            mismatch = true;
          }
        }
        case '[' -> sDepth++;
        case ']' -> {
          sDepth--;
          if (sDepth < 0 && !mismatch) {
            mismatch = true;
          }
        }
        default -> {}
      }
    }
    return new BracketScanResult(cDepth, sDepth, mismatch);
  }

  // ─── 内部辅助方法 ──────────────────────────────────────────────────────

  /**
   * 在有行数上限的条件下向缓冲区添加行。
   *
   * <p>防止超大记录无界累积行数导致内存问题。 超过 {@link JsonlConstants#MAX_LINES_PER_RECORD} 行后不再添加，但仍追踪 bufferChars
   * 以触发超限检测。
   *
   * @param lines 行缓冲区
   * @param line 待添加的行
   */
  private static void addLineIfRoom(List<String> lines, String line) {
    if (lines.size() < JsonlConstants.MAX_LINES_PER_RECORD) {
      lines.add(line);
    }
  }

  /**
   * 检测文件的行终止符字节长度。
   *
   * <p>读取文件开头的字节，如果检测到 {@code \r\n} 返回 2，否则返回 1。 用于字节偏移的近似估算。
   *
   * @param path 文件路径
   * @return 行终止符字节长度
   */
  private static int detectLineTerminatorByteLen(Path path) throws IOException {
    byte[] head = new byte[Math.min(4096, (int) Math.max(1, Files.size(path)))];
    int bytesRead;
    try (var is = Files.newInputStream(path)) {
      bytesRead = is.read(head);
    }
    if (bytesRead <= 0) {
      return 1;
    }
    for (int i = 0; i < bytesRead - 1; i++) {
      if (head[i] == '\r' && head[i + 1] == '\n') {
        return 2;
      }
      if (head[i] == '\n') {
        return 1;
      }
    }
    return 1;
  }

  /**
   * 估算字符串的 UTF-8 字节长度。
   *
   * <p>使用 Java 内置字符编码计算准确的 UTF-8 字节数。
   *
   * @param text 待估算的字符串
   * @return UTF-8 字节长度
   */
  private static int estimateUtf8ByteLength(String text) {
    return text.getBytes(StandardCharsets.UTF_8).length;
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
        if (depth <= 0) {
          // 深度回到零或以下：当前片段结束
          // 处理拼接对象（}{）、多余闭合括号（}}）等场景
          String candidate = text.substring(currentStart, i + 1).strip();
          if (!candidate.isEmpty()) {
            parts.add(candidate);
          }
          currentStart = i + 1;
          depth = 0;
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
   * @param lineNo 记录起始行号（从 1 开始计数）
   * @param events 成功解析的事件列表
   * @param diagnostics 诊断信息列表
   * @param startByte 记录起始字节偏移
   * @param endByte 记录结束字节偏移
   */
  private void tryParseJson(
      String text,
      int lineNo,
      List<JsonNode> events,
      List<SourceDiagnostic> diagnostics,
      long startByte,
      long endByte) {
    try {
      JsonNode node = mapper.readTree(text);
      if (node.isObject()) {
        events.add(node);
      } else {
        String typeName = typeNameFor(node);
        diagnostics.add(buildNonObjectDiagnostic(lineNo, typeName, text, startByte, endByte));
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
            diagnostics.add(buildNonObjectDiagnostic(lineNo, typeName, part, startByte, endByte));
          }
        } catch (JsonProcessingException e2) {
          diagnostics.add(
              buildBadJsonDiagnostic(
                  lineNo, part, ParseIssueType.BAD_JSON.name(), startByte, endByte));
        }
      }
    } else {
      diagnostics.add(
          buildBadJsonDiagnostic(lineNo, text, ParseIssueType.BAD_JSON.name(), startByte, endByte));
    }
  }

  /**
   * 对预览文本进行脱敏处理。
   *
   * <p>截断到配置的最大长度，并遮蔽疑似密钥值的 JSON 字符串。 防止敏感数据（token、password 等）出现在诊断输出中。 最终输出长度严格不超过 {@code
   * maxPreviewLength}。
   *
   * @param text 原始文本
   * @return 脱敏后的预览文本
   */
  private String sanitizePreview(String text) {
    String truncated = config.truncatePreview(text);
    // 遮蔽疑似密钥字段值（token、password、api_key 等）
    String masked =
        SECRET_VALUE_PATTERN
            .matcher(truncated)
            .replaceAll(
                match -> {
                  String m = match.group();
                  int colonIdx = m.indexOf(':');
                  if (colonIdx < 0) {
                    return m;
                  }
                  return m.substring(0, colonIdx + 1) + "\"***\"";
                });
    // 脱敏后可能因替换导致长度变化，再次截断确保不超限
    return config.truncatePreview(masked);
  }

  /** 构建 BAD_JSON 诊断信息（带专用代码和字节范围）。 */
  private SourceDiagnostic buildBadJsonDiagnostic(
      int lineNo, String text, String code, long startByte, long endByte) {
    String preview = sanitizePreview(text);
    return new SourceDiagnostic(
        ParseSeverity.ERROR,
        ParseIssueType.BAD_JSON,
        "Unparseable JSON at line " + lineNo,
        lineNo,
        Optional.of(preview),
        code,
        "",
        OptionalInt.empty(),
        startByte >= 0 ? OptionalInt.of((int) startByte) : OptionalInt.empty(),
        endByte >= 0 ? OptionalInt.of((int) endByte) : OptionalInt.empty());
  }

  /** 构建 NON_OBJECT_SKIPPED 诊断信息。 */
  private SourceDiagnostic buildNonObjectDiagnostic(
      int lineNo, String typeName, String text, long startByte, long endByte) {
    String preview = sanitizePreview(text);
    return new SourceDiagnostic(
        ParseSeverity.WARNING,
        ParseIssueType.NON_OBJECT_SKIPPED,
        "Non-dict JSON value skipped: " + typeName,
        lineNo,
        Optional.of(preview),
        ParseIssueType.NON_OBJECT_SKIPPED.name(),
        "",
        OptionalInt.empty(),
        startByte >= 0 ? OptionalInt.of((int) startByte) : OptionalInt.empty(),
        endByte >= 0 ? OptionalInt.of((int) endByte) : OptionalInt.empty());
  }

  /** 构建 INFO 级别诊断信息（如 STOPPED_BY_LIMIT）。 */
  private SourceDiagnostic buildInfoDiagnostic(
      int lineNo, String code, String message, long startByte, long endByte) {
    return new SourceDiagnostic(
        ParseSeverity.INFO,
        ParseIssueType.BAD_JSON,
        message,
        lineNo,
        Optional.empty(),
        code,
        "",
        OptionalInt.empty(),
        startByte >= 0 ? OptionalInt.of((int) startByte) : OptionalInt.empty(),
        endByte >= 0 ? OptionalInt.of((int) endByte) : OptionalInt.empty());
  }

  /** 构建 WARNING 级别诊断信息（如 RETRYABLE_INCOMPLETE）。 */
  private SourceDiagnostic buildWarnDiagnostic(
      int lineNo, String code, String message, long byteOff) {
    return new SourceDiagnostic(
        ParseSeverity.WARNING,
        ParseIssueType.BAD_JSON,
        message,
        lineNo,
        Optional.empty(),
        code,
        "",
        OptionalInt.empty(),
        byteOff >= 0 ? OptionalInt.of((int) byteOff) : OptionalInt.empty(),
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
