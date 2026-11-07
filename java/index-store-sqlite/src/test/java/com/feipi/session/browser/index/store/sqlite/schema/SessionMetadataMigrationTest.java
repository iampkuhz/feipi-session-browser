package com.feipi.session.browser.index.store.sqlite.schema;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;
import org.junit.jupiter.api.Test;

class SessionMetadataMigrationTest {
  @Test
  void upgradePreservesExtensionsIndexesAndArtifactLinksAndAllowsUnknownValues() throws Exception {
    try (Connection conn = legacyIndex()) {
      IndexSchema.withDefaults().ensureSchema(conn);
      verifyPublishedData(conn);
      try (var statement = conn.createStatement()) {
        statement.execute(
            "INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at)"
                + " VALUES ('unknown', 'codex', 'unknown', '', '')");
        statement.execute(
            "INSERT INTO session_artifacts(session_key, artifact_type, path) VALUES ('unknown', 'normalized', '/synthetic/new.json')");
        try (var result = statement.executeQuery("SELECT kind FROM trigger_audit ORDER BY rowid")) {
          assertThat(result.next()).isTrue();
          assertThat(result.getString(1)).isEqualTo("session");
          assertThat(result.next()).isTrue();
          assertThat(result.getString(1)).isEqualTo("artifact");
          assertThat(result.next()).isFalse();
        }
        try (var result = statement.executeQuery("PRAGMA foreign_key_check")) {
          assertThat(result.next()).isFalse();
        }
        assertThatThrownBy(
                () ->
                    statement.execute(
                        "INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at)"
                            + " VALUES ('invalid', '', 'invalid', '', '')"))
            .isInstanceOf(SQLException.class);
      }
    }
  }

  @Test
  void failureRollsBackDdlRowsArtifactLinksAndMigrationVersion() throws Exception {
    try (Connection conn = legacyIndex();
        var statement = conn.createStatement()) {
      statement.execute(
          "CREATE TRIGGER reject_v2 BEFORE INSERT ON schema_migrations WHEN NEW.version = 2"
              + " BEGIN SELECT RAISE(ABORT, 'synthetic migration failure'); END");
      assertThatThrownBy(() -> IndexSchema.withDefaults().ensureSchema(conn))
          .isInstanceOf(SQLException.class)
          .hasMessageContaining("已回滚");
      verifyPublishedData(conn);
      assertThat(MigrationRunner.withAllMigrations().currentVersion(conn).version()).isEqualTo(1);
      assertThatThrownBy(
              () ->
                  statement.execute(
                      "INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at)"
                          + " VALUES ('unknown', 'codex', 'unknown', '', '')"))
          .isInstanceOf(SQLException.class);
    }
  }

  private Connection legacyIndex() throws Exception {
    Connection conn = SqliteTestHelper.createInMemoryConnection();
    new MigrationRunner(List.of(Migration.allMigrations().getFirst())).applyAll(conn);
    try (var statement = conn.createStatement()) {
      statement.execute(
          "ALTER TABLE sessions ADD COLUMN retained_extension TEXT NOT NULL DEFAULT ''");
      statement.execute("CREATE INDEX idx_retained_extension ON sessions(retained_extension)");
      statement.execute(
          "INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at, retained_extension)"
              + " VALUES ('known', 'codex', 'known', 'project', '2026-01-01T00:00:00Z', 'retained')");
      statement.execute(
          "INSERT INTO session_artifacts(session_key, artifact_type, path) VALUES ('known', 'normalized', '/synthetic/artifact.json')");
    }
    try (var statement = conn.createStatement()) {
      statement.execute("CREATE TABLE trigger_audit(kind TEXT NOT NULL)");
      statement.execute(
          "CREATE TRIGGER session_audit AFTER INSERT ON sessions BEGIN INSERT INTO trigger_audit VALUES ('session'); END");
      statement.execute(
          "CREATE TRIGGER artifact_audit AFTER INSERT ON session_artifacts BEGIN INSERT INTO trigger_audit VALUES ('artifact'); END");
    }
    return conn;
  }

  private void verifyPublishedData(Connection conn) throws Exception {
    try (var statement = conn.createStatement();
        var result =
            statement.executeQuery(
                "SELECT retained_extension, path FROM sessions JOIN session_artifacts USING(session_key) WHERE session_key='known'")) {
      assertThat(result.next()).isTrue();
      assertThat(result.getString(1)).isEqualTo("retained");
      assertThat(result.getString(2)).isEqualTo("/synthetic/artifact.json");
    }
    try (var statement = conn.createStatement();
        var result =
            statement.executeQuery(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_retained_extension'")) {
      assertThat(result.next()).isTrue();
    }
  }
}
