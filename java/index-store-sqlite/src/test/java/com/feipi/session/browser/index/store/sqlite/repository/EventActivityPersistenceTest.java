package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.api.query.EventActivity;
import com.feipi.session.browser.index.api.write.MissingTranscriptSession;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.query.api.AgentFilter;
import com.feipi.session.browser.query.api.TrendFilter;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class EventActivityPersistenceTest {
  @TempDir Path tempDir;

  @Test
  void persistedEventDaysDoNotUseSessionStartAndKeepZeroUnknownAndUndatedPrecision()
      throws Exception {
    String date = today().minusDays(1).toString();
    String url = url();
    try (var connection = open(url)) {
      var writer = writer(connection);
      long scan = writer.startScan(1, "full");
      write(
          writer,
          "a",
          NormalizedAgent.CODEX,
          summary(Map.of(date, day(2, date + "T23:00:00Z"))),
          false);
      writer.completeScan(scan, 2, Map.of("codex", 1));
    }
    // 重开 SQLite，不创建或读取任何正文制品，证明日事实已经持久化。
    try (var connection = open(url)) {
      EventActivity result = query(connection, 2, "codex");
      assertThat(result.days()).hasSize(1);
      var day = result.days().getFirst();
      assertThat(day.date()).isEqualTo(date);
      assertThat(day.observedUserMessages()).isEqualTo(2);
      assertThat(day.tokens().get("fresh").reportedTokens()).isEqualTo(0L);
      assertThat(day.tokens().get("fresh").reportedSamples()).isEqualTo(1);
      assertThat(day.tokens().get("output").reportedTokens()).isNull();
      assertThat(day.tokens().get("output").unknownSamples()).isEqualTo(1);
      assertThat(result.undatedTokens().get("cacheRead").estimatedSamples()).isEqualTo(1);
      assertThat(result.undatedTokens().get("cacheRead").reportedTokens()).isNull();
      assertThat(result.undatedTokens().get("cacheWrite").unavailableSamples()).isEqualTo(1);
      assertThat(result.undatedTokens().get("output").mixedSamples()).isEqualTo(1);
      assertThat(result.coverage())
          .containsEntry("indexedSessions", 1L)
          .containsEntry("summarizedSessions", 1L)
          .containsEntry("unknownSessions", 0L)
          .containsEntry("observedUserMessages", 3L)
          .containsEntry("undatedUserMessages", 1L)
          .containsEntry("supportedUsageEvents", 2L)
          .containsEntry("undatedUsageEvents", 1L)
          .containsEntry("unsupportedUsageEvents", 3L);
    }
  }

  @Test
  void filtersUseEventWindowAndConservativelyExcludeFutureMixedBuckets() throws Exception {
    String past = today().minusDays(1).toString();
    String old = today().minusDays(40).toString();
    String current = today().toString();
    String future = today().plusDays(1).toString();
    try (var connection = open(url())) {
      var writer = writer(connection);
      long scan = writer.startScan(1, "full");
      write(
          writer,
          "a",
          NormalizedAgent.CODEX,
          summary(
              Map.of(
                  past,
                  day(2, past + "T12:00:00Z"),
                  old,
                  day(4, old + "T12:00:00Z"),
                  current,
                  day(5, current + "T23:59:59.999999999Z"),
                  future,
                  day(6, future + "T12:00:00Z"))),
          true);
      write(
          writer,
          "b",
          NormalizedAgent.QODER,
          summary(Map.of(past, day(9, past + "T12:00:00Z"))),
          false);
      writer.completeScan(scan, 2, Map.of("codex", 1, "qoder", 1));
      var result = query(connection, 2, "codex");
      assertThat(result.days()).extracting(EventActivity.Day::date).containsExactly(past);
      assertThat(result.days().getFirst().observedUserMessages()).isEqualTo(2);
      assertThat(result.coverage())
          .containsEntry("indexedSessions", 1L)
          .containsEntry("observedUserMessages", 18L)
          .containsEntry("futureExcludedDayBuckets", 2L)
          .containsEntry("futureExcludedObservedUserMessages", 11L);
      assertThat(query(connection, 2, "qoder").days().getFirst().observedUserMessages())
          .isEqualTo(9);
      assertThat(query(connection, 60, "codex").days())
          .extracting(EventActivity.Day::date)
          .containsExactly(old, past);
    }
  }

  @Test
  void replacementDoesNotAccumulateAndMissingTranscriptClearsOldFacts() throws Exception {
    String date = today().minusDays(1).toString();
    try (var connection = open(url())) {
      var writer = writer(connection);
      long scan = writer.startScan(1, "full");
      write(
          writer,
          "a",
          NormalizedAgent.CODEX,
          summary(Map.of(date, day(8, date + "T12:00:00Z"))),
          false);
      writer.completeScan(scan, 2, Map.of());
      scan = writer.startScan(3, "incremental");
      write(
          writer,
          "a",
          NormalizedAgent.CODEX,
          summary(Map.of(date, day(2, date + "T12:00:00Z"))),
          true);
      write(writer, "legacy", NormalizedAgent.CODEX, null, false);
      writer.completeScan(scan, 4, Map.of());
      assertThat(query(connection, 2, "codex").days().getFirst().observedUserMessages())
          .isEqualTo(2);
      assertThat(query(connection, 2, "codex").coverage()).containsEntry("unknownSessions", 1L);
      scan = writer.startScan(5, "incremental");
      writer.writeMissingTranscriptSession(
          new MissingTranscriptSession(
              "codex:a", "codex", "a", "", "", "", "", "", "", "", Instant.EPOCH));
      writer.completeScan(scan, 6, Map.of());
      assertThat(query(connection, 2, "codex").days()).isEmpty();
      assertThat(query(connection, 2, "codex").coverage())
          .containsEntry("unknownSessions", 2L)
          .containsEntry("summarizedSessions", 0L);
    }
  }

  @Test
  void failedScanRestoresDaysCoverageAndAssociationAndClearsAreScoped() throws Exception {
    String date = today().minusDays(1).toString();
    try (var connection = open(url())) {
      var writer = writer(connection);
      long scan = writer.startScan(1, "full");
      for (var agent : List.of(NormalizedAgent.CODEX, NormalizedAgent.QODER)) {
        write(writer, "a", agent, summary(Map.of(date, day(2, date + "T12:00:00Z"))), false);
      }
      writer.completeScan(scan, 2, Map.of());
      var before = query(connection, 2, "");
      scan = writer.startScan(3, "full");
      writer.clearExistingIndex(Set.of("codex"));
      write(
          writer,
          "a",
          NormalizedAgent.CODEX,
          summary(Map.of(date, day(99, date + "T12:00:00Z"))),
          true);
      writer.flushPendingWrites();
      writer.failScan(scan, 4, Map.of());
      assertThat(query(connection, 2, "")).isEqualTo(before);
      try (var statement = connection.writerConnection().createStatement();
          var rows =
              statement.executeQuery(
                  "SELECT path FROM session_artifacts WHERE session_key = 'codex:a'")) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getString(1)).endsWith("codex-a.json");
        assertThat(rows.next()).isFalse();
      }
      scan = writer.startScan(5, "full");
      writer.clearExistingIndex(Set.of("codex"));
      writer.completeScan(scan, 6, Map.of());
      assertThat(query(connection, 2, "codex").days()).isEmpty();
      assertThat(query(connection, 2, "qoder").days()).hasSize(1);
      assertThat(query(connection, 2, "").coverage()).containsEntry("indexedSessions", 1L);
      scan = writer.startScan(7, "full");
      writer.clearExistingIndex();
      writer.completeScan(scan, 8, Map.of());
      assertThat(query(connection, 2, "").days()).isEmpty();
      assertThat(query(connection, 2, "").coverage())
          .containsEntry("indexedSessions", 0L)
          .containsEntry("summarizedSessions", 0L);
    }
  }

  @Test
  void malformedSummaryIsNotPublishedAsSuccessfulEmptyObservation() throws Exception {
    try (var connection = open(url())) {
      var writer = writer(connection);
      long scan = writer.startScan(1, "full");
      assertThatThrownBy(
              () -> {
                write(
                    writer,
                    "bad",
                    NormalizedAgent.CODEX,
                    Map.of("version", 1, "days", Map.of("not-a-day", Map.of())),
                    false);
                writer.flushPendingWrites();
              })
          .isInstanceOf(RuntimeException.class);
      writer.failScan(scan, 2, Map.of());
    }
  }

  private static LocalDate today() {
    return LocalDate.now(ZoneOffset.UTC);
  }

  private String url() {
    return "jdbc:sqlite:" + tempDir.resolve("event.db");
  }

  private static IndexConnection open(String url) throws Exception {
    return IndexConnection.withDefaults(DriverManager.getConnection(url), url);
  }

  private static SqliteIndexWriter writer(IndexConnection connection) {
    var writer = new SqliteIndexWriter(connection.writerConnection());
    writer.ensureSchema();
    return writer;
  }

  private static EventActivity query(IndexConnection connection, int days, String agent) {
    return new SqliteAggregateQueryRepository(connection)
        .eventActivity(TrendFilter.ofDays(days).withAgent(AgentFilter.of(agent)));
  }

  private void write(
      SqliteIndexWriter writer,
      String id,
      NormalizedAgent agent,
      Map<String, Object> summary,
      boolean content)
      throws Exception {
    Map<String, Object> metadata = new LinkedHashMap<>();
    metadata.put("session_key", agent.getValue() + ":" + id);
    metadata.put("session_id", id);
    metadata.put("started_at", "2000-01-01T00:00:00Z");
    if (summary != null) metadata.put("eventActivity", summary);
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            agent,
            List.of(),
            metadata,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    Path path =
        tempDir.resolve(agent.getValue() + "-" + id + (content ? "-content" : "") + ".json");
    if (content)
      writer.writeNormalizedContent(
          NormalizedSessionContent.fromArtifact(artifact),
          path,
          "synthetic.jsonl",
          1,
          1,
          Instant.EPOCH);
    else writer.writeNormalizedArtifact(artifact, path, "synthetic.jsonl", 1, 1, Instant.EPOCH);
  }

  private static Map<String, Object> summary(Map<String, Object> days) {
    long messages =
        days.values().stream()
            .mapToLong(
                value -> ((Number) ((Map<?, ?>) value).get("observedUserMessages")).longValue())
            .sum();
    return Map.of(
        "version",
        1,
        "basis",
        "source_event_utc",
        "tokenBasis",
        "codex_modern_usage_report_day",
        "observedUserMessages",
        messages + 1,
        "undatedUserMessages",
        1L,
        "supportedUsageEvents",
        (long) days.size() + 1,
        "undatedUsageEvents",
        1L,
        "unsupportedUsageEvents",
        3L,
        "days",
        days,
        "undatedTokens",
        undatedTokens());
  }

  private static Map<String, Object> day(long messages, String latest) {
    return Map.of(
        "observedUserMessages", messages, "latestEventTimestamp", latest, "tokens", tokens());
  }

  private static Map<String, Object> tokens() {
    return Map.of(
        "fresh",
        component(0, 1, 0, 0, 0, 0),
        "cacheRead",
        component(0, 0, 1, 0, 0, 0),
        "cacheWrite",
        component(0, 0, 0, 1, 0, 0),
        "output",
        component(0, 0, 0, 0, 1, 0));
  }

  private static Map<String, Object> undatedTokens() {
    var values = new LinkedHashMap<>(tokens());
    values.put("output", component(0, 0, 0, 0, 0, 1));
    return values;
  }

  private static Map<String, Object> component(
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
}
