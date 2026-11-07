package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 事件日只表示源事件观察与现代 Codex usage 报告日，不替代会话开始日累计。 */
class EventActivityTest {
  private static final String BODY = "synthetic-activity-body-not-metadata";

  @Test
  void utcEventDaysDoNotReplaceSessionStartCohortAndKeepMeasuredZeroSamples() throws Exception {
    var records =
        List.of(
            record(0, "neutral", "2026-01-01T00:00:00Z", SourceRecordUsage.empty(), ""),
            record(1, "user", "2026-01-01T23:30:00-02:00", SourceRecordUsage.empty(), ""),
            record(2, "user", "2026-01-02T01:00:00+02:00", SourceRecordUsage.empty(), ""),
            record(3, "modern", "2026-01-03T00:30:00+02:00", reported(7, 0, 0, 9), ""));
    var content =
        new NormalizationEngine()
            .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
    assertThat(content.header().session().get("started_at")).isEqualTo("2026-01-01T00:00:00Z");
    assertThat(content.header().session().get("totalTokens")).isEqualTo(16L);
    for (var activity : codexActivities(records)) {
      assertContract(activity, 2, 0, 1, 0, 0);
      assertThat(activity.get("days"))
          .isEqualTo(
              Map.of(
                  "2026-01-01", day(1, zeroTokens(), "2026-01-01T23:00:00Z"),
                  "2026-01-02", day(1, reportedTokens(7, 0, 0, 9), "2026-01-02T22:30:00Z")));
      assertThat(activity.get("undatedTokens")).isEqualTo(zeroTokens());
    }
  }

  @Test
  void explicitMainUserIdentityExcludesMetaToolsChildrenAndSidecarsButNotRepeatedText()
      throws Exception {
    String time = "2026-01-02T12:00:00Z";
    var records =
        List.of(
            record(0, "user", time, SourceRecordUsage.empty(), ""),
            // 同源同 event 的拆分表示不能重复计数；另一个相同正文的 event 必须保留。
            record(0, "response_item", time, SourceRecordUsage.empty(), "explicit-user"),
            record(1, "user", time, SourceRecordUsage.empty(), ""),
            record(2, "user", time, SourceRecordUsage.empty(), "meta"),
            record(3, "user", time, SourceRecordUsage.empty(), "tool"),
            record(4, "user", time, SourceRecordUsage.empty(), "child"),
            record(5, "user", time, SourceRecordUsage.empty(), "sidecar"),
            record(6, "user", time, SourceRecordUsage.empty(), "no-role"),
            record(7, "tool_result", time, SourceRecordUsage.empty(), ""));
    for (var activity : codexActivities(records)) {
      assertContract(activity, 2, 0, 0, 0, 0);
      assertThat(activity.get("days"))
          .isEqualTo(Map.of("2026-01-02", day(2, zeroTokens(), "2026-01-02T12:00:00Z")));
    }
  }

  @Test
  void precisionCountsNeverTurnMissingEstimatedUnavailableOrMixedIntoReportedAmounts()
      throws Exception {
    var partial =
        new SourceRecordUsage(
            500,
            600,
            700,
            800,
            Map.of(
                "freshInputTokenPrecision", "estimated",
                "cacheReadTokenPrecision", "unavailable",
                "outputTokenPrecision", "mixed"));
    var records = List.of(record(0, "modern", "2026-02-01T12:00:00Z", partial, ""));
    for (var activity : codexActivities(records)) {
      assertContract(activity, 0, 0, 1, 0, 0);
      assertThat(activity.get("days"))
          .isEqualTo(
              Map.of(
                  "2026-02-01",
                  day(
                      0,
                      tokens(
                          samples(0, 0, 1, 0, 0, 0), samples(0, 0, 0, 1, 0, 0),
                          samples(0, 0, 0, 0, 1, 0), samples(0, 0, 0, 0, 0, 1)),
                      "2026-02-01T12:00:00Z")));
    }
  }

