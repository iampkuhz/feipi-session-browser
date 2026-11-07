package com.feipi.session.browser.index.store.sqlite.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.Migration;
import com.feipi.session.browser.index.store.sqlite.schema.MigrationRunner;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class MessageMeasurementPersistenceTest {
  @TempDir Path directory;

  @Test
  void unchangedSuccessPreservesGenerationAndStillRecordsScanCompletion() throws Exception {
    try (var connection =
        DriverManager.getConnection("jdbc:sqlite:" + directory.resolve("noop.db"))) {
      var writer = new SqliteIndexWriter(connection);
      writer.ensureSchema();
      long first = writer.startScan(0, "full");
      writer.saveScanLogicVersion(10, Instant.EPOCH);
      writer.completeScan(first, 1, Map.of());
      String generation = generation(connection);
      long unchanged = writer.startScan(2, "incremental");
      writer.saveScanLogicVersion(10, Instant.EPOCH);
      writer.completeScan(unchanged, 3, Map.of());
      assertThat(generation(connection)).isEqualTo(generation);
      long changed = writer.startScan(4, "incremental");
      writer.saveScanLogicVersion(11, Instant.EPOCH);
      writer.completeScan(changed, 5, Map.of());
      assertThat(generation(connection)).isNotEqualTo(generation);
      try (var statement = connection.createStatement();
          var rows =
              statement.executeQuery("SELECT COUNT(*) FROM scan_log WHERE status = 'success'")) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getLong(1)).isEqualTo(3);
      }
    }
  }

  private static String generation(java.sql.Connection connection) throws Exception {
    try (var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT value FROM index_metadata WHERE key = 'published_generation'")) {
      assertThat(rows.next()).isTrue();
      return rows.getString(1);
    }
  }

  @Test
  void userAndAssistantMeasurementAreIndependent() {
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(
                "session_key",
                "codex:user-only",
                "session_id",
                "user-only",
                "userMessageCount",
                1,
                "assistantMessageCount",
                0,
                "userMessageCountMeasured",
                true,
                "assistantMessageCountMeasured",
                false),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var row = ArtifactRowMapper.toSessionRow(artifact, 0, "fixture");
    assertThat(row.userMessageMeasured()).isTrue();
    assertThat(row.assistantMessageMeasured()).isFalse();
  }

  @Test
  void explicitRoleMeasurementSurvivesPublicationAndReopenWithoutCountInference() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("measurement.db");
    try (var connection = DriverManager.getConnection(url)) {
      var writer = new SqliteIndexWriter(connection);
      writer.ensureSchema();
      long scan = writer.startScan(0, "full");
      writer.writeNormalizedArtifact(
          artifact("unknown", 7, false), Path.of("unknown.json"), "fixture", 0, 0, Instant.EPOCH);
      writer.writeNormalizedArtifact(
          artifact("zero", 0, true), Path.of("zero.json"), "fixture", 0, 0, Instant.EPOCH);
      writer.writeNormalizedArtifact(
          artifact("positive", 7, true), Path.of("positive.json"), "fixture", 0, 0, Instant.EPOCH);
      writer.completeScan(scan, 1, Map.of());
    }
    try (var connection = DriverManager.getConnection(url);
        var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT "
                    + SqliteSessionResultSetMapper.ALL_COLUMNS
                    + " FROM sessions ORDER BY session_id")) {
      assertThat(rows.next()).isTrue();
      var positive = SqliteSessionResultSetMapper.mapRow(rows);
      assertThat(positive.userMessageMeasured()).isTrue();
      assertThat(positive.assistantMessageMeasured()).isTrue();
      assertThat(positive.assistantMessageCount()).isEqualTo(7);
      assertThat(rows.next()).isTrue();
      var unknown = SqliteSessionResultSetMapper.mapRow(rows);
      assertThat(unknown.contentMeasured()).isTrue();
      assertThat(unknown.userMessageMeasured()).isFalse();
      assertThat(unknown.assistantMessageMeasured()).isFalse();
      assertThat(rows.next()).isTrue();
      var zero = SqliteSessionResultSetMapper.mapRow(rows);
      assertThat(zero.userMessageMeasured()).isTrue();
      assertThat(zero.assistantMessageMeasured()).isTrue();
      assertThat(zero.assistantMessageCount()).isZero();
    }
  }

  @Test
  void v2AndV3ExistingCountsRemainUnmeasuredAfterV4Migration() throws Exception {
    for (int version : List.of(2, 3)) {
      try (var connection =
          DriverManager.getConnection("jdbc:sqlite:" + directory.resolve("v" + version + ".db"))) {
        new MigrationRunner(Migration.allMigrations().subList(0, version)).applyAll(connection);
        try (var statement = connection.createStatement()) {
          statement.executeUpdate(
              "INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at,"
                  + " user_message_count, assistant_message_count) VALUES ('codex:old', 'codex',"
                  + " 'old', '', '', 4, 9)");
        }
        IndexSchema.withDefaults().ensureSchema(connection);
        try (var statement = connection.createStatement();
            var rows =
                statement.executeQuery(
                    "SELECT " + SqliteSessionResultSetMapper.ALL_COLUMNS + " FROM sessions")) {
          assertThat(rows.next()).isTrue();
          var row = SqliteSessionResultSetMapper.mapRow(rows);
          assertThat(row.userMessageCount()).isEqualTo(4);
          assertThat(row.assistantMessageCount()).isEqualTo(9);
          assertThat(row.userMessageMeasured()).isFalse();
          assertThat(row.assistantMessageMeasured()).isFalse();
        }
      }
    }
  }

  private static NormalizedSessionArtifact artifact(String id, long count, boolean measured) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CODEX,
        List.of(),
        Map.of(
            "session_key",
            "codex:" + id,
            "session_id",
            id,
            "contentMeasured",
            true,
            "userMessageCount",
            count,
            "assistantMessageCount",
            count,
            "userMessageCountMeasured",
            measured,
            "assistantMessageCountMeasured",
            measured),
        List.of(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }
}
