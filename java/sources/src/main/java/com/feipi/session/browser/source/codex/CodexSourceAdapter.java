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
import com.feipi.session.browser.source.json.JsonRecordTypes;
import com.feipi.session.browser.source.json.JsonSourceRecordMapper;
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
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;
import java.util.TreeMap;
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
  public RecordKind classifyRecord(String type, String role, String messageRole) {
    return JsonRecordTypes.classify(sourceId(), type, role, messageRole);
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
        Map<String, String> meta = buildCandidateMetadata(disc);
        String projectKey = meta.getOrDefault("cwd", "");
        Candidate candidate = new Candidate(fp, sessionKey, projectKey, meta);
        candidates.add(candidate);
      } catch (Exception e) {
        LOG.log(Level.FINE, "Codex 候选构建失败: " + disc.sessionId(), e);
        throw new IllegalStateException(
            "Codex 候选构建失败 (" + e.getClass().getSimpleName() + "): " + disc.sessionId(), e);
      }
    }

    Comparator<Candidate> bySessionKey = Comparator.comparing(Candidate::sessionKey);
    return BoundedStream.of(
        candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.of(bySessionKey));
  }

  /** 源数据库时间按纪元秒解析；索引时间按标准时间文本解析。 */
  private static Optional<String> sourceTimestamp(String value) {
    if (value == null || value.isBlank()) {
      return Optional.empty();
    }
    try {
      return Optional.of(java.time.Instant.ofEpochSecond(Long.parseLong(value)).toString());
    } catch (NumberFormatException ignored) {
      try {
        return Optional.of(java.time.Instant.parse(value).toString());
      } catch (java.time.DateTimeException invalid) {
        return Optional.empty();
      }
    } catch (java.time.DateTimeException invalid) {
      return Optional.empty();
    }
  }

  /** 从发现结果构建 Candidate 元数据。 */
  private static Map<String, String> buildCandidateMetadata(
      CodexDiscovery.CodexSessionDiscovery disc) {
    Map<String, String> meta = new java.util.HashMap<>();
    meta.put("has_transcript", String.valueOf(disc.hasFile()));
    for (Map<String, String> source :
        java.util.stream.Stream.of(disc.threadInfo(), disc.indexEntry())
            .filter(Objects::nonNull)
            .toList()) {
      for (String field : List.of("cwd", "git_branch", "model")) {
        String value = source.getOrDefault(field, "");
        if (!value.isBlank()) {
          meta.putIfAbsent(field, value);
        }
      }
      sourceTimestamp(source.get("created_at"))
          .ifPresent(value -> meta.putIfAbsent("started_at", value));
      sourceTimestamp(source.get("updated_at"))
          .ifPresent(value -> meta.putIfAbsent("ended_at", value));
    }

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
    meta.putAll(tokenProvenance(disc));
    return Map.copyOf(meta);
  }

  private static Map<String, String> tokenProvenance(CodexDiscovery.CodexSessionDiscovery disc) {
    CodexTokenProvenance provenance = new CodexTokenProvenance();
    if (!disc.hasFile()) {
      provenance.addUnknown();
      return provenance.metadata();
    }
    try {
      var result = CodexMetadataProjection.read(new JsonlReader(), disc.rolloutPath());
      var range = CodexActivityRange.create(result.events(), result.diagnostics());
      appendTokenProvenance(range, provenance);
      Map<String, String> parentMeta = readFirstSessionMeta(disc.rolloutPath());
      List<Path> children =
          childRolloutFiles(
              disc.rolloutPath(), parentThreadIdForParent(parentMeta, "codex:" + disc.sessionId()));
      Map<String, SourceRecordRelation> relations =
          spawnRelations(
              range.events(), children, new ArrayList<>(), disc.rolloutPath().toString());
      for (Path child : children) {
        String id = readFirstSessionMeta(child).getOrDefault("id", "").trim();
        if (relations.containsKey(id)) {
          var childResult = CodexMetadataProjection.read(new JsonlReader(), child);
          try {
            appendTokenProvenance(
                CodexActivityRange.create(childResult.events(), childResult.diagnostics()),
                provenance);
          } catch (CodexActivityRange.InvalidHistoryException e) {
            if (!CodexActivityRange.PARENT_CONFLICT.equals(e.code())) throw e;
            provenance.addUnknown();
          }
        }
      }
    } catch (IOException e) {
      provenance.addUnknown();
      LOG.fine("读取 Codex usage provenance 失败");
    }
    return provenance.metadata();
  }

  private static void appendTokenProvenance(
      CodexActivityRange range, CodexTokenProvenance provenance) {
    List<JsonNode> events = range.events();
    CodexUsageSelection selection = new CodexUsageSelection(range);
    selection.usageIndices.forEach(
        index ->
            provenance.addProvenance(
                hasResponseUsage(events.get(index))
                    ? CodexTokenProvenance.forUsage(
                        events.get(index).path("payload").path("usage"), true)
                    : selection.legacyDeltas.get(index).provenance()));
    if (!selection.ambiguousEvents.isEmpty() || selection.usageIndices.isEmpty()) {
      provenance.addUnknown();
    }
  }

  /** 复用同文件现代/历史 usage 归属裁定，不执行 child rollout 发现。 */
  @Override
  public Map<String, String> singleFileMetadata(Path filePath) throws IOException {
    CodexTokenProvenance provenance = new CodexTokenProvenance();
    try (var batch = CodexEventBatch.read(new JsonlReader(), filePath)) {
      appendTokenProvenance(
          CodexActivityRange.create(batch.events(), batch.result().diagnostics()), provenance);
    }
    return provenance.metadata();
  }

  private static boolean isTokenCount(JsonNode event) {
    return "event_msg".equals(extractEventType(event))
        && "token_count".equals(extractEventMsgType(event));
  }

  /** 在原始事件身份和完整线程累计锚点上选择 usage，不把数值残差猜成现代响应。 */
  private static final class CodexUsageSelection {
    private final Map<Integer, TokenTotals> modernEvents = new LinkedHashMap<>();
    private final Map<Integer, SourceRecordUsage> legacyDeltas = new LinkedHashMap<>();
    private final Set<Integer> usageIndices = new java.util.LinkedHashSet<>();
    private final Set<Integer> ambiguousEvents = new java.util.LinkedHashSet<>();
    private final Set<Integer> resetEvents = new java.util.LinkedHashSet<>();
    private final Set<String> modernTurns = new HashSet<>();
    private final NavigableMap<Integer, TokenTotals> anchors = new TreeMap<>();
    private final Map<TokenTotals, Set<String>> mirrorTurns = new LinkedHashMap<>();
    private TokenTotals baseline = TokenTotals.zero();
    private boolean anchored;
    private boolean completeCounterCoverage = true;
    private TokenTotals legacyBaseline;
    private boolean legacyCovered;
    private int lastLegacyIndex = -1;
    private int latestModernIndex = -1;
    private TokenTotals latestModernUsage = TokenTotals.zero();

    private CodexUsageSelection(CodexActivityRange range) {
      List<JsonNode> events = range.events();
      Set<String> responseIds = new HashSet<>();
      for (int index = range.start(); index < events.size(); index++) {
        JsonNode event = events.get(index);
        if (hasResponseUsage(event)) {
          String responseId = text(event.path("payload"), "response_id");
          if (responseId.isBlank() || responseIds.add(responseId)) {
            modernEvents.put(index, usageTotals(event.path("payload").path("usage"), true));
            String turn = text(event.path("payload"), "turn_id");
            modernTurns.add(turn);
            usageIndices.add(index);
            TokenTotals total = threadTotals(event);
            if (total != null) {
              anchors.put(index, total);
              mirrorTurns.computeIfAbsent(total.components(), ignored -> new HashSet<>()).add(turn);
            }
          }
        } else if (range.inheritedUsage()
            && isTokenCount(event)
            && (hasCumulativeUsage(event) || hasLastTokenUsage(event))) {
          ambiguousEvents.add(index);
        }
      }
      // 继承区有计量证据时，不知道新旧累计计数器是否相接；只保留新活动的显式响应 usage。
      if (range.inheritedUsage()) return;
      if (!modernEvents.isEmpty()) {
        selectLegacyEvents(events);
      } else {
        selectLegacyOnly(events);
      }
    }

    private Map<String, String> baselineProvenance = CodexTokenProvenance.reportedZero();

    private void selectLegacyOnly(List<JsonNode> events) {
      TokenTotals previous = TokenTotals.zero();
      boolean ambiguous = false;
      for (int index = 0; index < events.size(); index++) {
        JsonNode event = events.get(index);
        if (!isTokenCount(event)) continue;
        JsonNode usage = cumulativeUsageNode(event);
        if (usage == null) {
          if (hasLastTokenUsage(event)) ambiguousEvents.add(index);
          continue;
        }
        TokenTotals current = cumulativeTotals(event);
        if (!current.covers(previous)) {
          if (!ambiguous) resetEvents.add(index);
          ambiguous = true;
        }
        if (ambiguous) {
          ambiguousEvents.add(index);
          continue;
        }
        if (!current.sameAs(previous) || usageIndices.isEmpty()) {
          Map<String, String> precision = CodexTokenProvenance.forUsage(usage, false);
          legacyDeltas.put(
              index,
              withUsageProvenance(
                  current.deltaSince(previous),
                  CodexTokenProvenance.deltaProvenance(precision, baselineProvenance)));
          usageIndices.add(index);
          baselineProvenance = precision;
        }
        previous = current;
      }
    }

    private void selectLegacyEvents(List<JsonNode> events) {
      String turn = "";
      for (int index = 0; index < events.size(); index++) {
        JsonNode event = events.get(index);
        if ("turn_context".equals(extractEventType(event))
            || ("event_msg".equals(extractEventType(event))
                && "task_started".equals(extractEventMsgType(event)))) {
          turn = text(event.path("payload"), "turn_id");
        }
        if (modernEvents.containsKey(index)) {
          advanceModern(index, event);
        } else if (isTokenCount(event)) {
          selectLegacy(index, event, turn);
        }
      }
    }

    private void advanceModern(int index, JsonNode event) {
      TokenTotals total = anchors.get(index);
      TokenTotals usage = usageTotals(event.path("payload").path("usage"), true);
      baselineProvenance =
          total != null
              ? CodexTokenProvenance.forUsage(
                  event.path("payload").path("thread_token_usage"), true)
              : CodexTokenProvenance.deltaProvenance(
                  CodexTokenProvenance.forUsage(event.path("payload").path("usage"), true),
                  baselineProvenance);
      latestModernIndex = index;
      latestModernUsage = usage;
      if (total != null) {
        boolean startsCounter = total.sameComponents(usage);
        completeCounterCoverage =
            startsCounter
                || (completeCounterCoverage && total.sameComponents(baseline.plus(usage)));
        if (!total.covers(baseline)) {
          resetEvents.add(index);
          if (!startsCounter) {
            ambiguousEvents.add(index);
          }
        }
        if (!completeCounterCoverage && ambiguousEvents.isEmpty()) {
          ambiguousEvents.add(index);
        }
        baseline = total;
        anchored = true;
      } else {
        baseline = baseline.plus(usage);
        anchored = false;
      }
    }

    private void selectLegacy(int index, JsonNode event, String turn) {
      JsonNode usage = cumulativeUsageNode(event);
      if (usage == null) {
        if (hasLastTokenUsage(event)) {
          ambiguousEvents.add(index);
        }
        return;
      }
      TokenTotals total = legacyTotals(usage);
      if (total.sameComponents(baseline)
          || isMirror(total, turn)
          || isIncrementalMirror(total, event)) {
        rememberLegacy(index, total, true);
        return;
      }
      if (!total.covers(baseline) || !ownsLegacyDelta(index, event, total, turn)) {
        ambiguousEvents.add(index);
        rememberLegacy(index, total, false);
        return;
      }
      legacyDeltas.put(
          index,
          withUsageProvenance(
              total.deltaSince(baseline),
              CodexTokenProvenance.deltaProvenance(legacyPrecision(usage), baselineProvenance)));
      baselineProvenance = legacyPrecision(usage);
      usageIndices.add(index);
      baseline = total;
      rememberLegacy(index, total, true);
    }

    private boolean isIncrementalMirror(TokenTotals total, JsonNode event) {
      if (!legacyCovered || legacyBaseline == null) {
        return false;
      }
      if (total.sameComponents(legacyBaseline)) {
        return true;
      }
      JsonNode last = lastTokenUsageNode(event);
      // legacy counter 可以漏过一个响应后永久落后，但相邻增量与完整 last usage 必须仍对应新现代响应。
      return anchored
          && completeCounterCoverage
          && latestModernIndex > lastLegacyIndex
          && baseline.covers(total)
          && total.covers(legacyBaseline)
          && last != null
          && CodexTokenProvenance.hasCompleteUsage(last, legacyIncludesCache(last))
          && legacyTotals(last).sameComponents(latestModernUsage)
          && total.minus(legacyBaseline).sameComponents(latestModernUsage);
    }

    private void rememberLegacy(int index, TokenTotals total, boolean covered) {
      legacyBaseline = total;
      legacyCovered = covered;
      lastLegacyIndex = index;
    }

    private boolean isMirror(TokenTotals total, String turn) {
      Set<String> owners = mirrorTurns.getOrDefault(total.components(), Set.of());
      return owners.contains(turn) || (turn.isEmpty() && !owners.isEmpty());
    }

    private boolean ownsLegacyDelta(int index, JsonNode event, TokenTotals total, String turn) {
      Map.Entry<Integer, TokenTotals> next = anchors.higherEntry(index);
      if (next != null) {
        TokenTotals before = next.getValue().minus(modernEvents.get(next.getKey()));
        return before.covers(total) && before.covers(baseline);
      }
      if (!turn.isBlank() && !modernTurns.contains("") && !modernTurns.contains(turn)) {
        return true;
      }
      JsonNode last = lastTokenUsageNode(event);
      return anchored && last != null && legacyTotals(last).sameComponents(total.minus(baseline));
    }

    private static boolean legacyIncludesCache(JsonNode usage) {
      return usage.has("cached_input_tokens") && !usage.has("cache_read_input_tokens");
    }

    private static Map<String, String> legacyPrecision(JsonNode usage) {
      return CodexTokenProvenance.forUsage(usage, legacyIncludesCache(usage));
    }

    private static TokenTotals legacyTotals(JsonNode usage) {
      return usageTotals(usage, legacyIncludesCache(usage));
    }

    private static TokenTotals threadTotals(JsonNode event) {
      JsonNode payload = event.path("payload");
      JsonNode thread = payload.path("thread_token_usage");
      JsonNode usage = payload.path("usage");
      if (!CodexTokenProvenance.hasCompleteUsage(thread, true)
          || !CodexTokenProvenance.hasCompleteUsage(usage, true)) {
        return null;
      }
      TokenTotals total = usageTotals(thread, true);
      return total.covers(usageTotals(usage, true)) ? total : null;
    }
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
    return subagentMetaField(meta, "parent_thread_id");
  }

  private static String subagentMetaField(Map<String, String> meta, String field) {
    if (meta == null || meta.isEmpty()) {
      return "";
    }
    String value = meta.getOrDefault(field, "").trim();
    if (!value.isEmpty()) {
      return value;
    }
    String source = meta.getOrDefault("source", "");
    if (source.isBlank()) {
      return "";
    }
    try {
      JsonNode sourceNode = MAPPER.readTree(source);
      JsonNode spawn = sourceNode.path("subagent").path("thread_spawn");
      return text(spawn, field).trim();
    } catch (IOException e) {
      return "";
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

    List<SourceDiagnostic> diagnostics = new ArrayList<>();
    try (var owner = new CodexRecordOwner()) {
      String locator = candidate.fingerprint().locator();
      int candidateCount;
      try (var batch = CodexEventBatch.read(jsonlReader, filePath)) {
        JsonlReaderResult result = batch.result();
        // 从候选元数据初始化模型，确保早期事件可使用发现阶段提取的模型
        String metaModel = candidate.metadata().get("model");
        String initialModel = metaModel == null || metaModel.isBlank() ? "" : metaModel;
        diagnostics.addAll(result.diagnostics());
        var range = CodexActivityRange.create(batch.events(), result.diagnostics());
        List<JsonNode> events = range.events();
        Map<String, String> parentMeta = readFirstSessionMeta(filePath);
        List<Path> childRollouts =
            CodexDiscovery.isSubagentMetaEvent(parentMeta)
                ? List.of()
                : childRolloutFiles(
                    filePath, parentThreadIdForParent(parentMeta, candidate.sessionKey()));
        Map<String, SourceRecordRelation> spawnRelations =
            spawnRelations(events, childRollouts, diagnostics, locator);

        candidateCount =
            appendParsedEvents(
                range,
                new CodexParseState(locator, range.initialModel(initialModel), cancellation),
                SourceRecordRelation.empty(),
                spawnRelations,
                diagnostics,
                owner.spool);
        // 每个事件写入批次 spool 前已投影；正文和身份逐条重放，非文本原文按 locator 读取。

        if (!childRollouts.isEmpty()) {
          for (Path childRollout : childRollouts) {
            Map<String, String> childMeta = readFirstSessionMeta(childRollout);
            String childId = childMeta.getOrDefault("id", "").trim();
            SourceRecordRelation parentRelation = spawnRelations.get(childId);
            if (parentRelation == null) {
              diagnostics.add(
                  codexInfoDiagnostic(
                      "Subagent rollout has parent metadata but no unambiguous spawn_agent output: "
                          + childId,
                      "SUBAGENT_SPAWN_UNMATCHED",
                      childRollout.toString()));
              continue;
            }
            try (var childBatch = CodexEventBatch.read(jsonlReader, childRollout)) {
              JsonlReaderResult childResult = childBatch.result();
              diagnostics.addAll(childResult.diagnostics());
              var childRange =
                  CodexActivityRange.create(childBatch.events(), childResult.diagnostics());
              candidateCount +=
                  appendParsedEvents(
                      childRange,
                      new CodexParseState(
                          childRollout.toAbsolutePath().toString(),
                          childRange.initialModel(initialModel),
                          cancellation),
                      parentRelation,
                      spawnRelations(
                          childRange.events(), List.of(), diagnostics, childRollout.toString()),
                      diagnostics,
                      owner.spool);
            } catch (CodexActivityRange.InvalidHistoryException e) {
              if (!CodexActivityRange.PARENT_CONFLICT.equals(e.code())) throw e;
              diagnostics.add(
                  new SourceDiagnostic(
                      ParseSeverity.WARNING,
                      ParseIssueType.NON_OBJECT_SKIPPED,
                      "Conflicting Codex child rollout omitted: " + e.getMessage(),
                      1,
                      Optional.empty(),
                      e.code(),
                      childRollout.toString(),
                      OptionalInt.empty(),
                      OptionalInt.empty(),
                      OptionalInt.empty()));
              LOG.log(
                  Level.WARNING,
                  "Codex 子会话已跳过，父会话继续扫描。source=codex phase=PARSE code={0}",
                  e.getMessage());
            }
          }
        }
      }
      return owner.finish(boundedDiagnostics(diagnostics), candidateCount, candidate);
    } catch (CancelledMapping e) {
      return new SourceResult.Skipped(List.of(), "解析已取消");
    } catch (CodexActivityRange.InvalidHistoryException e) {
      return new SourceResult.Fatal(boundedDiagnostics(diagnostics), e.getMessage(), e.code());
    } catch (java.io.UncheckedIOException e) {
      return SourceResult.Fatal.ioFailure("SOURCE_TEMP_IO_FAILED", e);
    } catch (IOException e) {
      return SourceResult.Fatal.ioFailure("SOURCE_IO_FAILED", e);
    }
  }

  /** 仅在超限时合并重复的非错误诊断；真正的解析错误始终优先保留。 */
  private static List<SourceDiagnostic> boundedDiagnostics(List<SourceDiagnostic> diagnostics) {
    if (diagnostics.size() <= SourceResult.MAX_DIAGNOSTICS) return diagnostics;
    int detailLimit = SourceResult.MAX_DIAGNOSTICS - 1;
    List<SourceDiagnostic> retained = new ArrayList<>();
    for (var severity : List.of(ParseSeverity.ERROR, ParseSeverity.WARNING, ParseSeverity.INFO)) {
      Set<String> seenCodes = new HashSet<>();
      for (var diagnostic : diagnostics) {
        if (retained.size() == detailLimit) break;
        if (diagnostic.severity() == severity
            && (severity == ParseSeverity.ERROR || seenCodes.add(diagnostic.code()))) {
          retained.add(diagnostic);
        }
      }
    }
    retained.add(
        codexInfoDiagnostic(
            "Additional Codex diagnostics omitted: " + (diagnostics.size() - retained.size()),
            "CODEX_DIAGNOSTICS_TRUNCATED",
            ""));
    return retained;
  }

  /** 最终 spool 仅在 managed 工厂成功后转移所有权，小表示同时受数量和全部载荷预算约束。 */
  private static final class CodexRecordOwner implements AutoCloseable {
    private final CodexRecordSpool spool;
    private boolean transferred;

    private CodexRecordOwner() throws IOException {
      spool = new CodexRecordSpool();
    }

    private SourceResult.Success finish(
        List<SourceDiagnostic> diagnostics, int count, Candidate candidate) throws IOException {
      spool.seal();
      if (spool.recordCount() <= 1024 && spool.payloadBytes() <= 2L * 1024 * 1024) {
        List<SourceRecord> records = new ArrayList<>();
        try (var cursor = spool.openCursor()) {
          while (cursor.hasNext()) records.add(cursor.next());
        }
        return new SourceResult.Success(
            diagnostics,
            count,
            records,
            candidate.fingerprint(),
            candidate.fingerprint().locator());
      }
      var success =
          SourceResult.Success.managed(
              diagnostics,
              count,
              spool,
              candidate.fingerprint(),
              candidate.fingerprint().locator());
      transferred = true;
      return success;
    }

    @Override
    public void close() throws IOException {
      if (!transferred) spool.close();
    }
  }

  /** 取消不发布部分成功，外层 finally 仍清理所有中间文件。 */
  private static final class CancelledMapping extends IOException {
    private static final long serialVersionUID = 1L;
  }

  private static int appendParsedEvents(
      CodexActivityRange range,
      CodexParseState state,
      SourceRecordRelation defaultRelation,
      Map<String, SourceRecordRelation> toolRelations,
      List<SourceDiagnostic> diagnostics,
      CodexRecordSpool records)
      throws IOException {
    try (var rawRecords = new CodexRecordSpool()) {
      List<JsonNode> events = range.events();
      String locator = state.locator;
      CancellationSignal cancellation = state.cancellation;
      CodexUsageSelection selection = new CodexUsageSelection(range);
      boolean hasResponseUsage = !selection.modernEvents.isEmpty();
      boolean hasTokenUsage =
          hasResponseUsage || events.stream().anyMatch(CodexSourceAdapter::hasCumulativeUsage);
      Set<String> responseIds = new HashSet<>();
      TokenTotals previousTotals = TokenTotals.zero();
      for (int eventIndex = range.start(); eventIndex < events.size(); eventIndex++) {
        if (cancellation != null && cancellation.isCancelled()) throw new CancelledMapping();
        JsonNode event = events.get(eventIndex);
        String rawEventType = extractEventType(event);
        String ts = extractTimestamp(event);
        collectEventDiagnostics(state, event, eventIndex, rawEventType, locator, diagnostics);
        updateCurrentModel(state, event);

        CodexRecordMapping mapped;
        if (hasResponseUsage(event)) {
          mapped =
              new CodexRecordMapping(
                  mapResponseUsage(event, eventIndex, locator, state.currentModel, responseIds),
                  previousTotals);
        } else if (isTokenCount(event)) {
          SourceRecordUsage legacy = selection.legacyDeltas.get(eventIndex);
          mapped =
              new CodexRecordMapping(
                  legacy == null || legacy.total() == 0
                      ? neutralUsageRecord(
                          locator + "#event[" + eventIndex + "]",
                          eventIndex,
                          rawEventType,
                          ts,
                          state.currentModel,
                          legacy == null
                              ? withUsageProvenance(
                                  SourceRecordUsage.empty(), new CodexTokenProvenance().metadata())
                              : legacy)
                      : new SourceRecord(
                          locator + "#event[" + eventIndex + "]",
                          eventIndex,
                          "assistant",
                          Optional.of("token_count:" + eventIndex),
                          optionalText(state.currentModel),
                          optionalText(ts),
                          Optional.empty(),
                          legacy,
                          List.of(),
                          Optional.empty(),
                          Optional.empty(),
                          Optional.empty()),
                  previousTotals);
        } else {
          mapped =
              mapCodexRecord(
                  event,
                  eventIndex,
                  locator,
                  state.currentModel,
                  hasTokenUsage,
                  previousTotals,
                  ts);
        }
        previousTotals = mapped.previousTotals();
        rawRecords.add(
            withRelation(mapped.record(), relationForEvent(event, defaultRelation, toolRelations)));
        // 工具正文/输入已由 SourceRecord 持有；后备与 usage 分段不再读取这些中间树。
        // 就地释放也覆盖 result.events() 的别名，不改变物理顺序、身份或原始来源。
        if (event.path("payload")
            instanceof com.fasterxml.jackson.databind.node.ObjectNode payload) {
          if ("tool_result".equals(mapped.record().eventType())) {
            payload.remove("output");
          } else if ("tool_use".equals(mapped.record().eventType())
              && !mapped.record().toolCalls().isEmpty()) {
            payload.remove(
                "function_call".equals(payload.path("type").asText()) ? "arguments" : "input");
          }
        }
      }
      selection.ambiguousEvents.forEach(
          index ->
              diagnostics.add(
                  codexInfoDiagnostic(
                      "Usage ownership cannot be established at event[" + index + "]",
                      "TOKEN_USAGE_AMBIGUOUS",
                      locator)));
      selection.resetEvents.forEach(
          index ->
              diagnostics.add(
                  codexInfoDiagnostic(
                      (selection.modernEvents.isEmpty()
                              ? "Legacy cumulative counter decreased; ownership is unknown at"
                                  + " event["
                              : "Modern cumulative counter decreased or restarted at event[")
                          + index
                          + "]",
                      "TOKEN_COUNTER_RESET",
                      locator)));
      rawRecords.seal();
      appendEventMessageFallbacks(events, rawRecords, records, cancellation, selection);
      collectCompletionDiagnostics(state, diagnostics);
      return events.size();
    }
  }

  /**
   * 仅在当前物理 rollout 缺少权威 assistant message 时补正文表示。
   *
   * <p>保留原 event_msg 供消息计数；后备记录复用原 locator/index，不是新增源事件。 candidateCount 仍计原事件，normalized
   * eventCount 则包含后备表示。按显式输入/任务边界检查已有调用帧，仅向本段补 response_item 文本； 本段没有调用帧时才创建零 usage 的 assistant
   * 表示，不从别的轮次借用 usage 或伪造 turnId。
   */
  private static void appendEventMessageFallbacks(
      List<JsonNode> events,
      CodexRecordSpool rawRecords,
      CodexRecordSpool records,
      CancellationSignal cancellation,
      CodexUsageSelection selection)
      throws IOException {
    Set<Integer> mirroredEvents = completeMessageMirrors(events);
    List<SourceRecord> fileRecords =
        new java.util.AbstractList<>() {
          @Override
          public int size() {
            return rawRecords.size();
          }

          @Override
          public SourceRecord get(int ordinal) {
            SourceRecord record = rawRecords.get(ordinal);
            return mirroredEvents.contains(record.eventIndex())
                ? withRelation(
                    basicRecord(
                        record.locator(),
                        record.eventIndex(),
                        "event_msg",
                        record.timestamp().orElse("")),
                    record.relation())
                : record;
          }
        };
    int[] segments = messageSegments(events, fileRecords);
    boolean[] framedSegments = framedMessageSegments(fileRecords, segments);
    Map<Integer, SourceRecordUsage> zeroFrames =
        responseFrames(events, fileRecords, segments, framedSegments, selection);
    Set<Integer> zeroSegments = new HashSet<>();
    zeroFrames.keySet().forEach(index -> zeroSegments.add(segments[index]));
    for (int index = 0; index < framedSegments.length; index++) {
      framedSegments[index] |= zeroSegments.contains(segments[index]);
    }
    boolean[] authoritativeUsers = responseMessageSegments(events, fileRecords, segments, "user");
    boolean[] authoritativeAssistants =
        responseMessageSegments(events, fileRecords, segments, "assistant");
    for (int index = 0; index < fileRecords.size(); index++) {
      if (cancellation != null && cancellation.isCancelled()) throw new CancelledMapping();
      SourceRecord record = fileRecords.get(index);
      if (zeroFrames.containsKey(index)) {
        record = responseFrame(record, zeroFrames.get(index));
      }
      records.add(record);
      if (!"event_msg".equals(record.eventType())) {
        continue;
      }
      String subtype = record.turnId().orElse("");
      boolean user = "user_message".equals(subtype);
      if ((user && authoritativeUsers[index])
          || (!user && (!"agent_message".equals(subtype) || authoritativeAssistants[index]))) {
        continue;
      }
      String content = eventMessageContent(events.get(record.eventIndex()));
      if (content.isBlank()) {
        continue;
      }
      String type =
          user
              ? "user"
              : framedSegments[index] ? CodexConstants.EVENT_TYPE_RESPONSE_ITEM : "assistant";
      records.add(
          new SourceRecord(
              record.locator(),
              record.eventIndex(),
              type,
              Optional.empty(),
              record.model(),
              record.timestamp(),
              Optional.empty(),
              SourceRecordUsage.empty(),
              List.of(),
              Optional.empty(),
              Optional.empty(),
              Optional.empty(),
              record.relation(),
              content));
    }
  }

  /** 调用依据独立于计量归属：正文可证调用，工具声明另需 closing counter。 */
  private static Map<Integer, SourceRecordUsage> responseFrames(
      List<JsonNode> events,
      List<SourceRecord> records,
      int[] segments,
      boolean[] framed,
      CodexUsageSelection selection) {
    Map<Integer, Integer> bodies = new LinkedHashMap<>();
    Set<Integer> outputs = new HashSet<>();
    Set<Integer> planned = new HashSet<>();
    Map<Integer, SourceRecordUsage> frames = new LinkedHashMap<>();
    SourceRecordUsage unknown =
        withUsageProvenance(SourceRecordUsage.empty(), new CodexTokenProvenance().metadata());
    for (int index = 0; index < records.size(); index++) {
      SourceRecord record = records.get(index);
      int segment = segments[index];
      JsonNode event = events.get(record.eventIndex());
      if ("assistant".equals(record.messageRole().orElse("")) && !record.content().isBlank()) {
        bodies.putIfAbsent(segment, index);
        outputs.add(segment);
      } else if ("tool_use".equals(record.eventType()) && !record.toolCalls().isEmpty()) {
        outputs.add(segment);
      } else if (isEventMessage(event, "agent_message")
          && record.turnId().filter("agent_message"::equals).isPresent()
          && !eventMessageContent(event).isBlank()) {
        outputs.add(segment);
      }
      if (framed[index]
          || planned.contains(segment)
          || !outputs.contains(segment)
          || !isTokenCount(event)
          || cumulativeUsageNode(event) == null
          || !cumulativeTotals(event).sameAs(TokenTotals.zero())
          || selection.ambiguousEvents.contains(record.eventIndex())) {
        continue;
      }
      SourceRecordUsage selected = selection.legacyDeltas.get(record.eventIndex());
      // 被选择的 closing 保留原分量精度；重复累计值只能证明输出存在，不能背书实测零。
      frames.put(index, selected == null ? unknown : selected);
      planned.add(segment);
    }
    for (var body : bodies.entrySet()) {
      int index = body.getValue();
      if (!framed[index]
          && !planned.contains(body.getKey())
          && CodexConstants.EVENT_TYPE_RESPONSE_ITEM.equals(records.get(index).eventType())) {
        frames.put(index, unknown);
      }
    }
    return frames;
  }

  private static SourceRecord responseFrame(SourceRecord record, SourceRecordUsage usage) {
    return new SourceRecord(
        record.locator(),
        record.eventIndex(),
        "assistant",
        Optional.of(
            (CodexConstants.EVENT_TYPE_RESPONSE_ITEM.equals(record.eventType())
                    ? "unmetered_response:"
                    : "token_count:")
                + record.eventIndex()),
        record.model(),
        record.timestamp(),
        record.turnId(),
        usage,
        record.toolCalls(),
        record.toolUseId(),
        record.toolName(),
        record.toolError(),
        record.relation(),
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing(),
        record.metaContext(),
        record.messageRole());
  }

  /** 仅把连续完整、且源身份精确相同的问答表示视为镜像。 */
  private static Set<Integer> completeMessageMirrors(List<JsonNode> events) {
    Set<Integer> mirrors = new HashSet<>();
    for (int index = 0; index + 3 < events.size(); index++) {
      int[] roles = {-1, -1, -1, -1};
      boolean complete = true;
      for (int offset = 0; offset < 4; offset++) {
        JsonNode event = events.get(index + offset);
        int slot;
        if (isEventMessage(event, "user_message")) {
          slot = 0;
        } else if (isEventMessage(event, "agent_message")) {
          slot = 1;
        } else if (isResponseMessage(event, "user")) {
          slot = 2;
        } else if (isResponseMessage(event, "assistant")) {
          slot = 3;
        } else {
          complete = false;
          break;
        }
        if (roles[slot] >= 0) {
          complete = false;
          break;
        }
        roles[slot] = index + offset;
      }
      if (!complete || roles[0] >= roles[1] || roles[2] >= roles[3]) {
        continue;
      }
      if (sameMessageIdentity(events, roles[0], roles[1], roles[2], roles[3])) {
        mirrors.add(roles[0]);
        mirrors.add(roles[1]);
        index += 3;
      }
    }
    return mirrors;
  }

  private static boolean isEventMessage(JsonNode event, String subtype) {
    return "event_msg".equals(extractEventType(event))
        && subtype.equals(text(event.path("payload"), "type"));
  }

  private static String messageTurnId(JsonNode event) {
    String payloadId = text(event.path("payload"), "turn_id");
    return payloadId.isBlank() ? text(event, "turn_id") : payloadId;
  }

  private static boolean sameMessageIdentity(
      List<JsonNode> events,
      int eventUser,
      int eventAssistant,
      int responseUser,
      int responseAssistant) {
    Set<String> turnIds = new HashSet<>();
    boolean timestampsMatch = true;
    for (int offset = 0; offset < 2; offset++) {
      JsonNode event = events.get(offset == 0 ? eventUser : eventAssistant);
      JsonNode response = events.get(offset == 0 ? responseUser : responseAssistant);
      String content = eventMessageContent(event);
      if (content.isBlank()
          || !content.equals(responseText(response.path("payload").get("content")))) {
        return false;
      }
      String eventTurn = messageTurnId(event);
      String responseTurn = messageTurnId(response);
      if (!eventTurn.isBlank()) {
        turnIds.add(eventTurn);
      }
      if (!responseTurn.isBlank()) {
        turnIds.add(responseTurn);
      }
      String timestamp = extractTimestamp(event);
      timestampsMatch &=
          sourceTimestamp(timestamp).isPresent() && timestamp.equals(extractTimestamp(response));
    }
    if (turnIds.size() > 1) {
      return false;
    }
    boolean sameTurn =
        !messageTurnId(events.get(eventUser)).isBlank()
            && messageTurnId(events.get(eventUser)).equals(messageTurnId(events.get(responseUser)));
    return timestampsMatch || sameTurn;
  }

  /** 仅配对相邻且非空同文的输入镜像，禁止跨输入查找相同正文。 */
  private static int[] messageSegments(List<JsonNode> events, List<SourceRecord> records) {
    int[] segments = new int[records.size()];
    int segment = 0;
    String pendingRepresentation = "";
    CodexFallbackPlan.Fingerprint pendingFingerprint = null;
    int pendingOrdinal = -1;
    for (int index = 0; index < records.size(); index++) {
      SourceRecord record = records.get(index);
      JsonNode event = events.get(record.eventIndex());
      String subtype = record.turnId().orElse("");
      boolean eventUser = "event_msg".equals(record.eventType()) && "user_message".equals(subtype);
      boolean responseUser = isResponseMessage(event, "user");
      if (eventUser || responseUser) {
        String representation = eventUser ? "event_msg" : CodexConstants.EVENT_TYPE_RESPONSE_ITEM;
        String content =
            eventUser
                ? eventMessageContent(event)
                : responseText(event.path("payload").get("content"));
        boolean mirror =
            !pendingRepresentation.isEmpty()
                && !pendingRepresentation.equals(representation)
                && !content.isBlank()
                && CodexFallbackPlan.fingerprint(content).equals(pendingFingerprint)
                && content.equals(
                    "event_msg".equals(pendingRepresentation)
                        ? eventMessageContent(events.get(pendingOrdinal))
                        : responseText(events.get(pendingOrdinal).path("payload").get("content")));
        if (!mirror) {
          segment++;
        }
        pendingRepresentation = mirror ? "" : representation;
        pendingFingerprint = mirror ? null : CodexFallbackPlan.fingerprint(content);
        pendingOrdinal = mirror ? -1 : record.eventIndex();
      } else {
        pendingRepresentation = "";
        pendingFingerprint = null;
        pendingOrdinal = -1;
        if ("turn_context".equals(record.eventType())
            || ("event_msg".equals(record.eventType()) && "task_started".equals(subtype))) {
          segment++;
        }
      }
      segments[index] = segment;
    }
    return segments;
  }

  private static String eventMessageContent(JsonNode event) {
    JsonNode payload = event.path("payload");
    return responseText(
        payload.hasNonNull("message") ? payload.get("message") : payload.get("content"));
  }

  /** 不能仅凭角色判断权威表示；只有当前输入分段内相同且非空的正文才算镜像。 */
  private static boolean[] responseMessageSegments(
      List<JsonNode> events, List<SourceRecord> records, int[] segments, String role) {
    CodexFallbackPlan bodies = new CodexFallbackPlan();
    for (int index = 0; index < records.size(); index++) {
      JsonNode event = events.get(records.get(index).eventIndex());
      if (isResponseMessage(event, role)) {
        String content = responseText(event.path("payload").get("content"));
        if (!content.isBlank()) {
          bodies.add(segments[index], records.get(index).eventIndex(), content);
        }
      }
    }
    boolean[] authoritative = new boolean[records.size()];
    for (int index = 0; index < records.size(); index++) {
      authoritative[index] =
          bodies.contains(
              segments[index],
              eventMessageContent(events.get(records.get(index).eventIndex())),
              ordinal -> responseText(events.get(ordinal).path("payload").get("content")));
    }
    return authoritative;
  }

  private static boolean[] framedMessageSegments(List<SourceRecord> records, int[] segments) {
    Set<Integer> framed = new HashSet<>();
    for (int index = 0; index < records.size(); index++) {
      if ("assistant".equals(records.get(index).eventType())) {
        framed.add(segments[index]);
      }
    }
    boolean[] result = new boolean[records.size()];
    for (int index = 0; index < records.size(); index++) {
      result[index] = framed.contains(segments[index]);
    }
    return result;
  }

  private static boolean isResponseMessage(JsonNode event, String role) {
    JsonNode payload = event.path("payload");
    return CodexConstants.EVENT_TYPE_RESPONSE_ITEM.equals(extractEventType(event))
        && "message".equals(text(payload, "type"))
        && role.equals(text(payload, "role"));
  }

  private static boolean hasResponseUsage(JsonNode event) {
    return "token_usage_record".equals(extractEventType(event))
        && event.path("payload").path("usage").isObject();
  }

  private static SourceRecord mapResponseUsage(
      JsonNode event, int eventIndex, String locator, String model, Set<String> responseIds) {
    JsonNode payload = event.path("payload");
    String responseId = text(payload, "response_id");
    String recordLocator = locator + "#event[" + eventIndex + "]";
    if (!responseId.isBlank() && !responseIds.add(responseId)) {
      return basicRecord(recordLocator, eventIndex, "token_usage_record", extractTimestamp(event));
    }
    return new SourceRecord(
        recordLocator,
        eventIndex,
        "assistant",
        Optional.of(
            responseId.isBlank()
                ? "token_usage_ordinal:" + eventIndex
                : "token_usage_record:" + responseId),
        optionalText(model),
        optionalText(extractTimestamp(event)),
        optionalText(text(payload, "turn_id")),
        withUsageProvenance(
            usageTotals(payload.path("usage"), true).deltaSince(TokenTotals.zero()),
            CodexTokenProvenance.forUsage(payload.path("usage"), true)),
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty());
  }

  private static SourceRecordUsage withUsageProvenance(
      SourceRecordUsage usage, Map<String, String> provenance) {
    return new SourceRecordUsage(
        usage.inputTokens(),
        usage.cacheReadInputTokens(),
        usage.cacheCreationInputTokens(),
        usage.outputTokens(),
        provenance);
  }

  private static SourceRecord neutralUsageRecord(
      String locator,
      int index,
      String type,
      String timestamp,
      String model,
      SourceRecordUsage usage) {
    return new SourceRecord(
        locator,
        index,
        type,
        Optional.empty(),
        optionalText(model),
        optionalText(timestamp),
        Optional.empty(),
        usage,
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty());
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
        relation == null ? SourceRecordRelation.empty() : relation,
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing(),
        record.metaContext(),
        record.messageRole());
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

  private static Map<String, SourceRecordRelation> spawnRelations(
      List<JsonNode> events,
      List<Path> childRollouts,
      List<SourceDiagnostic> diagnostics,
      String locator) {
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

    Map<String, SpawnAgentResult> spawnResults = new LinkedHashMap<>();
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
      parseSpawnAgentResult(payload.get("output"))
          .ifPresent(result -> spawnResults.put(callId, result));
    }

    List<Map<String, String>> children =
        childRollouts.stream().map(CodexSourceAdapter::readFirstSessionMeta).toList();
    Map<String, SourceRecordRelation> relations = new LinkedHashMap<>();
    for (Map.Entry<String, SpawnAgentResult> entry : spawnResults.entrySet()) {
      String callId = entry.getKey();
      SpawnAgentResult result = entry.getValue();
      List<Map<String, String>> matches =
          children.stream()
              .filter(
                  meta ->
                      result.agentId().isEmpty()
                          ? result.agentPath().equals(subagentMetaField(meta, "agent_path"))
                          : result.agentId().equals(meta.get("id")))
              .toList();
      String agentId = result.agentId();
      if (agentId.isEmpty()) {
        long matchingSpawns =
            spawnResults.values().stream()
                .filter(spawn -> result.agentPath().equals(spawn.agentPath()))
                .count();
        if (matches.size() > 1 || matchingSpawns > 1) {
          diagnostics.add(
              codexInfoDiagnostic(
                  "Multiple child rollouts or spawn outputs share an agent_path",
                  "SUBAGENT_SPAWN_AMBIGUOUS",
                  locator));
          continue;
        }
        if (matches.isEmpty()) {
          continue;
        }
        agentId = matches.getFirst().getOrDefault("id", "").trim();
        if (agentId.isEmpty()) {
          continue;
        }
      }
      SourceRecordRelation relation =
          new SourceRecordRelation(
              Optional.of(agentId),
              matches.size() == 1
                  ? optionalText(parentThreadId(matches.getFirst()))
                  : Optional.empty(),
              Optional.of(callId),
              Optional.empty(),
              Optional.of("spawn_agent"));
      relations.put(callId, relation);
      relations.put(agentId, relation);
    }
    return Map.copyOf(relations);
  }

  /** 复用原关联解析，仅为 discovery 留下可核对的 child 身份。 */
  static JsonNode metadataSpawnOutput(JsonNode output) {
    var projected = MAPPER.createObjectNode();
    parseSpawnAgentResult(output)
        .ifPresent(
            result -> {
              projected.put("agent_id", result.agentId());
              projected.put("task_name", result.agentPath());
            });
    return projected;
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
    String agentId = text(resultNode, "agent_id").trim();
    String agentPath = text(resultNode, "task_name").trim();
    if (agentId.isEmpty() && agentPath.isEmpty()) {
      return Optional.empty();
    }
    return Optional.of(new SpawnAgentResult(agentId, agentPath));
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
    if (!CodexConstants.EVENT_TYPE_RESPONSE_ITEM.equals(rawType)
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
                  Optional.empty(),
                  SourceRecordRelation.empty(),
                  "user_message".equals(payloadType)
                      ? responseText(
                          payload.hasNonNull("message")
                              ? payload.get("message")
                              : payload.get("content"))
                      : "")
              .withTiming(JsonSourceRecordMapper.extractTiming(event))
              .withMessageRole(
                  "user_message".equals(payloadType)
                      ? Optional.of("user")
                      : "agent_message".equals(payloadType)
                          ? Optional.of("assistant")
                          : Optional.empty()),
          previousTotals);
    }

    if (CodexConstants.EVENT_TYPE_RESPONSE_ITEM.equals(rawType)) {
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
              ? List.of(
                  new SourceToolCall(callId.get(), name.get(), toolInput(payload, payloadType)))
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
          extractCodexToolError(payload),
          SourceRecordRelation.empty(),
          responseText(payload.get("output")));
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
                Optional.empty(),
                SourceRecordUsage.empty(),
                List.of(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                SourceRecordRelation.empty(),
                responseText(payload.get("content")))
            .withMessageRole(Optional.of(role));
      }
      if ("assistant".equals(role)) {
        return new SourceRecord(
                recordLocator,
                eventIndex,
                hasTokenUsage ? CodexConstants.EVENT_TYPE_RESPONSE_ITEM : "assistant",
                Optional.empty(),
                optionalText(currentModel),
                optionalText(timestamp),
                Optional.empty(),
                SourceRecordUsage.empty(),
                List.of(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                SourceRecordRelation.empty(),
                responseText(payload.get("content")))
            .withMessageRole(Optional.of(role));
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
          Optional.empty(),
          SourceRecordUsage.empty(),
          List.of(),
          Optional.empty(),
          Optional.empty(),
          Optional.empty());
    }
    return basicRecord(
        recordLocator, eventIndex, CodexConstants.EVENT_TYPE_RESPONSE_ITEM, timestamp);
  }

  private static String toolInput(JsonNode payload, String payloadType) {
    JsonNode input = payload.get("function_call".equals(payloadType) ? "arguments" : "input");
    if (input == null || input.isNull()) {
      return "";
    }
    return input.isTextual() ? input.asText() : input.toString();
  }

  /** 提取文本块，保持源顺序和空白，不将非文本结构序列化为响应内容。 */
  private static String responseText(JsonNode node) {
    if (node == null) {
      return "";
    }
    if (node.isTextual()) {
      return node.asText();
    }
    if (node.isArray()) {
      StringBuilder content = new StringBuilder();
      for (JsonNode part : node) {
        content.append(responseText(part));
      }
      return content.toString();
    }
    String type = text(node, "type");
    if (type.isEmpty()
        || "text".equals(type)
        || "input_text".equals(type)
        || "output_text".equals(type)) {
      JsonNode value = node.get("text");
      return value != null && value.isTextual() ? value.asText() : "";
    }
    return "";
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
  private record CodexRecordMapping(
      /* 原始记录对象 */
      @NotNull SourceRecord record,
      /* 上一条累计 token 值 */
      @NotNull TokenTotals previousTotals) {
    public CodexRecordMapping {
      ValidationSupport.validateCanonicalConstructor(
          CodexRecordMapping.class, record, previousTotals);
    }
  }

  /**
   * 表示 spawn_agent 输出中的稳定归属字段。
   *
   * @param agentId Codex 子线程标识。
   * @param agentPath 子线程完整 agent 路径，用于 task_name 与同父线程的 metadata 精确配对。
   */
  private record SpawnAgentResult(
      /* Codex 子线程标识 */
      @NotNull String agentId,
      /* 子线程完整 agent 路径 */
      @NotNull String agentPath) {
    public SpawnAgentResult {
      ValidationSupport.validateCanonicalConstructor(SpawnAgentResult.class, agentId, agentPath);
    }
  }

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
      /* 该字段在 API 响应中的业务值 */
      @PositiveOrZero long freshInput,
      /* 缓存读取令牌数量 */
      @PositiveOrZero long cacheRead,
      /* 缓存写入令牌数量 */
      @PositiveOrZero long cacheWrite,
      /* 该字段在 API 响应中的业务值 */
      @PositiveOrZero long output,
      /* provider 原始 token 总数 */
      @PositiveOrZero long rawTotal) {
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

    private TokenTotals components() {
      return new TokenTotals(freshInput, cacheRead, cacheWrite, output, 0);
    }

    private boolean sameComponents(TokenTotals other) {
      return freshInput == other.freshInput
          && cacheRead == other.cacheRead
          && cacheWrite == other.cacheWrite
          && output == other.output;
    }

    private boolean covers(TokenTotals other) {
      return freshInput >= other.freshInput
          && cacheRead >= other.cacheRead
          && cacheWrite >= other.cacheWrite
          && output >= other.output;
    }

    private TokenTotals plus(TokenTotals other) {
      return new TokenTotals(
          freshInput + other.freshInput,
          cacheRead + other.cacheRead,
          cacheWrite + other.cacheWrite,
          output + other.output,
          0);
    }

    private TokenTotals minus(TokenTotals other) {
      return new TokenTotals(
          freshInput - other.freshInput,
          cacheRead - other.cacheRead,
          cacheWrite - other.cacheWrite,
          output - other.output,
          0);
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
    private String locator;
    private final CancellationSignal cancellation;

    private CodexParseState(String locator, String initialModel, CancellationSignal cancellation) {
      this.locator = locator;
      this.currentModel = initialModel == null ? "" : initialModel;
      this.cancellation = cancellation;
    }
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
    return usageTotals(usage, false);
  }

  private static TokenTotals usageTotals(JsonNode usage, boolean responseUsage) {
    return new TokenTotals(
        CodexTokenProvenance.freshInputAmount(usage, responseUsage),
        CodexTokenProvenance.component(usage, "cacheReadTokenPrecision"),
        CodexTokenProvenance.component(usage, "cacheWriteTokenPrecision"),
        CodexTokenProvenance.component(usage, "outputTokenPrecision"),
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
        Long value = CodexTokenProvenance.readUsageLong(node, List.of(fieldName));
        return value == null ? 0 : value;
      }
    }
    return 0L;
  }
}
