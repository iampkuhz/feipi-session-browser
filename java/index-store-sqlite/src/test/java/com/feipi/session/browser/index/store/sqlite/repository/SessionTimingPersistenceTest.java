package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 新typed计时与legacy数字分离，旧列数字不得冒充测量。 */
class SessionTimingPersistenceTest {
  @TempDir Path tempDir;

  @Test
  void roundTripPreservesUnknownVersusMeasuredZeroAndIndependentActiveTime() throws Exception {
    String url = "jdbc:sqlite:" + tempDir.resolve("timing.db");
    try (IndexConnection connection =
        IndexConnection.withDefaults(DriverManager.getConnection(url), url)) {
      SqliteIndexWriter writer = new SqliteIndexWriter(connection.writerConnection());
      writer.ensureSchema();
      Map<String, Object> legacy = session("legacy");
      legacy.put("modelExecutionSeconds", 3600.0);
      write(writer, legacy);
      Map<String, Object> measured = session("measured");
      measured.putAll(
          new SessionTiming(
                  240.0,
                  "measured",
                  120.0,
                  "measured",
                  "main_task_windows",
                  null,
                  "unknown",
                  "",
                  0.0,
                  "measured",
                  0.0,
                  "measured",
                  1,
                  0,
                  0)
              .toMetadata());
      write(writer, measured);
      writer.flushPendingWrites();
      SqliteSessionQueryRepository sessions = new SqliteSessionQueryRepository(connection);
      var old = sessions.getSession("codex:legacy").orElseThrow();
      assertThat(old.modelExecutionSeconds()).isEqualTo(3600.0);
      assertThat(old.timing().modelExecutionSeconds()).isNull();
      assertThat(old.timing().modelExecutionPrecision()).isEqualTo("unknown");
      var current = sessions.getSession("codex:measured").orElseThrow();
      assertThat(current.durationSeconds()).isEqualTo(240.0);
      assertThat(current.timing().activeTaskSeconds()).isEqualTo(120.0);
      assertThat(current.timing().modelExecutionSeconds()).isZero();
      assertThat(current.timing().toolExecutionSeconds()).isZero();
      assertThat(current.timing().modelExecutionPrecision()).isEqualTo("measured");
      assertThat(current.timing().toolExecutionPrecision()).isEqualTo("measured");
      try (var statement = connection.writerConnection().createStatement();
          var rs =
              statement.executeQuery(
                  "SELECT timing_json FROM sessions WHERE session_id='measured'")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getString(1))
            .contains("\"activeTaskSeconds\":120.0")
            .doesNotContain("\"timing\":");
      }
    }
  }

  private static Map<String, Object> session(String id) {
    Map<String, Object> session = new HashMap<>();
    session.put("session_key", "codex:" + id);
    session.put("session_id", id);
    session.put("project_key", "/synthetic/timing");
    session.put("ended_at", "2026-01-01T00:04:00Z");
    session.put("duration_seconds", 240.0);
    return session;
  }

  private void write(SqliteIndexWriter writer, Map<String, Object> session) {
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            session,
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    writer.writeNormalizedArtifact(
        artifact,
        tempDir.resolve(session.get("session_id") + ".json"),
        "synthetic.jsonl",
        0,
        1,
        Instant.EPOCH);
  }
}
