package com.feipi.session.browser.source.qoder;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.json.JsonCandidateParser;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import com.feipi.session.browser.source.qoder.QoderDiscovery.QoderDiscoveredSession;
import com.feipi.session.browser.source.qoder.QoderDiscovery.QoderDiscoveryResult;
import com.feipi.session.browser.source.qoder.QoderDiscovery.SourceKind;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourcePathOps;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Qoder 源适配器实现。
 *
 * <p>实现 {@link SourceAdapter} SPI 接口，负责从 Qoder 本地数据目录 发现会话文件、生成文件指纹和解析 JSONL 会话内容。
 *
 * <p>Qoder 会话目录结构：
 *
 * <pre>{@code
 * {root}/
 *   projects/
 *     {project-dir}/
 *       {session-id}.jsonl
 *   cache/
 *     projects/
 *       {project-dir}/
 *         {session-id}.jsonl
 * }</pre>
 *
 * <p>该适配器保证：
 *
 * <ul>
 *   <li>{@link #discover(Path)} 对同一输入产生确定排序的结果。
 *   <li>{@link #fingerprint(Path)} 包含 SHA-256 内容哈希。
 *   <li>{@link #checkRoot(Path)} 检测符号链接、路径逃逸和只读状态。
 *   <li>{@link #parse(Candidate, CancellationSignal)} 不抛出异常表示可预期失败。
 * </ul>
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 {@code ClaudeSourceAdapter}、{@code CodexSourceAdapter}
 * 存在结构性相似（语句级 STATEMENT_DUPLICATE），原因：三者分别实现 {@link SourceAdapter} SPI， 各 provider
 * 数据格式不同但适配逻辑结构一致（目录遍历、指纹计算、JSONL 解析、诊断构建）。 此重复是 SPI 适配器模式的固有特征，不宜提取公共基类以避免 provider 间耦合。
 */
public final class QoderSourceAdapter implements SourceAdapter {

  private static final Logger LOG = Logger.getLogger(QoderSourceAdapter.class.getName());
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String DIAG_CODE_UNKNOWN_PART_TYPE = "UNKNOWN_PART_TYPE";
  private static final int ESTIMATE_TEXT_CAP_BYTES = 32 * 1024;
  private static final String DEFAULT_QODER_MODEL = "Qwen-3.6-Plus";

  private final JsonlReader jsonlReader;

  /** 使用默认 JSONL 读取器配置创建适配器。 */
  public QoderSourceAdapter() {
    this(new JsonlReader());
  }

  /**
   * 使用指定 JSONL 读取器创建适配器。
   *
   * @param jsonlReader JSONL 读取器实例，不得为 null
   */
  public QoderSourceAdapter(JsonlReader jsonlReader) {
    Objects.requireNonNull(jsonlReader, "jsonlReader 不得为 null");
    this.jsonlReader = jsonlReader;
  }

  @Override
  public SourceId sourceId() {
    return SourceId.QODER;
  }

  /**
   * 从源根目录发现候选会话。
   *
   * <p>使用结构化发现结果和 canonical map 去重：cache 中的会话若映射到已发现的 projects UUID，则跳过。 session_key 和 project_key
   * 与 Python 主分支对齐。
   *
   * @param rootPath 源根目录路径
   * @return 有界确定性候选项流
   */
  @Override
  public BoundedStream<Candidate> discover(Path rootPath) {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    QoderDiscoveryResult discoveryResult = QoderDiscovery.discoverSessionsStructured(rootPath);
    Map<String, String> canonicalMap = QoderDiscovery.buildCanonicalIdMap(discoveryResult);

    // 收集 projects/ 已发现的 canonical session IDs（小写），用于 cache 去重
    Set<String> projectsSessionIds = new HashSet<>();
    for (QoderDiscoveredSession s : discoveryResult.sessions()) {
      if (s.sourceKind() == SourceKind.PROJECTS) {
        projectsSessionIds.add(s.sessionId().toLowerCase(Locale.ROOT));
      }
    }

    List<Candidate> candidates = new ArrayList<>();
    for (QoderDiscoveredSession disc : discoveryResult.sessions()) {
      try {
        // cache 去重：如果短 ID 映射到的 UUID 已在 projects 中，跳过
        if (disc.sourceKind() == SourceKind.CACHE) {
          String shortId = disc.sessionId().toLowerCase(Locale.ROOT);
          String canonicalId = canonicalMap.get(shortId);
          if (canonicalId != null && projectsSessionIds.contains(canonicalId)) {
            continue;
          }
        }

        SourceFingerprint fp = fingerprint(disc.path());
        String canonicalSessionId = canonicalSessionId(disc, canonicalMap);
        String sessionKey = "qoder:" + canonicalSessionId;
        QoderCandidateMetadata discoveredMeta =
            inspectCandidateFile(disc.path(), canonicalSessionId, disc.sourceKind());
        String projectKey = meaningfulProject(discoveredMeta.cwd(), disc.projectKey());
        if (projectKey.isEmpty()) {
          projectKey = canonicalSessionId;
        }

        Map<String, String> meta = new HashMap<>();
        meta.put("source_kind", disc.sourceKind().name().toLowerCase(Locale.ROOT));
        putIfNotEmpty(meta, "title", discoveredMeta.title());
        putIfNotEmpty(meta, "cwd", discoveredMeta.cwd());
        putIfNotEmpty(meta, "model", discoveredMeta.model());
        putIfNotEmpty(meta, "git_branch", discoveredMeta.gitBranch());
        putIfPositive(meta, "freshInputTokens", discoveredMeta.freshInputTokens());
        putIfPositive(meta, "outputTokens", discoveredMeta.outputTokens());
        putIfPositive(meta, "cacheReadTokens", discoveredMeta.cacheReadTokens());
        putIfPositive(meta, "cacheWriteTokens", discoveredMeta.cacheWriteTokens());
        putIfPositive(meta, "totalTokens", discoveredMeta.totalTokens());
        Candidate candidate = new Candidate(fp, sessionKey, projectKey, Map.copyOf(meta));
        candidates.add(candidate);
      } catch (Exception e) {
        LOG.log(Level.FINE, "跳过无法处理的会话文件: " + disc.path(), e);
      }
    }

    Comparator<Candidate> bySessionKey = Comparator.comparing(Candidate::sessionKey);
    return BoundedStream.of(
        candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.of(bySessionKey));
  }

  /**
   * 构建与 Python 主分支对齐的 session key。
   *
   * <p>格式：{@code qoder:{canonical_session}}。对 cache 来源的会话，使用 canonical map 将短 ID 映射为完整 UUID。
   */
  private static String canonicalSessionId(
      QoderDiscoveredSession disc, Map<String, String> canonicalMap) {
    String sessionId = disc.sessionId();

    // cache 短 ID → 完整 UUID
    if (disc.sourceKind() == SourceKind.CACHE) {
      String shortId = sessionId.toLowerCase(Locale.ROOT);
      String canonicalId = canonicalMap.get(shortId);
      if (canonicalId != null) {
        sessionId = canonicalId;
      }
    }

    return sessionId;
  }

  private QoderCandidateMetadata inspectCandidateFile(
      Path path, String canonicalSessionId, SourceKind sourceKind) {
    try {
      JsonlReaderResult result = jsonlReader.read(path);
      List<JsonNode> events = result.events();
      String cwd = "";
      String title = "";
      String model = "";
      String gitBranch = "";
      for (JsonNode event : events) {
        if (cwd.isEmpty() && isUserEvent(event)) {
          cwd = text(event, "cwd");
        }
        if (title.isEmpty() && isUserEvent(event) && !isMetaEvent(event)) {
          title = firstMessageText(event);
        }
        if (model.isEmpty()) {
          model = extractModel(event);
        }
        if (gitBranch.isEmpty()) {
          gitBranch = extractGitBranch(event);
        }
        if (!cwd.isEmpty() && !title.isEmpty() && !model.isEmpty() && !gitBranch.isEmpty()) {
          break;
        }
      }
      if (model.isEmpty()) {
        model = DEFAULT_QODER_MODEL;
      }
      TokenEstimate estimate =
          sourceKind == SourceKind.CACHE
              ? estimateCacheTokens(events)
              : estimateProjectTokens(events);
      return new QoderCandidateMetadata(
          cwd, title, model, gitBranch, estimate.freshInputTokens(), 0, 0, estimate.outputTokens());
    } catch (IOException e) {
      LOG.log(Level.FINEST, "读取 Qoder 候选元数据失败: " + path, e);
      return QoderCandidateMetadata.empty();
    }
  }

  private static boolean isUserEvent(JsonNode event) {
    String type = text(event, "type");
    if (!type.isEmpty()) {
      return "user".equals(type);
    }
    return "user".equals(text(event, "role"));
  }

  private static String meaningfulProject(String cwd, String fallback) {
    if (cwd != null && !cwd.isBlank() && !".".equals(cwd) && !cwd.startsWith("./")) {
      return cwd;
    }
    return fallback == null ? "" : fallback;
  }

  private static void putIfNotEmpty(Map<String, String> meta, String key, String value) {
    if (value != null && !value.isBlank()) {
      meta.put(key, value);
    }
  }

  private static void putIfPositive(Map<String, String> meta, String key, long value) {
    if (value <= 0) {
      return;
    }
    meta.put(key, Long.toString(value));
  }

  private static String extractModel(JsonNode event) {
    String model = text(event, "model");
    if (!model.isEmpty()) {
      return model;
    }
    JsonNode message = objectChild(event, "message");
    model = text(message, "model");
    if (!model.isEmpty()) {
      return model;
    }
    JsonNode metadata = objectChild(event, "metadata");
    model = text(metadata, "model");
    if (!model.isEmpty()) {
      return model;
    }
    JsonNode content = message == null ? null : message.get("content");
    if (content != null && content.isArray()) {
      for (JsonNode item : content) {
        model = text(item, "model");
        if (!model.isEmpty()) {
          return model;
        }
      }
    }
    return "";
  }

  private static TokenEstimate estimateCacheTokens(List<JsonNode> events) {
    long inputTokens = 0;
    long outputTokens = 0;
    for (JsonNode event : events) {
      String role = text(event, "role");
      String text = messageText(event);
      if (text.isBlank()) {
        continue;
      }
      long tokens = countTokens(text);
      if ("user".equals(role)) {
        inputTokens += tokens;
      } else if ("assistant".equals(role)) {
        outputTokens += tokens;
      }
    }
    return new TokenEstimate(inputTokens, outputTokens);
  }

  private static TokenEstimate estimateProjectTokens(List<JsonNode> events) {
    if (hasRealUsage(events)) {
      return TokenEstimate.empty();
    }
    long visibleContextTokens = 0;
    long estimatedInput = 0;
    long estimatedOutput = 0;
    Set<String> seenAssistantKeys = new HashSet<>();
    for (JsonNode event : events) {
      EventText eventText = extractEventText(event);
      if (eventText.category().isEmpty() || eventText.text().isBlank()) {
        continue;
      }
      long tokens = countTokens(eventText.text());
      if (eventText.category().startsWith("assistant")) {
        String key = assistantKey(event);
        if (seenAssistantKeys.add(key)) {
          estimatedInput += visibleContextTokens;
        }
        estimatedOutput += tokens;
      }
      visibleContextTokens += tokens;
    }
    return new TokenEstimate(estimatedInput, estimatedOutput);
  }

  private static boolean hasRealUsage(List<JsonNode> events) {
    for (JsonNode event : events) {
      if (!"assistant".equals(text(event, "type"))) {
        continue;
      }
      JsonNode usage = objectChild(objectChild(event, "message"), "usage");
      if (usage != null && usage.has("input_tokens") && usage.get("input_tokens").asLong(0) > 0) {
        return true;
      }
    }
    return false;
  }

  private static EventText extractEventText(JsonNode event) {
    String type = text(event, "type");
    JsonNode message = objectChild(event, "message");
    JsonNode content = message == null ? null : message.get("content");
    if ("user".equals(type)) {
      JsonNode isMeta = event.get("isMeta");
      if (isMeta != null && isMeta.isBoolean() && isMeta.asBoolean()) {
        return EventText.empty();
      }
      if (content != null && content.isTextual()) {
        return new EventText("user_prompt", content.asText());
      }
      if (content != null && content.isArray()) {
        StringBuilder textParts = new StringBuilder();
        StringBuilder toolResultParts = new StringBuilder();
        for (JsonNode item : content) {
          if (item == null || !item.isObject()) {
            continue;
          }
          if ("text".equals(text(item, "type"))) {
            String text = text(item, "text");
            if (!text.isBlank() && !text.contains("Caveat: The messages below were generated")) {
              appendLine(textParts, text);
            }
          } else if ("tool_result".equals(text(item, "type"))) {
            appendLine(toolResultParts, stringifyContent(item.get("content")));
          }
        }
        if (!textParts.isEmpty()) {
          return new EventText("user_prompt", textParts.toString());
        }
        if (!toolResultParts.isEmpty()) {
          return new EventText("tool_result", toolResultParts.toString());
        }
      }
    }
    if ("assistant".equals(type) && content != null && content.isArray()) {
      StringBuilder textParts = new StringBuilder();
      StringBuilder toolParts = new StringBuilder();
      for (JsonNode item : content) {
        if (item == null || !item.isObject()) {
          continue;
        }
        if ("text".equals(text(item, "type"))) {
          appendLine(textParts, text(item, "text"));
        } else if ("tool_use".equals(text(item, "type"))) {
          appendLine(toolParts, pythonStyleJson(item));
        }
      }
      if (!toolParts.isEmpty() && textParts.isEmpty()) {
        return new EventText("assistant_tool_call", toolParts.toString());
      }
      if (!textParts.isEmpty() || !toolParts.isEmpty()) {
        String combined =
            !textParts.isEmpty() && !toolParts.isEmpty()
                ? textParts + "\n" + toolParts
                : (!textParts.isEmpty() ? textParts.toString() : toolParts.toString());
        return new EventText("assistant_text", combined);
      }
    }
    return EventText.empty();
  }

  private static String assistantKey(JsonNode event) {
    JsonNode message = objectChild(event, "message");
    String id = text(message, "id");
    if (!id.isEmpty()) {
      return id;
    }
    id = text(event, "uuid");
    if (!id.isEmpty()) {
      return id;
    }
    id = text(event, "parentUuid");
    if (!id.isEmpty()) {
      return id;
    }
    id = text(event, "id");
    return id.isEmpty() ? "event:" + System.identityHashCode(event) : id;
  }

  private static String messageText(JsonNode event) {
    JsonNode message = objectChild(event, "message");
    JsonNode content = message == null ? event.get("content") : message.get("content");
    return contentText(content);
  }

  private static String firstMessageText(JsonNode event) {
    String value = messageText(event).strip();
    if (value.isEmpty()) {
      value = text(event, "text").strip();
    }
    value = cleanTitle(value);
    if (value.length() > 120) {
      return value.substring(0, 120);
    }
    return value;
  }

  private static String cleanTitle(String value) {
    if (value == null || value.isBlank()) {
      return "";
    }
    String message = between(value, "<command-message>", "</command-message>");
    if (!message.isBlank()) {
      return message.strip();
    }
    return value.replaceAll("<[^>]+>", " ").replaceAll("\\s+", " ").strip();
  }

  private static String between(String value, String start, String end) {
    int startIndex = value.indexOf(start);
    if (startIndex < 0) {
      return "";
    }
    int contentStart = startIndex + start.length();
    int endIndex = value.indexOf(end, contentStart);
    if (endIndex < 0) {
      return "";
    }
    return value.substring(contentStart, endIndex);
  }

  private static String extractGitBranch(JsonNode event) {
    String branch = text(event, "git_branch");
    if (!branch.isEmpty()) {
      return branch;
    }
    branch = text(event, "gitBranch");
    if (!branch.isEmpty()) {
      return branch;
    }
    JsonNode git = objectChild(event, "git");
    branch = text(git, "branch");
    if (!branch.isEmpty()) {
      return branch;
    }
    JsonNode metadata = objectChild(event, "metadata");
    branch = text(metadata, "git_branch");
    if (!branch.isEmpty()) {
      return branch;
    }
    return text(metadata, "gitBranch");
  }

  private static String contentText(JsonNode content) {
    if (content == null) {
      return "";
    }
    if (content.isTextual()) {
      return content.asText();
    }
    if (!content.isArray()) {
      return "";
    }
    StringBuilder sb = new StringBuilder();
    for (JsonNode item : content) {
      String text = "";
      if (item != null && item.isObject() && "text".equals(text(item, "type"))) {
        text = text(item, "text");
      } else if (item != null && item.isTextual()) {
        text = item.asText();
      }
      if (!text.isBlank()) {
        if (!sb.isEmpty()) {
          sb.append('\n');
        }
        sb.append(text);
      }
    }
    return sb.toString();
  }

  private static String stringifyContent(JsonNode content) {
    if (content == null || content.isNull()) {
      return "";
    }
    if (content.isTextual()) {
      return content.asText();
    }
    if (content.isArray()) {
      StringBuilder sb = new StringBuilder();
      for (JsonNode item : content) {
        appendLine(sb, stringifyContent(item));
      }
      return sb.toString();
    }
    if (content.isObject()) {
      if ("text".equals(text(content, "type"))) {
        return text(content, "text");
      }
      if (content.has("content")) {
        return stringifyContent(content.get("content"));
      }
    }
    return content.toString();
  }

  private static void appendLine(StringBuilder sb, String text) {
    if (text == null || text.isBlank()) {
      return;
    }
    if (!sb.isEmpty()) {
      sb.append('\n');
    }
    sb.append(text);
  }

  private static String pythonStyleJson(JsonNode node) {
    if (node == null || node.isNull()) {
      return "null";
    }
    if (node.isObject()) {
      StringBuilder sb = new StringBuilder("{");
      var fields = node.fields();
      boolean first = true;
      while (fields.hasNext()) {
        var field = fields.next();
        if (!first) {
          sb.append(", ");
        }
        first = false;
        sb.append(quoteJson(field.getKey())).append(": ").append(pythonStyleJson(field.getValue()));
      }
      return sb.append('}').toString();
    }
    if (node.isArray()) {
      StringBuilder sb = new StringBuilder("[");
      boolean first = true;
      for (JsonNode item : node) {
        if (!first) {
          sb.append(", ");
        }
        first = false;
        sb.append(pythonStyleJson(item));
      }
      return sb.append(']').toString();
    }
    if (node.isTextual()) {
      return quoteJson(node.asText());
    }
    return node.toString();
  }

  private static String quoteJson(String value) {
    try {
      return MAPPER.writeValueAsString(value);
    } catch (IOException e) {
      return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
  }

  private static long countTokens(String text) {
    if (text == null || text.isBlank()) {
      return 0;
    }
    String capped = capText(text);
    return Math.max(1L, (long) (capped.getBytes(StandardCharsets.UTF_8).length / 3.5));
  }

  private static String capText(String text) {
    byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
    if (bytes.length <= ESTIMATE_TEXT_CAP_BYTES) {
      return text;
    }
    double averageBytes = (double) bytes.length / Math.max(1, text.length());
    int safeChars = Math.max(1, (int) (ESTIMATE_TEXT_CAP_BYTES / averageBytes));
    String capped = text.substring(0, Math.min(text.length(), safeChars));
    while (capped.getBytes(StandardCharsets.UTF_8).length > ESTIMATE_TEXT_CAP_BYTES
        && !capped.isEmpty()) {
      capped = capped.substring(0, Math.max(0, capped.length() - 100));
    }
    return capped;
  }

  private static JsonNode objectChild(JsonNode node, String fieldName) {
    if (node == null) {
      return null;
    }
    if (!node.isObject()) {
      return null;
    }
    JsonNode child = node.path(fieldName);
    return child.isObject() ? child : null;
  }

  private static String text(JsonNode node, String fieldName) {
    if (node == null) {
      return "";
    }
    if (!node.isObject()) {
      return "";
    }
    JsonNode child = node.get(fieldName);
    if (child == null || !child.isTextual()) {
      return "";
    }
    return child.textValue();
  }

  /**
   * 表示 QoderCandidateMetadata 数据。
   *
   * @param cwd 工作目录。
   * @param title 会话标题。
   * @param model 模型名称。
   * @param gitBranch Git branch 名称。
   * @param freshInputTokens fresh input token 数量。
   * @param cacheReadTokens cache read token 数量。
   * @param cacheWriteTokens cache write token 数量。
   * @param outputTokens output token 数量。
   */
  private record QoderCandidateMetadata(
      String cwd,
      String title,
      String model,
      String gitBranch,
      long freshInputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      long outputTokens) {
    private static QoderCandidateMetadata empty() {
      return new QoderCandidateMetadata("", "", "", "", 0, 0, 0, 0);
    }

    private long totalTokens() {
      return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    }
  }

  /**
   * 表示 TokenEstimate 数据。
   *
   * @param freshInputTokens fresh input token 数量。
   * @param outputTokens output token 数量。
   */
  private record TokenEstimate(long freshInputTokens, long outputTokens) {
    private static TokenEstimate empty() {
      return new TokenEstimate(0, 0);
    }
  }

  /**
   * 表示 EventText 数据。
   *
   * @param category 分类值。
   * @param text 文本内容。
   */
  private record EventText(String category, String text) {
    private static EventText empty() {
      return new EventText("", "");
    }
  }

  /**
   * 为指定源文件生成指纹。
   *
   * <p>指纹包含路径、源标识、文件大小、修改时间和 SHA-256 内容哈希。
   *
   * @param filePath 源文件路径
   * @return 文件指纹
   */
  @Override
  public SourceFingerprint fingerprint(Path filePath) {
    Objects.requireNonNull(filePath, "filePath 不得为 null");

    try {
      long size = Files.size(filePath);
      long lastModified = Files.getLastModifiedTime(filePath).toMillis();
      String hash = SourcePathOps.computeSha256(filePath);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.QODER,
          size,
          lastModified,
          Optional.of(hash),
          Optional.of(SourceConstants.DEFAULT_HASH_ALGORITHM));
    } catch (IOException e) {
      // 文件不存在或无法访问，返回零值指纹
      LOG.log(Level.FINE, "无法生成文件指纹: " + filePath, e);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.QODER,
          0,
          0,
          Optional.empty(),
          Optional.empty());
    }
  }

  /**
   * 解析指定候选项的会话数据。
   *
   * <p>使用 {@link JsonlReader} 解析 JSONL 文件，将每个 JSON 事件转为源中性 {@link SourceRecord}。
   *
   * <p>Qoder 特有的 schema 变体处理：
   *
   * <ul>
   *   <li>主格式事件使用 {@code type} 字段标识事件类型（如 {@code user}、{@code assistant}）。
   *   <li>Cache 格式事件使用 {@code role} 字段代替 {@code type}，产生 {@code CACHE_FORMAT_ROLE} 诊断信息。
   *   <li>缺少 {@code type} 和 {@code role} 字段的事件产生 {@code UNKNOWN_BLOCK_TYPE} 诊断警告， 但不会丢失整个 session。
   * </ul>
   *
   * <p>文件不存在返回 {@link SourceResult.Skipped}，IO 错误返回 {@link SourceResult.Fatal}， 解析成功（含诊断）返回 {@link
   * SourceResult.Success}。
   *
   * @param candidate 待解析的候选项
   * @param cancellation 可选的取消信号
   * @return 密封的解析结果
   */
  @Override
  public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
    return JsonCandidateParser.parse(
        candidate,
        cancellation,
        jsonlReader,
        QoderSourceAdapter::extractEventType,
        QoderSourceAdapter::collectEventDiagnostics,
        (diagnostics, eventCount) -> {});
  }

  private static void collectEventDiagnostics(
      JsonNode event,
      int eventIndex,
      String eventType,
      String locator,
      List<SourceDiagnostic> diagnostics) {
    if (isCacheRoleEvent(event)) {
      diagnostics.add(
          qoderDiagnostic(
              ParseSeverity.INFO,
              "Event at index " + eventIndex + " uses cache format with 'role' field: " + eventType,
              eventIndex,
              QoderConstants.DIAG_CODE_CACHE_FORMAT,
              locator));
    } else if (eventType.equals(QoderConstants.EVENT_TYPE_UNKNOWN)) {
      diagnostics.add(
          qoderDiagnostic(
              ParseSeverity.WARNING,
              "Event at index " + eventIndex + " missing 'type' field",
              eventIndex,
              QoderConstants.DIAG_CODE_MISSING_TYPE,
              locator));
    }
    addUnknownPartDiagnostics(event, diagnostics, locator, eventIndex);
  }

  private static SourceDiagnostic qoderDiagnostic(
      ParseSeverity severity, String message, int eventIndex, String code, String locator) {
    return new SourceDiagnostic(
        severity,
        ParseIssueType.NON_OBJECT_SKIPPED,
        message,
        eventIndex + 1,
        Optional.empty(),
        code,
        locator,
        OptionalInt.empty(),
        OptionalInt.empty(),
        OptionalInt.empty());
  }

  /**
   * 从 JSON 事件节点中提取 {@code type} 字段值。
   *
   * <p>当字段缺失或不是字符串时返回 {@link QoderConstants#EVENT_TYPE_UNKNOWN}。
   *
   * @param event JSON 事件节点
   * @return 非 null 的事件类型
   */
  private static String extractEventType(JsonNode event) {
    JsonNode typeNode = event.get("type");
    if (typeNode != null && typeNode.isTextual()) {
      if ("user".equals(typeNode.asText()) && isMetaEvent(event)) {
        return "meta";
      }
      return typeNode.asText();
    }
    if (hasRoleField(event)) {
      if ("user".equals(event.get("role").asText()) && isMetaEvent(event)) {
        return "meta";
      }
      return event.get("role").asText();
    }
    return QoderConstants.EVENT_TYPE_UNKNOWN;
  }

  private static boolean isMetaEvent(JsonNode event) {
    JsonNode isMeta = event.get("isMeta");
    return isMeta != null && isMeta.isBoolean() && isMeta.asBoolean();
  }

  /**
   * 检查 JSON 事件节点是否包含 {@code role} 字段。
   *
   * <p>Qoder cache 格式使用 {@code role} 字段代替 {@code type} 字段标识事件类型。
   *
   * @param event JSON 事件节点
   * @return 包含 {@code role} 字段且为字符串时返回 {@code true}
   */
  private static boolean hasRoleField(JsonNode event) {
    JsonNode roleNode = event.get("role");
    return roleNode != null && roleNode.isTextual();
  }

  private static boolean isCacheRoleEvent(JsonNode event) {
    JsonNode typeNode = event.get("type");
    return (typeNode == null || !typeNode.isTextual()) && hasRoleField(event);
  }

  private static void addUnknownPartDiagnostics(
      JsonNode event, List<SourceDiagnostic> diagnostics, String locator, int eventIndex) {
    JsonNode parts = event.get("parts");
    if (parts == null || !parts.isArray()) {
      return;
    }
    for (JsonNode part : parts) {
      JsonNode typeNode = part.get("type");
      if (typeNode == null || !typeNode.isTextual() || !isKnownPartType(typeNode.asText())) {
        diagnostics.add(
            new SourceDiagnostic(
                ParseSeverity.WARNING,
                ParseIssueType.NON_OBJECT_SKIPPED,
                "Event at index " + eventIndex + " contains unknown part type",
                eventIndex + 1,
                Optional.empty(),
                DIAG_CODE_UNKNOWN_PART_TYPE,
                locator,
                OptionalInt.empty(),
                OptionalInt.empty(),
                OptionalInt.empty()));
      }
    }
  }

  private static boolean isKnownPartType(String partType) {
    return switch (partType) {
      case "text", "tool_use", "tool_result", "image", "file", "reasoning" -> true;
      default -> false;
    };
  }
}
