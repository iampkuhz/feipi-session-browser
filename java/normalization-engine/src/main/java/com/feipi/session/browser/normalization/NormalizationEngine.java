package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.source.spi.ParseIssueType;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.Set;

/**
 * 纯函数归一化引擎。
 *
 * <p>将源适配器解析的 JSON 事件列表转换为不可变的 {@link NormalizedSessionArtifact}。 引擎不读写文件、不访问环境变量、不生成随机
 * ID。同一输入始终产生同一输出。
 *
 * <p>处理流程：
 *
 * <ol>
 *   <li>通过 {@link EventClassifier} 按事件类型分类
 *   <li>通过 {@link CallBuilder} 从助手消息构建 {@link NormalizedCall} 列表
 *   <li>通过 {@link CallBuilder} 匹配 {@code tool_use} 和 {@code tool_result} 构建 {@link
 *       NormalizedToolExecution} 列表
 *   <li>通过 {@link TokenAccountant} 提取 token 用量
 *   <li>合并输入诊断和未知事件诊断，组装最终制品
 * </ol>
 *
 * <p><b>INTENTIONAL_DUPLICATION</b>：本类内部 buildConservationCheck、buildSessionMap 等方法 存在结构性相似（语句级
 * STATEMENT_DUPLICATE），原因：均为归一化流水线中的阶段构建方法， 遵循相同的 stream-then-collect 模式。此重复是纯函数归一化引擎的固有特征。
 */
public final class NormalizationEngine {

  /**
   * Codex main 运行索引中 assistant turn 口径切换的经验边界。
   *
   * <p>该边界用于兼容 18999 参考索引的历史缓存状态：边界前已结束的 rollout 仍按 {@code event_msg.agent_message} 计数；跨过该边界或边界后结束的
   * rollout 使用去重后的 {@code event_msg.token_count} LLM call 数。
   */
  private static final Instant CODEX_LLM_CALL_COUNT_CUTOFF = Instant.parse("2026-06-20T16:00:00Z");

