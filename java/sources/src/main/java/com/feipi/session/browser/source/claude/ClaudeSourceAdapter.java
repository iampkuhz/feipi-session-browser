package com.feipi.session.browser.source.claude;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.source.claude.ClaudeDiscovery.ClaudeSessionDiscovery;
import com.feipi.session.browser.source.common.JsonCandidateMetadataReader;
import com.feipi.session.browser.source.common.JsonNodeReaders;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderResult;
import com.feipi.session.browser.source.common.SourceTitleTexts;
import com.feipi.session.browser.source.common.ToolFailureClassifier;
import com.feipi.session.browser.source.json.JsonCandidateParser;
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
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
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

  private static final Map<String, String> TOKEN_PRECISION_FIELDS =
      Map.of(
          "freshInputTokenPrecision", "input_tokens",
          "cacheReadTokenPrecision", "cache_read_input_tokens",
          "cacheWriteTokenPrecision", "cache_creation_input_tokens",
          "outputTokenPrecision", "output_tokens");

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

  /** 单文件沿用正式 usage 选择及字段存在性，不读取 sidecar。 */
  @Override
  public Map<String, String> singleFileMetadata(Path filePath) throws IOException {
    return tokenPrecision(assistantRecords(jsonlReader.read(filePath).events()));
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
          ClaudeSubagentTotals subagents = inspectSubagents(disc.transcriptPath());
          putSubagentMetadata(meta, subagents);
          meta.putAll(
              mergeTokenPrecision(transcriptMeta.tokenPrecision(), subagents.tokenPrecision()));
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
          metadata.cwd(),
          metadata.title(),
          metadata.model(),
          metadata.gitBranch(),
          tokenPrecision(assistantRecords(result.events())));
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
      if (text.isEmpty() && item != null && "thinking".equals(text(item, "type"))) {
        text = text(item, "thinking");
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
        0,
        toolNames.size(),
        failed,
        freshInput,
        cacheRead,
        cacheWrite,
        output,
        tokenPrecision(assistantRecords));
  }

  private static List<AssistantRecord> assistantRecords(List<JsonNode> events) {
    Map<String, AssistantRecordBuilder> records = new LinkedHashMap<>();
    for (JsonNode event : events) {
      if (!"assistant".equals(text(event, "type"))) {
        continue;
      }
      JsonNode message = JsonNodeReaders.objectChild(event, "message");
      if (message == null) {
        message = event;
      }
      String key = assistantMessageKey(event, message);
      AssistantRecordBuilder builder =
          records.computeIfAbsent(key, ignored -> new AssistantRecordBuilder());
      JsonNode usage = JsonNodeReaders.objectChild(message, "usage");
      if (usage != null) {
        builder.usageRows.add(message);
      }
      JsonNode content = message.get("content");
      if (content != null && content.isArray()) {
        for (JsonNode item : content) {
          if (item == null || !item.isObject()) {
            continue;
          }
          String itemType = text(item, "type");
          if ("tool_use".equals(itemType)) {
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
      result.add(
          new AssistantRecord(List.copyOf(builder.usageRows), List.copyOf(builder.toolUses)));
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
    JsonNode best = JsonNodeReaders.objectChild(selectUsageMessage(usages), "usage");
    Map<String, String> provenance = new LinkedHashMap<>();
    TOKEN_PRECISION_FIELDS.forEach(
        (key, field) ->
            provenance.put(
                key,
                usages.stream()
                        .anyMatch(
                            message ->
                                JsonNodeReaders.objectChild(message, "usage")
                                    .path(field)
                                    .isNumber())
                    ? "provider_reported"
                    : "unavailable"));
    return new UsageTotals(
        selectedUsageValue(best, usages, "input_tokens"),
        selectedUsageValue(best, usages, "cache_read_input_tokens"),
        selectedUsageValue(best, usages, "cache_creation_input_tokens"),
        selectedUsageValue(best, usages, "output_tokens"),
        Map.copyOf(provenance));
  }

  private static JsonNode selectUsageMessage(List<JsonNode> messages) {
    JsonNode best = null;
    int bestAuthority = -1;
    int bestCacheFieldCount = -1;
    long bestTokenTotal = -1;
    for (JsonNode message : messages) {
      JsonNode usage = JsonNodeReaders.objectChild(message, "usage");
      int cacheFieldCount =
          (usage.path("cache_read_input_tokens").isNumber() ? 1 : 0)
              + (usage.path("cache_creation_input_tokens").isNumber() ? 1 : 0);
      int authority = usageAuthority(message);
      long tokenTotal =
          longValue(usage, "input_tokens")
              + longValue(usage, "output_tokens")
              + longValue(usage, "cache_read_input_tokens")
              + longValue(usage, "cache_creation_input_tokens");
      if (best == null
          || authority > bestAuthority
          || (authority == bestAuthority && cacheFieldCount > bestCacheFieldCount)
          || (authority == bestAuthority
              && cacheFieldCount == bestCacheFieldCount
              && (authority > 0 || tokenTotal >= bestTokenTotal))) {
        best = message;
        bestAuthority = authority;
        bestCacheFieldCount = cacheFieldCount;
        bestTokenTotal = tokenTotal;
      }
    }
    return best;
  }

  private static int usageAuthority(JsonNode message) {
    JsonNode usage = JsonNodeReaders.objectChild(message, "usage");
    if (usage == null) {
      return 0;
    }
    if (!text(message, "stop_reason").isBlank()) {
      return 3;
    }
    if (usage.path("cache_read_input_tokens").isNumber()
        || usage.path("cache_creation_input_tokens").isNumber()) {
      return 2;
    }
    return longValue(usage, "output_tokens") > 0 ? 1 : 0;
  }

  private static Map<String, String> tokenPrecision(List<AssistantRecord> records) {
    Map<String, String> total = Map.of();
    for (AssistantRecord record : records) {
      JsonNode selected = selectUsageMessage(record.usageRows());
      JsonNode usage = JsonNodeReaders.objectChild(selected, "usage");
      // 非零 output 可用于无尾块的可观测值回退，但不能单独证明整行是正式最终 usage。
      boolean authoritative = usageAuthority(selected) >= 2;
      Map<String, String> precision = new LinkedHashMap<>();
      TOKEN_PRECISION_FIELDS.forEach(
          (key, field) ->
              precision.put(
                  key,
                  !authoritative
                      ? "unknown"
                      : usage.path(field).isNumber() ? "provider_reported" : "unavailable"));
      total = mergeTokenPrecision(total, precision);
    }
    return total;
  }

  private static Map<String, String> mergeTokenPrecision(
      Map<String, String> first, Map<String, String> second) {
    if (first.isEmpty() && second.isEmpty()) {
      return Map.of();
    }
    Map<String, String> merged = new LinkedHashMap<>();
    TOKEN_PRECISION_FIELDS.forEach(
        (key, field) -> {
          String left = first.get(key);
          String right = second.get(key);
          merged.put(
              key, left == null ? right : right == null || left.equals(right) ? left : "mixed");
        });
    Map.of(
            "estimated",
            "tokenContainsEstimated",
            "unavailable",
            "tokenContainsUnavailable",
            "unknown",
            "tokenContainsUnknown")
        .forEach(
            (state, key) -> {
              boolean contains =
                  Boolean.parseBoolean(first.get(key))
                      || Boolean.parseBoolean(second.get(key))
                      || first.containsValue(state)
                      || second.containsValue(state);
              merged.put(key, Boolean.toString(contains));
            });
    return Map.copyOf(merged);
  }

  private static long selectedUsageValue(JsonNode best, List<JsonNode> messages, String field) {
    if (best.path(field).isNumber()) {
      return longValue(best, field);
    }
    return messages.stream()
        .map(message -> JsonNodeReaders.objectChild(message, "usage"))
        .mapToLong(usage -> longValue(usage, field))
        .max()
        .orElse(0);
  }

  /** 在字段 presence 尚未丢失时裁定 usage，保留全部原始事件的定位、时间和内容。 */
  private static List<SourceRecord> resolveAssistantUsage(
      List<JsonNode> events, List<SourceRecord> records) {
    Map<String, List<JsonNode>> messages = new LinkedHashMap<>();
    for (SourceRecord record : records) {
      if (record.responseMessageId().filter(id -> !id.isBlank()).isPresent()) {
        JsonNode message = JsonNodeReaders.objectChild(events.get(record.eventIndex()), "message");
        if (JsonNodeReaders.objectChild(message, "usage") != null) {
          messages
              .computeIfAbsent(record.responseMessageId().get(), ignored -> new ArrayList<>())
              .add(message);
        }
      }
    }
    Map<String, UsageTotals> totals = new LinkedHashMap<>();
    messages.forEach((id, rows) -> totals.put(id, mergeUsage(rows)));
    return records.stream()
        .map(
            record -> {
              UsageTotals usage = record.responseMessageId().map(totals::get).orElse(null);
              if (!"assistant".equals(record.eventType())) {
                return record;
              }
              JsonNode message =
                  JsonNodeReaders.objectChild(events.get(record.eventIndex()), "message");
              String content = contentText(message == null ? null : message.get("content"));
              return new SourceRecord(
                  record.locator(),
                  record.eventIndex(),
                  record.eventType(),
                  record.callId(),
                  record.model(),
                  record.timestamp(),
                  record.turnId(),
                  usage == null
                      ? record.usage()
                      : new SourceRecordUsage(
                          usage.inputTokens(),
                          usage.cacheReadTokens(),
                          usage.cacheWriteTokens(),
                          usage.outputTokens(),
                          usage.provenance()),
                  record.toolCalls(),
                  record.toolUseId(),
                  record.toolName(),
                  record.toolError(),
                  record.relation(),
                  content.isEmpty() ? record.content() : content,
                  record.responseMessageId(),
                  record.responseStopReason(),
                  record.timing(),
                  record.metaContext(),
                  record.messageRole());
            })
        .toList();
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
  }

  /**
   * 表示 AssistantRecord 数据。
   *
   * @param usageRows 含原始 usage/stop_reason 的 message 行列表。
   * @param toolUses tool use 列表。
   */
  private record AssistantRecord(
      /* 含用量的原始 message 列表 */
      @NotNull List<JsonNode> usageRows,
      /* 工具调用条目列表 */
      @NotNull List<ToolUse> toolUses) {
    public AssistantRecord {
      ValidationSupport.validateCanonicalConstructor(AssistantRecord.class, usageRows, toolUses);
      usageRows = List.copyOf(usageRows);
      toolUses = List.copyOf(toolUses);
    }
  }

  /**
   * 表示 ToolUse 数据。
   *
   * @param id 标识符。
   * @param name 名称。
   */
  private record ToolUse(
      /* 工具调用标识符 */
      @NotBlank String id,
      /* 工具调用名称 */
      @NotBlank String name) {
    public ToolUse {
      ValidationSupport.validateCanonicalConstructor(ToolUse.class, id, name);
    }
  }

  /**
   * 表示 UsageTotals 数据。
   *
   * @param inputTokens 输入 token 数量。
   * @param cacheReadTokens cache read token 数量。
   * @param cacheWriteTokens cache write token 数量。
   * @param outputTokens output token 数量。
   * @param provenance 各 token 分量的来源精度。
   */
  private record UsageTotals(
      /* 输入 token 数量 */
      @PositiveOrZero long inputTokens,
      /* 缓存读取令牌数量 */
      @PositiveOrZero long cacheReadTokens,
      /* 缓存写入令牌数量 */
      @PositiveOrZero long cacheWriteTokens,
      /* 输出令牌数量 */
      @PositiveOrZero long outputTokens,
      @NotNull Map<String, String> provenance) {
    private static UsageTotals empty() {
      return new UsageTotals(0, 0, 0, 0, Map.of());
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
   * @param tokenPrecision 所有 sidechat 的计量来源精度和覆盖信息。
   */
  private record ClaudeSubagentTotals(
      /* subagent 实例数量 */
      @PositiveOrZero long subagentInstanceCount,
      /* 工具调用数量 */
      @PositiveOrZero long toolCallCount,
      /* 失败工具数量 */
      @PositiveOrZero long failedToolCount,
      /* 新鲜输入令牌数量 */
      @PositiveOrZero long freshInputTokens,
      /* 缓存读取令牌数量 */
      @PositiveOrZero long cacheReadTokens,
      /* 缓存写入令牌数量 */
      @PositiveOrZero long cacheWriteTokens,
      /* 输出令牌数量 */
      @PositiveOrZero long outputTokens,
      @NotNull Map<String, String> tokenPrecision) {
    private static ClaudeSubagentTotals empty() {
      return new ClaudeSubagentTotals(0, 0, 0, 0, 0, 0, 0, Map.of());
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
          outputTokens,
          tokenPrecision);
    }

    private ClaudeSubagentTotals plus(ClaudeSubagentTotals other) {
      return new ClaudeSubagentTotals(
          subagentInstanceCount + other.subagentInstanceCount,
          toolCallCount + other.toolCallCount,
          failedToolCount + other.failedToolCount,
          freshInputTokens + other.freshInputTokens,
          cacheReadTokens + other.cacheReadTokens,
          cacheWriteTokens + other.cacheWriteTokens,
          outputTokens + other.outputTokens,
          mergeTokenPrecision(tokenPrecision, other.tokenPrecision));
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
            (diagnostics, eventCount) -> {},
            ClaudeSourceAdapter::resolveAssistantUsage);
    if (!(primary instanceof SourceResult.Success)) return primary;
    List<Path> sidecars = subagentFiles(Path.of(candidate.fingerprint().locator()));
    // 没有消费 primary 时直接转移其所有权，不能在返回前关闭。
    if (sidecars.isEmpty()) return primary;
    return mergeSidecars(candidate, cancellation, (SourceResult.Success) primary, sidecars);
  }

  private SourceResult mergeSidecars(
      Candidate candidate,
      CancellationSignal cancellation,
      SourceResult.Success success,
      List<Path> sidecars) {
    SourceResult.Fatal originalFailure = null;
    try (success) {
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
                (ignored, eventCount) -> {},
                ClaudeSourceAdapter::resolveAssistantUsage);
        if (sidecarResult instanceof SourceResult.Success) {
          try (var sidecarSuccess = (SourceResult.Success) sidecarResult) {
            diagnostics.addAll(sidecarSuccess.diagnostics());
            records.addAll(sidecarSuccess.records());
            candidateCount += sidecarSuccess.candidateCount();
          }
        } else if (sidecarResult instanceof SourceResult.Fatal fatal) {
          originalFailure = fatal;
          return fatal;
        }
      }
      return new SourceResult.Success(
          diagnostics, candidateCount, records, success.fingerprint(), success.locator());
    } catch (IOException close) {
      String detail = "Claude 合并资源关闭失败: " + close.getMessage();
      return originalFailure == null
          ? new SourceResult.Fatal(List.of(), detail)
          : new SourceResult.Fatal(
              originalFailure.diagnostics(), originalFailure.message() + "; " + detail);
    }
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
   * @param tokenPrecision 主会话计量来源精度和覆盖信息。
   */
  private record ClaudeCandidateMetadata(
      @NotNull String cwd,
      @NotNull String title,
      @NotNull String model,
      @NotNull String gitBranch,
      @NotNull Map<String, String> tokenPrecision) {
    private static ClaudeCandidateMetadata empty() {
      return new ClaudeCandidateMetadata("", "", "", "", Map.of());
    }
  }
}
