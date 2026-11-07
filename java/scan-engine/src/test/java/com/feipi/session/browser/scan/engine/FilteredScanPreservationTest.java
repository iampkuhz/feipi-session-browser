package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 合成双来源 SQLite 回归：过滤重建只替换选中来源，不伪造全局版本升级。 */
class FilteredScanPreservationTest {
  @TempDir Path directory;

  @Test
  void filteredFullReplacesOnlySelectedSourceAndRetainsGlobalVersion() throws Exception {
    verifyFilteredRebuild(false);
  }

  @Test
  void filteredLogicUpgradeReplacesOnlySelectedSourceAndRetainsGlobalVersion() throws Exception {
    verifyFilteredRebuild(true);
  }

  private void verifyFilteredRebuild(boolean incremental) throws Exception {
    try (Connection connection = SqliteTestHelper.createInMemoryConnection()) {
      connection.setAutoCommit(false);
      var writer = SqliteTestHelper.createIndexWriter(connection);
      Candidate oldCodex = candidate(SourceId.CODEX, "current", "old");
      Candidate deletedCodex = candidate(SourceId.CODEX, "deleted", "old");
      Candidate qoder = candidate(SourceId.QODER, "preserved", "qoder-original");
      var initial = config(List.of(oldCodex, deletedCodex), List.of(qoder), Set.of(), false);
      assertThat(new FullScanEngine().scan(writer, initial).isFullySuccessful()).isTrue();
      writer.saveScanLogicVersion(10, java.time.Instant.EPOCH);
      connection.commit();
      var qoderFingerprint = writer.loadStoredSessionFingerprints().get(qoder.sessionKey());
      var qoderRows = sourceRows(connection, "qoder");
      Candidate changed = candidate(SourceId.CODEX, "current", "new");
      var filtered = config(List.of(changed), List.of(), Set.of("codex"), false);
      int errors =
          incremental
              ? new IncrementalScanEngine().scan(writer, filtered).errorCount()
              : new FullScanEngine().scan(writer, filtered).errorCount();
      assertThat(errors).isZero();
      assertThat(sourceRows(connection, "qoder")).isEqualTo(qoderRows);
      assertThat(writer.loadStoredSessionFingerprints().get(qoder.sessionKey()))
          .isEqualTo(qoderFingerprint);
      assertThat(writer.loadStoredSessionFingerprints())
          .containsKeys(changed.sessionKey(), qoder.sessionKey())
          .doesNotContainKey(deletedCodex.sessionKey());
      assertRemovedArtifactsAndMetadata(connection, deletedCodex.sessionKey());
      assertThat(writer.loadStoredSessionFingerprints().get(changed.sessionKey()).title())
          .isEqualTo("new");
      assertThat(writer.loadScanLogicVersion()).isEqualTo(10);
      // 只有全来源扫描成功，才能确认所有来源均已使用当前逻辑。
      assertThat(
              new FullScanEngine()
                  .scan(writer, config(List.of(changed), List.of(qoder), Set.of(), false))
                  .isFullySuccessful())
          .isTrue();
      assertThat(writer.loadScanLogicVersion())
          .isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);
      String generation = generation(connection);
      var unchanged = new IncrementalScanEngine().scan(writer, filtered);
      assertThat(unchanged.errorCount()).isZero();
      assertThat(unchanged.unchangedCount()).isEqualTo(1);
      assertThat(unchanged.rebuildTriggered()).isFalse();
      assertThat(generation(connection)).isEqualTo(generation);
    }
  }

  @Test
  void failedFilteredFullPreservesBothSourcesAndPublishedGeneration() throws Exception {
    verifyFailure(false);
  }

  @Test
  void failedFilteredLogicUpgradePreservesBothSourcesAndPublishedGeneration() throws Exception {
    verifyFailure(true);
  }

  private void verifyFailure(boolean incremental) throws Exception {
    try (Connection connection = SqliteTestHelper.createInMemoryConnection()) {
      connection.setAutoCommit(false);
      var writer = SqliteTestHelper.createIndexWriter(connection);
      Candidate codex = candidate(SourceId.CODEX, "current", "old");
      Candidate qoder = candidate(SourceId.QODER, "preserved", "old-qoder");
      assertThat(
              new FullScanEngine()
                  .scan(writer, config(List.of(codex), List.of(qoder), Set.of(), false))
                  .isFullySuccessful())
          .isTrue();
      writer.saveScanLogicVersion(10, java.time.Instant.EPOCH);
      connection.commit();
      var beforeCodex = sourceRows(connection, "codex");
      var beforeQoder = sourceRows(connection, "qoder");
      var beforeFingerprints = writer.loadStoredSessionFingerprints();
      String generation = generation(connection);
      var failing =
          config(
              List.of(candidate(SourceId.CODEX, "current", "new")),
              List.of(),
              Set.of("codex"),
              true);
      int errors =
          incremental
              ? new IncrementalScanEngine().scan(writer, failing).errorCount()
              : new FullScanEngine().scan(writer, failing).errorCount();
      assertThat(errors).isPositive();
      assertThat(sourceRows(connection, "codex")).isEqualTo(beforeCodex);
      assertThat(sourceRows(connection, "qoder")).isEqualTo(beforeQoder);
      assertThat(writer.loadStoredSessionFingerprints()).isEqualTo(beforeFingerprints);
      assertThat(writer.loadScanLogicVersion()).isEqualTo(10);
      assertThat(generation(connection)).isEqualTo(generation);
    }
  }

  private Candidate candidate(SourceId agent, String id, String title) throws Exception {
    Path path = directory.resolve(agent.getValue() + "-" + id + ".jsonl");
    if (!Files.exists(path)) Files.writeString(path, "synthetic");
    return new Candidate(
        new SourceFingerprint(
            path.toString(), agent, Files.size(path), 1000, Optional.empty(), Optional.empty()),
        agent.getValue() + ":" + id,
        "synthetic-project",
        Map.of("title", title));
  }

  private ScanConfig config(
      List<Candidate> codex, List<Candidate> qoder, Set<String> filter, boolean fail) {
    return new ScanConfig(
        List.of(
            new ScanConfig.SourceEntry(new Adapter(SourceId.CODEX, codex, fail), directory),
            new ScanConfig.SourceEntry(new Adapter(SourceId.QODER, qoder, false), directory)),
        directory.resolve("artifacts"),
        filter,
        1);
  }

  private static List<String> sourceRows(Connection connection, String agent) throws Exception {
    List<String> result = new ArrayList<>();
    try (var statement =
        connection.prepareStatement(
            "SELECT s.*, a.artifact_type, a.path, a.created_at, m.value FROM sessions s LEFT JOIN"
                + " session_artifacts a USING(session_key) LEFT JOIN index_metadata m ON m.key ="
                + " 'scan_candidate_metadata:' || s.session_key WHERE s.agent = ? ORDER BY"
                + " s.session_key, a.artifact_type")) {
      statement.setString(1, agent);
      try (var rows = statement.executeQuery()) {
        while (rows.next()) {
          StringBuilder row = new StringBuilder();
          for (int i = 1; i <= rows.getMetaData().getColumnCount(); i++)
            row.append(rows.getString(i)).append('|');
          result.add(row.toString());
          String artifact = rows.getString("path");
          if (artifact != null) result.add(Files.readString(Path.of(artifact)));
        }
      }
    }
    return result;
  }

  private static void assertRemovedArtifactsAndMetadata(Connection connection, String sessionKey)
      throws Exception {
    try (var statement =
        connection.prepareStatement(
            "SELECT (SELECT COUNT(*) FROM session_artifacts WHERE session_key = ?) + (SELECT"
                + " COUNT(*) FROM index_metadata WHERE key = 'scan_candidate_metadata:' || ?)")) {
      statement.setString(1, sessionKey);
      statement.setString(2, sessionKey);
      try (var rows = statement.executeQuery()) {
        assertThat(rows.next()).isTrue();
        assertThat(rows.getLong(1)).isZero();
      }
    }
  }

  private static String generation(Connection connection) throws Exception {
    try (var statement = connection.createStatement();
        var rows =
            statement.executeQuery(
                "SELECT value FROM index_metadata WHERE key = 'published_generation'")) {
      assertThat(rows.next()).isTrue();
      return rows.getString(1);
    }
  }

  private record Adapter(SourceId sourceId, List<Candidate> candidates, boolean fail)
      implements SourceAdapter {
    @Override
    public BoundedStream<Candidate> discover(Path root) {
      return BoundedStream.of(
          candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path path) {
      return candidates.getFirst().fingerprint();
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return fail
          ? new SourceResult.Fatal(List.of(), "synthetic failure")
          : new SourceResult.Success(List.of(), 1, List.of(), candidate.fingerprint(), null);
    }
  }
}
