package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;

/** 只保存事件身份、UTC日和用量分量标量，不保存源记录或正文。 */
final class EventActivityAccumulator {
  private final NormalizedAgent agent;
  private final Set<String> userEvents = new HashSet<>();
  private final Map<String, Day> days = new TreeMap<>();
  private final Tokens undatedTokens = new Tokens();
  private long observedUserMessages;
  private long undatedUserMessages;
  private long supportedUsageEvents;
  private long undatedUsageEvents;
  private long unsupportedUsageEvents;

  /**
   * 创建观察原始已解析事件流的独立累加器。
   *
   * @param agent 来源平台，决定是否支持现代 Codex usage 报告
   */
  EventActivityAccumulator(NormalizedAgent agent) {
    this.agent = agent;
  }

  /**
   * 观察当前记录后仅保留身份与数值；不使用正文、调用或会话时间补日期。
   *
   * @param record 当前原始源记录
   */
  void accept(SourceRecord record) {
    Optional<OffsetDateTime> timestamp = utcTimestamp(record);
    if (observedMainUser(record) && userEvents.add(userIdentity(record))) {
      observedUserMessages++;
      if (timestamp.isPresent()) day(timestamp.get()).observedUserMessages++;
      else undatedUserMessages++;
    }
    SourceRecordUsage usage = record.usage();
    boolean modern =
        agent == NormalizedAgent.CODEX
            && TokenAccountant.isResponseUsageFrame(record.callId().orElse(""));
    if (modern) {
      supportedUsageEvents++;
      if (timestamp.isPresent()) day(timestamp.get()).tokens.accept(usage);
      else {
        undatedUsageEvents++;
        undatedTokens.accept(usage);
      }
    } else if (!(agent == NormalizedAgent.CODEX
            && "assistant".equals(record.eventType())
            && record.callId().orElse("").startsWith("unmetered_response:"))
        && (!usage.provenance().isEmpty()
            || usage.inputTokens() != 0
            || usage.cacheReadInputTokens() != 0
            || usage.cacheCreationInputTokens() != 0
            || usage.outputTokens() != 0)) {
      unsupportedUsageEvents++;
    }
  }

  /**
   * 构造独立、深层不可变的观察摘要；重复读取不改变累加器。
   *
   * @return 冻结的 eventActivity metadata
   */
  Map<String, Object> snapshot() {
    Map<String, Object> dated = new LinkedHashMap<>();
    days.forEach((date, value) -> dated.put(date, value.snapshot()));
    return Map.of(
        "version",
        1,
        "basis",
        "source_event_utc",
        "tokenBasis",
        "codex_modern_usage_report_day",
        "observedUserMessages",
        observedUserMessages,
        "undatedUserMessages",
        undatedUserMessages,
        "supportedUsageEvents",
        supportedUsageEvents,
        "undatedUsageEvents",
        undatedUsageEvents,
        "unsupportedUsageEvents",
        unsupportedUsageEvents,
        "days",
        Map.copyOf(dated),
        "undatedTokens",
        undatedTokens.snapshot());
  }

  /**
   * 获取或创建具有实际观察证据的日桶。
   *
   * @param timestamp 已实际计入观察或支持usage的UTC时间
   * @return 该日的数值状态
   */
  private Day day(OffsetDateTime timestamp) {
    Day day = days.computeIfAbsent(timestamp.toLocalDate().toString(), ignored -> new Day());
    day.observe(timestamp.toInstant());
    return day;
  }

  /**
   * 沿用显式主user观察口径，不从正文或request角色推导。
   *
   * @param record 当前源记录
   * @return 是否符合主user观察条件
   */
  private static boolean observedMainUser(SourceRecord record) {
    return record.messageRole().filter("user"::equals).isPresent()
        && !record.metaContext()
        && record.toolUseId().isEmpty()
        && record.relation().subagentId().isEmpty()
        && !record.locator().replace('\\', '/').contains("/subagents/");
  }

  /**
   * 以来源和源事件位置识别拆分表示，保留不同事件的相同正文。
   *
   * @param record 当前源记录
   * @return 不含正文的观察身份
   */
  private static String userIdentity(SourceRecord record) {
    String locator = record.locator();
    int suffix = locator.lastIndexOf("#event[");
    String source = suffix < 0 ? locator : locator.substring(0, suffix);
    return source + "#event[" + record.eventIndex() + "]";
  }