  @Test
  void missingAndInvalidTimestampsStayUndatedWithoutSessionOrCallFallback() throws Exception {
    var records =
        List.of(
            record(0, "neutral", "2026-03-01T00:00:00Z", SourceRecordUsage.empty(), ""),
            record(1, "user", null, SourceRecordUsage.empty(), ""),
            record(2, "user", "not-a-timestamp", SourceRecordUsage.empty(), ""),
            record(3, "modern", null, reported(1, 2, 3, 4), ""),
            record(4, "modern", "2026-03-01T99:00:00Z", reported(0, 0, 0, 0), ""));
    for (var activity : codexActivities(records)) {
      assertContract(activity, 2, 2, 2, 2, 0);
      assertThat(activity.get("days")).isEqualTo(Map.of());
      assertThat(activity.get("undatedTokens"))
          .isEqualTo(
              tokens(
                  samples(1, 2, 0, 0, 0, 0), samples(2, 2, 0, 0, 0, 0),
                  samples(3, 2, 0, 0, 0, 0), samples(4, 2, 0, 0, 0, 0)));
    }
  }

  @Test
  void legacyAndNeutralUsageCountUnsupportedSourceRecordsButEmptyMirrorsDoNot() throws Exception {
    var records =
        List.of(
            record(0, "legacy", "2026-04-01T12:00:00Z", reported(2, 3, 4, 5), ""),
            record(1, "neutral", "2026-04-01T12:00:00Z", reported(0, 0, 0, 0), ""),
            record(2, "neutral", "2026-04-01T12:00:00Z", new SourceRecordUsage(1, 0, 0, 0), ""),
            record(3, "neutral", "2026-04-01T12:00:00Z", SourceRecordUsage.empty(), ""),
            record(4, "modern", "2026-04-01T12:00:00Z", reported(0, 0, 0, 0), ""),
            record(5, "legacy", "2026-04-01T12:00:00Z", reported(0, 0, 0, 0), ""));
    for (var activity : codexActivities(records)) {
      assertContract(activity, 0, 0, 1, 0, 4);
      assertThat(activity.get("days"))
          .isEqualTo(
              Map.of("2026-04-01", day(0, reportedTokens(0, 0, 0, 0), "2026-04-01T12:00:00Z")));
    }
  }

  @Test
  void listDerivedUnknownCallsDoNotBecomeRawUsageEvents() throws Exception {
    derivedUnknownCalls(false);
  }

  @Test
  void managedDerivedUnknownCallsDoNotBecomeRawUsageEvents() throws Exception {
    derivedUnknownCalls(true);
  }

  private static void derivedUnknownCalls(boolean managed) throws Exception {
    String time = "2026-08-01T12:00:00Z";
    var unknown =
        new SourceRecordUsage(
            0,
            0,
            0,
            0,
            Map.of(
                "freshInputTokenPrecision", "unknown",
                "cacheReadTokenPrecision", "unknown",
                "cacheWriteTokenPrecision", "unknown",
                "outputTokenPrecision", "unknown",
                "tokenContainsUnknown", "true"));
    var baseline =
        List.of(
            record(0, "legacy", time, reported(2, 3, 4, 5), ""),
            record(1, "neutral", time, unknown, ""),
            record(2, "neutral", time, reported(0, 0, 0, 0), ""),
            record(3, "modern", time, reported(0, 0, 0, 0), ""),
            record(4, "legacy", time, reported(0, 0, 0, 0), "child"));
    var records = new ArrayList<>(baseline);
    records.add(derivedUnknown(5, time, unknown, false));
    records.add(derivedUnknown(6, time, unknown, true));
    assertThat(records.get(6).callId()).contains("unmetered_response:6");
    var engine = new NormalizationEngine();
    com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact;
    if (managed) {
      try (var sequence = SourceRecordSequence.fromList(records)) {
        var content =
            engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
        artifact = content.toArtifact();
        assertThat(content.toArtifact()).isEqualTo(artifact);
      }
    } else {
      artifact = engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    }
    assertThat(artifact.calls()).hasSize(5);
    for (int index : List.of(5, 6)) {
      String body = BODY + "-derived-" + index;
      var calls =
          artifact.calls().stream()
              .filter(
                  call ->
                      call.sourceUnits().stream().anyMatch(unit -> body.equals(unit.get("text"))))
              .toList();
      assertThat(calls).hasSize(1);
      var call = calls.getFirst();
      assertThat(call.usage().total()).isZero();
      assertThat(call.usageSource())
          .containsEntry("freshInputTokenPrecision", "unknown")
          .containsEntry("cacheReadTokenPrecision", "unknown")
          .containsEntry("cacheWriteTokenPrecision", "unknown")
          .containsEntry("outputTokenPrecision", "unknown")
          .containsEntry("tokenContainsUnknown", "true");
      if (index == 5) assertThat(call.callId()).isEqualTo("unmetered_response:5");
      else {
        assertThat(call.subagentId()).contains("child");
        assertThat(call.callId()).doesNotStartWith("unmetered_response:");
      }
    }
    var before = codexActivities(baseline).getFirst();
    assertContract(before, 0, 0, 1, 0, 4);
    assertThat(activity(artifact.session())).isEqualTo(before);
  }

