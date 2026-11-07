package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import java.nio.file.Path;
import java.sql.DriverManager;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

/** 通过实际 SQL 分组验证 wall duration 的 nearest-rank P95，不混用其他 agent/model。 */
class AgentEfficiencyPercentileTest {
  @TempDir Path directory;
  private IndexConnection connection;
  private SqliteAggregateQueryRepository repository;
  private int nextSession;

  @BeforeEach
  void setUp() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("efficiency.db");
    connection = IndexConnection.withDefaults(DriverManager.getConnection(url), url);
    new SqliteIndexWriter(connection.writerConnection()).ensureSchema();
    repository = new SqliteAggregateQueryRepository(connection);
  }

  @AfterEach
  void close() {
    connection.close();
  }

  @ParameterizedTest
  @CsvSource({"1, 1", "2, 2", "20, 19", "21, 20"})
  void nearestRankSelectsExactObservationForCohortSize(int size, double expected) throws Exception {
    // 逆序插入，不能依赖输入顺序或把 nearest-rank 误写成插值索引。
    for (int value = size; value > 0; value--) {
      insert("claude_code", "synthetic-model", value, 1);
    }
    assertThat(repository.agentEfficiency())
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.agent()).isEqualTo("claude_code");
              assertThat(row.model()).isEqualTo("synthetic-model");
              assertThat(row.sessionCount()).isEqualTo(size);
              assertThat(row.p95Duration()).isEqualTo(expected);
              assertThat(row.tokenProvenance().unknownSessionCount()).isEqualTo(size);
            });
  }

  @Test
  void emptyTableHasNoEfficiencyRows() {
    assertThat(repository.agentEfficiency()).isEmpty();
  }

  @Test
  void groupWithoutPositiveDurationsKeepsExistingZeroPercentile() throws Exception {
    insert("claude_code", "synthetic-model", 0, 1);
    assertThat(repository.agentEfficiency())
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.sessionCount()).isEqualTo(1);
              assertThat(row.avgDuration()).isZero();
              assertThat(row.p95Duration()).isZero();
            });
  }

  @Test
  void positiveDurationFilterAndAgentModelGroupsRemainIndependent() throws Exception {
    insert("claude_code", "shared-model", 90, 1);
    insert("claude_code", "shared-model", 0, 1);
    insert("claude_code", "shared-model", 10, 1);
    insert("claude_code", "other-model", 1000, 1);
    insert("codex", "shared-model", 2000, 1);
    insert("qoder", "zero-token-model", 8000, 0);
    insert("claude_code", "", 9000, 1);
    var rows = repository.agentEfficiency();
    assertThat(rows)
        .extracting(row -> row.agent() + "/" + row.model())
        .containsExactlyInAnyOrder(
            "claude_code/shared-model",
            "claude_code/other-model",
            "codex/shared-model",
            "qoder/zero-token-model");
    assertThat(rows)
        .filteredOn(row -> row.agent().equals("claude_code") && row.model().equals("shared-model"))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.sessionCount()).isEqualTo(3);
              assertThat(row.avgDuration()).isEqualTo(33.3);
              assertThat(row.p95Duration()).isEqualTo(90);
              assertThat(row.tokenProvenance().unknownSessionCount()).isEqualTo(3);
            });
    assertThat(rows)
        .filteredOn(row -> row.agent().equals("claude_code") && row.model().equals("other-model"))
        .singleElement()
        .satisfies(row -> assertThat(row.p95Duration()).isEqualTo(1000));
    assertThat(rows)
        .filteredOn(row -> row.agent().equals("codex"))
        .singleElement()
        .satisfies(row -> assertThat(row.p95Duration()).isEqualTo(2000));
  }

  @Test
  void measuredZeroRatiosRemainZeroAndMissingMeasurementsDoNotContribute() throws Exception {
    insert("codex", "measured-zero", 1, 100);
    insert("codex", "measured-zero", 1, 900);
    insert("codex", "unknown-only", 1, 900);
    try (var statement = connection.writerConnection().createStatement()) {
      statement.executeUpdate(
          """
          UPDATE sessions SET fresh_input_token_precision = 'provider_reported',
              cache_read_token_precision = 'provider_reported',
              cache_write_token_precision = 'provider_reported',
              output_token_precision = 'provider_reported'
          WHERE session_id = 'synthetic-0'
          """);
      statement.executeUpdate(
          """
          UPDATE sessions SET content_measured = 0, failed_tool_count = 99,
              cache_read_tokens = 900
          WHERE session_id != 'synthetic-0'
          """);
    }
    var rows = repository.agentEfficiency();
    assertThat(rows)
        .filteredOn(row -> row.model().equals("measured-zero"))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.sessionCount()).isEqualTo(2);
              assertThat(row.contentSampleCount()).isEqualTo(1);
              assertThat(row.tokenSampleCount()).isEqualTo(1);
              assertThat(row.failedPerSession()).isEqualTo(0.0);
              assertThat(row.cacheReuseRatio()).isEqualTo(0.0);
            });
    assertThat(rows)
        .filteredOn(row -> row.model().equals("unknown-only"))
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.contentSampleCount()).isZero();
              assertThat(row.tokenSampleCount()).isZero();
              assertThat(row.failedPerSession()).isNull();
              assertThat(row.cacheReuseRatio()).isNull();
            });
  }

  @Test
  void fractionalDurationsKeepExistingDecimalRoundingAfterRankSelection() throws Exception {
    insert("claude_code", "synthetic-model", 19.375, 1);
    insert("claude_code", "synthetic-model", 1.125, 1);
    assertThat(repository.agentEfficiency())
        .singleElement()
        .satisfies(
            row -> {
              assertThat(row.avgDuration()).isEqualTo(10.3);
              assertThat(row.p95Duration()).isEqualTo(19.4);
            });
  }

  private void insert(String agent, String model, double duration, long tokens) throws Exception {
    String id = "synthetic-" + nextSession++;
    try (var statement =
        connection
            .writerConnection()
            .prepareStatement(
                """
                INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at,
                                     model, duration_seconds, fresh_input_tokens, total_tokens)
                VALUES (?, ?, ?, 'synthetic', '2026-01-01T00:00:00Z', ?, ?, ?, ?)
                """)) {
      statement.setString(1, agent + ":" + id);
      statement.setString(2, agent);
      statement.setString(3, id);
      statement.setString(4, model);
      statement.setDouble(5, duration);
      statement.setLong(6, tokens);
      statement.setLong(7, tokens);
      statement.executeUpdate();
      try (var observed =
          connection
              .writerConnection()
              .prepareStatement(
                  "UPDATE sessions SET content_measured = 1, started_at = '2026-01-01T00:00:00Z'"
                      + " WHERE session_key = ?")) {
        observed.setString(1, agent + ":" + id);
        observed.executeUpdate();
      }
      try (var artifact =
          connection
              .writerConnection()
              .prepareStatement(
                  "INSERT INTO session_artifacts(session_key, artifact_type, path) VALUES (?,"
                      + " 'normalized', 'synthetic')")) {
        artifact.setString(1, agent + ":" + id);
        artifact.executeUpdate();
      }
    }
  }
}
