package com.feipi.session.browser.source.claude;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.claude.ClaudeDiscovery.ClaudeSessionDiscovery;
import com.feipi.session.browser.source.json.JsonCandidateMetadataReader;
import com.feipi.session.browser.source.json.JsonCandidateParser;
import com.feipi.session.browser.source.json.JsonNodeReaders;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import com.feipi.session.browser.source.json.SourceTitleTexts;
import com.feipi.session.browser.source.json.ToolFailureClassifier;
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
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Claude Code 源适配器实现。
 *
 * <p>实现 {@link SourceAdapter} SPI 接口，负责从 Claude Code 本地数据目录 发现会话文件、生成文件指纹和解析 JSONL 会话内容。
 *
 * <p>发现策略与 Python master 对齐：从 {@code history.jsonl} 驱动，去重后按 sessionId 定位 transcript 文件。 transcript
 * 缺失的会话仍然创建候选项（零值指纹），由 scan engine fallback 入库。
 *
 * <p>该适配器保证：
 *
 * <ul>
 *   <li>{@link #discover(Path)} 对同一输入产生确定排序的结果。
 *   <li>{@link #fingerprint(Path)} 包含 SHA-256 内容哈希。
 *   <li>{@link #checkRoot(Path)} 检测符号链接、路径逃逸和只读状态。
 *   <li>{@link #parse(Candidate, CancellationSignal)} 不抛出异常表示可预期失败。
 * </ul>
 */
public final class ClaudeSourceAdapter implements SourceAdapter {

  private static final Logger LOG = Logger.getLogger(ClaudeSourceAdapter.class.getName());

  private final JsonlReader jsonlReader;

  /** 使用默认 JSONL 读取器配置创建适配器。 */
  public ClaudeSourceAdapter() {
    this(new JsonlReader());
  }

  /**
   * 使用指定 JSONL 读取器创建适配器。
   *
   * @param jsonlReader JSONL 读取器实例，不得为 null
   */
  public ClaudeSourceAdapter(JsonlReader jsonlReader) {
    Objects.requireNonNull(jsonlReader, "jsonlReader 不得为 null");
    this.jsonlReader = jsonlReader;
  }

  @Override
  public SourceId sourceId() {
    return SourceId.CLAUDE_CODE;
  }

  /**
   * 从源根目录发现候选会话。
   *
   * <p>从 {@code history.jsonl} 驱动发现：读取并去重后，对每个 session 定位 transcript 文件。 transcript 缺失的会话创建零值指纹候选项。
   *
   * @param rootPath 源根目录路径
   * @return 有界确定性候选项流
   */
  @Override
  public BoundedStream<Candidate> discover(Path rootPath) {
    Objects.requireNonNull(rootPath, "rootPath 不得为 null");

    List<ClaudeSessionDiscovery> discoveries =
        ClaudeDiscovery.discoverSessionsWithHistory(rootPath);
    List<Candidate> candidates = new ArrayList<>(discoveries.size());

    for (ClaudeSessionDiscovery disc : discoveries) {
      try {
        SourceFingerprint fp;
        if (disc.hasFile()) {
          fp = fingerprint(disc.transcriptPath());
        } else {
          // transcript 缺失：零值指纹，locator 使用 sessionId
          fp =
              new SourceFingerprint(
                  disc.entry().sessionId(),
                  SourceId.CLAUDE_CODE,
                  0,
                  0,
                  Optional.empty(),
                  Optional.empty());
        }

        String sessionKey = "claude_code:" + disc.entry().sessionId();
        String projectKey = disc.entry().project();

        Map<String, String> meta = new HashMap<>();
        if (!disc.entry().display().isEmpty()) {
          meta.put(ClaudeConstants.META_TITLE, disc.entry().display());
        }
        meta.put(ClaudeConstants.META_HAS_TRANSCRIPT, String.valueOf(disc.hasFile()));
        meta.put(ClaudeConstants.META_TIMESTAMP, String.valueOf(disc.entry().timestamp()));
        if (disc.hasFile()) {
          ClaudeCandidateMetadata transcriptMeta = inspectCandidateMetadata(disc.transcriptPath());
          putIfNotEmpty(meta, "title", transcriptMeta.title());
          putIfNotEmpty(meta, "cwd", transcriptMeta.cwd());
          putIfNotEmpty(meta, "model", transcriptMeta.model());
          putIfNotEmpty(meta, "git_branch", transcriptMeta.gitBranch());
          putSubagentMetadata(meta, inspectSubagents(disc.transcriptPath()));
        }

        Candidate candidate = new Candidate(fp, sessionKey, projectKey, Map.copyOf(meta));
        candidates.add(candidate);
      } catch (Exception e) {
        LOG.log(Level.FINE, "跳过无法处理的会话: " + disc.entry().sessionId(), e);
      }
    }

    Comparator<Candidate> bySessionKey = Comparator.comparing(Candidate::sessionKey);
    return BoundedStream.of(
        candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.of(bySessionKey));
  }

  private void putSubagentMetadata(Map<String, String> meta, ClaudeSubagentTotals totals) {
    putIfPositive(meta, "subagentInstanceCount", totals.subagentInstanceCount());
    putIfPositive(meta, "subagentToolCallCount", totals.toolCallCount());
    putIfPositive(meta, "subagentFailedToolCount", totals.failedToolCount());
    putIfPositive(meta, "subagentFreshInputTokens", totals.freshInputTokens());
    putIfPositive(meta, "subagentCacheReadTokens", totals.cacheReadTokens());
    putIfPositive(meta, "subagentCacheWriteTokens", totals.cacheWriteTokens());
    putIfPositive(meta, "subagentOutputTokens", totals.outputTokens());
    putIfPositive(meta, "subagentTotalTokens", totals.totalTokens());
  }

  private static void putIfPositive(Map<String, String> meta, String key, long value) {
    if (value > 0) {
      meta.put(key, Long.toString(value));
    }
  }

  private static void putIfNotEmpty(Map<String, String> meta, String key, String value) {
    if (value == null) {
      return;
    }
    String trimmed = value.trim();
    if (!trimmed.isEmpty()) {
      meta.put(key, trimmed);
    }
  }

  private ClaudeCandidateMetadata inspectCandidateMetadata(Path transcriptPath) {
    try {
      JsonlReaderResult result = jsonlReader.read(transcriptPath);
      JsonCandidateMetadataReader.Metadata metadata =
          JsonCandidateMetadataReader.firstComplete(
              result.events(),
              event -> text(event, "cwd"),
              event -> "user".equals(text(event, "type")) && !isMetaEvent(event),
              ClaudeSourceAdapter::firstMessageText,
              event -> text(JsonNodeReaders.objectChild(event, "message"), "model"),
              ClaudeSourceAdapter::extractGitBranch);
      return new ClaudeCandidateMetadata(
          metadata.cwd(), metadata.title(), metadata.model(), metadata.gitBranch());
    } catch (IOException e) {
      LOG.log(Level.FINEST, "读取 Claude 候选元数据失败: " + transcriptPath, e);
      return ClaudeCandidateMetadata.empty();
    }
  }

  private static boolean isMetaEvent(JsonNode event) {
    JsonNode isMeta = event == null ? null : event.get("isMeta");
    return isMeta != null && isMeta.isBoolean() && isMeta.asBoolean();
  }

  private static String firstMessageText(JsonNode event) {
    JsonNode message = JsonNodeReaders.objectChild(event, "message");
    String value = contentText(message == null ? event.get("content") : message.get("content"));
    if (value.isBlank()) {
      value = text(event, "text");
    }
    value = SourceTitleTexts.clean(value);
    return value.length() > 120 ? value.substring(0, 120) : value;
  }

  private static String contentText(JsonNode content) {
    if (content == null || content.isNull()) {
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
      String text = item != null && item.isObject() ? text(item, "text") : "";
      if (!text.isBlank()) {
        if (!sb.isEmpty()) {
          sb.append('\n');
        }
        sb.append(text);
      }
    }
    return sb.toString();
  }

  private static String extractGitBranch(JsonNode event) {
    String branch = text(event, "gitBranch");
    if (!branch.isEmpty()) {
      return branch;
    }
    branch = text(event, "git_branch");
    if (!branch.isEmpty()) {
      return branch;
    }
    JsonNode git = JsonNodeReaders.objectChild(event, "git");
    branch = text(git, "branch");
    if (!branch.isEmpty()) {
      return branch;
    }
    return text(JsonNodeReaders.objectChild(event, "metadata"), "git_branch");
  }

  private ClaudeSubagentTotals inspectSubagents(Path transcriptPath) {
    List<Path> files = subagentFiles(transcriptPath);
    if (files.isEmpty()) {
      return ClaudeSubagentTotals.empty();
    }

    ClaudeSubagentTotals totals = ClaudeSubagentTotals.empty();
    for (Path file : files) {
      try {
        JsonlReaderResult result = jsonlReader.read(file);
        totals = totals.plus(inspectSubagentEvents(result.events()));
      } catch (IOException e) {
        LOG.log(Level.FINEST, "读取 Claude subagent 文件失败: " + file, e);
      }
    }
    return totals.withSubagentInstanceCount(files.size());
  }

  private static Path sidecarSubagentsDir(Path transcriptPath) {
    String fileName = transcriptPath.getFileName().toString();
    String stem =
        fileName.endsWith(ClaudeConstants.SESSION_FILE_SUFFIX)
            ? fileName.substring(
                0, fileName.length() - ClaudeConstants.SESSION_FILE_SUFFIX.length())
            : fileName;
    return transcriptPath.resolveSibling(stem).resolve("subagents");
  }

  private static ClaudeSubagentTotals inspectSubagentEvents(List<JsonNode> events) {
    List<AssistantRecord> assistantRecords = assistantRecords(events);
    long freshInput = 0;
    long cacheRead = 0;
    long cacheWrite = 0;
    long output = 0;
    Map<String, String> toolNames = new LinkedHashMap<>();
    for (AssistantRecord record : assistantRecords) {
      UsageTotals usage = mergeUsage(record.usageRows());
      freshInput += usage.inputTokens();
      cacheRead += usage.cacheReadTokens();
      cacheWrite += usage.cacheWriteTokens();
      output += usage.outputTokens();
      for (ToolUse tool : record.toolUses()) {
        toolNames.put(tool.id(), tool.name());
      }
    }

    long failed = countFailedToolResults(events, toolNames);
    return new ClaudeSubagentTotals(
        0, toolNames.size(), failed, freshInput, cacheRead, cacheWrite, output);
  }

  private static List<AssistantRecord> assistantRecords(List<JsonNode> events) {
    Map<String, AssistantRecordBuilder> records = new LinkedHashMap<>();
    for (JsonNode event : events) {
      if (!"assistant".equals(text(event, "type"))) {
        continue;
      }
      JsonNode message = JsonNodeReaders.objectChild(event, "message");
      if (message == null) {
        continue;
      }
      String key = assistantMessageKey(event, message);
      AssistantRecordBuilder builder =
          records.computeIfAbsent(key, ignored -> new AssistantRecordBuilder());
      JsonNode usage = JsonNodeReaders.objectChild(message, "usage");
      if (usage != null) {
        builder.usageRows.add(usage);
      }
      JsonNode content = message.get("content");
      if (content != null && content.isArray()) {
        for (JsonNode item : content) {
          if (item == null || !item.isObject()) {
            continue;
          }
          String itemType = text(item, "type");
          if ("text".equals(itemType) || "thinking".equals(itemType)) {
            builder.hasContent = true;
          } else if ("tool_use".equals(itemType)) {
            builder.hasContent = true;
            String id = text(item, "id");
            String name = text(item, "name");
            if (!id.isEmpty() && !name.isEmpty()) {
              builder.toolUses.add(new ToolUse(id, name));
            }
          }
        }
      }
    }
    List<AssistantRecord> result = new ArrayList<>();
    for (AssistantRecordBuilder builder : records.values()) {
      if (builder.hasContent) {
        result.add(
            new AssistantRecord(List.copyOf(builder.usageRows), List.copyOf(builder.toolUses)));
      }
    }
    return List.copyOf(result);
  }

  private static String assistantMessageKey(JsonNode event, JsonNode message) {
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
    return Integer.toHexString(System.identityHashCode(event));
  }

  private static UsageTotals mergeUsage(List<JsonNode> usages) {
    if (usages.isEmpty()) {
      return UsageTotals.empty();
    }
    JsonNode best = null;
    int bestIndex = -1;
    int bestOutputPresent = -1;
    int bestCacheFieldCount = -1;
    long bestTokenTotal = -1;
    long maxInput = 0;
    for (int i = 0; i < usages.size(); i++) {
      JsonNode usage = usages.get(i);
      maxInput = Math.max(maxInput, longValue(usage, "input_tokens"));
      int outputPresent = longValue(usage, "output_tokens") > 0 ? 1 : 0;
      int cacheFieldCount =
          (usage.has("cache_read_input_tokens") ? 1 : 0)
              + (usage.has("cache_creation_input_tokens") ? 1 : 0);
      long tokenTotal =
          longValue(usage, "input_tokens")
              + longValue(usage, "output_tokens")
              + longValue(usage, "cache_read_input_tokens")
              + longValue(usage, "cache_creation_input_tokens");
      if (best == null
          || outputPresent > bestOutputPresent
          || (outputPresent == bestOutputPresent && cacheFieldCount > bestCacheFieldCount)
          || (outputPresent == bestOutputPresent
              && cacheFieldCount == bestCacheFieldCount
              && tokenTotal > bestTokenTotal)
          || (outputPresent == bestOutputPresent
              && cacheFieldCount == bestCacheFieldCount
              && tokenTotal == bestTokenTotal
              && i > bestIndex)) {
        best = usage;
        bestIndex = i;
        bestOutputPresent = outputPresent;
        bestCacheFieldCount = cacheFieldCount;
        bestTokenTotal = tokenTotal;
      }
    }
    return new UsageTotals(
        Math.max(maxInput, longValue(best, "input_tokens")),
        longValue(best, "cache_read_input_tokens"),
        longValue(best, "cache_creation_input_tokens"),
        longValue(best, "output_tokens"));
  }

  private static long countFailedToolResults(List<JsonNode> events, Map<String, String> toolNames) {
    long failed = 0;
    LinkedHashSet<String> failedIds = new LinkedHashSet<>();
    for (JsonNode event : events) {
      if (!"user".equals(text(event, "type"))) {
        continue;
      }
      JsonNode message = JsonNodeReaders.objectChild(event, "message");
      JsonNode content = message == null ? null : message.get("content");
      if (content == null || !content.isArray()) {
        continue;
      }
      for (JsonNode item : content) {
        if (item == null || !item.isObject() || !"tool_result".equals(text(item, "type"))) {
          continue;
        }
        String toolUseId = text(item, "tool_use_id");
        String resultText = stringifyToolResult(item.get("content"));
        boolean isError = booleanValue(item, "is_error");
        String toolName = toolNames.getOrDefault(toolUseId, "");
        if (isError || ToolFailureClassifier.looksFailed(resultText, toolName)) {
          if (toolUseId.isEmpty() || failedIds.add(toolUseId)) {
            failed++;
          }
        }
      }
    }
    return failed;
  }

  private static String stringifyToolResult(JsonNode value) {
    if (value == null || value.isNull()) {
      return "";
    }
    if (value.isTextual()) {
      return value.asText();
    }
    if (value.isArray()) {
      StringBuilder sb = new StringBuilder();
      for (JsonNode item : value) {
        String part = "";
        if (item != null && item.isObject()) {
          if ("text".equals(text(item, "type"))) {
            part = text(item, "text");
          } else if (item.has("content")) {
            part = stringifyToolResult(item.get("content"));
          }
        } else if (item != null) {
          part = item.asText("");
        }
        if (!part.isBlank()) {
          if (!sb.isEmpty()) {
            sb.append('\n');
          }
          sb.append(part);
        }
      }
      return sb.toString();
    }
    return value.toString();
  }

  private static String text(JsonNode node, String fieldName) {
    if (node == null) {
      return "";
    }
    if (!node.isObject()) {
      return "";
    }
    JsonNode child = node.path(fieldName);
    return child.isTextual() ? child.asText() : "";
  }

  private static boolean booleanValue(JsonNode node, String fieldName) {
    if (node == null || !node.isObject()) {
      return false;
    }
    JsonNode child = node.get(fieldName);
    return child != null && child.isBoolean() && child.asBoolean();
  }

  private static long longValue(JsonNode node, String fieldName) {
    if (node == null || !node.isObject()) {
      return 0;
    }
    JsonNode child = node.get(fieldName);
    return child != null && child.isNumber() ? child.asLong() : 0;
  }

  /** Claude assistant 事件解析过程中的临时聚合器。 */
  private static final class AssistantRecordBuilder {
    private final List<JsonNode> usageRows = new ArrayList<>();
    private final List<ToolUse> toolUses = new ArrayList<>();
    private boolean hasContent;
  }

  /**
   * 表示 AssistantRecord 数据。
   *
   * @param usageRows usage 行列表。
   * @param toolUses tool use 列表。
   */
  private record AssistantRecord(List<JsonNode> usageRows, List<ToolUse> toolUses) {}

  /**
   * 表示 ToolUse 数据。
   *
   * @param id 标识符。
   * @param name 名称。
   */
  private record ToolUse(String id, String name) {}

  /**
   * 表示 UsageTotals 数据。
   *
   * @param inputTokens 输入 token 数量。
   * @param cacheReadTokens cache read token 数量。
   * @param cacheWriteTokens cache write token 数量。
   * @param outputTokens output token 数量。
   */
  private record UsageTotals(
      long inputTokens, long cacheReadTokens, long cacheWriteTokens, long outputTokens) {
    private static UsageTotals empty() {
      return new UsageTotals(0, 0, 0, 0);
    }
  }

  /**
   * 表示 ClaudeSubagentTotals 数据。
   *
   * @param subagentInstanceCount subagent 实例数量。
   * @param toolCallCount 工具调用数量。
   * @param failedToolCount 失败工具数量。
   * @param freshInputTokens fresh input token 数量。
   * @param cacheReadTokens cache read token 数量。
   * @param cacheWriteTokens cache write token 数量。
   * @param outputTokens output token 数量。
   */
  private record ClaudeSubagentTotals(
      long subagentInstanceCount,
      long toolCallCount,
      long failedToolCount,
      long freshInputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      long outputTokens) {
    private static ClaudeSubagentTotals empty() {
      return new ClaudeSubagentTotals(0, 0, 0, 0, 0, 0, 0);
    }

    private long totalTokens() {
      return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    }

    private ClaudeSubagentTotals withSubagentInstanceCount(long count) {
      return new ClaudeSubagentTotals(
          count,
          toolCallCount,
          failedToolCount,
          freshInputTokens,
          cacheReadTokens,
          cacheWriteTokens,
          outputTokens);
    }

    private ClaudeSubagentTotals plus(ClaudeSubagentTotals other) {
      return new ClaudeSubagentTotals(
          subagentInstanceCount + other.subagentInstanceCount,
          toolCallCount + other.toolCallCount,
          failedToolCount + other.failedToolCount,
          freshInputTokens + other.freshInputTokens,
          cacheReadTokens + other.cacheReadTokens,
          cacheWriteTokens + other.cacheWriteTokens,
          outputTokens + other.outputTokens);
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
          SourceId.CLAUDE_CODE,
          size,
          lastModified,
          Optional.of(hash),
          Optional.of(SourceConstants.DEFAULT_HASH_ALGORITHM));
    } catch (IOException e) {
      // 文件不存在或无法访问，返回零值指纹
      LOG.log(Level.FINE, "无法生成文件指纹: " + filePath, e);
      return new SourceFingerprint(
          filePath.toAbsolutePath().toString(),
          SourceId.CLAUDE_CODE,
          0,
          0,
          Optional.empty(),
          Optional.empty());
    }
  }

  /**
   * 解析指定候选项的会话数据。
   *
   * <p>使用 {@link JsonlReader} 解析 JSONL 文件。 文件不存在（零值指纹）返回 {@link SourceResult.Skipped}。 IO 错误返回
   * {@link SourceResult.Fatal}，解析成功返回 {@link SourceResult.Success}。
   *
   * @param candidate 待解析的候选项
   * @param cancellation 可选的取消信号
   * @return 密封的解析结果
   */
  @Override
  public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
    // 零值指纹 → transcript 缺失 → 跳过解析（engine 会 fallback 入库）
    if (candidate.fingerprint().sizeBytes() == 0
        && candidate.fingerprint().contentHash().isEmpty()) {
      return new SourceResult.Skipped(
          List.of(), "Transcript file missing for session " + candidate.sessionKey());
    }

    SourceResult primary =
        JsonCandidateParser.parse(
            candidate,
            cancellation,
            jsonlReader,
            ClaudeSourceAdapter::extractEventType,
            ClaudeSourceAdapter::collectEventDiagnostics,
            (diagnostics, eventCount) -> {});
    if (!(primary instanceof SourceResult.Success success)) {
      return primary;
    }

    List<Path> sidecars = subagentFiles(Path.of(candidate.fingerprint().locator()));
    if (sidecars.isEmpty()) {
      return primary;
    }
    List<SourceDiagnostic> diagnostics = new ArrayList<>(success.diagnostics());
    List<SourceRecord> records = new ArrayList<>(success.records());
    int candidateCount = success.candidateCount();
    for (Path sidecar : sidecars) {
      SourceResult sidecarResult =
          JsonCandidateParser.parse(
              new Candidate(
                  fingerprint(sidecar),
                  candidate.sessionKey(),
                  candidate.projectKey(),
                  candidate.metadata()),
              cancellation,
              jsonlReader,
              ClaudeSourceAdapter::extractEventType,
              ClaudeSourceAdapter::collectEventDiagnostics,
              (ignored, eventCount) -> {});
      if (sidecarResult instanceof SourceResult.Success sidecarSuccess) {
        diagnostics.addAll(sidecarSuccess.diagnostics());
        records.addAll(sidecarSuccess.records());
        candidateCount += sidecarSuccess.candidateCount();
      } else if (sidecarResult instanceof SourceResult.Fatal fatal) {
        return fatal;
      }
    }
    return new SourceResult.Success(
        diagnostics, candidateCount, records, success.fingerprint(), success.locator());
  }

  private static List<Path> subagentFiles(Path transcriptPath) {
    Path subagentsDir = sidecarSubagentsDir(transcriptPath);
    if (!Files.isDirectory(subagentsDir)) {
      return List.of();
    }
    List<Path> files = new ArrayList<>();
    try (var stream = Files.list(subagentsDir)) {
      stream
          .filter(Files::isRegularFile)
          .filter(path -> path.getFileName().toString().endsWith(".jsonl"))
          .sorted()
          .forEach(files::add);
    } catch (IOException e) {
      LOG.log(Level.FINEST, "读取 Claude subagent 文件列表失败: " + subagentsDir, e);
    }
    return List.copyOf(files);
  }

  private static void collectEventDiagnostics(
      JsonNode event,
      int eventIndex,
      String eventType,
      String locator,
      List<SourceDiagnostic> diagnostics) {
    if (!eventType.equals(ClaudeConstants.EVENT_TYPE_UNKNOWN)) {
      return;
    }
    diagnostics.add(
        new SourceDiagnostic(
            ParseSeverity.WARNING,
            ParseIssueType.NON_OBJECT_SKIPPED,
            "Event at index " + eventIndex + " missing 'type' field",
            eventIndex + 1,
            Optional.empty(),
            ClaudeConstants.DIAG_CODE_MISSING_TYPE,
            locator,
            OptionalInt.empty(),
            OptionalInt.empty(),
            OptionalInt.empty()));
  }

  /**
   * 从 JSON 事件节点中提取 {@code type} 字段值。
   *
   * <p>当字段缺失或不是字符串时返回 {@link ClaudeConstants#EVENT_TYPE_UNKNOWN}。
   *
   * @param event JSON 事件节点
   * @return 非 null 的事件类型
   */
  private static String extractEventType(JsonNode event) {
    JsonNode typeNode = event.get("type");
    if (typeNode != null && typeNode.isTextual()) {
      return typeNode.asText();
    }
    return ClaudeConstants.EVENT_TYPE_UNKNOWN;
  }

  /**
   * 从会话文件路径中提取会话键。
   *
   * <p>会话键格式为 {@code {project-dir}/{session-id}}，其中 session-id 为 去掉 {@code .jsonl} 后缀的文件名。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 会话键
   */
  static String extractSessionKey(Path rootPath, Path sessionPath) {
    Path relative = SourcePathOps.toRelative(rootPath, sessionPath);
    // 目录结构为 {@code projects/项目名/会话.jsonl}，相对路径至少包含三段
    int nameCount = relative.getNameCount();
    if (nameCount >= 3) {
      String project = relative.getName(nameCount - 2).toString();
      String fileName = relative.getName(nameCount - 1).toString();
      String sessionId = SourcePathOps.stripSuffix(fileName, ClaudeConstants.SESSION_FILE_SUFFIX);
      return project + "/" + sessionId;
    }
    // 回退：使用文件名去后缀
    return SourcePathOps.stripSuffix(
        sessionPath.getFileName().toString(), ClaudeConstants.SESSION_FILE_SUFFIX);
  }

  /**
   * 从会话文件路径中提取项目键。
   *
   * <p>项目键为项目目录名（{@code projects/} 下的直接子目录）。
   *
   * @param rootPath 源根目录
   * @param sessionPath 会话文件路径
   * @return 项目键
   */
  static String extractProjectKey(Path rootPath, Path sessionPath) {
    Path relative = SourcePathOps.toRelative(rootPath, sessionPath);
    int nameCount = relative.getNameCount();
    if (nameCount >= 3) {
      return relative.getName(nameCount - 2).toString();
    }
    return "";
  }

  /**
   * 表示 ClaudeCandidateMetadata 数据。
   *
   * @param cwd 工作目录。
   * @param title 会话标题。
   * @param model 模型名称。
   * @param gitBranch Git branch 名称。
   */
  private record ClaudeCandidateMetadata(String cwd, String title, String model, String gitBranch) {
    private static ClaudeCandidateMetadata empty() {
      return new ClaudeCandidateMetadata("", "", "", "");
    }
  }
}