  private static SourceRecord derivedUnknown(
      int index, String time, SourceRecordUsage usage, boolean child) {
    var original = record(index, "assistant", time, usage, child ? "child" : "");
    return new SourceRecord(
        original.locator(),
        index,
        "assistant",
        Optional.of("unmetered_response:" + index),
        original.model(),
        original.timestamp(),
        Optional.empty(),
        usage,
        List.of(),
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        original.relation(),
        BODY + "-derived-" + index,
        Optional.empty(),
        Optional.empty(),
        original.timing(),
        false,
        Optional.of("assistant"));
  }

  @Test
  void otherProviderUsageIsUnsupportedBeforeProviderFragmentMerging() {
    // 同一响应的两个片段即使之后合成一个call，unsupported仍是原始源记录覆盖数。
    var first = record(0, "modern", "2026-05-01T12:00:00Z", reported(3, 0, 0, 4), "fragment");
    var second = record(1, "modern", "2026-05-02T12:00:00Z", reported(0, 0, 0, 0), "fragment");
    for (var agent : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.QODER)) {
      var content =
          new NormalizationEngine()
              .normalizeContent(agent, List.of(first, second), List.of(), List.of());
      var activity = activity(content.header().session());
      assertContract(activity, 0, 0, 0, 0, 2);
      assertThat(activity.get("days")).isEqualTo(Map.of());
      assertThat(activity.get("undatedTokens")).isEqualTo(zeroTokens());
    }
  }

  @Test
  void latestTimestampUsesOnlyActuallyCountedEventsAndComparesUtcInstants() throws Exception {
    var records =
        List.of(
            record(0, "user", "2026-07-01T10:00:00Z", SourceRecordUsage.empty(), ""),
            record(1, "user", "2026-07-01T14:30:00+02:00", SourceRecordUsage.empty(), ""),
            record(2, "user", "2026-07-01T11:00:00Z", SourceRecordUsage.empty(), ""),
            // 同一观察身份后来的不同时间不推进已计数事件的桶末证据。
            record(
                0,
                "response_item",
                "2026-07-01T23:00:00Z",
                SourceRecordUsage.empty(),
                "explicit-user"),
            record(3, "user", "2026-07-01T23:59:00Z", SourceRecordUsage.empty(), "no-role"),
            record(4, "user", "2026-07-01T23:58:00Z", SourceRecordUsage.empty(), "meta"),
            record(5, "user", "2026-07-01T23:57:00Z", SourceRecordUsage.empty(), "tool"),
            record(6, "user", "2026-07-01T23:56:00Z", SourceRecordUsage.empty(), "child"),
            record(7, "user", "2026-07-01T23:55:00Z", SourceRecordUsage.empty(), "sidecar"),
            record(8, "legacy", "2026-07-02T23:54:00Z", reported(100, 0, 0, 100), ""),
            // 实测0也是有效报告，推进桶末；乱序的后续报告不倒退桶末。
            record(9, "modern", "2026-07-01T14:15:00Z", reported(0, 0, 0, 0), ""),
            record(10, "modern", "2026-07-01T09:45:00-02:00", reported(0, 0, 0, 0), ""),
            record(11, "user", null, SourceRecordUsage.empty(), ""),
            record(12, "modern", "invalid", reported(0, 0, 0, 0), ""));
    for (var activity : codexActivities(records)) {
      assertContract(activity, 4, 1, 3, 1, 1);
      var datedTokens =
          tokens(
              samples(0, 2, 0, 0, 0, 0),
              samples(0, 2, 0, 0, 0, 0),
              samples(0, 2, 0, 0, 0, 0),
              samples(0, 2, 0, 0, 0, 0));
      assertThat(activity.get("days"))
          .isEqualTo(Map.of("2026-07-01", day(3, datedTokens, "2026-07-01T14:15:00Z")));
      assertThat(activity.get("undatedTokens")).isEqualTo(reportedTokens(0, 0, 0, 0));
    }
  }

  @Test
  void summaryIsDeeplyImmutableScalarOnlyAndStableAcrossBothManagedReplays() throws Exception {
    var records =
        List.of(
            record(0, "user", "2026-06-01T12:00:00Z", SourceRecordUsage.empty(), ""),
            record(1, "modern", "2026-06-01T12:00:00Z", reported(0, 1, 2, 3), ""));
    var expected =
        activity(
            new NormalizationEngine()
                .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of())
                .header()
                .session());
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var content =
          new NormalizationEngine()
              .normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      var actual = activity(content.header().session());
      assertThat(actual).isEqualTo(expected);
      scalarOnly(actual);
      assertThatThrownBy(() -> actual.put("version", 2))
          .isInstanceOf(UnsupportedOperationException.class);
      var days = map(actual.get("days"));
      var day = map(days.get("2026-06-01"));
      var tokens = map(day.get("tokens"));
      var fresh = map(tokens.get("fresh"));
      var undated = map(actual.get("undatedTokens"));
      var undatedFresh = map(undated.get("fresh"));
      for (var nested : List.of(days, day, tokens, fresh, undated, undatedFresh)) {
        assertThatThrownBy(() -> nested.put("unexpected", 1L))
            .isInstanceOf(UnsupportedOperationException.class);
      }
      for (int pass = 0; pass < 2; pass++) {
        long calls = 0;
        try (var cursor = content.openCursor()) {
          while (cursor.hasNext()) calls += cursor.next().calls().size();
        }
        assertThat(calls).isEqualTo(1);
        assertThat(activity(content.header().session())).isEqualTo(expected);
      }
    }
  }

  private static List<Map<String, Object>> codexActivities(List<SourceRecord> records)
      throws Exception {
    var engine = new NormalizationEngine();
    var result = new ArrayList<Map<String, Object>>();
    result.add(
        activity(
            engine
                .normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of())
                .header()
                .session()));
    try (var sequence = SourceRecordSequence.fromList(records)) {
      result.add(
          activity(
              engine
                  .normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
                  .header()
                  .session()));
    }
    assertThat(result.get(1)).isEqualTo(result.get(0));
    return result;
  }

  private static Map<String, Object> activity(Map<String, Object> session) {
    assertThat(session)
        .as("eventActivity must be present; missing is not measured zero")
        .containsKey("eventActivity");
    return map(session.get("eventActivity"));
  }

  private static Map<String, Object> map(Object value) {
    assertThat(value).isInstanceOf(Map.class);
    // 需要直接测试生产map的不可变性，不能返回测试侧防御副本。
    return castMap(value);
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> castMap(Object value) {
    return (Map<String, Object>) value;
  }

  private static void assertContract(
      Map<String, Object> value,
      long users,
      long undatedUsers,
      long supported,
      long undatedUsage,
      long unsupported) {
    assertThat(value.get("version")).isEqualTo(1);
    assertThat(value.get("basis")).isEqualTo("source_event_utc");
    assertThat(value.get("tokenBasis")).isEqualTo("codex_modern_usage_report_day");
    assertThat(value.get("observedUserMessages")).isEqualTo(users);
    assertThat(value.get("undatedUserMessages")).isEqualTo(undatedUsers);
    assertThat(value.get("supportedUsageEvents")).isEqualTo(supported);
    assertThat(value.get("undatedUsageEvents")).isEqualTo(undatedUsage);
    assertThat(value.get("unsupportedUsageEvents")).isEqualTo(unsupported);
  }

  private static void scalarOnly(Object value) {
    assertThat(value).isNotInstanceOf(SourceRecord.class);
    if (value instanceof Map<?, ?> map) {
      map.forEach(
          (key, child) -> {
            assertThat(key).isInstanceOf(String.class);
            scalarOnly(child);
          });
    } else {
      assertThat(value).isInstanceOfAny(String.class, Number.class);
      assertThat(value).isNotEqualTo(BODY);
    }
  }

  private static Map<String, Object> day(
      long users, Map<String, Object> tokens, String latestEventTimestamp) {
    return Map.of(
        "observedUserMessages",
        users,
        "tokens",
        tokens,
        "latestEventTimestamp",
        latestEventTimestamp);
  }

  private static Map<String, Object> tokens(
      Map<String, Long> fresh,
      Map<String, Long> read,
      Map<String, Long> write,
      Map<String, Long> output) {
    return Map.of("fresh", fresh, "cacheRead", read, "cacheWrite", write, "output", output);
  }

  private static Map<String, Object> zeroTokens() {
    return tokens(
        samples(0, 0, 0, 0, 0, 0),
        samples(0, 0, 0, 0, 0, 0),
        samples(0, 0, 0, 0, 0, 0),
        samples(0, 0, 0, 0, 0, 0));
  }

  private static Map<String, Object> reportedTokens(
      long fresh, long read, long write, long output) {
    return tokens(
        samples(fresh, 1, 0, 0, 0, 0),
        samples(read, 1, 0, 0, 0, 0),
        samples(write, 1, 0, 0, 0, 0),
        samples(output, 1, 0, 0, 0, 0));
  }

  private static Map<String, Long> samples(
      long amount, long reported, long estimated, long unavailable, long unknown, long mixed) {
    return Map.of(
        "reportedTokens",
        amount,
        "reportedSamples",
        reported,
        "estimatedSamples",
        estimated,
        "unavailableSamples",
        unavailable,
        "unknownSamples",
        unknown,
        "mixedSamples",
        mixed);
  }

  private static SourceRecordUsage reported(long fresh, long read, long write, long output) {
    return new SourceRecordUsage(
        fresh,
        read,
        write,
        output,
        Map.of(
            "freshInputTokenPrecision",
            "provider_reported",
            "cacheReadTokenPrecision",
            "provider_reported",
            "cacheWriteTokenPrecision",
            "provider_reported",
            "outputTokenPrecision",
            "provider_reported"));
  }

  private static SourceRecord record(
      int index, String type, String timestamp, SourceRecordUsage usage, String mode) {
    String locator = "synthetic/activity#event[" + index + "]";
    if ("sidecar".equals(mode)) locator = "synthetic/subagents/child#event[" + index + "]";
    var relation =
        "child".equals(mode)
            ? new SourceRecordRelation(
                Optional.of("child"),
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                Optional.empty())
            : SourceRecordRelation.empty();
    boolean usageFrame = List.of("modern", "legacy").contains(type);
    String id =
        "modern".equals(type)
            ? "token_usage_record:" + index
            : "legacy".equals(type) ? "token_count:" + index : "call-" + index;
    Optional<String> role =
        "no-role".equals(mode)
            ? Optional.empty()
            : "user".equals(type) || "explicit-user".equals(mode)
                ? Optional.of("user")
                : Optional.empty();
    return new SourceRecord(
        locator,
        index,
        usageFrame ? "assistant" : type,
        Optional.of(id),
        Optional.empty(),
        Optional.ofNullable(timestamp),
        Optional.of("shared-turn"),
        usage,
        List.of(),
        "tool".equals(mode) || "tool_result".equals(type)
            ? Optional.of("synthetic-tool")
            : Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        relation,
        BODY,
        "fragment".equals(mode) ? Optional.of("same-response") : Optional.empty(),
        Optional.empty(),
        com.feipi.session.browser.domain.source.SourceTiming.empty(),
        "meta".equals(mode),
        role);
  }
}