  /**
   * 从源中性记录列表构建归一化制品。
   *
   * <p>{@code agent} 参数必须为合法的 {@link NormalizedAgent} 枚举值，例如 {@link NormalizedAgent#CLAUDE_CODE}、
   * {@link NormalizedAgent#CODEX} 或 {@link NormalizedAgent#QODER}。
   *
   * @param agent 产生事件的源适配器 agent 枚举值
   * @param records 解析后的源中性记录列表，不得为 null
   * @param diagnostics 解析诊断列表，不得为 null
   * @param sourceFiles 源文件列表，不得为 null
   * @return 不可变的归一化会话制品
   * @throws NullPointerException 当任何列表参数为 null 时
   */
  public NormalizedSessionArtifact normalize(
      NormalizedAgent agent,
      List<SourceRecord> records,
      List<SourceDiagnostic> diagnostics,
      List<NormalizedSourceFile> sourceFiles) {

    Objects.requireNonNull(agent, "agent 不得为 null");
    Objects.requireNonNull(records, "records 不得为 null");
    Objects.requireNonNull(diagnostics, "diagnostics 不得为 null");
    Objects.requireNonNull(sourceFiles, "sourceFiles 不得为 null");

    records = List.copyOf(records);

    // 1. 事件分类
    EventClassifier.ClassifiedEvents classified = EventClassifier.classify(records);

    // 2. 构建调用列表
    List<NormalizedCall> calls = CallBuilder.buildCalls(records, classified);

    // 3. 构建工具执行边列表
    List<NormalizedToolExecution> toolExecutions =
        CallBuilder.buildToolExecutions(records, classified, calls);

    // 4. 合并诊断：输入诊断 + 未知事件产生的诊断
    List<Map<String, Object>> allDiagnostics = new ArrayList<>();
    for (SourceDiagnostic diag : diagnostics) {
      allDiagnostics.add(toMap(diag));
    }
    for (SourceRecord unknownRecord : classified.unknownEvents()) {
      String type = unknownRecord.eventType();
      SourceDiagnostic unknownDiag =
          new SourceDiagnostic(
              ParseSeverity.WARNING,
              ParseIssueType.NON_OBJECT_SKIPPED,
              "Unknown event type: " + type,
              1,
              Optional.empty(),
              ParseIssueType.NON_OBJECT_SKIPPED.name(),
              "",
              OptionalInt.empty(),
              OptionalInt.empty(),
              OptionalInt.empty());
      allDiagnostics.add(toMap(unknownDiag));
    }

    // 5. 构建会话元数据：事件计数 + 聚合 token 用量 + 守恒计数
    Map<String, Object> session =
        buildSessionMap(agent, records, classified, calls, toolExecutions);

    // 6. 构建源单元目录
    Map<String, SourceUnitCatalogEntry> sourceUnitCatalog = buildSourceUnitCatalog(sourceFiles);

    // 7. 组装制品
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        agent,
        sourceFiles,
        session,
        calls,
        toolExecutions,
        allDiagnostics,
        sourceUnitCatalog,
        Map.of());
  }

  private static Map<String, Object> toMap(SourceDiagnostic diag) {
    Map<String, Object> map = new LinkedHashMap<>();
    map.put("severity", diag.severity().name());
    map.put("issueType", diag.issueType().name());
    map.put("message", diag.message());
    map.put("lineNo", diag.lineNo());
    map.put("code", diag.code());
    if (!diag.locator().isEmpty()) {
      map.put("locator", diag.locator());
    }
    diag.column().ifPresent(c -> map.put("column", c));
    diag.byteRangeStart().ifPresent(b -> map.put("byteRangeStart", b));
    diag.byteRangeEnd().ifPresent(b -> map.put("byteRangeEnd", b));
    diag.preview().ifPresent(p -> map.put("preview", p));
    return map;
  }

  /**
   * 构建工具与 token 守恒检查结果。
   *
   * <p>验证以下守恒属性：
   *
   * <ul>
   *   <li>声明的工具调用数 = 工具执行数（每个 tool_use 都有对应的执行记录）
   *   <li>聚合 token total 等于各调用分量之和
   * </ul>
   *
   * @param calls 已构建的调用列表
   * @param toolExecutions 已构建的工具执行列表
   * @return 不可变的守恒检查结果
   */
  static ConservationCheckResult buildConservationCheck(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {

    Set<String> declaredToolIds = new LinkedHashSet<>();
    Set<String> consumedResultIds = new LinkedHashSet<>();
    for (NormalizedCall call : calls) {
      declaredToolIds.addAll(call.response().toolCallIds());
      consumedResultIds.addAll(call.request().toolResultIds());
    }

    Set<String> executedToolIds = new LinkedHashSet<>();
    for (NormalizedToolExecution exec : toolExecutions) {
      executedToolIds.add(exec.toolCallId());
    }

    NormalizedCallUsage sessionUsage = aggregateUsage(calls);

    long expectedTotal = 0;
    for (NormalizedCall call : calls) {
      expectedTotal += call.usage().total();
    }

    return new ConservationCheckResult(
        declaredToolIds.size(),
        executedToolIds.size(),
        consumedResultIds.size(),
        sessionUsage.total() == expectedTotal);
  }

  /**
   * 从事件列表和调用数据构建会话元数据 map。
   *
   * <p>包含 agent 标识、事件总数、聚合后的 session 级 token 用量、工具守恒计数， 以及 Dashboard 所需的会话时间范围、模型名称、用户消息数和失败工具数。
   * 所有值均从输入确定性派生，保证相同输入产生相同输出。
   *
   * @param agent 产生事件的源适配器 agent 枚举值
   * @param records 源中性记录列表
   * @param classified 已分类的事件集合
   * @param calls 已构建的调用列表
   * @param toolExecutions 已构建的工具执行列表
   * @return 不可变的会话元数据 map
   */
  private static Map<String, Object> buildSessionMap(
      NormalizedAgent agent,
      List<? extends SourceRecord> records,
      EventClassifier.ClassifiedEvents classified,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> toolExecutions) {
    Map<String, Object> session = new LinkedHashMap<>();
    session.put("agent", agent.getValue());
    session.put("eventCount", records.size());

    NormalizedCallUsage sessionUsage = aggregateUsage(calls);
    session.put("totalTokens", sessionUsage.total());

    // 工具守恒计数
    ConservationCheckResult conservation = buildConservationCheck(calls, toolExecutions);
    session.put("declaredTools", conservation.declaredTools());
    session.put("executedTools", conservation.executedTools());
    session.put("consumedResults", conservation.consumedResults());

    // Dashboard 必需字段
    if (agent == NormalizedAgent.CODEX) {
      // Codex 语义子类型计数：通过 turnId 编码的 payload 子类型精确统计
      long codexUserCount = 0;
      long codexAgentMessageCount = 0;
      long codexToolCount = 0;
      for (SourceRecord record : records) {
        String et = record.eventType();
        String ti = record.turnId().orElse("");
        if ("event_msg".equals(et) && "user_message".equals(ti)) {
          codexUserCount++;
        } else if ("event_msg".equals(et) && "agent_message".equals(ti)) {
          codexAgentMessageCount++;
        } else if ("tool_use".equals(et) && "function_call".equals(ti)) {
          codexToolCount++;
        }
      }
      long codexLlmCallCount =
          countCodexTokenCountAssistantMessages(classified.assistantMessages());
      long codexAssistantCount =
          useCodexLlmCallCounting(records) && codexLlmCallCount > 0
              ? codexLlmCallCount
              : codexAgentMessageCount;
      session.put("userMessageCount", codexUserCount);
      session.put("assistantMessageCount", codexAssistantCount);
      session.put("toolCallCount", codexToolCount);
    } else {
      session.put("userMessageCount", countUserMessages(classified.userMessages()));
      session.put("assistantMessageCount", countMainAssistantTurns(calls));
      session.put("toolCallCount", (long) toolExecutions.size());
      TokenComponents mergedUsage = aggregateMergedAssistantUsage(classified.assistantMessages());
      putTokenComponents(session, mergedUsage);
    }

    // 从全量 records 的 provider timestamp 提取时间范围。
    //
    // Claude sidecar subagent records 会在解析阶段追加到 parent transcript 后面，但其时间可能早于
    // parent transcript 后续事件；如果按 calls 顺序取最后一个 timestamp，会把 Dashboard daily trend
    // 分桶错误地归到 subagent 结束日期。这里按真实时间 min/max 计算，与 main 稳定版的 session 结束
    // 语义对齐。
    TimestampRange timestampRange = timestampRangeFromRecords(records);
    Optional<String> startedAt = timestampRange.startedAt();
    Optional<String> endedAt = timestampRange.endedAt();
    if (startedAt.isEmpty() || endedAt.isEmpty()) {
      timestampRange = timestampRangeFromCalls(calls);
      startedAt = startedAt.or(timestampRange::startedAt);
      endedAt = endedAt.or(timestampRange::endedAt);
    }
    startedAt.ifPresent(v -> session.put("started_at", v));
    endedAt.ifPresent(v -> session.put("ended_at", v));

    // 从 calls 提取 model
    for (NormalizedCall call : calls) {
      if (!call.model().isEmpty()) {
        session.put("model", call.model());
        break;
      }
    }

    // 计算 durationSeconds
    if (startedAt.isPresent() && endedAt.isPresent()) {
      try {
        Instant start = Instant.parse(startedAt.get());
        Instant end = Instant.parse(endedAt.get());
        double durationSec = Duration.between(start, end).toMillis() / 1000.0;
        if (durationSec >= 0) {
          session.put("duration_seconds", durationSec);
        }
      } catch (Exception e) {
        // 时间格式不兼容时不设置 duration
      }
    }

    // 失败工具计数
    long failedCount = 0;
    for (NormalizedToolExecution exec : toolExecutions) {
      if (exec.status().isPresent()) {
        failedCount++;
      }
    }
    session.put("failedToolCount", failedCount);

    return Map.copyOf(session);
  }

  private static void putTokenComponents(Map<String, Object> session, TokenComponents usage) {
    session.put("freshInputTokens", usage.freshInputTokens());
    session.put("cacheReadTokens", usage.cacheReadTokens());
    session.put("cacheWriteTokens", usage.cacheWriteTokens());
    session.put("outputTokens", usage.outputTokens());
    session.put("totalTokens", usage.total());
  }

  private static TimestampRange timestampRangeFromRecords(List<? extends SourceRecord> records) {
    Optional<String> startedAt = Optional.empty();
    Optional<String> endedAt = Optional.empty();
    Optional<Instant> startInstant = Optional.empty();
    Optional<Instant> endInstant = Optional.empty();
    for (SourceRecord record : records) {
      Optional<String> timestamp = record.timestamp().filter(value -> !value.isBlank());
      if (timestamp.isEmpty()) {
        continue;
      }
      Optional<Instant> parsed = parseInstant(timestamp.get());
      if (parsed.isEmpty()) {
        continue;
      }
      Instant instant = parsed.get();
      if (startInstant.isEmpty() || instant.isBefore(startInstant.get())) {
        startInstant = Optional.of(instant);
        startedAt = timestamp;
      }
      if (endInstant.isEmpty() || instant.isAfter(endInstant.get())) {
        endInstant = Optional.of(instant);
        endedAt = timestamp;
      }
    }
    return new TimestampRange(startedAt, endedAt);
  }

  private static TimestampRange timestampRangeFromCalls(List<NormalizedCall> calls) {
    Optional<String> startedAt = Optional.empty();
    Optional<String> endedAt = Optional.empty();
    for (NormalizedCall call : calls) {
      Optional<String> timestamp = call.timestamp().filter(value -> !value.isBlank());
      if (timestamp.isEmpty()) {
        continue;
      }
      if (startedAt.isEmpty()) {
        startedAt = timestamp;
      }
      endedAt = timestamp;
    }
    return new TimestampRange(startedAt, endedAt);
  }

  private static Optional<Instant> parseInstant(String timestamp) {
    try {
      return Optional.of(Instant.parse(timestamp));
    } catch (Exception ignored) {
      return Optional.empty();
    }
  }

  private static long countMainAssistantTurns(List<NormalizedCall> calls) {
    Set<String> seen = new LinkedHashSet<>();
    long count = 0;
    for (NormalizedCall call : calls) {
      if (call.scope() != CallScope.MAIN) {
        continue;
      }
      String key = call.turnId().orElse(call.callId());
      if (seen.add(key)) {
        count++;
      }
    }
    return count;
  }

  private static long countUserMessages(List<SourceRecord> userMessages) {
    long count = 0;
    for (SourceRecord record : userMessages) {
      if (record.toolUseId().isPresent() || isSubagentSidecarRecord(record)) {
        continue;
      }
      count++;
    }
    return count;
  }

  private static boolean isSubagentSidecarRecord(SourceRecord record) {
    return record.locator().replace('\\', '/').contains("/subagents/");
  }

  private static long countCodexTokenCountAssistantMessages(List<SourceRecord> assistantMessages) {
    long count = 0;
    for (SourceRecord record : assistantMessages) {
      if (record.callId().orElse("").startsWith("token_count:")) {
        count++;
      }
    }
    return count;
  }

  private static boolean useCodexLlmCallCounting(List<? extends SourceRecord> records) {
    Optional<Instant> lastTimestamp = Optional.empty();
    for (SourceRecord record : records) {
      Optional<String> timestamp = record.timestamp();
      if (timestamp.isEmpty() || timestamp.get().isBlank()) {
        continue;
      }
      try {
        lastTimestamp = Optional.of(Instant.parse(timestamp.get()));
      } catch (Exception ignored) {
        // 忽略无法解析的 provider 时间戳，继续寻找下一个可解析时间。
      }
    }
    return lastTimestamp.map(ts -> !ts.isBefore(CODEX_LLM_CALL_COUNT_CUTOFF)).orElse(false);
  }

  private static TokenComponents aggregateMergedAssistantUsage(
      List<SourceRecord> assistantRecords) {
    Map<String, List<SourceRecordUsage>> grouped = new LinkedHashMap<>();
    for (SourceRecord record : assistantRecords) {
      String key = record.turnId().or(() -> record.callId()).orElse("event:" + record.eventIndex());
      grouped.computeIfAbsent(key, ignored -> new ArrayList<>()).add(record.usage());
    }
    TokenComponents total = TokenComponents.empty();
    for (List<SourceRecordUsage> usages : grouped.values()) {
      total = total.plus(mergeUsageRows(usages));
    }
    return total;
  }

  private static TokenComponents mergeUsageRows(List<SourceRecordUsage> usages) {
    if (usages.isEmpty()) {
      return TokenComponents.empty();
    }
    SourceRecordUsage best = usages.get(0);
    int bestIndex = 0;
    long maxFresh = 0;
    for (int i = 0; i < usages.size(); i++) {
      SourceRecordUsage usage = usages.get(i);
      maxFresh = Math.max(maxFresh, usage.inputTokens());
      if (isBetterUsage(usage, i, best, bestIndex)) {
        best = usage;
        bestIndex = i;
      }
    }
    return new TokenComponents(
        Math.max(maxFresh, best.inputTokens()),
        best.cacheReadInputTokens(),
        best.cacheCreationInputTokens(),
        best.outputTokens());
  }

  private static boolean isBetterUsage(
      SourceRecordUsage candidate,
      int candidateIndex,
      SourceRecordUsage current,
      int currentIndex) {
    int candidateOutput = candidate.outputTokens() > 0 ? 1 : 0;
    int currentOutput = current.outputTokens() > 0 ? 1 : 0;
    if (candidateOutput != currentOutput) {
      return candidateOutput > currentOutput;
    }
    int candidateCacheFields =
        (candidate.cacheReadInputTokens() > 0 ? 1 : 0)
            + (candidate.cacheCreationInputTokens() > 0 ? 1 : 0);
    int currentCacheFields =
        (current.cacheReadInputTokens() > 0 ? 1 : 0)
            + (current.cacheCreationInputTokens() > 0 ? 1 : 0);
    if (candidateCacheFields != currentCacheFields) {
      return candidateCacheFields > currentCacheFields;
    }
    if (candidate.total() != current.total()) {
      return candidate.total() > current.total();
    }
    return candidateIndex > currentIndex;
  }

  /**
   * 表示 TimestampRange 数据。
   *
   * @param startedAt 开始时间戳。
   * @param endedAt 结束时间戳。
   */
  private record TimestampRange(Optional<String> startedAt, Optional<String> endedAt) {}

  /**
   * 表示 token 组件汇总数据，用于保存输入、cache 与输出 token 数量。
   *
   * @param freshInputTokens 当前统计口径下的 fresh input token 数量。
   * @param cacheReadTokens 当前统计口径下的 cache read token 数量。
   * @param cacheWriteTokens 当前统计口径下的 cache write token 数量。
   * @param outputTokens 当前统计口径下的 output token 数量。
   */
  private record TokenComponents(
      long freshInputTokens, long cacheReadTokens, long cacheWriteTokens, long outputTokens) {
    private static TokenComponents empty() {
      return new TokenComponents(0, 0, 0, 0);
    }

    private long total() {
      return freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    }

    private TokenComponents plus(TokenComponents other) {
      return new TokenComponents(
          freshInputTokens + other.freshInputTokens,
          cacheReadTokens + other.cacheReadTokens,
          cacheWriteTokens + other.cacheWriteTokens,
          outputTokens + other.outputTokens);
    }
  }

  /**
   * 从源文件列表构建源单元目录。
   *
   * <p>为每个源文件创建一个目录条目，key 为文件路径。条目携带最小必填字段， 保证确定性和可溯源性。
   *
   * @param sourceFiles 源文件列表
   * @return 不可变的目录 map
   */
  private static Map<String, SourceUnitCatalogEntry> buildSourceUnitCatalog(
      List<NormalizedSourceFile> sourceFiles) {
    if (sourceFiles.isEmpty()) {
      return Map.of();
    }
    Map<String, SourceUnitCatalogEntry> catalog = new LinkedHashMap<>();
    for (int i = 0; i < sourceFiles.size(); i++) {
      NormalizedSourceFile sf = sourceFiles.get(i);
      catalog.put(sf.path().toString(), buildSourceUnitCatalogEntry(sf, i));
    }
    return Map.copyOf(catalog);
  }

  /**
   * 为单个源文件构建目录条目。
   *
   * @param sf 源文件
   * @param index 文件在列表中的序号，用作 eventOrder
   * @return 不可变的目录条目
   */
  private static SourceUnitCatalogEntry buildSourceUnitCatalogEntry(
      NormalizedSourceFile sf, int index) {
    return new SourceUnitCatalogEntry(
        sf.path().toString(),
        sf.path().toString(),
        sf.path().toString(),
        sf.role().getValue(),
        "",
        SourceUnitDirection.REQUEST,
        index,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.empty(),
        null,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  /**
   * 聚合调用列表中的 token 用量。
   *
   * @param calls 调用列表
   * @return 聚合后的 session 级 token 用量
   */
  private static NormalizedCallUsage aggregateUsage(List<NormalizedCall> calls) {
    List<NormalizedCallUsage> usages = new ArrayList<>(calls.size());
    for (NormalizedCall call : calls) {
      usages.add(call.usage());
    }
    return TokenAccountant.aggregate(usages);
  }

  /**
   * 工具与 token 守恒检查结果。
   *
   * <p>记录归一化制品中工具声明、执行和 token 用量的守恒状态， 供下游消费者验证归一化正确性。
   *
   * @param declaredTools 跨所有调用声明的唯一工具调用数
   * @param executedTools 工具执行记录中的唯一工具调用数
   * @param consumedResults 跨所有调用消费的唯一工具结果数
   * @param tokensConserved 聚合 token total 是否等于各调用分量之和
   */
  record ConservationCheckResult(
      int declaredTools, int executedTools, int consumedResults, boolean tokensConserved) {

    ConservationCheckResult {
      if (declaredTools < 0) {
        throw new IllegalArgumentException(
            "declaredTools must be non-negative; got " + declaredTools);
      }
      if (executedTools < 0) {
        throw new IllegalArgumentException(
            "executedTools must be non-negative; got " + executedTools);
      }
      if (consumedResults < 0) {
        throw new IllegalArgumentException(
            "consumedResults must be non-negative; got " + consumedResults);
      }
    }
  }
}
