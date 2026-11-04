package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.web.api.DashboardApiResponses.RatioDto;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Session Detail API-first 页面使用的 main parity 分析器。 */
final class SessionDetailParityAnalyzer {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final ZoneId DISPLAY_ZONE = ZoneId.of("Asia/Shanghai");
  private static final DateTimeFormatter DATE_TIME =
      DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss").withZone(DISPLAY_ZONE);
  private static final DateTimeFormatter DATE =
      DateTimeFormatter.ofPattern("yyyy-MM-dd").withZone(DISPLAY_ZONE);
  private static final DateTimeFormatter TIME =
      DateTimeFormatter.ofPattern("HH:mm:ss").withZone(DISPLAY_ZONE);
  private static final Pattern EXIT_FAILURE =
      Pattern.compile("(?i)(?:process exited with code|exit code:|exit status)\\s+([1-9][0-9]*)");
  private static final Pattern CJK =
      Pattern.compile("[\\u4e00-\\u9fff\\u3040-\\u309f\\u30a0-\\u30ff\\uac00-\\ud7af]");
  private static final Pattern ASCII = Pattern.compile("[\\x20-\\x7e]");
  private static final Pattern CODE_PUNCT =
      Pattern.compile("[{}()\\[\\]\\\"'\\\\;:,.<>+=~`/@#$%^&*|]");
  private static final String FIELD_CONTENT = "content";
  private static final String FIELD_FAILED_TOOLS = "failedTools";
  private static final String FIELD_FAILED_TOOLS_RATE = "failedToolsRate";
  private static final String FIELD_OUTPUT = "output";
  private static final String FIELD_TOKENS = "tokens";
  private static final String FIELD_TOOL = "tool";
  private static final String FIELD_TYPE = "type";
  private static final String ISSUE_PAYLOAD_GAP = "Payload gap";
  private static final String SCOPE_MAIN = "main";
  private static final String SCOPE_SUBAGENT = "subagent";
  private static final String STATUS_AVAILABLE = "available";
  private static final String TONE_CRITICAL = "critical";

  private SessionDetailParityAnalyzer() {}

  /** 构建 Session Detail parity 结果。 */
  static Result analyze(SessionDetail detail) {
    return analyze(detail, null);
  }

  /** 构建 Session Detail parity 结果。 */
  static Result analyze(SessionDetail detail, NormalizedSessionArtifact artifact) {
    return analyze(detail, artifact, true);
  }

  /** 导入分析仅信任已归一化的上传内容，不探测本机原路径或相邻会话。 */
  static Result analyze(
      SessionDetail detail, NormalizedSessionArtifact artifact, boolean allowSourceFiles) {
    Objects.requireNonNull(detail, "detail must not be null");
    SessionRecord row = detail.sessionRow();
    String sourcePath = allowSourceFiles ? resolveSessionFilePath(detail, row, artifact) : "";
    RolloutStats parent = RolloutStats.empty(sourcePath);
    if (artifact == null && !sourcePath.isBlank()) {
      parent = parseRollout(Path.of(sourcePath), SCOPE_MAIN, SCOPE_MAIN, false);
    }
    List<RolloutStats> children =
        artifact == null && !sourcePath.isBlank()
            ? discoverChildRollouts(Path.of(sourcePath), row.sessionId()).stream()
                .map(path -> parseRollout(path, SCOPE_SUBAGENT, row.sessionId(), true))
                .filter(stats -> !stats.sessionId.isBlank())
                .toList()
            : List.of();
    if (artifact != null) {
      // 查询冻结制品时不能重读持续变化的原文件，或从相邻文件注入未索引的子会话。
      children = populateArtifactStats(parent, artifact, row.sessionId(), allowSourceFiles);
    }

    Map<String, RolloutStats> childrenById = new HashMap<>();
    for (RolloutStats child : children) {
      childrenById.put(child.sessionId, child);
    }
    for (ToolEvent tool : parent.tools.values()) {
      if (artifact == null) {
        String childId = extractAgentId(tool.output);
        if (!childId.isBlank() && childrenById.containsKey(childId)) {
          tool.subagentId = childId;
        }
      }
    }

    Map<Integer, RoundParity> rounds =
        buildRoundParity(
            detail.rounds(), parent, row.sessionId(), artifact, measuredCacheInput(row));
    long subagentCalls = children.stream().mapToLong(child -> child.llmCalls).sum();
    long mainCalls = parent.llmCalls > 0 ? parent.llmCalls : detail.roundCount();
    if (artifact != null) {
      // 计数必须与 Trace 使用同一归一化集合，不能再把累计 usage 的响应分片算作多次调用。
      mainCalls = artifact.calls().stream().filter(call -> call.scope() == CallScope.MAIN).count();
      subagentCalls = artifact.calls().size() - mainCalls;
    }
    long workload = mainCalls + subagentCalls;
    long totalTools =
        artifact == null
            ? row.toolCallCount()
            : parent.tools.size() + children.stream().mapToLong(child -> child.tools.size()).sum();
    long failedTools =
        artifact == null
            ? row.failedToolCount()
            : parent.tools.values().stream().filter(tool -> tool.failed).count()
                + children.stream()
                    .flatMap(child -> child.tools.values().stream())
                    .filter(tool -> tool.failed)
                    .count();
    long subagentRuns = artifact == null ? row.subagentInstanceCount() : children.size();
    long inputSide = row.freshInputTokens() + row.cacheReadTokens() + row.cacheWriteTokens();
    long lowCacheRounds = rounds.values().stream().filter(round -> round.lowCache).count();
    long freshSpikeRounds = rounds.values().stream().filter(round -> round.freshSpike).count();

    List<IssueSeed> issues = buildIssues(rounds);
    long payloadGaps = issues.stream().filter(seed -> ISSUE_PAYLOAD_GAP.equals(seed.issue)).count();
    int issueRounds =
        (int)
            rounds.values().stream()
                .filter(round -> round.hasIssues() || !round.issueSeeds.isEmpty())
                .count();
    long attributionGaps = 0;

    RunIssueSummary issueSummary =
        new RunIssueSummary(
            totalTools, failedTools, payloadGaps, attributionGaps, issueRounds, issues);
    Map<String, Object> diagnostics =
        diagnosticsMap(
            new DiagnosticsInput(
                row, sourcePath, parent, children, rounds, issueSummary, mainCalls));
    Map<String, Object> metrics =
        metricsMap(
            new MetricsInput(
                row,
                mainCalls,
                subagentCalls,
                workload,
                subagentRuns,
                inputSide,
                lowCacheRounds,
                freshSpikeRounds,
                issueSummary));
    Map<String, Object> meta = metaMap(row, sourcePath);
    return new Result(meta, metrics, diagnostics, rounds);
  }

  private static List<RolloutStats> populateArtifactStats(
      RolloutStats parent,
      NormalizedSessionArtifact artifact,
      String sessionId,
      boolean allowSourceFiles) {
    parent.sessionId = sessionId;
    Map<String, RolloutStats> children = new LinkedHashMap<>();
    Map<String, RolloutStats> callOwners = new HashMap<>();
    for (NormalizedCall call : artifact.calls()) {
      RolloutStats owner =
          call.scope() == CallScope.MAIN
              ? parent
              : artifactChild(children, call.subagentId().orElse(""), sessionId);
      owner.llmCalls++;
      owner.llmTokens += call.usage().total();
      owner.addUsage(
          new UsageDelta(
              call.usage().fresh(),
              call.usage().cacheRead(),
              call.usage().cacheWrite(),
              call.usage().output()),
          TokenProvenance.fromMetadata(call.usageSource()));
      owner.tokenUsageBasis = "artifact_call_usage";
      owner.inputSideTokens +=
          call.usage().fresh() + call.usage().cacheRead() + call.usage().cacheWrite();
      if (call.scope() == CallScope.SUBAGENT) {
        owner.agentType = call.parentToolName().orElse(SCOPE_SUBAGENT);
      }
      callOwners.put(call.callId(), owner);
    }
    Map<String, String> outputs = PayloadCallContentExtractor.extractToolResultContents(artifact);
    for (NormalizedToolExecution execution : artifact.toolExecutions()) {
      RolloutStats owner = parent;
      if (execution.scope() == CallScope.SUBAGENT) {
        owner = callOwners.get(execution.declaredByCallId());
        if (owner == null || Objects.equals(owner, parent)) {
          owner = artifactChild(children, execution.subagentId().orElse(""), sessionId);
        }
      }
      ToolEvent tool = new ToolEvent(execution.toolCallId(), execution.name(), owner.scope, "", 0);
      tool.failed = hasFailedStatus(execution);
      tool.output = outputs.getOrDefault(execution.toolCallId(), "");
      tool.resultTokens = estimateTokens(tool.output);
      owner.tools.putIfAbsent(tool.id, tool);
    }
    if (allowSourceFiles) {
      for (var sourceFile : artifact.sourceFiles()) {
        RolloutStats child = children.get(sourceFile.subagentId().orElse(null));
        if (child != null) child.path = sourceFile.path().toString();
      }
    }
    return List.copyOf(children.values());
  }

