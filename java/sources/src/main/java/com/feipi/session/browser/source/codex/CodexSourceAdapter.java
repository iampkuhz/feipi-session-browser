package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceToolCall;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderResult;
import com.feipi.session.browser.source.common.ToolFailureClassifier;
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
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
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
  private static final ObjectMapper MAPPER = new ObjectMapper();

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
                  disc.sessionId(), SourceId.CODEX, 0, 0, Optional.empty(), Optional.empty());
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
      String gitBranch = firstNonEmpty(disc.threadInfo(), "git_branch", "gitBranch", "branch");
      if (!gitBranch.isEmpty()) {
        meta.put("git_branch", gitBranch);
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
    // 模型回退：优先 threads.db，其次 session_index.jsonl
    if (disc.threadInfo() != null) {
      String model = disc.threadInfo().getOrDefault("model", "");
      if (!model.isEmpty()) {
        meta.put("model", model);
      }
    }
    if (!meta.containsKey("model") && disc.indexEntry() != null) {
      String model = disc.indexEntry().getOrDefault("model", "");
      if (!model.isEmpty()) {
        meta.put("model", model);
      }
    }
    if (disc.hasFile()) {
      Map<String, String> fileMeta = readFirstSessionMeta(disc.rolloutPath());
      if (!meta.containsKey("cwd")) {
        String cwd = fileMeta.getOrDefault("cwd", "");
        if (!cwd.isEmpty()) {
          meta.put("cwd", cwd);
        }
      }
      if (!meta.containsKey("git_branch")) {
        String gitBranch = firstNonEmpty(fileMeta, "git_branch", "gitBranch", "branch");
        if (gitBranch.isEmpty()) {
          gitBranch = extractGitBranchFromSource(fileMeta.getOrDefault("source", ""));
        }
        if (!gitBranch.isEmpty()) {
          meta.put("git_branch", gitBranch);
        }
      }
    }
    if (disc.hasFile()) {
      long subagentCount = countSubagentChildren(disc.rolloutPath(), disc.sessionId());
      if (subagentCount > 0) {
        meta.put("subagentInstanceCount", Long.toString(subagentCount));
      }
    }
    return Map.copyOf(meta);
  }

  private static String firstNonEmpty(Map<String, String> values, String... keys) {
    if (values == null) {
      return "";
    }
    for (String key : keys) {
      String value = values.getOrDefault(key, "").trim();
      if (!value.isEmpty()) {
        return value;
      }
    }
    return "";
  }

  private static String extractGitBranchFromSource(String source) {
    if (source == null || source.isBlank()) {
      return "";
    }
    try {
      JsonNode sourceNode = MAPPER.readTree(source);
      JsonNode git = sourceNode.path("git");
      JsonNode branch = git.get("branch");
      if (branch != null && branch.isTextual()) {
        return branch.asText().trim();
      }
      JsonNode direct = sourceNode.get("git_branch");
      if (direct != null && direct.isTextual()) {
        return direct.asText().trim();
      }
    } catch (IOException e) {
      return "";
    }
    return "";
  }

  private static long countSubagentChildren(Path rolloutPath, String parentSessionId) {
    if (rolloutPath == null || parentSessionId == null || parentSessionId.isBlank()) {
      return 0;
    }
    return childRolloutFiles(rolloutPath, parentSessionId).size();
  }

  private static Map<String, String> readFirstSessionMeta(Path candidate) {
    try (BufferedReader reader = Files.newBufferedReader(candidate, StandardCharsets.UTF_8)) {
      String line;
      while ((line = reader.readLine()) != null) {
        if (line.isBlank()) {
          continue;
        }
        JsonNode event = MAPPER.readTree(line);
        if (event != null
            && event.isObject()
            && event.has("type")
            && "session_meta".equals(event.get("type").asText())) {
          return CodexDiscovery.flattenPayloadFields(event);
        }
        return Map.of();
      }
    } catch (IOException e) {
      LOG.log(Level.FINEST, "读取 Codex session_meta 失败: " + candidate, e);
    }
    return Map.of();
  }

  private static String parentThreadId(Map<String, String> meta) {
    if (meta == null || meta.isEmpty()) {
      return "";
    }
    String parent = meta.getOrDefault("parent_thread_id", "").trim();
    if (!parent.isEmpty()) {
      return parent;
    }
    String source = meta.getOrDefault("source", "");
    if (source.isBlank()) {
      return "";
    }
    try {
      JsonNode sourceNode = MAPPER.readTree(source);
      JsonNode spawn = sourceNode.path("subagent").path("thread_spawn");
      JsonNode spawnParent = spawn.get("parent_thread_id");
      return spawnParent != null && spawnParent.isTextual() ? spawnParent.asText().trim() : "";
    } catch (IOException e) {
      return "";
    }
  }

  /** 从发现结果提取项目键。 */
  private static String extractProjectKeyFromThreadInfo(CodexDiscovery.CodexSessionDiscovery disc) {
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
    if (candidate.fingerprint().sizeBytes() == 0
        && candidate.fingerprint().contentHash().isEmpty()) {
      return new SourceResult.Skipped(
          List.of(), "Rollout file missing for session " + candidate.sessionKey());
    }

    if (cancellation != null && cancellation.isCancelled()) {
      return new SourceResult.Skipped(List.of(), "解析已取消");
    }

    Path filePath = Path.of(candidate.fingerprint().locator());
    if (!Files.exists(filePath)) {
      return new SourceResult.Skipped(List.of(), "文件不存在: " + filePath);
    }

    try {
      JsonlReaderResult result = jsonlReader.read(filePath);
      String locator = candidate.fingerprint().locator();
      // 从候选元数据初始化模型，确保早期事件可使用发现阶段提取的模型
      String metaModel = candidate.metadata().get("model");
      String initialModel = metaModel == null || metaModel.isBlank() ? "" : metaModel;
      List<SourceDiagnostic> diagnostics = new ArrayList<>(result.diagnostics());
      List<JsonNode> events = result.events();
      List<SourceRecord> records = new ArrayList<>(events.size());
      Map<String, SourceRecordRelation> spawnRelations = spawnRelations(events);

      int candidateCount =
          appendParsedEvents(
              events,
              locator,
              initialModel,
              SourceRecordRelation.empty(),
              spawnRelations,
              diagnostics,
              records);

      Map<String, String> parentMeta = readFirstSessionMeta(filePath);
      if (!CodexDiscovery.isSubagentMetaEvent(parentMeta)) {
        String parentThreadId = parentThreadIdForParent(parentMeta, candidate.sessionKey());
        List<Path> childRollouts = childRolloutFiles(filePath, parentThreadId);
        for (Path childRollout : childRollouts) {
          Map<String, String> childMeta = readFirstSessionMeta(childRollout);
          String childId = childMeta.getOrDefault("id", "").trim();
          SourceRecordRelation parentRelation = spawnRelations.get(childId);
          if (parentRelation == null) {
            diagnostics.add(
                codexInfoDiagnostic(
                    "Subagent rollout has parent metadata but no visible spawn_agent output: "
                        + childId,
                    "SUBAGENT_SPAWN_UNMATCHED",
                    childRollout.toString()));
            continue;
          }
          JsonlReaderResult childResult = jsonlReader.read(childRollout);
          diagnostics.addAll(childResult.diagnostics());
          candidateCount +=
              appendParsedEvents(
                  childResult.events(),
                  childRollout.toAbsolutePath().toString(),
                  initialModel,
                  parentRelation,
                  spawnRelations(childResult.events()),
                  diagnostics,
                  records);
        }
      }

      return new SourceResult.Success(
          diagnostics, candidateCount, List.copyOf(records), candidate.fingerprint(), locator);
    } catch (IOException e) {
      String detail = "文件读取失败: " + filePath + " - " + e.getMessage();
      return new SourceResult.Fatal(List.of(), detail);
    }
  }

  private static int appendParsedEvents(
      List<JsonNode> events,
      String locator,
      String initialModel,
      SourceRecordRelation defaultRelation,
      Map<String, SourceRecordRelation> toolRelations,
      List<SourceDiagnostic> diagnostics,
      List<SourceRecord> records) {
    CodexParseState state = new CodexParseState();
    state.locator = locator;
    state.currentModel = initialModel == null ? "" : initialModel;
    boolean hasTokenUsage = events.stream().anyMatch(CodexSourceAdapter::hasCumulativeUsage);
    TokenTotals previousTotals = TokenTotals.zero();
    for (int eventIndex = 0; eventIndex < events.size(); eventIndex++) {
      JsonNode event = events.get(eventIndex);
      String rawEventType = extractEventType(event);
      String ts = extractTimestamp(event);
      collectEventDiagnostics(state, event, eventIndex, rawEventType, locator, diagnostics);
      updateCurrentModel(state, event);

      CodexRecordMapping mapped =
          mapCodexRecord(
              event, eventIndex, locator, state.currentModel, hasTokenUsage, previousTotals, ts);
      previousTotals = mapped.previousTotals();
      records.add(
          withRelation(mapped.record(), relationForEvent(event, defaultRelation, toolRelations)));
    }
    collectCompletionDiagnostics(state, diagnostics);
    return events.size();
  }

  private static SourceRecord withRelation(SourceRecord record, SourceRecordRelation relation) {
    return new SourceRecord(
        record.locator(),
        record.eventIndex(),
        record.eventType(),
        record.callId(),
        record.model(),
        record.timestamp(),
        record.turnId(),
        record.usage(),
        record.toolCalls(),
        record.toolUseId(),
        record.toolName(),
        record.toolError(),
        relation == null ? SourceRecordRelation.empty() : relation);
  }

  private static SourceRecordRelation relationForEvent(
      JsonNode event,
      SourceRecordRelation defaultRelation,
      Map<String, SourceRecordRelation> toolRelations) {
    String callId = responseItemCallId(event);
    if (!callId.isBlank()) {
      SourceRecordRelation relation = toolRelations.get(callId);
      if (relation != null) {
        return relation;
      }
    }
    return defaultRelation == null ? SourceRecordRelation.empty() : defaultRelation;
  }

  private static Map<String, SourceRecordRelation> spawnRelations(List<JsonNode> events) {
    Map<String, String> spawnCalls = new LinkedHashMap<>();
    for (JsonNode event : events) {
      JsonNode payload = event.path("payload");
      String payloadType = text(payload, "type");
      if (("function_call".equals(payloadType) || "custom_tool_call".equals(payloadType))
          && "spawn_agent".equals(text(payload, "name"))) {
        String callId = text(payload, "call_id");
        if (!callId.isBlank()) {
          spawnCalls.put(callId, "spawn_agent");
        }
      }
    }

    Map<String, SourceRecordRelation> relations = new LinkedHashMap<>();
    for (JsonNode event : events) {
      JsonNode payload = event.path("payload");
      String payloadType = text(payload, "type");
      if (!("function_call_output".equals(payloadType)
          || "custom_tool_call_output".equals(payloadType))) {
        continue;
      }
      String callId = text(payload, "call_id");
      if (!spawnCalls.containsKey(callId)) {
        continue;
      }
      Optional<SpawnAgentResult> spawnResult = parseSpawnAgentResult(payload.get("output"));
      if (spawnResult.isEmpty()) {
        continue;
      }
      SpawnAgentResult result = spawnResult.get();
      SourceRecordRelation relation =
          new SourceRecordRelation(
              Optional.of(result.agentId()),
              Optional.empty(),
              Optional.of(callId),
              Optional.empty(),
              Optional.of("spawn_agent"));
      relations.put(callId, relation);
      relations.put(result.agentId(), relation);
    }
    return Map.copyOf(relations);
  }

  private static Optional<SpawnAgentResult> parseSpawnAgentResult(JsonNode output) {
    if (output == null || output.isMissingNode() || output.isNull()) {
      return Optional.empty();
    }
    JsonNode resultNode = output;
    if (output.isTextual()) {
      try {
        resultNode = MAPPER.readTree(output.asText());
      } catch (IOException e) {
        return Optional.empty();
      }
    }
    if (!resultNode.isObject()) {
      return Optional.empty();
    }
    JsonNode agentId = resultNode.get("agent_id");
    if (agentId == null || !agentId.isTextual() || agentId.asText().isBlank()) {
      return Optional.empty();
    }
    JsonNode nickname = resultNode.get("nickname");
    return Optional.of(
        new SpawnAgentResult(
            agentId.asText().trim(),
            nickname != null && nickname.isTextual() ? nickname.asText().trim() : ""));
  }

  private static List<Path> childRolloutFiles(Path parentRollout, String parentThreadId) {
    if (parentRollout == null || parentThreadId == null || parentThreadId.isBlank()) {
      return List.of();
    }
    Path dir = parentRollout.getParent();
    if (dir == null || !Files.isDirectory(dir)) {
      return List.of();
    }
    List<Path> children = new ArrayList<>();
    try (var stream = Files.list(dir)) {
      for (Path candidate :
          stream
              .filter(Files::isRegularFile)
              .filter(path -> path.getFileName().toString().startsWith("rollout-"))
              .filter(path -> path.getFileName().toString().endsWith(".jsonl"))
              .sorted()
              .toList()) {
        if (candidate.equals(parentRollout)) {
          continue;
        }
        Map<String, String> meta = readFirstSessionMeta(candidate);
        if (parentThreadId.equals(parentThreadId(meta))) {
          children.add(candidate);
        }
      }
    } catch (IOException e) {
      LOG.log(Level.FINEST, "扫描 Codex child rollout 失败: " + dir, e);
    }
    return List.copyOf(children);
  }

  private static String parentThreadIdForParent(Map<String, String> parentMeta, String sessionKey) {
    String id = parentMeta.getOrDefault("id", "").trim();
    if (!id.isEmpty()) {
      return id;
    }
    return sessionKey.startsWith("codex:") ? sessionKey.substring("codex:".length()) : sessionKey;
  }

  private static String responseItemCallId(JsonNode event) {
    Optional<JsonNode> payloadNode = objectPayload(event);
    if (payloadNode.isEmpty()) {
      return "";
    }
    JsonNode payload = payloadNode.get();
    String rawType = extractEventType(event);
    String payloadType = text(payload, "type");
    if (!"response_item".equals(rawType)
        || !("function_call".equals(payloadType)
            || "custom_tool_call".equals(payloadType)
            || "function_call_output".equals(payloadType)
            || "custom_tool_call_output".equals(payloadType))) {
      return "";
    }
    return text(payload, "call_id");
  }

  private static void updateCurrentModel(CodexParseState state, JsonNode event) {
    String model = extractPayloadModel(event);
    if (!model.isBlank()) {
      state.currentModel = model;
    }
  }

  private static String extractPayloadModel(JsonNode event) {
    Optional<JsonNode> payloadNode = objectPayload(event);
    if (payloadNode.isEmpty()) {
      return "";
    }
    JsonNode payload = payloadNode.get();
    JsonNode model = payload.get("model");
    if (model != null && model.isTextual()) {
      return model.asText();
    }
    JsonNode collaborationMode = payload.get("collaboration_mode");
    if (collaborationMode != null && collaborationMode.isObject()) {
      JsonNode settings = collaborationMode.get("settings");
      if (settings != null && settings.isObject()) {
        JsonNode nestedModel = settings.get("model");
        if (nestedModel != null && nestedModel.isTextual()) {
          return nestedModel.asText();
        }
      }
    }
    return "";
  }

  /**
   * 从 JSON 事件节点提取顶层 {@code timestamp} 字段。
   *
   * @param event JSON 事件节点
   * @return 时间戳字符串，缺失时返回空字符串
   */
  private static String extractTimestamp(JsonNode event) {
    if (event == null || !event.isObject()) {
      return "";
    }
    JsonNode ts = event.get("timestamp");
    return ts != null && ts.isTextual() ? ts.asText() : "";
  }

  private static Optional<JsonNode> objectPayload(JsonNode event) {
    if (event == null || !event.isObject()) {
      return Optional.empty();
    }
    JsonNode payload = event.get("payload");
    return payload != null && payload.isObject() ? Optional.of(payload) : Optional.empty();
  }

  private static CodexRecordMapping mapCodexRecord(
      JsonNode event,
      int eventIndex,
      String locator,
      String currentModel,
      boolean hasTokenUsage,
      TokenTotals previousTotals,
      String timestamp) {
    String rawType = extractEventType(event);
    String recordLocator = locator + "#event[" + eventIndex + "]";
    JsonNode payload = event.get("payload");
    if (payload == null || !payload.isObject()) {
      return new CodexRecordMapping(
          basicRecord(recordLocator, eventIndex, rawType, timestamp), previousTotals);
    }

    String payloadType = text(payload, "type");
    if ("event_msg".equals(rawType)) {
      // 为 event_msg 事件编码语义子类型到 turnId
      Optional<String> subType = optionalText(payloadType);
      if ("token_count".equals(payloadType)) {
        if (hasCumulativeUsage(event)) {
          TokenTotals currentTotals = cumulativeTotals(event);
          if (currentTotals.sameAs(previousTotals)) {
            return new CodexRecordMapping(
                basicRecord(recordLocator, eventIndex, rawType, timestamp), currentTotals);
          }
          SourceRecordUsage delta = currentTotals.deltaSince(previousTotals);
          return new CodexRecordMapping(
              new SourceRecord(
                  recordLocator,
                  eventIndex,
                  "assistant",
                  Optional.of("token_count:" + eventIndex),
                  optionalText(currentModel),
                  optionalText(timestamp),
                  Optional.empty(),
                  delta,
                  List.of(),
                  Optional.empty(),
                  Optional.empty(),
                  Optional.empty()),
              currentTotals);
        }
        if (hasLastTokenUsage(event)) {
          return new CodexRecordMapping(
              new SourceRecord(
                  recordLocator,
                  eventIndex,
                  "assistant",
                  Optional.of("token_count:" + eventIndex),
                  optionalText(currentModel),
                  optionalText(timestamp),
                  Optional.empty(),
                  SourceRecordUsage.empty(),
                  List.of(),
                  Optional.empty(),
                  Optional.empty(),
                  Optional.empty()),
              previousTotals);
        }
        return new CodexRecordMapping(
            basicRecord(recordLocator, eventIndex, rawType, timestamp), previousTotals);
      }
      // 非 token_count 的 event_msg：传递 payload 子类型作为 turnId
      return new CodexRecordMapping(
          new SourceRecord(
              recordLocator,
              eventIndex,
              rawType,
              Optional.empty(),
              optionalText(currentModel),
              optionalText(timestamp),
              subType,
              SourceRecordUsage.empty(),
              List.of(),
              Optional.empty(),
              Optional.empty(),
              Optional.empty()),
          previousTotals);
    }

    if ("response_item".equals(rawType)) {
      return new CodexRecordMapping(
          mapResponseItem(
              recordLocator, eventIndex, payload, currentModel, hasTokenUsage, timestamp),
          previousTotals);
    }

    return new CodexRecordMapping(
        basicRecord(recordLocator, eventIndex, rawType, timestamp), previousTotals);
  }

  private static SourceRecord mapResponseItem(
      String recordLocator,
      int eventIndex,
      JsonNode payload,
      String currentModel,
      boolean hasTokenUsage,
      String timestamp) {
    String payloadType = text(payload, "type");
    if ("function_call".equals(payloadType) || "custom_tool_call".equals(payloadType)) {
      Optional<String> callId = optionalText(text(payload, "call_id"));
      Optional<String> name = optionalText(text(payload, "name"));
      List<SourceToolCall> toolCalls =
          callId.isPresent() && name.isPresent()
              ? List.of(new SourceToolCall(callId.get(), name.get()))
              : List.of();
      return new SourceRecord(
          recordLocator,
          eventIndex,
          "tool_use",
          callId,
          optionalText(currentModel),
          optionalText(timestamp),
          Optional.of(payloadType),
          SourceRecordUsage.empty(),
          toolCalls,
          Optional.empty(),
          name,
          Optional.empty());
    }
    if ("function_call_output".equals(payloadType)
        || "custom_tool_call_output".equals(payloadType)) {
      return new SourceRecord(
          recordLocator,
          eventIndex,
          "tool_result",
          Optional.empty(),
          optionalText(currentModel),
          optionalText(timestamp),
          Optional.of(payloadType),
          SourceRecordUsage.empty(),
          List.of(),
          optionalText(text(payload, "call_id")),
          Optional.empty(),
          extractCodexToolError(payload));
    }
    if ("message".equals(payloadType)) {
      String role = text(payload, "role");
      if ("user".equals(role)) {
        return new SourceRecord(
            recordLocator,
            eventIndex,
            "user",
            Optional.empty(),
            optionalText(currentModel),
            optionalText(timestamp),
            Optional.of("message"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
      }
      if ("assistant".equals(role) && !hasTokenUsage) {
        return new SourceRecord(
            recordLocator,
            eventIndex,
            "assistant",
            Optional.empty(),
            optionalText(currentModel),
            optionalText(timestamp),
            Optional.of("message"),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
      }
    }
    if ("reasoning".equals(payloadType) && !hasTokenUsage) {
      return new SourceRecord(
          recordLocator,
          eventIndex,
          "assistant",
          Optional.empty(),
          optionalText(currentModel),
          optionalText(timestamp),
          Optional.of("reasoning"),
          SourceRecordUsage.empty(),
          List.of(),
          Optional.empty(),
          Optional.empty(),
          Optional.empty());
    }
    return basicRecord(recordLocator, eventIndex, "response_item", timestamp);
  }

  private static SourceRecord basicRecord(
      String recordLocator, int eventIndex, String eventType, String timestamp) {
    return new SourceRecord(
        recordLocator,
        eventIndex,
        eventType,
        Optional.empty(),
        Optional.empty(),
        optionalText(timestamp),
        Optional.empty(),
        SourceRecordUsage.empty(),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty());
  }

  private static Optional<String> optionalText(String value) {
    return value == null || value.isBlank() ? Optional.empty() : Optional.of(value);
  }

  /**
   * 从 Codex function_call_output payload 提取工具错误信息。
   *
   * <p>先检查显式 {@code error} 字段，再通过 {@link ToolFailureClassifier} 对 {@code output} 内容进行文本启发式失败检测。
   *
   * @param payload response_item 的 payload 节点
   * @return 错误信息，非空表示工具执行失败
   */
  private static Optional<String> extractCodexToolError(JsonNode payload) {
    if (payload == null || !payload.isObject()) {
      return Optional.empty();
    }
    JsonNode error = payload.get("error");
    if (error != null && error.isTextual() && !error.asText().isBlank()) {
      return Optional.of(error.asText());
    }
    if (error != null && error.isObject()) {
      JsonNode message = error.get("message");
      if (message != null && message.isTextual() && !message.asText().isBlank()) {
        return Optional.of(message.asText());
      }
    }
    // 文本启发式：检查 output 内容是否包含运行时错误标记
    JsonNode output = payload.get("output");
    if (output != null) {
      String outputText = output.isTextual() ? output.asText() : output.toString();
      if (!outputText.isBlank() && ToolFailureClassifier.looksFailed(outputText, "")) {
        return Optional.of("text_heuristic_failure");
      }
    }
    return Optional.empty();
  }

  private static String text(JsonNode node, String fieldName) {
    if (node == null || !node.isObject()) {
      return "";
    }
    JsonNode child = node.get(fieldName);
    return child != null && child.isTextual() ? child.asText() : "";
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
    if (state.sessionMeta != null && CodexDiscovery.isSubagentMetaEvent(state.sessionMeta)) {
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

  /**
   * 表示 CodexRecordMapping 数据。
   *
   * @param record 原始记录对象。
   * @param previousTotals 上一条累计 token 值。
   */
  private record CodexRecordMapping(SourceRecord record, TokenTotals previousTotals) {}

  /**
   * 表示 spawn_agent 输出中的稳定归属字段。
   *
   * @param agentId Codex 子线程标识。
   * @param nickname 子线程展示昵称。
   */
  private record SpawnAgentResult(String agentId, String nickname) {}

  /**
   * 表示 TokenTotals 数据。
   *
   * @param freshInput 该字段在 API 响应中的业务值。
   * @param cacheRead cache read token 数量。
   * @param cacheWrite cache write token 数量。
   * @param output 该字段在 API 响应中的业务值。
   * @param rawTotal provider 原始 token 总数。
   */
  private record TokenTotals(
      long freshInput, long cacheRead, long cacheWrite, long output, long rawTotal) {
    private static TokenTotals zero() {
      return new TokenTotals(0, 0, 0, 0, 0);
    }

    private SourceRecordUsage deltaSince(TokenTotals previous) {
      return new SourceRecordUsage(
          Math.max(0L, freshInput - previous.freshInput),
          Math.max(0L, cacheRead - previous.cacheRead),
          Math.max(0L, cacheWrite - previous.cacheWrite),
          Math.max(0L, output - previous.output));
    }

    private boolean sameAs(TokenTotals previous) {
      return freshInput == previous.freshInput
          && cacheRead == previous.cacheRead
          && cacheWrite == previous.cacheWrite
          && output == previous.output
          && rawTotal == previous.rawTotal;
    }
  }

  /** Codex 单文件解析期间累计的 provider 特有诊断状态。 */
  private static final class CodexParseState {
    private Map<String, String> sessionMeta;
    private int toolCallCount;
    private int toolOutputCount;
    private int tokenCountEvents;
    private boolean hasCumulativeTokenUsage;
    private String currentModel = "";
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
    return Map.copyOf(CodexDiscovery.flattenPayloadFields(event));
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
    return cumulativeUsageNode(event) != null;
  }

  private static boolean hasLastTokenUsage(JsonNode event) {
    return lastTokenUsageNode(event) != null;
  }

  private static TokenTotals cumulativeTotals(JsonNode event) {
    JsonNode usage = cumulativeUsageNode(event);
    if (usage == null) {
      return TokenTotals.zero();
    }
    long inputTokens = readLong(usage, "input_tokens", "inputTokens", "prompt_tokens");
    long cacheRead =
        readLong(
            usage,
            "cached_input_tokens",
            "cache_read_input_tokens",
            "cacheReadInputTokens",
            "cached_tokens");
    long freshInput =
        usage.has("cached_input_tokens") && !usage.has("cache_read_input_tokens")
            ? Math.max(0L, inputTokens - cacheRead)
            : inputTokens;
    return new TokenTotals(
        freshInput,
        cacheRead,
        readLong(usage, "cache_creation_input_tokens", "cacheCreationInputTokens"),
        readLong(usage, "output_tokens", "outputTokens", "completion_tokens"),
        readLong(usage, "total_tokens", "total_token_usage", "tokens_used"));
  }

  private static JsonNode cumulativeUsageNode(JsonNode event) {
    JsonNode payload = event.get("payload");
    if (payload == null || !payload.isObject()) {
      return null;
    }
    // 检查 payload.info.total_token_usage
    JsonNode info = payload.get("info");
    if (info != null && info.isObject()) {
      JsonNode totalUsage = info.get("total_token_usage");
      if (totalUsage != null && totalUsage.isObject()) {
        return totalUsage;
      }
    }
    // 检查 payload.total_token_usage
    JsonNode directUsage = payload.get("total_token_usage");
    return directUsage != null && directUsage.isObject() ? directUsage : null;
  }

  private static JsonNode lastTokenUsageNode(JsonNode event) {
    JsonNode payload = event.get("payload");
    if (payload == null || !payload.isObject()) {
      return null;
    }
    JsonNode info = payload.get("info");
    if (info != null && info.isObject()) {
      JsonNode lastUsage = info.get("last_token_usage");
      if (lastUsage != null && lastUsage.isObject()) {
        return lastUsage;
      }
    }
    JsonNode directUsage = payload.get("last_token_usage");
    return directUsage != null && directUsage.isObject() ? directUsage : null;
  }

  private static long readLong(JsonNode node, String... fieldNames) {
    if (node == null || !node.isObject()) {
      return 0L;
    }
    for (String fieldName : fieldNames) {
      JsonNode child = node.get(fieldName);
      if (child != null && child.isNumber()) {
        return child.asLong();
      }
    }
    return 0L;
  }
}