  /**
   * 仅将源显式时间按offset转换至UTC日期，不设置人为日期窗口。
   *
   * @param record 当前源记录
   * @return 转为UTC offset的显式时间，缺失或非法时为空
   */
  private static Optional<OffsetDateTime> utcTimestamp(SourceRecord record) {
    if (record.timestamp().isEmpty()) return Optional.empty();
    try {
      return Optional.of(
          OffsetDateTime.parse(record.timestamp().get()).withOffsetSameInstant(ZoneOffset.UTC));
    } catch (DateTimeException ignored) {
      return Optional.empty();
    }
  }

  /** 一天的观察用户数和四分量计量覆盖。 */
  private static final class Day {
    private long observedUserMessages;
    private final Tokens tokens = new Tokens();
    private Instant latestEventTimestamp;

    /**
     * 只在事件实际计入该日桶时更新UTC最大时间；不保留逐事件时间列表。
     *
     * @param timestamp 已计入事件的真实UTC瞬时
     */
    private void observe(Instant timestamp) {
      if (latestEventTimestamp == null || timestamp.isAfter(latestEventTimestamp)) {
        latestEventTimestamp = timestamp;
      }
    }

    /**
     * 冻结当前标量状态，不暴露可变的内部计数。
     *
     * @return 深层不可变的metadata
     */
    private Map<String, Object> snapshot() {
      return Map.of(
          "observedUserMessages",
          observedUserMessages,
          "tokens",
          tokens.snapshot(),
          "latestEventTimestamp",
          latestEventTimestamp.toString());
    }
  }

  /** 四个分量的金额与精度覆盖相互独立，不从其它分量或总数补值。 */
  private static final class Tokens {
    private final Component fresh = new Component();
    private final Component cacheRead = new Component();
    private final Component cacheWrite = new Component();
    private final Component output = new Component();

    /**
     * 独立累加四个分量的原始数值和来源精度。
     *
     * @param usage 当前源记录的用量
     */
    private void accept(SourceRecordUsage usage) {
      var provenance = usage.provenance();
      fresh.accept(
          usage.inputTokens(), provenance.getOrDefault("freshInputTokenPrecision", "unknown"));
      cacheRead.accept(
          usage.cacheReadInputTokens(),
          provenance.getOrDefault("cacheReadTokenPrecision", "unknown"));
      cacheWrite.accept(
          usage.cacheCreationInputTokens(),
          provenance.getOrDefault("cacheWriteTokenPrecision", "unknown"));
      output.accept(
          usage.outputTokens(), provenance.getOrDefault("outputTokenPrecision", "unknown"));
    }

    /**
     * 冻结当前标量状态，不暴露可变的内部计数。
     *
     * @return 深层不可变的metadata
     */
    private Map<String, Object> snapshot() {
      return Map.of(
          "fresh",
          fresh.snapshot(),
          "cacheRead",
          cacheRead.snapshot(),
          "cacheWrite",
          cacheWrite.snapshot(),
          "output",
          output.snapshot());
    }
  }

  /** 单分量只记录 provider_reported 金额，其它精度仅记录样本数。 */
  private static final class Component {
    private long reportedTokens;
    private long reportedSamples;
    private long estimatedSamples;
    private long unavailableSamples;
    private long unknownSamples;
    private long mixedSamples;

    /**
     * 按精度分类样本；实测零保留样本，非实测金额不相加。
     *
     * @param amount 源分量的非负数值
     * @param precision 该分量的来源精度
     */
    private void accept(long amount, String precision) {
      switch (precision) {
        case "provider_reported" -> {
          reportedTokens = Math.addExact(reportedTokens, amount);
          reportedSamples++;
        }
        case "estimated" -> estimatedSamples++;
        case "unavailable" -> unavailableSamples++;
        case "mixed" -> mixedSamples++;
        default -> unknownSamples++;
      }
    }

    /**
     * 冻结该分量的金额和各精度样本数。
     *
     * @return 六个非负long字段
     */
    private Map<String, Long> snapshot() {
      return Map.of(
          "reportedTokens",
          reportedTokens,
          "reportedSamples",
          reportedSamples,
          "estimatedSamples",
          estimatedSamples,
          "unavailableSamples",
          unavailableSamples,
          "unknownSamples",
          unknownSamples,
          "mixedSamples",
          mixedSamples);
    }
  }
}