  private static RolloutStats artifactChild(
      Map<String, RolloutStats> children, String childId, String sessionId) {
    return children.computeIfAbsent(
        childId,
        id -> {
          RolloutStats child = new RolloutStats("", SCOPE_SUBAGENT, sessionId);
          child.sessionId = id;
          return child;
        });
  }

  private static boolean hasFailedStatus(NormalizedToolExecution execution) {
    return execution.status().filter(status -> !status.isBlank()).isPresent()
        || execution.exitCode().filter(code -> code != 0).isPresent();
  }

  private static String resolveSessionFilePath(
      SessionDetail detail, SessionRecord row, NormalizedSessionArtifact artifact) {
    if (!row.filePath().isBlank() && Files.isRegularFile(Path.of(row.filePath()))) {
      return row.filePath();
    }
    if (artifact != null && !detail.artifactPath().isBlank()) {
      for (var sourceFile : artifact.sourceFiles()) {
        Path path = sourceFile.path();
        if (path != null && Files.isRegularFile(path)) {
          return path.toString();
        }
      }
    }
    return "";
  }

  private static List<Path> discoverChildRollouts(Path parentPath, String parentSessionId) {
    if (parentPath == null || parentPath.getParent() == null || parentSessionId.isBlank()) {
      return List.of();
    }
    List<Path> result = new ArrayList<>();
    // 1. 兼容旧格式：在父 session 同目录查找子 rollout
    try (var stream = Files.list(parentPath.getParent())) {
      stream
          .filter(path -> !path.equals(parentPath))
          .filter(path -> path.getFileName().toString().endsWith(".jsonl"))
          .sorted()
          .forEach(
              path -> {
                if (isChildRollout(path, parentSessionId)) {
                  result.add(path);
                }
              });
    } catch (IOException ignored) {
      // 回退到 subagent 目录发现
    }
    // 2. Claude Code subagent 目录（session 目录下的 subagents 子目录）
    Path subagentDir = parentPath.getParent().resolve(parentSessionId).resolve("subagents");
    if (Files.isDirectory(subagentDir)) {
      try (var stream = Files.list(subagentDir)) {
        stream
            .filter(path -> path.getFileName().toString().startsWith("agent-"))
            .filter(path -> path.getFileName().toString().endsWith(".jsonl"))
            .sorted()
            .forEach(result::add);
      } catch (IOException ignored) {
        // 忽略读取异常
      }
    }
    return List.copyOf(result);
  }

