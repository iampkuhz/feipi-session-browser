package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 新增会话趋势按 UTC 开始日统计整段用量，不把结束日或未知日期当作新增日期。 */
class TrendDateCohortTest {
  @TempDir Path directory;
  private IndexConnection connection;
  private SqliteIndexWriter writer;
  private SqliteAggregateQueryRepository repository;
  private LocalDate today;
  private int nextSession;

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("trend-cohort.db");
    connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url);
    writer = new SqliteIndexWriter(connection.writerConnection());
    writer.ensureSchema();
    repository = new SqliteAggregateQueryRepository(connection);
    try (var statement = connection.writerConnection().createStatement();
        var row = statement.executeQuery("SELECT DATE('now')")) {
      assertThat(row.next()).isTrue();
      today = LocalDate.parse(row.getString(1));
    }
  }

  @AfterEach
  void close() {
    connection.close();
  }

  @Test
  void midnightCrossingKeepsWholeSessionWorkloadOnItsStartDay() {
    LocalDate day = today.minusDays(2);
    // 会话行已包含 MAIN + child workload；不能按天再拆分或叠加 child。
    insert(
        NormalizedAgent.CODEX,
        day + "T23:50:00Z",
        day.plusDays(1) + "T01:00:00Z",
        usage(10, 20, 30, 40),
        2,
        4,
        reported());
    var filter = TrendFilter.ofDays(7);
    assertThat(repository.trendData(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.totalCount()).isEqualTo(1);
              assertThat(row.codexCount()).isEqualTo(1);
              assertThat(row.claudeCount()).isZero();
              assertThat(row.qoderCount()).isZero();
              assertThat(row.codexTokens()).isEqualTo(100);
              assertThat(row.totalTokens()).isEqualTo(100);
              assertThat(row.freshInputTokens()).isEqualTo(10);
              assertThat(row.cacheReadTokens()).isEqualTo(20);
              assertThat(row.cacheWriteTokens()).isEqualTo(30);
              assertThat(row.outputTokens()).isEqualTo(40);
              assertThat(row.codexFreshInput()).isEqualTo(10);
              assertThat(row.codexCacheRead()).isEqualTo(20);
              assertThat(row.codexCacheWrite()).isEqualTo(30);
              assertThat(row.toolCalls()).isEqualTo(4);
              assertThat(row.failedTools()).isEqualTo(1);
              assertThat(row.tokenProvenance()).isEqualTo(reported());
            });
    assertThat(repository.activityTrend(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.codexPrompts()).isEqualTo(2);
              assertThat(row.totalPrompts()).isEqualTo(2);
              assertThat(row.assistantTurns()).isEqualTo(3);
              assertThat(row.toolCalls()).isEqualTo(4);
            });
  }

  @Test
  void startOffsetsNormalizeToUtcRatherThanTheWrittenCalendarDate() {
    LocalDate day = today.minusDays(2);
    insert(
        NormalizedAgent.CLAUDE_CODE,
        day.plusDays(1) + "T00:30:00+02:00",
        day.plusDays(1) + "T04:00:00Z",
        usage(10, 0, 0, 0),
        1,
        1,
        reported());
    insert(
        NormalizedAgent.QODER,
        day + "T23:30:00-02:00",
        day.plusDays(2) + "T01:00:00Z",
        usage(20, 0, 0, 0),
        2,
        2,
        TokenProvenance.unknown());
    var filter = TrendFilter.ofDays(7);
    assertThat(repository.trendData(filter))
        .extracting(row -> row.date())
        .containsExactly(day.toString(), day.plusDays(1).toString());
    assertThat(repository.trendData(filter))
        .extracting(row -> row.totalTokens())
        .containsExactly(10L, 20L);
    assertThat(repository.activityTrend(filter))
        .extracting(row -> row.date())
        .containsExactly(day.toString(), day.plusDays(1).toString());
    assertThat(repository.activityTrend(filter))
        .extracting(row -> row.totalPrompts())
        .containsExactly(1L, 2L);
  }

  @Test
  void windowBoundaryUsesUtcStartEvenWhenEndOrWrittenDateSuggestsTheOpposite() {
    LocalDate cutoff = today.minusDays(3);
    // 结束元数据故意相反，证明窗口只依据可信的开始 cohort，不从结束日推导。
    insert(
        NormalizedAgent.CODEX,
        cutoff + "T00:00:00Z",
        cutoff.minusDays(5) + "T00:00:00Z",
        usage(1, 0, 0, 0),
        1,
        1,
        reported());
    insert(
        NormalizedAgent.CODEX,
        cutoff.minusDays(1) + "T23:59:59Z",
        today + "T01:00:00Z",
        usage(100, 0, 0, 0),
        100,
        100,
        TokenProvenance.unknown());
    insert(
        NormalizedAgent.CODEX,
        cutoff + "T00:30:00+01:00",
        today + "T01:00:00Z",
        usage(1000, 0, 0, 0),
        1000,
        1000,
        TokenProvenance.unknown());
    insert(
        NormalizedAgent.CODEX,
        cutoff.minusDays(1) + "T23:30:00-01:00",
        today + "T01:00:00Z",
        usage(2, 0, 0, 0),
        2,
        2,
        reported());
    var filter = TrendFilter.ofDays(3);
    assertThat(repository.trendData(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(cutoff.toString());
              assertThat(row.totalCount()).isEqualTo(2);
              assertThat(row.totalTokens()).isEqualTo(3);
              assertThat(row.toolCalls()).isEqualTo(3);
              assertThat(row.tokenProvenance()).isEqualTo(reported());
            });
    assertThat(repository.activityTrend(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(cutoff.toString());
              assertThat(row.totalPrompts()).isEqualTo(3);
              assertThat(row.assistantTurns()).isEqualTo(6);
              assertThat(row.toolCalls()).isEqualTo(3);
            });
  }

  @Test
  void missingOrInvalidStartIsExcludedInsteadOfBeingAssignedToToday() {
    for (String start :
        List.of(
            "",
            "not-a-date",
            "2026-13-99T00:00:00Z",
            "now",
            "2460000.5",
            "1700000000",
            today.getYear() + "-02-30T01:00:00Z")) {
      insert(
          NormalizedAgent.QODER,
          start,
          today + "T03:00:00Z",
          usage(100, 0, 0, 0),
          100,
          100,
          TokenProvenance.unknown());
    }
    insert(
        NormalizedAgent.CLAUDE_CODE,
        today + "T01:00:00Z",
        today + "T02:00:00Z",
        usage(7, 0, 0, 0),
        3,
        2,
        reported());
    var filter = TrendFilter.ofDays(400);
    assertThat(repository.trendData(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(today.toString());
              assertThat(row.totalCount()).isEqualTo(1);
              assertThat(row.totalTokens()).isEqualTo(7);
              assertThat(row.tokenProvenance()).isEqualTo(reported());
            });
    assertThat(repository.activityTrend(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(today.toString());
              assertThat(row.totalPrompts()).isEqualTo(3);
              assertThat(row.qoderPrompts()).isZero();
              assertThat(row.toolCalls()).isEqualTo(2);
            });
  }

  @Test
  void agentFilterAndMixedPrecisionUseExactlyTheSameStartCohort() {
    LocalDate day = today.minusDays(2);
    String start = day + "T23:00:00Z";
    String end = day.plusDays(1) + "T02:00:00Z";
    var estimate =
        new TokenProvenance(
            "estimated", "unavailable", "unavailable", "estimated", "visible_context_v1", 1, 1, 0);
    insert(NormalizedAgent.CLAUDE_CODE, start, end, usage(1, 2, 3, 4), 2, 3, reported());
    insert(NormalizedAgent.QODER, start, end, usage(20, 0, 0, 5), 4, 7, estimate);
    insert(NormalizedAgent.CODEX, start, end, usage(7, 2, 1, 3), 6, 11, TokenProvenance.unknown());
    var filter = TrendFilter.ofDays(7);
    assertThat(repository.trendData(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.totalCount()).isEqualTo(3);
              assertThat(row.freshInputTokens()).isEqualTo(28);
              assertThat(row.cacheReadTokens()).isEqualTo(4);
              assertThat(row.cacheWriteTokens()).isEqualTo(4);
              assertThat(row.outputTokens()).isEqualTo(12);
              assertThat(row.totalTokens()).isEqualTo(48);
              assertThat(row.claudeTokens()).isEqualTo(10);
              assertThat(row.qoderTokens()).isEqualTo(25);
              assertThat(row.codexTokens()).isEqualTo(13);
              assertThat(row.toolCalls()).isEqualTo(21);
              assertThat(row.tokenProvenance().freshInput()).isEqualTo("mixed");
              assertThat(row.tokenProvenance().estimatedSessionCount()).isEqualTo(1);
              assertThat(row.tokenProvenance().unavailableSessionCount()).isEqualTo(1);
              assertThat(row.tokenProvenance().unknownSessionCount()).isEqualTo(1);
            });
    assertThat(repository.activityTrend(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.claudePrompts()).isEqualTo(2);
              assertThat(row.qoderPrompts()).isEqualTo(4);
              assertThat(row.codexPrompts()).isEqualTo(6);
              assertThat(row.totalPrompts()).isEqualTo(12);
              assertThat(row.assistantTurns()).isEqualTo(9);
              assertThat(row.toolCalls()).isEqualTo(21);
            });
    var qoder = filter.withAgent(AgentFilter.of("qoder"));
    assertThat(repository.trendData(qoder))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.totalCount()).isEqualTo(1);
              assertThat(row.totalTokens()).isEqualTo(25);
              assertThat(row.toolCalls()).isEqualTo(7);
              assertThat(row.tokenProvenance()).isEqualTo(estimate);
            });
    assertThat(repository.activityTrend(qoder))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.claudePrompts()).isZero();
              assertThat(row.codexPrompts()).isZero();
              assertThat(row.qoderPrompts()).isEqualTo(4);
              assertThat(row.totalPrompts()).isEqualTo(4);
              assertThat(row.toolCalls()).isEqualTo(7);
            });
  }

  @Test
  void sameStartDayWithDifferentEndDaysRemainsOneBucket() {
    LocalDate day = today.minusDays(3);
    insert(
        NormalizedAgent.CODEX,
        day + "T01:00:00Z",
        day.plusDays(1) + "T01:00:00Z",
        usage(7, 0, 0, 0),
        2,
        6,
        reported());
    insert(
        NormalizedAgent.CODEX,
        day + "T02:00:00Z",
        day.plusDays(2) + "T02:00:00Z",
        usage(11, 0, 0, 0),
        3,
        7,
        TokenProvenance.unknown());
    var filter = TrendFilter.ofDays(7);
    assertThat(repository.trendData(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.totalCount()).isEqualTo(2);
              assertThat(row.totalTokens()).isEqualTo(18);
              assertThat(row.toolCalls()).isEqualTo(13);
              assertThat(row.tokenProvenance().freshInput()).isEqualTo("mixed");
              assertThat(row.tokenProvenance().unknownSessionCount()).isEqualTo(1);
            });
    assertThat(repository.activityTrend(filter))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.date()).isEqualTo(day.toString());
              assertThat(row.totalPrompts()).isEqualTo(5);
              assertThat(row.toolCalls()).isEqualTo(13);
            });
  }

  private static TokenProvenance reported() {
    return new TokenProvenance(
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "",
        0,
        0,
        0);
  }

  private static NormalizedCallUsage usage(long fresh, long read, long write, long output) {
    return new NormalizedCallUsage(fresh, read, write, output, fresh + read + write + output);
  }

  private void insert(
      NormalizedAgent agent,
      String start,
      String end,
      NormalizedCallUsage usage,
      long prompts,
      long tools,
      TokenProvenance precision) {
    String id = "synthetic-" + nextSession++;
    Map<String, Object> session = new HashMap<>();
    session.put("session_key", agent.getValue() + ":" + id);
    session.put("session_id", id);
    session.put("project_key", "synthetic");
    session.put("started_at", start);
    session.put("ended_at", end);
    session.put("freshInputTokens", usage.fresh());
    session.put("cacheReadTokens", usage.cacheRead());
    session.put("cacheWriteTokens", usage.cacheWrite());
    session.put("outputTokens", usage.output());
    session.put("totalTokens", usage.total());
    session.put("userMessageCount", prompts);
    session.put("assistantMessageCount", 3L);
    session.put("toolCallCount", tools);
    session.put("failedToolCount", 1L);
    session.put("subagentInstanceCount", 1L);
    session.putAll(precision.toMetadata());
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            agent,
            List.of(),
            session,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    writer.writeNormalizedArtifact(
        artifact, directory.resolve(id + ".json"), "synthetic.jsonl", 1, 1, Instant.EPOCH);
    writer.flushPendingWrites();
  }
}
