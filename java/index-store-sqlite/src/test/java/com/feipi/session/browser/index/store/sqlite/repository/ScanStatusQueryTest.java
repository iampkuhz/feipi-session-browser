package com.feipi.session.browser.index.store.sqlite.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.api.write.ScanFailure;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.query.api.SessionListFilter;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ScanStatusQueryTest {
  @TempDir Path directory;

  @Test
  void latestFailureIsReadableWithoutGenerationChangeAndRetainsPublishedData() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("status.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url)) {
      var writer = new SqliteIndexWriter(connection);
      writer.ensureSchema();
      var query = new SqliteSessionQueryRepository(index);
      assertThat(query.latestScan()).isEmpty();
      long first = writer.startScan(0, "full");
      writer.completeScan(first, 1, Map.of());
      String generation = query.publishedGeneration();
      long second = writer.startScan(2, "incremental");
      assertThat(query.latestScan().orElseThrow().status()).isEqualTo("running");
      writer.failScan(
          second,
          3,
          Map.of("codex", 2),
          1,
          List.of(
              new ScanFailure("codex", "fixture-local-key", "PARSE", "BUFFER_OVERFLOW", 42),
              new ScanFailure("codex", "fixture-local-key", "PARSE", "BAD_JSON", 43)));
      assertThat(query.publishedGeneration()).isEqualTo(generation);
      var status = query.latestScan().orElseThrow();
      assertThat(status.status()).isEqualTo("failure");
      assertThat(status.errorCount()).isEqualTo(1);
      assertThat(status.failures()).hasSize(2);
      assertThat(status.processedCount()).isEqualTo(2);
      assertThat(status.publishedDataAvailable()).isTrue();
      assertThat(status.failures().getFirst().code()).isEqualTo("BUFFER_OVERFLOW");
      long aborted = writer.startScan(4, "full");
      writer.failScan(aborted, 5, Map.of());
      assertThat(query.latestScan().orElseThrow().failures().getFirst().code())
          .isEqualTo("SCAN_ABORTED");
    }
  }

  @Test
  void unknownProjectIsNotAProjectCountOrAnInvalidFilterOption() throws Exception {
    String url = "jdbc:sqlite:" + directory.resolve("unknown-project.db");
    try (var connection = DriverManager.getConnection(url);
        var index = IndexConnection.withDefaults(connection, url)) {
      IndexSchema.withDefaults().ensureSchema(connection);
      try (var statement = connection.createStatement()) {
        statement.executeUpdate(
            "INSERT INTO sessions(session_key, agent, session_id, project_key, project_name, cwd, ended_at) VALUES ('codex:unknown', 'codex', 'unknown', '', '', '', '')");
      }
      var query = new SqliteSessionQueryRepository(index);
      assertThat(query.listSummary(SessionListFilter.defaults()).projectCount()).isZero();
      assertThat(query.listAggregate(SessionListFilter.defaults()).projectCount()).isZero();
      assertThat(query.listProjectOptions(SessionListFilter.defaults())).isEmpty();
    }
  }
}
