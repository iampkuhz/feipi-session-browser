package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.json.JsonCandidateParser;
import com.feipi.session.browser.source.json.JsonlReader;
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
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Codex 源适配器实现。
 *
 * <p>实现 {@link SourceAdapter} SPI 接口，负责从 Codex 本地数据目录 发现会话文件、生成文件指纹和解析 JSONL 会话内容。
 *
 * <p>Codex 会话目录结构：
 *
 * <pre>{@code
 * {root}/
 *   sessions/
 *     {year}/
 *       {month}/
 *         {day}/
 *           rollout-{timestamp}-{uuid}.jsonl
 *   archived_sessions/
 *     rollout-{timestamp}-{uuid}.jsonl
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
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类与 {@code ClaudeSourceAdapter}、{@code QoderSourceAdapter}
 * 存在结构性相似（语句级 STATEMENT_DUPLICATE），原因：三者分别实现 {@link SourceAdapter} SPI， 各 provider
 * 数据格式不同但适配逻辑结构一致（目录遍历、指纹计算、JSONL 解析、诊断构建）。 此重复是 SPI 适配器模式的固有特征，不宜提取公共基类以避免 provider 间耦合。
 */
public final class CodexSourceAdapter implements SourceAdapter {

  private static final Logger LOG = Logger.getLogger(CodexSourceAdapter.class.getName());

  private final JsonlReader jsonlReader;

  /** 使用默认 JSONL 读取器配置创建适配器。 */
  public CodexSourceAdapter() {
    this(new JsonlReader());
  }

  /**
   * 使用指定 JSONL 读取器创建适配器。
   *
   * @param jsonlReader JSONL 读取器实例，不得为 null
   */
  public CodexSourceAdapter(JsonlReader jsonlReader) {
    Objects.requireNonNull(jsonlReader, "jsonlReader 不得为 null");
    this.jsonlReader = jsonlReader;
  }

  @Override
  public SourceId sourceId() {
    return SourceId.CODEX;
  }

  /**
   * 从源根目录发现候选会话。
   *
   * <p>遍历日期目录，找到所有 {@code session.jsonl} 会话文件，按路径排序。 目录不存在或为空时返回空的 {@link BoundedStream}。
   *
   * @param rootPath 源根目录路径
   * @return 有界确定性候选项流
   */
  @Override
  public BoundedStream<Candidate> discover(Path rootPath) {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    List<CodexDiscovery.CodexSessionDiscovery> discoveries =
        CodexDiscovery.discoverSessionsWithMetadata(rootPath);
    List<Candidate> candidates = new ArrayList<>(discoveries.size());

    for (CodexDiscovery.CodexSessionDiscovery disc : discoveries) {
      try {
        SourceFingerprint fp;
        if (disc.hasFile()) {
          fp = fingerprint(disc.rolloutPath());
        } else {
          // rollout 缺失：零值指纹，locator 使用 sessionId
          fp =
              new SourceFingerprint(
                  disc.sessionId(),
                  SourceId.CODEX,
                  0,
                  0,
                  Optional.empty(),
                  Optional.empty());
        }

        String sessionKey = "codex:" + disc.sessionId();
        String projectKey = extractProjectKeyFromThreadInfo(disc);

        Map<String, String> meta = buildCandidateMetadata(disc);
        Candidate candidate = new Candidate(fp, sessionKey, projectKey, meta);
        candidates.add(candidate);
      } catch (Exception e) {
        LOG.log(Level.FINE, "跳过无法处理的会话: " + disc.sessionId(), e);
      }
    }

    Comparator<Candidate> bySessionKey = Comparator.comparing(Candidate::sessionKey);
    return BoundedStream.of(
        candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.of(bySessionKey));
  }

  /** 从发现结果构建 Candidate 元数据。 */
  private static Map<String, String> buildCandidateMetadata(
      CodexDiscovery.CodexSessionDiscovery disc) {
    Map<String, String> meta = new java.util.HashMap<>();
    meta.put("has_transcript", String.valueOf(disc.hasFile()));

    // 优先从 threads.db 取 title
    if (disc.threadInfo() != null) {
      String title = disc.threadInfo().getOrDefault("title", "");
      if (!title.isEmpty()) {
        meta.put("title", title);
      }
      String cwd = disc.threadInfo().getOrDefault("cwd", "");
      if (!cwd.isEmpty()) {
        meta.put("cwd", cwd);
      }
    }
    // 回退到 session_index.jsonl
    if (!meta.containsKey("title") && disc.indexEntry() != null) {
      String threadName = disc.indexEntry().getOrDefault("thread_name", "");
      if (!threadName.isEmpty()) {
        meta.put("title", threadName);
      }
    }
    // 从 first_user_message 补充 title
    if (!meta.containsKey("title") && disc.threadInfo() != null) {
      String fum = disc.threadInfo().getOrDefault("first_user_message", "");
      if (!fum.isEmpty()) {
        meta.put("title", fum.length() > 120 ? fum.substring(0, 120) : fum);
      }
    }
    return Map.copyOf(meta);
  }

  /** 从发现结果提取项目键。 */
  private static String extractProjectKeyFromThreadInfo(
      CodexDiscovery.CodexSessionDiscovery disc) {
    if (disc.threadInfo() != null) {
      String cwd = disc.threadInfo().getOrDefault("cwd", "");
      if (!cwd.isEmpty()) {
        return cwd;
      }
    }
    return "";
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
          SourceId.CODEX,
          size,
          lastModified,
          Optional.of(hash),
          Optional.of(SourceConstants.DEFAULT_HASH_ALGORITHM));
    } catch (IOException e) {
      // 文件不存在或无法访问，返回零值指纹
      LOG.log(Level.FINE, "无法生成文件指纹: " + filePath, e);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.CODEX,
          0,
          0,
          Optional.empty(),
          Optional.empty());
    }
  }

  /**
   * 解析指定候选项的会话数据。
   *
   * <p>使用 {@link JsonlReader} 解析 JSONL 文件，将每个 JSON 事件转为源中性 {@link SourceRecord}。 缺少 {@code type}
   * 字段的事件产生 {@code UNKNOWN_BLOCK_TYPE} 诊断警告，但不会丢失整个 session。
   *
   * <p>Codex 特有的语义提取：
   *
   * <ul>
   *   <li>session_meta 事件用于 subagent 检测（parent_thread_id、thread_source）。
   *   <li>token_count 事件跟踪 cumulative token 用量语义。
   *   <li>function_call 与 function_call_output 的 orphan 检测。
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
    // 零值指纹 → rollout 缺失 → 跳过解析（engine 会 fallback 入库）
    if (candidate.fingerprint().sizeBytes() == 0 && candidate.fingerprint().contentHash().isEmpty()) {
      return new SourceResult.Skipped(
          List.of(), "Rollout file missing for session " + candidate.sessionKey());
    }

    CodexParseState state = new CodexParseState();
    return JsonCandidateParser.parse(
        candidate,
        cancellation,
        jsonlReader,
        CodexSourceAdapter::extractEventType,
        (event, eventIndex, eventType, locator, diagnostics) ->
            collectEventDiagnostics(state, event, eventIndex, eventType, locator, diagnostics),
        (diagnostics, eventCount) -> collectCompletionDiagnostics(state, diagnostics));
  }

  private static void collectEventDiagnostics(
      CodexParseState state,
      JsonNode event,
      int eventIndex,
      String eventType,
      String locator,
      List<SourceDiagnostic> diagnostics) {
    state.locator = locator;
    if (eventType.equals(CodexConstants.EVENT_TYPE_UNKNOWN)) {
      diagnostics.add(
          new SourceDiagnostic(
              ParseSeverity.WARNING,
              ParseIssueType.NON_OBJECT_SKIPPED,
              "Event at index " + eventIndex + " missing 'type' field",
              eventIndex + 1,
              Optional.empty(),
              CodexConstants.DIAG_CODE_MISSING_TYPE,
              locator,
              OptionalInt.empty(),
              OptionalInt.empty(),
              OptionalInt.empty()));
    }

    if (eventType.equals(CodexConstants.EVENT_TYPE_SESSION_META) && state.sessionMeta == null) {
      state.sessionMeta = extractSessionMeta(event);
      return;
    }
    if (eventType.equals(CodexConstants.EVENT_TYPE_EVENT_MSG)) {
      updateTokenState(state, event);
      return;
    }
    if (eventType.equals(CodexConstants.EVENT_TYPE_RESPONSE_ITEM)) {
      updateToolState(state, event);
    }
  }

  private static void updateTokenState(CodexParseState state, JsonNode event) {
    if (!"token_count".equals(extractEventMsgType(event))) {
      return;
    }
    state.tokenCountEvents++;
    state.hasCumulativeTokenUsage = state.hasCumulativeTokenUsage || hasCumulativeUsage(event);
  }

  private static void updateToolState(CodexParseState state, JsonNode event) {
    String responseType = extractResponseType(event);
    if ("function_call".equals(responseType) || "custom_tool_call".equals(responseType)) {
      state.toolCallCount++;
    } else if ("function_call_output".equals(responseType)
        || "custom_tool_call_output".equals(responseType)) {
      state.toolOutputCount++;
    }
  }

  private static void collectCompletionDiagnostics(
      CodexParseState state, List<SourceDiagnostic> diagnostics) {
    appendToolOrphanDiagnostics(state, diagnostics);
    appendTokenDiagnostics(state, diagnostics);
    appendSubagentDiagnostics(state, diagnostics);
  }

  private static void appendToolOrphanDiagnostics(
      CodexParseState state, List<SourceDiagnostic> diagnostics) {
    if (state.toolCallCount > 0 && state.toolOutputCount == 0) {
      diagnostics.add(
          codexInfoDiagnostic(
              "Tool calls without matching outputs (orphan): " + state.toolCallCount + " calls",
              "TOOL_ORPHAN",
              state.locator));
    }
    if (state.toolOutputCount > 0 && state.toolCallCount == 0) {
      diagnostics.add(
          codexInfoDiagnostic(
              "Tool outputs without matching requests (orphan result): "
                  + state.toolOutputCount
                  + " outputs",
              "TOOL_ORPHAN_RESULT",
              state.locator));
    }
  }

  private static void appendTokenDiagnostics(
      CodexParseState state, List<SourceDiagnostic> diagnostics) {
    if (state.tokenCountEvents > 0 && !state.hasCumulativeTokenUsage) {
      diagnostics.add(
          codexInfoDiagnostic(
              "Token count events present but no cumulative usage data",
              "TOKEN_NO_CUMULATIVE",
              state.locator));
    }
  }

  private static void appendSubagentDiagnostics(
      CodexParseState state, List<SourceDiagnostic> diagnostics) {
    if (state.sessionMeta != null && isSubagentMeta(state.sessionMeta)) {
      diagnostics.add(
          codexInfoDiagnostic(
              "Session identified as subagent thread", "SUBAGENT_SESSION", state.locator));
    }
  }

  private static SourceDiagnostic codexInfoDiagnostic(String message, String code, String locator) {
    return new SourceDiagnostic(
        ParseSeverity.INFO,
        ParseIssueType.NON_OBJECT_SKIPPED,
        message,
        1,
        Optional.empty(),
        code,
        locator,
        OptionalInt.empty(),
        OptionalInt.empty(),
        OptionalInt.empty());
  }

  /** Codex 单文件解析期间累计的 provider 特有诊断状态。 */
  private static final class CodexParseState {
    private Map<String, String> sessionMeta;
    private int toolCallCount;
    private int toolOutputCount;
    private int tokenCountEvents;
    private boolean hasCumulativeTokenUsage;
    private String locator = "";
  }

  /**
   * 从 JSON 事件节点中提取 {@code type} 字段值。
   *
   * <p>当字段缺失或不是字符串时返回 {@link CodexConstants#EVENT_TYPE_UNKNOWN}。
   *
   * @param event JSON 事件节点
   * @return 非 null 的事件类型
   */
  private static String extractEventType(JsonNode event) {
    JsonNode typeNode = event.get("type");
    if (typeNode != null && typeNode.isTextual()) {
      return typeNode.asText();
    }
    return CodexConstants.EVENT_TYPE_UNKNOWN;
  }

  /**
   * 从 session_meta 事件中提取 payload 键值对。
   *
   * @param event session_meta 事件节点
   * @return payload 字段的扁平字符串映射，缺失时返回空 map
   */
  private static Map<String, String> extractSessionMeta(JsonNode event) {
    JsonNode payload = event.get("payload");
    if (payload == null || !payload.isObject()) {
      return Map.of();
    }
    var result = new java.util.HashMap<String, String>();
    var fields = payload.fields();
    while (fields.hasNext()) {
      var entry = fields.next();
      JsonNode value = entry.getValue();
      if (value.isTextual()) {
        result.put(entry.getKey(), value.asText());
      } else if (value.isNumber()) {
        result.put(entry.getKey(), String.valueOf(value.asLong()));
      } else if (value.isBoolean()) {
        result.put(entry.getKey(), String.valueOf(value.asBoolean()));
      } else if (value.isObject() || value.isArray()) {
        // 嵌套结构序列化为 JSON 字符串保留
        result.put(entry.getKey(), value.toString());
      }
    }
    return Map.copyOf(result);
  }

  /**
   * 从 event_msg 事件中提取内部 {@code payload.type} 字段。
   *
   * @param event event_msg 事件节点
   * @return 消息类型字符串，缺失时返回空字符串
   */
  private static String extractEventMsgType(JsonNode event) {
    JsonNode payload = event.get("payload");
    if (payload != null && payload.isObject()) {
      JsonNode msgType = payload.get("type");
      if (msgType != null && msgType.isTextual()) {
        return msgType.asText();
      }
    }
    return "";
  }

  /**
   * 从 response_item 事件中提取内部 {@code payload.type} 字段。
   *
   * @param event response_item 事件节点
   * @return 响应类型字符串，缺失时返回空字符串
   */
  private static String extractResponseType(JsonNode event) {
    JsonNode payload = event.get("payload");
    if (payload != null && payload.isObject()) {
      JsonNode type = payload.get("type");
      if (type != null && type.isTextual()) {
        return type.asText();
      }
    }
    return "";
  }

  /**
   * 检查 token_count 事件是否包含 cumulative usage 数据。
   *
   * <p>Codex 通过 {@code total_token_usage} 字段提供累计 token 用量。 检查 {@code
   * payload.info.total_token_usage} 或 {@code payload.total_token_usage}。
   *
   * @param event token_count 事件节点
   * @return 包含 cumulative usage 时返回 {@code true}
   */
  private static boolean hasCumulativeUsage(JsonNode event) {
    JsonNode payload = event.get("payload");
    if (payload == null || !payload.isObject()) {
      return false;
    }
    // 检查 payload.info.total_token_usage
    JsonNode info = payload.get("info");
    if (info != null && info.isObject()) {
      JsonNode totalUsage = info.get("total_token_usage");
      if (totalUsage != null && totalUsage.isObject()) {
        return true;
      }
    }
    // 检查 payload.total_token_usage
    JsonNode directUsage = payload.get("total_token_usage");
    return directUsage != null && directUsage.isObject();
  }

  /**
   * 判断 session_meta 是否表示 subagent 会话。
   *
   * <p>检测条件与 Python 参考实现 {@code is_codex_subagent_session_meta} 对齐：
   *
   * <ul>
   *   <li>{@code thread_source} 为 "subagent"
   *   <li>{@code parent_thread_id} 非空
   *   <li>{@code source.subagent.thread_spawn.parent_thread_id} 非空
   * </ul>
   *
   * @param meta session_meta payload 映射
   * @return 识别为 subagent 时返回 {@code true}
   */
  private static boolean isSubagentMeta(Map<String, String> meta) {
    // 检查 thread_source
    String threadSource = meta.getOrDefault("thread_source", "");
    if ("subagent".equalsIgnoreCase(threadSource.trim())) {
      return true;
    }
    // 检查 parent_thread_id
    String parentId = meta.getOrDefault("parent_thread_id", "").trim();
    if (!parentId.isEmpty()) {
      return true;
    }
    // 检查嵌套 source.subagent.thread_spawn.parent_thread_id
    String sourceJson = meta.get("source");
    if (sourceJson != null && !sourceJson.isEmpty()) {
      try {
        com.fasterxml.jackson.databind.ObjectMapper mapper =
            new com.fasterxml.jackson.databind.ObjectMapper();
        JsonNode sourceNode = mapper.readTree(sourceJson);
        if (sourceNode.isObject()) {
          JsonNode subagent = sourceNode.get("subagent");
          if (subagent != null && subagent.isObject()) {
            JsonNode spawn = subagent.get("thread_spawn");
            if (spawn != null && spawn.isObject()) {
              JsonNode spawnParent = spawn.get("parent_thread_id");
              if (spawnParent != null
                  && spawnParent.isTextual()
                  && !spawnParent.asText().trim().isEmpty()) {
                return true;
              }
            }
          }
        }
      } catch (IOException e) {
        // source 字段不是合法 JSON，忽略
        LOG.log(Level.FINEST, "session_meta.source 解析失败", e);
      }
    }
    return false;
  }

  /**
   * 从会话文件路径中提取会话键。
   *
   * <p>新结构（{@code sessions/{year}/{month}/{day}/rollout-*.jsonl}）：使用文件名去掉 {@code .jsonl} 后缀作为会话键。
   * 归档结构（{@code archived_sessions/rollout-*.jsonl}）：同样使用文件名去掉 {@code .jsonl} 后缀。
   * 旧结构（{@code {day-dir}/{session-id}/session.jsonl}）：使用 {@code {day-dir}/{session-id}} 作为会话键（向后兼容）。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 会话键
   */
  private static String extractSessionKey(Path rootPath, Path sessionPath) {
    Path relative = SourcePathOps.toRelative(rootPath, sessionPath);
    int nameCount = relative.getNameCount();
    if (nameCount == 0) {
      return sessionPath.getFileName().toString();
    }

    String firstDir = relative.getName(0).toString();

    // 新结构：sessions/...
    if (firstDir.equals(CodexConstants.SESSIONS_DIR)) {
      String fileName = sessionPath.getFileName().toString();
      return SourcePathOps.stripSuffix(fileName, CodexConstants.SESSION_FILE_SUFFIX);
    }

    // 归档结构：archived_sessions/...
    if (firstDir.equals(CodexConstants.ARCHIVED_SESSION_DIR)) {
      String fileName = sessionPath.getFileName().toString();
      return SourcePathOps.stripSuffix(fileName, CodexConstants.SESSION_FILE_SUFFIX);
    }

    // 旧结构 fallback：{day-dir}/{session-id}/session.jsonl
    if (nameCount >= 3) {
      String dayDir = relative.getName(0).toString();
      String sessionId = relative.getName(1).toString();
      return dayDir + "/" + sessionId;
    }
    if (nameCount >= 2) {
      return relative.getName(0).toString();
    }
    return sessionPath.getFileName().toString();
  }

  /**
   * 从会话文件路径中提取项目键。
   *
   * <p>新结构（{@code sessions/{year}/{month}/{day}/rollout-*.jsonl}）：使用日期路径 {@code sessions/{year}/{month}/{day}} 作为项目键。
   * 归档结构（{@code archived_sessions/rollout-*.jsonl}）：使用 {@code archived_sessions} 作为项目键。
   * 旧结构（{@code {day-dir}/{session-id}/session.jsonl}）：使用 {@code {day-dir}} 作为项目键（向后兼容）。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 项目键
   */
  private static String extractProjectKey(Path rootPath, Path sessionPath) {
    Path relative = SourcePathOps.toRelative(rootPath, sessionPath);
    int nameCount = relative.getNameCount();
    if (nameCount == 0) {
      return "";
    }

    String firstDir = relative.getName(0).toString();

    // 归档结构：archived_sessions/...
    if (firstDir.equals(CodexConstants.ARCHIVED_SESSION_DIR)) {
      return CodexConstants.ARCHIVED_SESSION_DIR;
    }

    // 新结构：sessions/{year}/{month}/{day}/...
    if (firstDir.equals(CodexConstants.SESSIONS_DIR) && nameCount >= 4) {
      return relative.getName(0) + "/" + relative.getName(1) + "/"
          + relative.getName(2) + "/" + relative.getName(3);
    }

    // 旧结构 fallback：{day-dir}/...
    return firstDir;
  }
}