  private static boolean isChildRollout(Path path, String parentSessionId) {
    try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
      String line;
      while ((line = reader.readLine()) != null) {
        JsonNode root = MAPPER.readTree(line);
        if (!"session_meta".equals(text(root, FIELD_TYPE))) {
          continue;
        }
        JsonNode payload = root.path("payload");
        String parent = text(payload, "parent_thread_id");
        if (parent.isBlank()) {
          parent =
              payload
                  .path("source")
                  .path(SCOPE_SUBAGENT)
                  .path("thread_spawn")
                  .path("parent_thread_id")
                  .asText("");
        }
        return parentSessionId.equals(parent);
      }
    } catch (IOException ignored) {
      return false;
    }
    return false;
  }

  private static RolloutStats parseRollout(
      Path path, String scope, String parentSessionId, boolean child) {
    RolloutStats stats = new RolloutStats(path.toString(), scope, parentSessionId);
    // Claude Code subagent 文件：从文件名提取 agentId，从 .meta.json 读取 agentType
    if (child && stats.sessionId.isBlank()) {
      String filename = path.getFileName().toString();
      if (filename.startsWith("agent-") && filename.endsWith(".jsonl")) {
        stats.sessionId =
            filename.substring("agent-".length(), filename.length() - ".jsonl".length());
      }
      Path metaJson = path.resolveSibling(filename.replace(".jsonl", ".meta.json"));
      if (Files.isRegularFile(metaJson)) {
        try {
          JsonNode meta = MAPPER.readTree(Files.readString(metaJson, StandardCharsets.UTF_8));
          String agentType = text(meta, "agentType");
          if (!agentType.isBlank()) {
            stats.agentType = agentType;
          }
        } catch (IOException ignored) {
          // 忽略读取异常
        }
      }
    }
    Map<String, Long> previousUsage = new HashMap<>();
    long previousTotal = -1;
    String pendingAssistant = "";
    String pendingUser = "";
    List<String> pendingToolNames = new ArrayList<>();
    List<String> pendingToolInputPreviews = new ArrayList<>();
    try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
      String line;
      int index = 0;
      while ((line = reader.readLine()) != null) {
        index++;
        JsonNode root = MAPPER.readTree(line);
        String timestamp = text(root, "timestamp");
        String type = text(root, FIELD_TYPE);
        JsonNode payload = root.path("payload");
        if ("session_meta".equals(type)) {
          stats.sessionId = firstNonBlank(text(payload, "id"), text(payload, "session_id"));
          stats.agentType = firstNonBlank(text(payload, "agent_role"), SCOPE_SUBAGENT);
          stats.startedAt = firstNonBlank(text(payload, "timestamp"), timestamp);
          continue;
        }
        if ("response_item".equals(type)) {
          String responseToolName = handleResponseItem(stats, payload, timestamp, index);
          if (!responseToolName.isBlank()) {
            pendingToolNames.add(responseToolName);
            pendingToolInputPreviews.add("");
          }
          String payloadType = text(payload, FIELD_TYPE);
          if ("message".equals(payloadType)) {
            String role = text(payload, "role");
            String messageText = messageText(payload.path(FIELD_CONTENT));
            if ("assistant".equals(role) && !messageText.isBlank()) {
              pendingAssistant = messageText;
            } else if ("user".equals(role) && isVisibleUserInput(messageText)) {
              pendingUser = messageText;
            }
          }
          continue;
        }
        if ("user".equals(type)) {
          // Claude Code subagent 文件：从首行提取 agentId（如果尚未设置）
          if (child && stats.sessionId.isBlank()) {
            String agentId = text(root, "agentId");
            if (!agentId.isBlank()) {
              stats.sessionId = agentId;
            }
          }
          String messageText = userVisibleMessageText(root.path("message").path(FIELD_CONTENT));
          if (isVisibleUserInput(messageText)) {
            pendingUser = messageText;
          }
          // 从 Claude Code / Qoder 原生格式提取 tool_result blocks
          JsonNode content = root.path("message").path(FIELD_CONTENT);
          if (content.isArray()) {
            final int lineIndex = index;
            for (JsonNode part : content) {
              if ("tool_result".equals(text(part, FIELD_TYPE))) {
                String callId = text(part, "tool_use_id");
                if (!callId.isBlank()) {
                  ToolEvent tool =
                      stats.tools.computeIfAbsent(
                          callId,
                          id -> new ToolEvent(id, FIELD_TOOL, stats.scope, timestamp, lineIndex));
                  JsonNode resultContent = part.path(FIELD_CONTENT);
                  if (resultContent.isArray()) {
                    StringBuilder sb = new StringBuilder();
                    for (JsonNode rp : resultContent) {
                      String t = text(rp, "text");
                      if (!t.isBlank()) {
                        if (sb.length() > 0) sb.append("\n");
                        sb.append(t);
                      }
                    }
                    tool.output = sb.toString();
                  } else if (resultContent.isTextual()) {
                    tool.output = resultContent.asText("");
                  }
                  tool.failed =
                      part.path("is_error").asBoolean(false) || isFailedOutput(tool.output);
                  tool.resultTokens = estimateTokens(tool.output);
                }
              }
            }
          }
          continue;
        }
        if ("assistant".equals(type)) {
          JsonNode message = root.path("message");
          String messageText = messageText(message.path(FIELD_CONTENT));
          if (!messageText.isBlank()) {
            pendingAssistant = messageText;
          }
          // 从 Claude Code / Qoder 原生格式提取 tool_use blocks
          JsonNode content = message.path(FIELD_CONTENT);
          if (content.isArray()) {
            for (JsonNode part : content) {
              if ("tool_use".equals(text(part, FIELD_TYPE))) {
                String callId = text(part, "id");
                if (!callId.isBlank()) {
                  String name = firstNonBlank(text(part, "name"), FIELD_TOOL);
                  ToolEvent toolEvent = new ToolEvent(callId, name, stats.scope, timestamp, index);
                  toolEvent.inputPreview = extractToolUseInputPreview(name, part);
                  stats.tools.put(callId, toolEvent);
                  if (!name.isBlank() && !FIELD_TOOL.equals(name)) {
                    pendingToolNames.add(name);
                    pendingToolInputPreviews.add(toolEvent.inputPreview);
                  }
                }
              }
            }
          }
          UsageDelta usage = usageFromMessage(message.path("usage"));
          boolean hasStopReason = !text(message, "stop_reason").isBlank();
          if (usage.output > 0 || hasStopReason) {
            recordLlmRound(
                stats,
                usage,
                pendingUser,
                pendingAssistant,
                pendingToolNames,
                pendingToolInputPreviews,
                timestamp);
            pendingAssistant = "";
            pendingUser = "";
            pendingToolNames = new ArrayList<>();
            pendingToolInputPreviews = new ArrayList<>();
          }
          continue;
        }
        if ("event_msg".equals(type) && "token_count".equals(text(payload, FIELD_TYPE))) {
          JsonNode total = payload.path("info").path("total_token_usage");
          long totalTokens = total.path("total_tokens").asLong(-1);
          if (totalTokens >= 0 && totalTokens == previousTotal) {
            continue;
          }
          previousTotal = totalTokens;
          UsageDelta usage = usageDelta(total, previousUsage);
          if (usage.total <= 0 && totalTokens > 0 && stats.llmCalls > 0) {
            continue;
          }
          recordLlmRound(
              stats,
              usage,
              pendingUser,
              pendingAssistant,
              pendingToolNames,
              pendingToolInputPreviews,
              timestamp);
          pendingAssistant = "";
          pendingUser = "";
          pendingToolNames = new ArrayList<>();
          pendingToolInputPreviews = new ArrayList<>();
        }
      }
    } catch (IOException ignored) {
      return stats;
    }
    for (ToolEvent tool : stats.tools.values()) {
      tool.resultTokens = estimateTokens(tool.output);
      tool.failed |= isFailedOutput(tool.output);
    }
    return stats;
  }

  private static UsageDelta usageFromMessage(JsonNode usage) {
    if (usage == null || !usage.isObject()) {
      return new UsageDelta(0, 0, 0, 0);
    }
    long fresh = usage.path("input_tokens").asLong(0);
    long cacheRead =
        firstPositive(
            usage.path("cache_read_input_tokens").asLong(0),
            usage.path("cached_input_tokens").asLong(0));
    long cacheWrite = usage.path("cache_creation_input_tokens").asLong(0);
    long output = usage.path("output_tokens").asLong(0);
    return new UsageDelta(fresh, cacheRead, cacheWrite, output);
  }

  private static void recordLlmRound(
      RolloutStats stats,
      UsageDelta usage,
      String pendingUser,
      String pendingAssistant,
      List<String> pendingToolNames,
      List<String> pendingToolInputPreviews,
      String timestamp) {
    stats.llmCalls++;
    stats.inputSideTokens += usage.fresh + usage.cacheRead + usage.cacheWrite;
    stats.llmTokens += usage.total;
    stats.addUsage(usage, TokenProvenance.unknown());
    String summary = firstNonBlank(pendingUser, pendingAssistant);
    if (summary.isBlank()) {
      summary = toolSummaryLabel(pendingToolNames, pendingToolInputPreviews);
    }
    stats.roundSummaries.add(
        new RawRoundSummary(stats.llmCalls, summary, localTime(timestamp), !pendingUser.isBlank()));
  }

  private static String handleResponseItem(
      RolloutStats stats, JsonNode payload, String timestamp, int index) {
    String payloadType = text(payload, FIELD_TYPE);
    if ("function_call".equals(payloadType) || "custom_tool_call".equals(payloadType)) {
      String callId = text(payload, "call_id");
      if (callId.isBlank()) {
        return "";
      }
      String name = firstNonBlank(text(payload, "name"), FIELD_TOOL);
      stats.tools.put(callId, new ToolEvent(callId, name, stats.scope, timestamp, index));
      return !name.isBlank() && !FIELD_TOOL.equals(name) ? name : "";
    }
    if ("function_call_output".equals(payloadType)
        || "custom_tool_call_output".equals(payloadType)) {
      String callId = text(payload, "call_id");
      if (callId.isBlank()) {
        return "";
      }
      ToolEvent tool =
          stats.tools.computeIfAbsent(
              callId, id -> new ToolEvent(id, FIELD_TOOL, stats.scope, timestamp, index));
      tool.output =
          payload.path(FIELD_OUTPUT).isMissingNode() ? "" : payload.path(FIELD_OUTPUT).asText("");
      tool.failed = isFailedOutput(tool.output);
    }
    return "";
  }

  private static UsageDelta usageDelta(JsonNode total, Map<String, Long> previousUsage) {
    long input = total.path("input_tokens").asLong(0);
    long cached = total.path("cached_input_tokens").asLong(0);
    long output = total.path("output_tokens").asLong(0);
    long cacheWrite = total.path("cache_creation_input_tokens").asLong(0);
    long deltaInput = Math.max(input - previousUsage.getOrDefault("input", 0L), 0);
    long deltaCached = Math.max(cached - previousUsage.getOrDefault("cached", 0L), 0);
    long deltaOutput = Math.max(output - previousUsage.getOrDefault(FIELD_OUTPUT, 0L), 0);
    long deltaWrite = Math.max(cacheWrite - previousUsage.getOrDefault("write", 0L), 0);
    previousUsage.put("input", input);
    previousUsage.put("cached", cached);
    previousUsage.put(FIELD_OUTPUT, output);
    previousUsage.put("write", cacheWrite);
    long fresh = Math.max(deltaInput - deltaCached, 0);
    return new UsageDelta(fresh, deltaCached, deltaWrite, deltaOutput);
  }

  private static Map<Integer, RoundParity> buildRoundParity(
      List<CallRound> detailRounds,
      RolloutStats parent,
      String sessionId,
      NormalizedSessionArtifact artifact,
      boolean measuredInput) {
    List<Long> freshValues =
        detailRounds.stream().map(CallRound::freshInputTokens).sorted().toList();
    double medianFresh = median(freshValues);
    Set<String> recordedResults = artifact == null ? Set.of() : recordedToolResultIds(artifact);
    Set<String> failedIds = new HashSet<>();
    for (ToolEvent tool : parent.tools.values()) {
      if (tool.failed) {
        failedIds.add(tool.id);
      }
    }
    if (artifact != null) {
      artifact.toolExecutions().stream()
          .filter(SessionDetailParityAnalyzer::hasFailedStatus)
          .map(NormalizedToolExecution::toolCallId)
          .forEach(failedIds::add);
    }
    Map<Integer, RoundParity> result = new LinkedHashMap<>();
    for (CallRound round : detailRounds) {
      List<String> executionIds =
          artifact == null
              ? round.toolCallIds()
              : RoundIndexProjection.project(round, artifact).toolCallIds();
      List<String> failedInRound =
          executionIds.stream()
              .filter(
                  id ->
                      failedIds.contains(id)
                          || (artifact == null && round.failedToolCallIds().contains(id)))
              .distinct()
              .toList();
      long inputSide =
          round.freshInputTokens() + round.cacheReadTokens() + round.cacheWriteTokens();
      boolean lowCache =
          measuredInput && inputSide > 0 && (round.cacheReadTokens() * 100.0 / inputSide) < 20.0;
      boolean freshSpike = medianFresh > 0 && round.freshInputTokens() > medianFresh * 2.0;
      RawRoundSummary raw = parent.roundSummary(round.roundIndex());
      RoundParity parity = new RoundParity(round.roundIndex());
      parity.summary = firstNonBlank(raw.summary, "Round " + round.roundIndex());
      parity.time = firstNonBlank(raw.time, "");
      parity.userInput = raw.userInput;
      if (artifact != null) {
        RoundContentProjection content = RoundContentProjection.from(round, artifact);
        parity.summary = content.summary();
        parity.time = content.time();
        parity.userInput = content.userInput();
      }
      parity.lowCache = lowCache;
      parity.freshSpike = freshSpike;
      parity.failedToolIds.addAll(failedInRound);
      if (artifact != null) {
        addArtifactIssues(parity, round, artifact, sessionId, recordedResults);
      } else if (!failedInRound.isEmpty()) {
        parity.signals.add("Failed");
        for (String failedId : failedInRound) {
          parity.issueSeeds.add(
              new IssueSeed(
                  "Tool failure",
                  parent.toolName(failedId) + " · failed",
                  round.roundIndex(),
                  sessionId + " + R" + round.roundIndex() + " + " + failedId,
                  TONE_CRITICAL));
        }
      }
      result.put(round.roundIndex(), parity);
    }
    return result;
  }

  private static void addArtifactIssues(
      RoundParity parity,
      CallRound round,
      NormalizedSessionArtifact artifact,
      String sessionId,
      Set<String> recordedResults) {
    Set<String> failureIds = new HashSet<>();
    for (NormalizedToolExecution execution : artifact.toolExecutions()) {
      if (!round.calls().contains(execution.declaredByCallId())
          || !hasFailedStatus(execution)
          || !failureIds.add(execution.toolCallId())) continue;
      boolean child = execution.scope() == CallScope.SUBAGENT;
      String signal = child ? "Subagent failed" : "Failed";
      if (!parity.signals.contains(signal)) parity.signals.add(signal);
      parity.issueSeeds.add(
          new IssueSeed(
              "Tool failure",
              (child ? "Subagent · " : "")
                  + execution.name()
                  + " · "
                  + execution.status().filter(status -> !status.isBlank()).orElse("failed")
                  + execution.exitCode().map(code -> " · exit " + code).orElse(""),
              round.roundIndex(),
              sessionId + " + " + execution.declaredByCallId() + " + " + execution.toolCallId(),
              TONE_CRITICAL));
    }
    Set<String> displayedCalls =
        Set.copyOf(RoundIndexProjection.project(round, artifact).callIds());
    for (NormalizedCall call : artifact.calls()) {
      if (!round.calls().contains(call.callId())) continue;
      Set<String> missingRefs = missingSourceRefs(call, artifact);
      for (String resultId : call.request().toolResultIds()) {
        if (!recordedResults.contains(resultId)) missingRefs.add("tool-result:" + resultId);
      }
      for (String missing : missingRefs) {
        boolean displayed = displayedCalls.contains(call.callId());
        parity.payloadGap |= displayed;
        String signal = displayed ? "Payload Gap" : "Subagent payload gap";
        if (!parity.signals.contains(signal)) parity.signals.add(signal);
        parity.issueSeeds.add(
            new IssueSeed(
                ISSUE_PAYLOAD_GAP,
                call.callKey() + " · payload reference missing",
                round.roundIndex(),
                sessionId + " + " + call.callId() + " + " + missing,
                "warning"));
      }
    }
  }

  private static Set<String> recordedToolResultIds(NormalizedSessionArtifact artifact) {
    Set<String> ids = new HashSet<>();
    for (NormalizedCall call : artifact.calls()) {
      call.sourceUnits().forEach(unit -> collectToolResultIds(unit, ids));
    }
    for (var entry : artifact.sourceUnitCatalog().values()) {
      if (isToolResultType(entry.unitType())) entry.label().ifPresent(ids::add);
      collectToolResultIds(entry.payload(), ids);
    }
    return ids;
  }

  private static void collectToolResultIds(Object value, Set<String> ids) {
    if (value instanceof Map<?, ?> map) {
      if (isToolResultType(String.valueOf(map.get(FIELD_TYPE)))) {
        for (String field : List.of("tool_call_id", "tool_use_id", "call_id")) {
          if (map.get(field) instanceof String id && !id.isBlank()) {
            ids.add(id);
            break;
          }
        }
      }
      map.values().forEach(nested -> collectToolResultIds(nested, ids));
    } else if (value instanceof List<?> list) {
      list.forEach(nested -> collectToolResultIds(nested, ids));
    }
  }

  private static boolean isToolResultType(String type) {
    return List.of("tool_result", "function_call_output", "custom_tool_call_output").contains(type);
  }

  private static Set<String> missingSourceRefs(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    Set<String> missing = new LinkedHashSet<>();
    for (var range : call.sourceUnitRefRanges()) {
      if (!range.refs().isEmpty()) {
        for (String ref : range.refs()) {
          if (!artifact.sourceUnitCatalog().containsKey(ref)) missing.add(ref);
        }
      } else if (range.sequence().isPresent()) {
        String name = range.sequence().get();
        List<String> sequence = artifact.sourceUnitSequences().getOrDefault(name, List.of());
        // 越界范围是一项不可解析引用，不能按不可信的end扩展出任意数量的伪payload。
        if (range.end() > Math.max(range.start(), sequence.size())) {
          missing.add(
              name + "[" + Math.max(range.start(), sequence.size()) + ":" + range.end() + "]");
        }
        for (int index = range.start(); index < Math.min(range.end(), sequence.size()); index++) {
          if (!artifact.sourceUnitCatalog().containsKey(sequence.get(index))) {
            missing.add(sequence.get(index));
          }
        }
      }
    }
    return missing;
  }

  private static List<IssueSeed> buildIssues(Map<Integer, RoundParity> rounds) {
    List<IssueSeed> critical = new ArrayList<>();
    List<IssueSeed> warnings = new ArrayList<>();
    for (RoundParity round : rounds.values()) {
      for (IssueSeed seed : round.issueSeeds) {
        if (TONE_CRITICAL.equals(seed.tone)) {
          critical.add(seed);
        } else {
          warnings.add(seed);
        }
      }
    }
    critical.sort(Comparator.comparingInt(seed -> seed.roundId));
    warnings.sort(Comparator.comparingInt(seed -> seed.roundId));
    List<IssueSeed> all = new ArrayList<>(critical);
    all.addAll(warnings);
    return List.copyOf(all);
  }

  private static Map<String, Object> metaMap(SessionRecord row, String sourcePath) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("sessionFilePath", sourcePath);
    map.put("agentLabel", agentLabel(row.agent()));
    map.put("date", localDate(row.startedAt()));
    map.put("updatedLocal", localDateTime(row.endedAt()));
    return map;
  }

  private static boolean measuredCacheInput(SessionRecord row) {
    var precision = row.tokenProvenance();
    return "provider_reported".equals(precision.freshInput())
        && "provider_reported".equals(precision.cacheRead())
        && "provider_reported".equals(precision.cacheWrite());
  }

  private static Map<String, Object> metricsMap(MetricsInput input) {
    SessionRecord row = input.row;
    RunIssueSummary issueSummary = input.issueSummary;
    long totalTools = issueSummary.totalTools;
    long failedTools = issueSummary.failedTools;
    long inputSide = input.inputSide;
    long payloadGaps = issueSummary.payloadGaps;
    long attributionGaps = issueSummary.attributionGaps;
    long totalTokens =
        row.freshInputTokens()
            + row.cacheReadTokens()
            + row.cacheWriteTokens()
            + row.outputTokens();
    SessionTiming timing = row.timing();
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("mainCalls", input.mainCalls);
    map.put("subagentCalls", input.subagentCalls);
    map.put("workloadCalls", input.workload);
    map.put("toolCalls", totalTools);
    map.put(FIELD_FAILED_TOOLS, failedTools);
    map.put(FIELD_FAILED_TOOLS_RATE, ratioLabel(failedTools, totalTools));
    map.put("subagentRuns", input.subagentRuns);
    map.put("inputSideTokens", inputSide);
    map.put("lowCacheRoundsAvailable", measuredCacheInput(row));
    if (measuredCacheInput(row)) {
      map.put("lowCacheRounds", input.lowCacheRounds);
    }
    map.put("freshSpikeRounds", input.freshSpikeRounds);
    map.put("payloadGaps", payloadGaps);
    map.put("attributionGaps", attributionGaps);
    map.put("issueRounds", issueSummary.issueRounds);
    map.put(
        "runHealth",
        hasRunIssues(failedTools, payloadGaps, attributionGaps)
            ? "Completed with issue signals"
            : "Completed");
    Double active =
        ApiSessionTimings.available(timing.activeTaskSeconds(), timing.activeTaskPrecision());
    map.put("activeTimeAvailable", active != null);
    if (active != null) {
      map.put("activeSeconds", active);
      if ("measured".equals(timing.activeTaskPrecision()) && timing.wallSeconds() != null) {
        map.put(
            "nonTaskWallSeconds", Math.max(timing.wallSeconds() - timing.activeTaskSeconds(), 0));
      }
    }
    map.put(
        "modelTimeAvailable",
        ApiSessionTimings.available(
                timing.modelExecutionSeconds(), timing.modelExecutionPrecision())
            != null);
    map.put(
        "toolTimeAvailable",
        ApiSessionTimings.available(timing.toolExecutionSeconds(), timing.toolExecutionPrecision())
            != null);
    map.put("freshShare", ratioLabel(row.freshInputTokens(), totalTokens));
    map.put("cacheReadShare", ratioLabel(row.cacheReadTokens(), totalTokens));
    map.put("cacheWriteShare", ratioLabel(row.cacheWriteTokens(), totalTokens));
    map.put("outputShare", ratioLabel(row.outputTokens(), totalTokens));
    RatioDto cacheRatio =
        RatioDto.of(
            inputSide > 0 ? row.cacheReadTokens() / (double) inputSide : null,
            row.tokenProvenance());
    map.put(
        "cacheReuse",
        cacheRatio.value() == null
            ? "N/A"
            : String.format(
                Locale.ROOT,
                "%.1f%%%s",
                cacheRatio.value() * 100,
                cacheRatio.reason().isEmpty() ? "" : " · Partial"));
    map.put("cacheReuseReason", cacheRatio.reason());
    map.put("updatedLocal", localDateTime(row.endedAt()));
    return map;
  }

  private static Map<String, Object> diagnosticsMap(DiagnosticsInput input) {
    RunIssueSummary issueSummary = input.issueSummary;
    long totalTools = issueSummary.totalTools;
    long failedTools = issueSummary.failedTools;
    long payloadGaps = issueSummary.payloadGaps;
    long attributionGaps = issueSummary.attributionGaps;
    List<IssueSeed> issues = issueSummary.issues;
    Map<String, Object> map = new LinkedHashMap<>();
    map.put(
        "runHealth",
        hasRunIssues(failedTools, payloadGaps, attributionGaps)
            ? "Completed with issue signals"
            : "Completed");
    map.put("issueRounds", issueSummary.issueRounds);
    map.put(FIELD_FAILED_TOOLS, failedTools);
    map.put(FIELD_FAILED_TOOLS_RATE, ratioLabel(failedTools, totalTools));
    map.put("payloadGaps", payloadGaps);
    map.put("attributionGaps", attributionGaps);
    map.put("issueStrip", issueStrip(issues));
    map.put(
        "agents",
        agentRows(input.row, input.sourcePath, input.parent, input.children, input.mainCalls));
    map.put("contextSegments", contextSegments(input.row, input.parent, input.children));
    map.put("toolImpact", toolImpact(input.parent, input.children, totalTools, failedTools));
    map.put("issues", issueRows(issues));
    map.put("issueCount", issues.size());
    map.put("roundSignals", roundSignalMap(input.rounds));
    return map;
  }

  private static List<Map<String, Object>> agentRows(
      SessionRecord row,
      String sourcePath,
      RolloutStats parent,
      List<RolloutStats> children,
      long mainCalls) {
    long parentSubagentTools =
        parent.tools.values().stream().filter(tool -> !tool.subagentId.isBlank()).count();
    long mainTools = Math.max(parent.tools.size() - parentSubagentTools, 0);
    long mainFailures =
        parent.tools.values().stream()
            .filter(tool -> tool.failed && tool.subagentId.isBlank())
            .count();
    // 会话聚合包含子会话，不能当作主会话用量；仅单一作用域缺逐次用量时可回退到会话估算。
    if (children.isEmpty()
        && row.subagentInstanceCount() == 0
        && (parent.tokenSegments == null
            || (parent.llmTokens == 0 && row.tokenProvenance().estimatedSessionCount() > 0))) {
      parent.tokenSegments =
          TokenSegments.of(
              row.freshInputTokens(),
              row.cacheReadTokens(),
              row.cacheWriteTokens(),
              row.outputTokens(),
              row.tokenProvenance());
      parent.llmTokens = row.totalTokens();
      parent.tokenUsageBasis =
          row.tokenProvenance().estimatedSessionCount() > 0 ? "session_estimate" : "session_usage";
    }
    long shareDenominator =
        parent.llmTokens + children.stream().mapToLong(child -> child.llmTokens).sum();
    TokenProvenance workloadPrecision =
        parent.tokenSegments == null
            ? TokenProvenance.unknown()
            : parent.tokenSegments.provenance();
    for (RolloutStats child : children) {
      workloadPrecision =
          workloadPrecision.plus(
              child.tokenSegments == null
                  ? TokenProvenance.unknown()
                  : child.tokenSegments.provenance());
    }
    boolean reportedUsage =
        List.of(
                workloadPrecision.freshInput(),
                workloadPrecision.cacheRead(),
                workloadPrecision.cacheWrite(),
                workloadPrecision.output())
            .stream()
            .allMatch("provider_reported"::equals);
    String shareStatus =
        shareDenominator <= 0
            ? "unavailable"
            : !reportedUsage
                    || shareDenominator != row.totalTokens()
                    || workloadPrecision.estimatedSessionCount() > 0
                    || workloadPrecision.unavailableSessionCount() > 0
                    || workloadPrecision.unknownSessionCount() > 0
                ? "partial"
                : STATUS_AVAILABLE;
    String shareBasis =
        "session_estimate".equals(parent.tokenUsageBasis)
            ? "session_estimate"
            : "observed_agent_usage";
    List<Map<String, Object>> rows = new ArrayList<>();
    rows.add(
        agentRow(
            new AgentRowInput(
                SCOPE_MAIN,
                "main agent",
                "",
                SCOPE_MAIN,
                sourcePath,
                row.sessionId(),
                mainCalls,
                parent.llmTokens,
                ratioLabel(parent.llmTokens, shareDenominator),
                parent.tokenSegments,
                parent.tokenUsageBasis,
                shareDenominator,
                shareStatus,
                shareBasis,
                mainTools,
                mainFailures,
                ratioLabel(mainFailures, mainTools))));
    List<RolloutStats> sortedChildren =
        children.stream()
            .sorted(
                Comparator.comparingLong(SessionDetailParityAnalyzer::childAgentFootprint)
                    .reversed())
            .toList();
    for (RolloutStats child : sortedChildren) {
      long parentTools =
          parent.tools.values().stream()
              .filter(tool -> child.sessionId.equals(tool.subagentId))
              .count();
      long tools = child.tools.size() + parentTools;
      long failures =
          child.tools.values().stream().filter(tool -> tool.failed).count()
              + parent.tools.values().stream()
                  .filter(tool -> tool.failed && child.sessionId.equals(tool.subagentId))
                  .count();
      long footprint = childAgentFootprint(child);
      rows.add(
          agentRow(
              new AgentRowInput(
                  SCOPE_SUBAGENT,
                  firstNonBlank(child.agentType, SCOPE_SUBAGENT),
                  child.sessionId,
                  child.shortId(),
                  child.path,
                  child.sessionId,
                  child.llmCalls,
                  footprint,
                  ratioLabel(footprint, shareDenominator),
                  child.tokenSegments,
                  child.tokenUsageBasis,
                  shareDenominator,
                  shareStatus,
                  shareBasis,
                  tools,
                  failures,
                  ratioLabel(failures, tools))));
    }
    return List.copyOf(rows);
  }

  private static long childAgentFootprint(RolloutStats child) {
    // 工具结果上下文已包含在模型输入中，不能作为额外用量重复累计。
    return child.llmTokens;
  }

  private static Map<String, Object> agentRow(AgentRowInput input) {
    Map<String, Object> row = new LinkedHashMap<>();
    row.put("scope", input.scope);
    row.put("agent", input.agent);
    row.put("subagentId", input.subagentId);
    row.put("shortId", input.shortId);
    row.put("sessionFile", input.sessionFile);
    row.put("sessionFileDisplay", displayPath(input.sessionFile));
    row.put("sessionId", input.sessionId);
    row.put("sessionIdDisplay", compactId(input.sessionId));
    row.put("llmCalls", input.llmCalls);
    row.put(FIELD_TOKENS, compact(input.tokens));
    row.put("tokenSegments", input.tokenSegments);
    row.put("tokenUsageBasis", input.tokenUsageBasis);
    row.put("tokenShare", input.tokenShare);
    row.put(
        "tokenShareValue",
        input.shareDenominator <= 0 ? null : ratioValue(input.tokens, input.shareDenominator));
    row.put("tokenShareBasis", input.shareBasis);
    row.put("tokenShareStatus", input.shareStatus);
    row.put("tools", input.tools);
    row.put("failures", input.failures);
    row.put("failureRate", input.failureRate);
    row.put("failureLabel", input.failures + " failed · " + input.failureRate);
    return row;
  }

  private static List<Map<String, Object>> contextSegments(
      SessionRecord row, RolloutStats parent, List<RolloutStats> children) {
    long toolResultTokens = totalToolResultTokens(parent, children);
    var precision = row.tokenProvenance();
    List<Segment> segments =
        List.of(
            new Segment("System", -1, "unavailable"),
            new Segment("Provider Cached Input", row.cacheReadTokens(), precision.cacheRead()),
            new Segment("Fresh Input", row.freshInputTokens(), precision.freshInput()),
            new Segment("Cache Write", row.cacheWriteTokens(), precision.cacheWrite()),
            new Segment("Output", row.outputTokens(), precision.output()),
            new Segment("Tool Results", toolResultTokens, "estimated"));
    long denominator = row.totalTokens();
    boolean partial =
        !List.of(
                    precision.freshInput(),
                    precision.cacheRead(),
                    precision.cacheWrite(),
                    precision.output())
                .stream()
                .allMatch("provider_reported"::equals)
            || precision.estimatedSessionCount() > 0
            || precision.unavailableSessionCount() > 0
            || precision.unknownSessionCount() > 0;
    List<Map<String, Object>> rows = new ArrayList<>();
    for (Segment segment : segments) {
      boolean usage = segment.tokens >= 0 && !"Tool Results".equals(segment.label);
      boolean known = !"unknown".equals(segment.status) && !"unavailable".equals(segment.status);
      Map<String, Object> rowMap = new LinkedHashMap<>();
      rowMap.put("label", segment.label);
      rowMap.put(FIELD_TOKENS, segment.tokens);
      rowMap.put(
          "tokensLabel",
          !known
              ? "N/A"
              : ("estimated".equals(segment.status) ? "~" : "") + compact(segment.tokens));
      rowMap.put(
          "share", !usage || !known ? "unavailable" : ratioLabel(segment.tokens, denominator));
      rowMap.put("shareValue", !usage || !known ? 0.0 : ratioValue(segment.tokens, denominator));
      rowMap.put(
          "status", "provider_reported".equals(segment.status) ? STATUS_AVAILABLE : segment.status);
      rowMap.put("precision", segment.status);
      rowMap.put("includedInUsage", usage);
      rowMap.put("shareBasis", usage ? "session_workload_usage" : "not_usage");
      rowMap.put(
          "shareStatus",
          !usage || !known || denominator <= 0
              ? "unavailable"
              : partial ? "partial" : STATUS_AVAILABLE);
      rows.add(rowMap);
    }
    return List.copyOf(rows);
  }

  private static Map<String, Object> toolImpact(
      RolloutStats parent, List<RolloutStats> children, long totalTools, long failedTools) {
    Map<String, ToolStat> stats = new LinkedHashMap<>();
    accumulateToolStats(stats, parent, true);
    for (RolloutStats child : children) {
      accumulateToolStats(stats, child, false);
    }
    List<Map<String, Object>> rows =
        stats.values().stream()
            .sorted(
                Comparator.comparingLong(ToolStat::calls)
                    .reversed()
                    .thenComparing(stat -> stat.name))
            .limit(5)
            .map(SessionDetailParityAnalyzer::toolRow)
            .toList();
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("allToolCalls", totalTools);
    map.put(FIELD_FAILED_TOOLS, failedTools);
    map.put(FIELD_FAILED_TOOLS_RATE, ratioLabel(failedTools, totalTools));
    map.put("distinctTools", stats.size());
    map.put("rows", rows);
    return map;
  }

  private static void accumulateToolStats(
      Map<String, ToolStat> stats, RolloutStats rollout, boolean main) {
    for (ToolEvent tool : rollout.tools.values()) {
      ToolStat stat = stats.computeIfAbsent(tool.name, ToolStat::new);
      stat.calls++;
      if (main && tool.subagentId.isBlank()) {
        stat.mainCalls++;
      } else {
        stat.subagentCalls++;
      }
      if (tool.failed) {
        stat.failures++;
      }
      stat.resultTokens += tool.resultTokens;
    }
  }

  private static Map<String, Object> toolRow(ToolStat stat) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put(FIELD_TOOL, stat.name);
    map.put("calls", stat.calls);
    map.put(FIELD_TOKENS, stat.resultTokens == 0 ? "0" : "~" + compact(stat.resultTokens));
    map.put("failures", stat.failures);
    map.put("failureRate", ratioLabel(stat.failures, stat.calls));
    map.put("splitNote", "Main " + stat.mainCalls + " · Subagent " + stat.subagentCalls);
    return map;
  }

  private static List<Map<String, Object>> issueStrip(List<IssueSeed> signals) {
    Map<String, Integer> counts = new LinkedHashMap<>();
    Map<String, IssueSeed> first = new LinkedHashMap<>();
    for (IssueSeed seed : signals) {
      if (seed.roundId <= 0) {
        continue;
      }
      String key = seed.roundId + "\t" + seed.issue;
      counts.put(key, counts.getOrDefault(key, 0) + 1);
      first.putIfAbsent(key, seed);
    }
    List<Map<String, Object>> rows = new ArrayList<>();
    for (Map.Entry<String, IssueSeed> entry : first.entrySet()) {
      if (rows.size() >= 4) {
        break;
      }
      IssueSeed seed = entry.getValue();
      int count = counts.getOrDefault(entry.getKey(), 1);
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("label", "R" + seed.roundId + " · " + seed.issue + (count > 1 ? " ×" + count : ""));
      map.put("roundId", seed.roundId);
      map.put("tone", TONE_CRITICAL.equals(seed.tone) ? "err" : "warn");
      rows.add(map);
    }
    return List.copyOf(rows);
  }

  private static List<Map<String, Object>> issueRows(List<IssueSeed> issues) {
    return issues.stream()
        .map(
            seed -> {
              Map<String, Object> map = new LinkedHashMap<>();
              map.put("issue", seed.issue);
              map.put("evidence", seed.evidence);
              map.put("roundId", seed.roundId);
              map.put("roundLabel", "R" + seed.roundId);
              map.put("seed", seed.seed);
              map.put("tone", seed.tone);
              return map;
            })
        .toList();
  }

  private static Map<String, Object> roundSignalMap(Map<Integer, RoundParity> rounds) {
    Map<String, Object> map = new LinkedHashMap<>();
    for (RoundParity round : rounds.values()) {
      map.put(String.valueOf(round.roundIndex), round.toMap());
    }
    return map;
  }

  private static long totalToolResultTokens(RolloutStats parent, List<RolloutStats> children) {
    long total = parent.tools.values().stream().mapToLong(tool -> tool.resultTokens).sum();
    for (RolloutStats child : children) {
      total += child.tools.values().stream().mapToLong(tool -> tool.resultTokens).sum();
    }
    return total;
  }

  private static boolean hasRunIssues(long failedTools, long payloadGaps, long attributionGaps) {
    return failedTools > 0 || payloadGaps > 0 || attributionGaps > 0;
  }

  private static String extractAgentId(String output) {
    if (output == null || output.isBlank()) {
      return "";
    }
    // 先尝试 JSON 格式（Codex 风格）
    try {
      JsonNode node = MAPPER.readTree(output);
      String agentId = text(node, "agent_id");
      if (!agentId.isBlank()) {
        return agentId;
      }
    } catch (IOException ignored) {
      // 非 JSON，回退到纯文本解析
    }
    // Claude Code 纯文本格式："agentId: <id> ..."
    int idx = output.indexOf("agentId: ");
    if (idx >= 0) {
      String rest = output.substring(idx + "agentId: ".length()).strip();
      int end = rest.indexOf(' ');
      if (end < 0) end = rest.indexOf('\n');
      if (end < 0) end = rest.length();
      String candidate = rest.substring(0, end).strip();
      if (!candidate.isBlank() && !candidate.contains("(")) {
        return candidate;
      }
    }
    return "";
  }

  private static boolean isFailedOutput(String output) {
    return output != null && EXIT_FAILURE.matcher(output).find();
  }

  private static int estimateTokens(String text) {
    if (text == null || text.isBlank()) {
      return 0;
    }
    int cjk = regexCount(CJK, text);
    int ascii = regexCount(ASCII, text);
    int punct = regexCount(CODE_PUNCT, text);
    int asciiNonCode = Math.max(0, ascii - punct);
    int other = Math.max(0, text.length() - cjk - ascii);
    double estimate = cjk / 1.8 + punct / 3.0 + asciiNonCode / 4.0 + other / 2.5;
    return Math.max(1, (int) Math.round(estimate));
  }

  private static int regexCount(Pattern pattern, String text) {
    Matcher matcher = pattern.matcher(text);
    int count = 0;
    while (matcher.find()) {
      count++;
    }
    return count;
  }

  private static double median(List<Long> values) {
    if (values.isEmpty()) {
      return 0.0;
    }
    int mid = values.size() / 2;
    if (values.size() % 2 == 1) {
      return values.get(mid);
    }
    return (values.get(mid - 1) + values.get(mid)) / 2.0;
  }

  private static String text(JsonNode node, String field) {
    if (node == null || !node.isObject()) {
      return "";
    }
    JsonNode value = node.get(field);
    return value != null && value.isTextual() ? value.asText() : "";
  }

  private static String messageText(JsonNode content) {
    if (!content.isArray()) {
      return content.isTextual() ? content.asText() : "";
    }
    StringBuilder text = new StringBuilder();
    for (JsonNode part : content) {
      String value = firstNonBlank(text(part, "text"), text(part, FIELD_CONTENT));
      if (!value.isBlank()) {
        if (!text.isEmpty()) {
          text.append("\n\n");
        }
        text.append(value);
      }
    }
    return text.toString();
  }

  /** 从 user 消息 content 提取可见用户文本，跳过 tool_result 部件。 */
  private static String userVisibleMessageText(JsonNode content) {
    if (!content.isArray()) {
      return content.isTextual() ? content.asText() : "";
    }
    StringBuilder text = new StringBuilder();
    for (JsonNode part : content) {
      if ("tool_result".equals(text(part, FIELD_TYPE))) {
        continue;
      }
      String value = firstNonBlank(text(part, "text"), text(part, FIELD_CONTENT));
      if (!value.isBlank()) {
        if (!text.isEmpty()) {
          text.append("\n\n");
        }
        text.append(value);
      }
    }
    return text.toString();
  }

  static boolean isVisibleUserInput(String messageText) {
    if (messageText == null || messageText.isBlank()) {
      return false;
    }
    String trimmed = messageText.stripLeading();
    return !trimmed.startsWith("<subagent_notification>")
        && !trimmed.startsWith("<codex_internal_context")
        && !trimmed.startsWith("<environment_context>")
        && !trimmed.startsWith("<permissions instructions>")
        && !trimmed.startsWith("# AGENTS.md instructions for ");
  }

  private static String firstNonBlank(String first, String second) {
    return first != null && !first.isBlank() ? first : (second == null ? "" : second);
  }

  /**
   * 从工具名列表和输入预览生成稳定安全摘要。
   *
   * <p>如果有输入预览，格式为 "Read: path, Grep: pattern in path"；否则回退到 "Tool: Read, Write"。
   */
  private static String toolSummaryLabel(List<String> toolNames, List<String> inputPreviews) {
    if (toolNames == null || toolNames.isEmpty()) {
      return "";
    }
    // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Build labeled summaries with input previews when available`
    if (inputPreviews != null && inputPreviews.size() == toolNames.size()) {
      List<String> labeled = new ArrayList<>();
      for (int i = 0; i < toolNames.size(); i++) {
        String name = toolNames.get(i);
        String preview = inputPreviews.get(i);
        if (preview != null && !preview.isBlank()) {
          labeled.add(name + ": " + preview);
        } else {
          labeled.add(name);
        }
      }
      return "Tool: " + String.join(", ", labeled);
    }
    LinkedHashSet<String> unique = new LinkedHashSet<>(toolNames);
    return "Tool: " + String.join(", ", unique);
  }

  /**
   * 从 tool_use JSON 节点中提取安全输入预览。
   *
   * <p>Read → file_path，Grep → pattern + path，Bash → command，其他 → 空字符串。
   */
  private static String extractToolUseInputPreview(String toolName, JsonNode toolUseNode) {
    if (toolUseNode == null) return "";
    JsonNode inputNode = toolUseNode.path("input");
    if (!inputNode.isObject()) return "";
    String name = toolName == null ? "" : toolName.toLowerCase();
    if (name.contains("read") || name.contains("write") || name.contains("edit")) {
      String path = inputNode.path("file_path").asText("");
      if (!path.isBlank()) return path;
    }
    if (name.contains("grep") || name.contains("search")) {
      String pattern = inputNode.path("pattern").asText("");
      String path = inputNode.path("path").asText("");
      if (!pattern.isBlank() && !path.isBlank()) return pattern + " in " + path;
      if (!pattern.isBlank()) return pattern;
    }
    if (name.contains("bash") || name.contains("shell") || name.contains("exec")) {
      String cmd = inputNode.path("command").asText("");
      if (!cmd.isBlank()) {
        String singleLine = cmd.replace('\n', ' ').replace('\r', ' ').trim();
        return singleLine.length() <= 80 ? singleLine : singleLine.substring(0, 79) + "…";
      }
    }
    return "";
  }

  private static long firstPositive(long first, long second) {
    return first > 0 ? first : Math.max(second, 0);
  }

  private static String localDateTime(String value) {
    return parseInstant(value).map(DATE_TIME::format).orElse(value == null ? "" : value);
  }

  private static String localDate(String value) {
    return parseInstant(value).map(DATE::format).orElse("—");
  }

  private static String localTime(String value) {
    return parseInstant(value).map(TIME::format).orElse("");
  }

  private static Optional<Instant> parseInstant(String value) {
    if (value == null || value.isBlank()) {
      return Optional.empty();
    }
    try {
      return Optional.of(Instant.parse(value));
    } catch (RuntimeException ignored) {
      return Optional.empty();
    }
  }

  private static String agentLabel(String agent) {
    String normalized = agent == null ? "" : agent.toLowerCase(Locale.ROOT).replace('-', '_');
    if ("codex".equals(normalized)) {
      return "Codex";
    }
    if ("qoder".equals(normalized)) {
      return "Qoder";
    }
    if ("claude_code".equals(normalized)) {
      return "Claude";
    }
    return agent == null || agent.isBlank() ? "Agent" : agent;
  }

  private static String compact(long value) {
    double n = value;
    if (n >= 1_000_000_000) {
      return String.format(Locale.ROOT, "%.1fB", n / 1_000_000_000.0);
    }
    if (n >= 1_000_000) {
      return String.format(Locale.ROOT, "%.1fM", n / 1_000_000.0);
    }
    if (n >= 1_000) {
      return String.format(Locale.ROOT, "%.1fK", n / 1_000.0);
    }
    return Long.toString(value);
  }

  private static String ratioLabel(long numerator, long denominator) {
    if (denominator <= 0) {
      return "N/A";
    }
    return String.format(Locale.ROOT, "%.1f%%", numerator * 100.0 / denominator);
  }

  private static double ratioValue(long numerator, long denominator) {
    if (denominator <= 0) {
      return 0.0;
    }
    return Math.max(0.0, Math.min(100.0, numerator * 100.0 / denominator));
  }

  private static String displayPath(String path) {
    if (path == null || path.isBlank()) {
      return "—";
    }
    String home = System.getProperty("user.home", "");
    String display =
        !home.isBlank() && path.startsWith(home) ? "~" + path.substring(home.length()) : path;
    String[] parts = display.replace('\\', '/').split("/");
    List<String> clean = new ArrayList<>();
    for (String part : parts) {
      if (!part.isBlank()) {
        clean.add(part);
      }
    }
    if (clean.size() < 2) {
      return truncateMiddle(display, 24, 9, 11);
    }
    String file = truncateMiddle(clean.get(clean.size() - 1), 24, 9, 11);
    String parent = truncateMiddle(clean.get(clean.size() - 2), 14, 6, 6);
    return display.startsWith("~/") ? "~/…/" + parent + "/" + file : "/…/" + parent + "/" + file;
  }

  private static String compactId(String id) {
    return truncateMiddle(id, 18, 8, 7);
  }

  private static String truncateMiddle(String value, int max, int head, int tail) {
    if (value == null || value.length() <= max) {
      return value == null ? "" : value;
    }
    return value.substring(0, Math.min(head, value.length()))
        + "…"
        + value.substring(Math.max(0, value.length() - tail));
  }

  /** 分析结果。 */
  static final class Result {
    final Map<String, Object> meta;
    final Map<String, Object> metrics;
    final Map<String, Object> diagnostics;
    final Map<Integer, RoundParity> rounds;

    Result(
        Map<String, Object> meta,
        Map<String, Object> metrics,
        Map<String, Object> diagnostics,
        Map<Integer, RoundParity> rounds) {
      this.meta = Map.copyOf(meta);
      this.metrics = Map.copyOf(metrics);
      this.diagnostics = Map.copyOf(diagnostics);
      this.rounds = Map.copyOf(rounds);
    }

    RoundParity round(int roundIndex) {
      return rounds.getOrDefault(roundIndex, new RoundParity(roundIndex));
    }
  }

  /** 每轮 trace 的 parity 字段。 */
  static final class RoundParity {
    final int roundIndex;
    final List<String> failedToolIds = new ArrayList<>();
    final List<String> signals = new ArrayList<>();
    final List<IssueSeed> issueSeeds = new ArrayList<>();
    String summary = "";
    String time = "";
    boolean lowCache;
    boolean freshSpike;
    boolean payloadGap;
    boolean userInput;

    RoundParity(int roundIndex) {
      this.roundIndex = roundIndex;
    }

    boolean hasIssues() {
      return !failedToolIds.isEmpty() || payloadGap;
    }

    Map<String, Object> toMap() {
      Map<String, Object> map = new LinkedHashMap<>();
      map.put("summary", summary);
      map.put("time", time);
      map.put("isLowCache", lowCache);
      map.put("isFreshSpike", freshSpike);
      map.put("isUserInput", userInput);
      map.put("hasPayloadGap", payloadGap);
      map.put("hasIssues", hasIssues());
      map.put("failedToolIds", List.copyOf(failedToolIds));
      map.put("signals", List.copyOf(new LinkedHashSet<>(signals)));
      return map;
    }
  }

  /** 表示单个 rollout 文件解析出的会话统计。 */
  private static final class RolloutStats {
    String path;
    final String scope;
    final String parentSessionId;
    final Map<String, ToolEvent> tools = new LinkedHashMap<>();
    final List<RawRoundSummary> roundSummaries = new ArrayList<>();
    String sessionId = "";
    String agentType = "";
    String startedAt = "";
    long llmCalls;
    long llmTokens;
    long inputSideTokens;
    TokenSegments tokenSegments;
    String tokenUsageBasis = "raw_rollout_usage";

    RolloutStats(String path, String scope, String parentSessionId) {
      this.path = path == null ? "" : path;
      this.scope = scope;
      this.parentSessionId = parentSessionId == null ? "" : parentSessionId;
    }

    static RolloutStats empty(String path) {
      return new RolloutStats(path, SCOPE_MAIN, "");
    }

    void addUsage(UsageDelta usage, TokenProvenance incoming) {
      TokenSegments previous = tokenSegments;
      TokenProvenance combined = incoming;
      if (previous != null) {
        TokenProvenance current = previous.provenance();
        Set<String> methods = new LinkedHashSet<>();
        for (String method :
            (current.estimationMethod() + "," + incoming.estimationMethod()).split(",")) {
          if (!method.isBlank()) methods.add(method);
        }
        // 多次调用属于同一会话：合并来源状态及覆盖标记，不重复累计会话数。
        combined =
            new TokenProvenance(
                mergePrecision(current.freshInput(), incoming.freshInput()),
                mergePrecision(current.cacheRead(), incoming.cacheRead()),
                mergePrecision(current.cacheWrite(), incoming.cacheWrite()),
                mergePrecision(current.output(), incoming.output()),
                String.join(",", methods),
                Math.max(current.estimatedSessionCount(), incoming.estimatedSessionCount()),
                Math.max(current.unavailableSessionCount(), incoming.unavailableSessionCount()),
                Math.max(current.unknownSessionCount(), incoming.unknownSessionCount()));
      }
      tokenSegments =
          TokenSegments.of(
              usage.fresh + (previous == null ? 0 : previous.fresh()),
              usage.cacheRead + (previous == null ? 0 : previous.cacheRead()),
              usage.cacheWrite + (previous == null ? 0 : previous.cacheWrite()),
              usage.output + (previous == null ? 0 : previous.output()),
              combined);
    }

    private static String mergePrecision(String left, String right) {
      return left.equals(right) ? left : "mixed";
    }

    String shortId() {
      return sessionId.length() <= 8 ? sessionId : sessionId.substring(sessionId.length() - 8);
    }

    long footprintTokens() {
      long toolTokens = tools.values().stream().mapToLong(tool -> tool.resultTokens).sum();
      return llmTokens + toolTokens;
    }

    RawRoundSummary roundSummary(int roundIndex) {
      int idx = roundIndex - 1;
      return idx >= 0 && idx < roundSummaries.size()
          ? roundSummaries.get(idx)
          : new RawRoundSummary(roundIndex, "", "", false);
    }

    String toolName(String id) {
      ToolEvent tool = tools.get(id);
      return tool == null ? FIELD_TOOL : tool.name;
    }
  }

  /** 表示 rollout 中的一次工具调用事件。 */
  private static final class ToolEvent {
    final String id;
    final String name;
    final String scope;
    final String timestamp;
    final int lineIndex;
    String output = "";
    String subagentId = "";
    String inputPreview = "";
    boolean failed;
    int resultTokens;

    ToolEvent(String id, String name, String scope, String timestamp, int lineIndex) {
      this.id = id;
      this.name = name;
      this.scope = scope;
      this.timestamp = timestamp;
      this.lineIndex = lineIndex;
    }
  }

  /** 表示按工具名称聚合后的统计。 */
  private static final class ToolStat {
    final String name;
    long calls;
    long mainCalls;
    long subagentCalls;
    long failures;
    long resultTokens;

    ToolStat(String name) {
      this.name = name;
    }

    long calls() {
      return calls;
    }
  }

  /** 表示 token 使用量增量。 */
  private static final class UsageDelta {
    final long fresh;
    final long cacheRead;
    final long cacheWrite;
    final long output;
    final long total;

    UsageDelta(long fresh, long cacheRead, long cacheWrite, long output) {
      this.fresh = fresh;
      this.cacheRead = cacheRead;
      this.cacheWrite = cacheWrite;
      this.output = output;
      this.total = fresh + cacheRead + cacheWrite + output;
    }
  }

  /** 表示从原始数据抽取出的轮次摘要。 */
  private static final class RawRoundSummary {
    final long index;
    final String summary;
    final String time;
    final boolean userInput;

    RawRoundSummary(long index, String summary, String time, boolean userInput) {
      this.index = index;
      this.summary = summary == null ? "" : summary;
      this.time = time == null ? "" : time;
      this.userInput = userInput;
    }
  }

  /** 表示生成诊断 issue 所需的种子信息。 */
  private static final class IssueSeed {
    final String issue;
    final String evidence;
    final int roundId;
    final String seed;
    final String tone;

    IssueSeed(String issue, String evidence, int roundId, String seed, String tone) {
      this.issue = issue;
      this.evidence = evidence;
      this.roundId = roundId;
      this.seed = seed;
      this.tone = tone;
    }
  }

  /** 表示 token 分段展示条目。 */
  private static final class Segment {
    final String label;
    final long tokens;
    final String status;

    Segment(String label, long tokens, String status) {
      this.label = label;
      this.tokens = tokens;
      this.status = status;
    }
  }

  /** 表示整次运行的 issue 汇总。 */
  private static final class RunIssueSummary {
    final long totalTools;
    final long failedTools;
    final long payloadGaps;
    final long attributionGaps;
    final int issueRounds;
    final List<IssueSeed> issues;

    RunIssueSummary(
        long totalTools,
        long failedTools,
        long payloadGaps,
        long attributionGaps,
        int issueRounds,
        List<IssueSeed> issues) {
      this.totalTools = totalTools;
      this.failedTools = failedTools;
      this.payloadGaps = payloadGaps;
      this.attributionGaps = attributionGaps;
      this.issueRounds = issueRounds;
      this.issues = List.copyOf(issues);
    }
  }

  /** 表示 metrics 构建阶段的输入集合。 */
  private static final class MetricsInput {
    final SessionRecord row;
    final long mainCalls;
    final long subagentCalls;
    final long workload;
    final long subagentRuns;
    final long inputSide;
    final long lowCacheRounds;
    final long freshSpikeRounds;
    final RunIssueSummary issueSummary;

    MetricsInput(
        SessionRecord row,
        long mainCalls,
        long subagentCalls,
        long workload,
        long subagentRuns,
        long inputSide,
        long lowCacheRounds,
        long freshSpikeRounds,
        RunIssueSummary issueSummary) {
      this.row = row;
      this.mainCalls = mainCalls;
      this.subagentCalls = subagentCalls;
      this.workload = workload;
      this.subagentRuns = subagentRuns;
      this.inputSide = inputSide;
      this.lowCacheRounds = lowCacheRounds;
      this.freshSpikeRounds = freshSpikeRounds;
      this.issueSummary = issueSummary;
    }
  }

  /** 表示 diagnostics 构建阶段的输入集合。 */
  private static final class DiagnosticsInput {
    final SessionRecord row;
    final String sourcePath;
    final RolloutStats parent;
    final List<RolloutStats> children;
    final Map<Integer, RoundParity> rounds;
    final RunIssueSummary issueSummary;
    final long mainCalls;

    DiagnosticsInput(
        SessionRecord row,
        String sourcePath,
        RolloutStats parent,
        List<RolloutStats> children,
        Map<Integer, RoundParity> rounds,
        RunIssueSummary issueSummary,
        long mainCalls) {
      this.row = row;
      this.sourcePath = sourcePath;
      this.parent = parent;
      this.children = children;
      this.rounds = rounds;
      this.issueSummary = issueSummary;
      this.mainCalls = mainCalls;
    }
  }

  /** 表示 agent 表格行构建输入。 */
  private static final class AgentRowInput {
    final String scope;
    final String agent;
    final String subagentId;
    final String shortId;
    final String sessionFile;
    final String sessionId;
    final long llmCalls;
    final long tokens;
    final String tokenShare;
    final TokenSegments tokenSegments;
    final String tokenUsageBasis;
    final long shareDenominator;
    final String shareStatus;
    final String shareBasis;
    final long tools;
    final long failures;
    final String failureRate;

    AgentRowInput(
        String scope,
        String agent,
        String subagentId,
        String shortId,
        String sessionFile,
        String sessionId,
        long llmCalls,
        long tokens,
        String tokenShare,
        TokenSegments tokenSegments,
        String tokenUsageBasis,
        long shareDenominator,
        String shareStatus,
        String shareBasis,
        long tools,
        long failures,
        String failureRate) {
      this.scope = scope;
      this.agent = agent;
      this.subagentId = subagentId;
      this.shortId = shortId;
      this.sessionFile = sessionFile;
      this.sessionId = sessionId;
      this.llmCalls = llmCalls;
      this.tokens = tokens;
      this.tokenShare = tokenShare;
      this.tokenSegments = tokenSegments;
      this.tokenUsageBasis = tokenUsageBasis;
      this.shareDenominator = shareDenominator;
      this.shareStatus = shareStatus;
      this.shareBasis = shareBasis;
      this.tools = tools;
      this.failures = failures;
      this.failureRate = failureRate;
    }
  }
}
