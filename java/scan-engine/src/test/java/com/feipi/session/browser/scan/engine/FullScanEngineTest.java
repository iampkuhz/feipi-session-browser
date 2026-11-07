package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.source.spi.SourceRoot;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link FullScanEngine} 集成测试。
 *
 * <p>使用内存 SQLite 数据库和可配置的假适配器验证扫描管线。 由于当前归一化引擎不填充 session 元数据字段（session_key 等）， 成功管线测试使用 {@link
 * FatalAdapter} 验证错误处理路径。后续任务补齐 session 元数据后将增加完整成功路径测试。
 */
class FullScanEngineTest {

  @TempDir Path tempDir;

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    conn.setAutoCommit(false);
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void transcriptMetadataChangesReindexWithoutFileChangesAndThenRemainUnchanged() throws Exception {
    Path root = Files.createDirectories(tempDir.resolve("unchanged-transcript"));
    Path source = Files.writeString(root.resolve("session.jsonl"), "synthetic");
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            source.toString(),
            SourceId.CODEX,
            Files.size(source),
            1000,
            Optional.empty(),
            Optional.empty());
    Map<String, String> metadata = new java.util.LinkedHashMap<>();
    var writer = SqliteTestHelper.createIndexWriter(conn);
    var engine = new IncrementalScanEngine();
    for (String field :
        List.of(
            "initial", "title", "model", "git_branch", "source", "cwd", "started_at", "ended_at")) {
      if (!field.equals("initial"))
        metadata.put(field, field.endsWith("_at") ? "2026-01-01T00:00:00Z" : "new-" + field);
      Candidate candidate = new Candidate(fingerprint, "codex:unchanged", "project", metadata);
      ScanConfig config =
          ScanConfig.defaults(
              List.of(
                  new ScanConfig.SourceEntry(
                      new SuccessfulAdapter(SourceId.CODEX, candidate), root)),
              tempDir.resolve("unchanged-artifacts"));
      var changed = engine.scan(writer, config);
      assertThat(changed.errorCount()).isZero();
      assertThat(changed.successCount()).as(field).isEqualTo(1);
      var unchanged = engine.scan(writer, config);
      assertThat(unchanged.successCount()).as(field).isZero();
      assertThat(unchanged.unchangedCount()).isEqualTo(1);
    }
  }

  @Test
  void transcriptWithoutProjectOrEventTimesDoesNotInventMetadata() throws Exception {
    Path root = Files.createDirectories(tempDir.resolve("unknown-source"));
    Path source = Files.writeString(root.resolve("session.jsonl"), "synthetic");
    Candidate candidate =
        new Candidate(
            new SourceFingerprint(
                source.toString(),
                SourceId.CODEX,
                Files.size(source),
                123456789L,
                Optional.empty(),
                Optional.empty()),
            "codex:unknown",
            "",
            Map.of());
    var config =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new SuccessfulAdapter(SourceId.CODEX, candidate), root)),
            tempDir.resolve("unknown-artifacts"));
    assertThat(
            new FullScanEngine()
                .scan(SqliteTestHelper.createIndexWriter(conn), config)
                .errorCount())
        .isZero();
    try (var statement = conn.createStatement();
        var row = statement.executeQuery("SELECT * FROM sessions")) {
      assertThat(row.next()).isTrue();
      assertThat(row.getString("project_key")).isEmpty();
      assertThat(row.getString("started_at")).isEmpty();
      assertThat(row.getString("ended_at")).isEmpty();
    }
  }

  @Test
  void failedFullScanRetainsPublishedArtifactsAndAllowsRetry() throws Exception {
    verifyFailedPublication(false);
  }

  @Test
  void failedIncrementalRebuildRetainsPublishedArtifactsAndAllowsRetry() throws Exception {
    verifyFailedPublication(true);
  }

  private void verifyFailedPublication(boolean incremental) throws Exception {
    Path root = Files.createDirectories(tempDir.resolve("atomic-source"));
    Path source = Files.writeString(root.resolve("session.jsonl"), "synthetic");
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            source.toString(),
            SourceId.CODEX,
            Files.size(source),
            1000,
            Optional.empty(),
            Optional.empty());
    Candidate original =
        new Candidate(fingerprint, "codex:atomic", "project", Map.of("title", "old"));
    var writer = SqliteTestHelper.createIndexWriter(conn);
    ScanConfig initial =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new SuccessfulAdapter(SourceId.CODEX, original), root)),
            tempDir.resolve("atomic-artifacts"));
    assertThat(new FullScanEngine().scan(writer, initial).isFullySuccessful()).isTrue();
    assertThat(writer.loadScanLogicVersion())
        .isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);
    Path published;
    try (Statement statement = conn.createStatement();
        ResultSet result = statement.executeQuery("SELECT path FROM session_artifacts")) {
      assertThat(result.next()).isTrue();
      published = Path.of(result.getString(1));
    }
    byte[] previous = Files.readAllBytes(published);
    String previousMetadata =
        writer
            .loadStoredSessionFingerprints()
            .get(original.sessionKey())
            .candidateMetadataFingerprint();
    writer.saveScanLogicVersion(8, java.time.Instant.EPOCH);
    conn.commit();
    Candidate changed =
        new Candidate(fingerprint, original.sessionKey(), "project", Map.of("title", "new"));
    ScanConfig failing =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new SuccessfulAdapter(SourceId.CODEX, changed), root),
                new ScanConfig.SourceEntry(new FatalAdapter(List.of(original)), root)),
            initial.artifactOutputDir());
    for (int retry = 0; retry < 2; retry++) {
      int errors =
          incremental
              ? new IncrementalScanEngine().scan(writer, failing).errorCount()
              : new FullScanEngine().scan(writer, failing).errorCount();
      assertThat(errors).isPositive();
      assertThat(writer.loadScanLogicVersion()).isEqualTo(8);
      assertThat(Files.readAllBytes(published)).isEqualTo(previous);
      assertThat(
              writer
                  .loadStoredSessionFingerprints()
                  .get(original.sessionKey())
                  .candidateMetadataFingerprint())
          .isEqualTo(previousMetadata);
      try (Statement statement = conn.createStatement();
          ResultSet result =
              statement.executeQuery(
                  "SELECT title, path FROM sessions JOIN session_artifacts USING(session_key)")) {
        assertThat(result.next()).isTrue();
        assertThat(result.getString("title")).isEqualTo("old");
        assertThat(result.getString("path")).isEqualTo(published.toString());
      }
      verifyScanLogStatus("failure");
    }
    if (incremental) {
      var rebuilt = new IncrementalScanEngine().scan(writer, initial);
      assertThat(rebuilt.rebuildTriggered()).isTrue();
      assertThat(rebuilt.successCount()).isEqualTo(1);
      assertThat(writer.loadScanLogicVersion())
          .isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);
    } else {
      assertThat(new FullScanEngine().scan(writer, initial).isFullySuccessful()).isTrue();
    }
    var unchanged = new IncrementalScanEngine().scan(writer, initial);
    assertThat(unchanged.rebuildTriggered()).isFalse();
    assertThat(unchanged.errorCount()).isZero();
    verifyScanLogStatus("success");
  }

  @Test
  void emptyDirectoryProducesZeroSummary() throws Exception {
    Path emptyRoot = tempDir.resolve("empty");
    Files.createDirectories(emptyRoot);

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), emptyRoot)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.successCount()).isZero();
    assertThat(summary.errorCount()).isZero();
    assertThat(summary.scanLogId()).isGreaterThan(0);
    assertThat(summary.issues()).isEmpty();
    verifyScanLogStatus("success");
  }

  @Test
  void nonExistentRootIsSkipped() throws Exception {
    Path nonExistent = tempDir.resolve("does-not-exist");

    ScanConfig config =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), nonExistent)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.issues()).isEmpty();
    verifyScanLogStatus("success");
  }

  @Test
  void unsafeRootProducesIssue() throws Exception {
    Path root = tempDir.resolve("unsafe");
    Files.createDirectories(root);

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new UnsafeRootAdapter(SourceId.CLAUDE_CODE), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.issues()).hasSize(1);
    assertThat(summary.issues().get(0).phase()).isEqualTo(ScanIssue.ScanPhase.ROOT_CHECK);
    verifyScanLogStatus("failure");
  }

  @Test
  void agentFilterSkipsNonMatchingSources() throws Exception {
    Path root = tempDir.resolve("filtered");
    Files.createDirectories(root);

    ScanConfig config =
        new ScanConfig(
            List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
            tempDir.resolve("artifacts"),
            java.util.Set.of("codex"),
            1);

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.perSourceCount()).isEmpty();
    verifyScanLogStatus("success");
  }

  @Test
  void parseFailuresAreRecordedAsIssues() throws Exception {
    Path root = tempDir.resolve("fatal");
    Files.createDirectories(root);

    Candidate candidate =
        new Candidate(
            new SourceFingerprint(
                "test.jsonl",
                SourceId.CLAUDE_CODE,
                100,
                1000L,
                Optional.of("abc"),
                Optional.of("SHA-256")),
            "test-session-key",
            "test-project",
            Map.of());

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(candidate)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isEqualTo(1);
    assertThat(summary.errorCount()).isEqualTo(1);
    assertThat(summary.successCount()).isZero();
    assertThat(summary.issues()).hasSize(1);
    assertThat(summary.issues().get(0).phase()).isEqualTo(ScanIssue.ScanPhase.PARSE);
    verifyScanLogStatus("failure");
  }

  @Test
  void skippedCandidatesAreCounted() throws Exception {
    Path root = tempDir.resolve("skipped");
    Files.createDirectories(root);

    Candidate candidate =
        new Candidate(
            new SourceFingerprint(
                "test.jsonl",
                SourceId.CLAUDE_CODE,
                100,
                1000L,
                Optional.of("abc"),
                Optional.of("SHA-256")),
            "test-session-key",
            "test-project",
            Map.of());

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new SkippedAdapter(List.of(candidate)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isEqualTo(1);
    assertThat(summary.skippedCount()).isEqualTo(1);
    assertThat(summary.successCount()).isZero();
    assertThat(summary.errorCount()).isZero();
  }

  @Test
  void perSourceCountSumNeverExceedsSuccessCount() throws Exception {
    Path root = tempDir.resolve("per-source-invariant");
    Files.createDirectories(root);

    Candidate c1 = makeCandidate("c1", "session-1");
    Candidate c2 = makeCandidate("c2", "session-2");

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(c1, c2)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    // 核心不变量：perSourceCount 值的总和 ≤ successCount
    // perSourceCount 只记录成功处理数，不应超过 totalCandidates 或 successCount
    int perSourceSum = summary.perSourceCount().values().stream().mapToInt(Integer::intValue).sum();
    assertThat(perSourceSum).isEqualTo(summary.successCount());
    // 全失败时 perSourceCount 应为空
    assertThat(perSourceSum).isZero();
    assertThat(summary.perSourceCount()).isEmpty();
  }

  @Test
  void perSourceCountIsEmptyWhenAllCandidatesFail() throws Exception {
    Path root = tempDir.resolve("per-source-all-fail");
    Files.createDirectories(root);

    Candidate c1 = makeCandidate("c1", "session-1");
    Candidate c2 = makeCandidate("c2", "session-2");

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(c1, c2)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    // 所有候选都失败，perSourceCount 应为空
    assertThat(summary.totalCandidates()).isEqualTo(2);
    assertThat(summary.successCount()).isZero();
    assertThat(summary.errorCount()).isEqualTo(2);
    assertThat(summary.perSourceCount()).isEmpty();
  }

  @Test
  void perSourceCountIsEmptyWhenAllCandidatesSkipped() throws Exception {
    Path root = tempDir.resolve("per-source-all-skip");
    Files.createDirectories(root);

    Candidate c1 = makeCandidate("c1", "session-1");

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new SkippedAdapter(List.of(c1)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    // 所有候选被跳过，perSourceCount 应为空
    assertThat(summary.totalCandidates()).isEqualTo(1);
    assertThat(summary.successCount()).isZero();
    assertThat(summary.skippedCount()).isEqualTo(1);
    assertThat(summary.perSourceCount()).isEmpty();
  }

  @Test
  void scanLogCountsReflectPerSourceSuccessCounts() throws Exception {
    Path root = tempDir.resolve("counted");
    Files.createDirectories(root);

    Candidate c1 = makeCandidate("c1", "session-1");
    Candidate c2 = makeCandidate("c2", "session-2");

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(c1, c2)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    // 验证 scan_log 的 per-source 计数只记录成功数，fatal 候选不计入
    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery("SELECT claude_count, codex_count, qoder_count FROM scan_log")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getInt("claude_count")).isZero();
      assertThat(rs.getInt("codex_count")).isZero();
      assertThat(rs.getInt("qoder_count")).isZero();
    }
  }

  @Test
  void multipleSourceEntriesAreProcessed() throws Exception {
    Path root1 = tempDir.resolve("src1");
    Path root2 = tempDir.resolve("src2");
    Files.createDirectories(root1);
    Files.createDirectories(root2);

    ScanConfig config =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root1),
                new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CODEX), root2)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.isFullySuccessful()).isTrue();
  }

  @Test
  void successfulScanUsesCandidateSessionKeyAsSessionId() throws Exception {
    Path root = tempDir.resolve("canonical-session-id");
    Files.createDirectories(root);
    Path rollout =
        root.resolve("rollout-2026-03-27T22-55-12-019d2fca-cb74-70a0-b00b-426b38f34584.jsonl");
    Files.writeString(rollout, "{}\n");
    Candidate candidate =
        new Candidate(
            new SourceFingerprint(
                rollout.toString(),
                SourceId.CODEX,
                Files.size(rollout),
                Files.getLastModifiedTime(rollout).toMillis(),
                Optional.of("hash"),
                Optional.of("SHA-256")),
            "codex:019d2fca-cb74-70a0-b00b-426b38f34584",
            "/tmp/project",
            Map.of(
                "title",
                "真实标题",
                "cwd",
                "/tmp/project",
                "model",
                "gpt-test",
                "git_branch",
                "main_java",
                "source",
                "codex"));

    ScanConfig config =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new SuccessfulAdapter(SourceId.CODEX, candidate), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    ScanSummary summary = engine.scan(SqliteTestHelper.createIndexWriter(conn), config);

    assertThat(summary.successCount()).isEqualTo(1);
    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery(
                "SELECT session_key, session_id, title, project_key, project_name, cwd, model,"
                    + " git_branch, source FROM sessions WHERE session_key = "
                    + "'codex:019d2fca-cb74-70a0-b00b-426b38f34584'")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString("session_key"))
          .isEqualTo("codex:019d2fca-cb74-70a0-b00b-426b38f34584");
      assertThat(rs.getString("session_id")).isEqualTo("019d2fca-cb74-70a0-b00b-426b38f34584");
      assertThat(rs.getString("title")).isEqualTo("真实标题");
      assertThat(rs.getString("project_key")).isEqualTo("/tmp/project");
      assertThat(rs.getString("project_name")).isEqualTo("project");
      assertThat(rs.getString("cwd")).isEqualTo("/tmp/project");
      assertThat(rs.getString("model")).isEqualTo("gpt-test");
      assertThat(rs.getString("git_branch")).isEqualTo("main_java");
      assertThat(rs.getString("source")).isEqualTo("codex");
    }
  }

  @Test
  void candidateSubagentMetadataDoesNotDoubleCountWhenSubagentRecordsAreMaterialized()
      throws Exception {
    Candidate candidate =
        makeCandidate(
            "claude-session.jsonl",
            "claude:session",
            Map.of(
                "subagentInstanceCount",
                "1",
                "subagentToolCallCount",
                "2",
                "subagentFailedToolCount",
                "1",
                "subagentFreshInputTokens",
                "20",
                "subagentCacheReadTokens",
                "10",
                "subagentCacheWriteTokens",
                "5",
                "subagentOutputTokens",
                "15",
                "subagentTotalTokens",
                "50"));
    Map<String, Object> session =
        new HashMap<>(
            Map.of(
                "freshInputTokens",
                40L,
                "cacheReadTokens",
                20L,
                "cacheWriteTokens",
                10L,
                "outputTokens",
                30L,
                "totalTokens",
                100L,
                "toolCallCount",
                3L,
                "failedToolCount",
                1L));
    NormalizedSessionArtifact artifact =
        artifactWith(
            List.of(
                call("main-call", 1, CallScope.MAIN, new NormalizedCallUsage(20, 10, 5, 15, 50)),
                call(
                    "agent-sub-SR1",
                    2,
                    CallScope.SUBAGENT,
                    new NormalizedCallUsage(20, 10, 5, 15, 50))),
            List.of(
                new NormalizedToolExecution(
                    "tool-main",
                    "Read",
                    CallScope.MAIN,
                    "main-call",
                    Optional.empty(),
                    Optional.empty(),
                    Optional.empty(),
                    0L,
                    List.of(),
                    Optional.empty()),
                new NormalizedToolExecution(
                    "tool-sub",
                    "Bash",
                    CallScope.SUBAGENT,
                    "agent-sub-SR1",
                    Optional.empty(),
                    Optional.of("error"),
                    Optional.empty(),
                    0L,
                    List.of(),
                    Optional.of("agent-sub"))));

    invokeApplyCandidateMetadata(
        session, candidate, new EmptyAdapter(SourceId.CLAUDE_CODE), artifact);

    assertThat(session.get("totalTokens")).isEqualTo(100L);
    assertThat(session.get("freshInputTokens")).isEqualTo(40L);
    assertThat(session.get("toolCallCount")).isEqualTo(3L);
    assertThat(session.get("failedToolCount")).isEqualTo(1L);
    assertThat(session.get("subagentInstanceCount")).isEqualTo(1L);
  }

  @Test
  void candidateSubagentMetadataStillBackfillsWhenOnlySidecarTotalsAreAvailable() throws Exception {
    Candidate candidate =
        makeCandidate(
            "claude-session.jsonl",
            "claude:session",
            Map.of(
                "subagentInstanceCount",
                "1",
                "subagentToolCallCount",
                "2",
                "subagentFailedToolCount",
                "1",
                "subagentFreshInputTokens",
                "1",
                "subagentCacheReadTokens",
                "2",
                "subagentCacheWriteTokens",
                "3",
                "subagentOutputTokens",
                "4"));
    Map<String, Object> session =
        new HashMap<>(
            Map.of(
                "freshInputTokens",
                10L,
                "cacheReadTokens",
                20L,
                "cacheWriteTokens",
                30L,
                "outputTokens",
                40L,
                "totalTokens",
                100L,
                "toolCallCount",
                1L,
                "failedToolCount",
                0L));
    NormalizedSessionArtifact artifact =
        artifactWith(
            List.of(
                call("main-call", 1, CallScope.MAIN, new NormalizedCallUsage(10, 20, 30, 40, 100))),
            List.of());

    invokeApplyCandidateMetadata(
        session, candidate, new EmptyAdapter(SourceId.CLAUDE_CODE), artifact);

    assertThat(session.get("freshInputTokens")).isEqualTo(11L);
    assertThat(session.get("cacheReadTokens")).isEqualTo(22L);
    assertThat(session.get("cacheWriteTokens")).isEqualTo(33L);
    assertThat(session.get("outputTokens")).isEqualTo(44L);
    assertThat(session.get("totalTokens")).isEqualTo(110L);
    assertThat(session.get("toolCallCount")).isEqualTo(3L);
    assertThat(session.get("failedToolCount")).isEqualTo(1L);
    assertThat(session.get("subagentInstanceCount")).isEqualTo(1L);
  }

  @Test
  void candidatePrecisionSurvivesAlongsideEstimatedValuesAndMixedCoverage() throws Exception {
    Candidate candidate =
        makeCandidate(
            "estimated.jsonl",
            "qoder:estimated",
            Map.of(
                "freshInputTokens",
                "20",
                "outputTokens",
                "10",
                "freshInputTokenPrecision",
                "mixed",
                "cacheReadTokenPrecision",
                "unavailable",
                "cacheWriteTokenPrecision",
                "unavailable",
                "outputTokenPrecision",
                "estimated",
                "tokenEstimationMethod",
                "visible_context_v1",
                "tokenContainsEstimated",
                "true"));
    Map<String, Object> session = new HashMap<>();
    invokeApplyCandidateMetadata(
        session, candidate, new EmptyAdapter(SourceId.QODER), artifactWith(List.of(), List.of()));
    assertThat(session)
        .containsEntry("freshInputTokens", 20L)
        .containsEntry("freshInputTokenPrecision", "mixed")
        .containsEntry("cacheReadTokenPrecision", "unavailable")
        .containsEntry("outputTokenPrecision", "estimated")
        .containsEntry("tokenEstimationMethod", "visible_context_v1")
        .containsEntry("tokenContainsEstimated", true)
        .containsEntry("tokenContainsUnavailable", true);
  }

  @Test
  void missingPrecisionIsUnknownEvenWhenNumbersArePresent() throws Exception {
    Map<String, Object> session = new HashMap<>(Map.of("freshInputTokens", 42L));
    invokeApplyCandidateMetadata(
        session,
        makeCandidate("unknown.jsonl", "codex:unknown", Map.of()),
        new EmptyAdapter(SourceId.CODEX),
        artifactWith(List.of(), List.of()));
    assertThat(session)
        .containsEntry("freshInputTokens", 42L)
        .containsEntry("freshInputTokenPrecision", "unknown")
        .containsEntry("tokenContainsUnknown", true);
  }

  @Test
  void scanPersistsTheSamePrecisionInArtifactAndSqlite() throws Exception {
    Path root = Files.createDirectories(tempDir.resolve("estimated-source"));
    Path source = Files.writeString(root.resolve("estimated.jsonl"), "{}\n");
    Candidate candidate =
        new Candidate(
            new SourceFingerprint(
                source.toString(),
                SourceId.QODER,
                Files.size(source),
                Files.getLastModifiedTime(source).toMillis(),
                Optional.empty(),
                Optional.empty()),
            "qoder:synthetic-estimated",
            "/synthetic/project",
            Map.of(
                "freshInputTokens",
                "20",
                "outputTokens",
                "10",
                "freshInputTokenPrecision",
                "estimated",
                "cacheReadTokenPrecision",
                "unavailable",
                "cacheWriteTokenPrecision",
                "unavailable",
                "outputTokenPrecision",
                "estimated",
                "tokenEstimationMethod",
                "visible_context_v1"));
    ScanConfig config =
        ScanConfig.defaults(
            List.of(
                new ScanConfig.SourceEntry(new SuccessfulAdapter(SourceId.QODER, candidate), root)),
            tempDir.resolve("precision-artifacts"));
    ScanSummary summary =
        new FullScanEngine().scan(SqliteTestHelper.createIndexWriter(conn), config);
    assertThat(summary.successCount()).isEqualTo(1);
    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery(
                "SELECT s.fresh_input_tokens, s.cache_read_tokens, s.fresh_input_token_precision, "
                    + "s.cache_read_token_precision, s.token_contains_estimated, a.path "
                    + "FROM sessions s JOIN session_artifacts a USING(session_key)")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getLong("fresh_input_tokens")).isEqualTo(20);
      assertThat(rs.getLong("cache_read_tokens")).isZero();
      assertThat(rs.getString("fresh_input_token_precision")).isEqualTo("estimated");
      assertThat(rs.getString("cache_read_token_precision")).isEqualTo("unavailable");
      assertThat(rs.getLong("token_contains_estimated")).isEqualTo(1);
      var artifact =
          new com.fasterxml.jackson.databind.ObjectMapper()
              .readTree(Path.of(rs.getString("path")).toFile());
      assertThat(artifact.path("session").path("freshInputTokenPrecision").asText())
          .isEqualTo("estimated");
      assertThat(artifact.path("session").path("cacheReadTokenPrecision").asText())
          .isEqualTo("unavailable");
      assertThat(artifact.path("session").path("tokenContainsEstimated").asBoolean()).isTrue();
    }
  }

  @Test
  void scanPersistsExplicitTimingWithoutInventingModelExecution() throws Exception {
    Path root = Files.createDirectories(tempDir.resolve("timing-source"));
    Path source = Files.writeString(root.resolve("timing.jsonl"), "{}\n");
    Candidate candidate =
        new Candidate(
            new SourceFingerprint(
                source.toString(),
                SourceId.CODEX,
                Files.size(source),
                Files.getLastModifiedTime(source).toMillis(),
                Optional.empty(),
                Optional.empty()),
            "codex:synthetic-timing",
            "/synthetic/timing",
            Map.of());
    var timing =
        new com.feipi.session.browser.domain.source.SourceTiming(
            "task_complete",
            "turn",
            Optional.of("2026-01-01T00:00:00Z"),
            Optional.of("2026-01-01T00:00:01Z"),
            java.util.OptionalLong.of(1250),
            java.util.OptionalLong.empty(),
            java.util.OptionalLong.empty(),
            "end");
    var record =
        com.feipi.session.browser.domain.source.SourceRecord.of(
                source + "#event[0]", 0, "event_msg")
            .withTiming(timing);
    SourceAdapter adapter =
        new SuccessfulAdapter(SourceId.CODEX, candidate) {
          @Override
          public SourceResult parse(Candidate ignored, CancellationSignal cancellation) {
            return new SourceResult.Success(
                List.of(), 1, List.of(record), candidate.fingerprint(), null);
          }
        };
    ScanSummary summary =
        new FullScanEngine()
            .scan(
                SqliteTestHelper.createIndexWriter(conn),
                ScanConfig.defaults(
                    List.of(new ScanConfig.SourceEntry(adapter, root)),
                    tempDir.resolve("timing-artifacts")));
    assertThat(summary.successCount()).isEqualTo(1);
    try (var statement = conn.createStatement();
        var rs =
            statement.executeQuery(
                "SELECT s.model_execution_seconds, s.timing_json, a.path FROM sessions s JOIN"
                    + " session_artifacts a USING(session_key)")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getDouble("model_execution_seconds")).isZero();
      var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
      var stored = mapper.readTree(rs.getString("timing_json"));
      var artifact = mapper.readTree(Path.of(rs.getString("path")).toFile());
      assertThat(stored.path("activeTaskSeconds").asDouble()).isEqualTo(1.25);
      assertThat(stored.path("modelExecutionPrecision").asText()).isEqualTo("unknown");
      assertThat(stored.has("modelExecutionSeconds")).isFalse();
      assertThat(artifact.path("session").path("timing")).isEqualTo(stored);
    }
  }

  // ===== 辅助方法 =====

  /** 验证 scan_log 表中的 status 字段。 */
  private void verifyScanLogStatus(String expectedStatus) throws SQLException {
    try (Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT status FROM scan_log ORDER BY id DESC LIMIT 1")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString("status")).isEqualTo(expectedStatus);
    }
  }

  private static void invokeApplyCandidateMetadata(
      Map<String, Object> session,
      Candidate candidate,
      SourceAdapter adapter,
      NormalizedSessionArtifact artifact)
      throws Exception {
    CandidateContentMetadata.apply(
        session, candidate, adapter, NormalizedSessionContent.fromArtifact(artifact));
  }

  private static NormalizedSessionArtifact artifactWith(
      List<NormalizedCall> calls, List<NormalizedToolExecution> toolExecutions) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of(),
        calls,
        toolExecutions,
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(
      String callId, int callIndex, CallScope scope, NormalizedCallUsage usage) {
    return new NormalizedCall(
        callId,
        callIndex,
        "C" + callIndex,
        scope,
        scope == CallScope.SUBAGENT ? Optional.of("subagent:agent-sub") : Optional.empty(),
        scope == CallScope.SUBAGENT ? Optional.of("agent-sub") : Optional.empty(),
        Optional.empty(),
        "model",
        Optional.empty(),
        usage,
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  /** 创建测试候选项。 */
  private static Candidate makeCandidate(String locator, String sessionKey) {
    return makeCandidate(locator, sessionKey, Map.of());
  }

  private static Candidate makeCandidate(
      String locator, String sessionKey, Map<String, String> metadata) {
    return new Candidate(
        new SourceFingerprint(
            locator,
            SourceId.CLAUDE_CODE,
            100,
            1000L,
            Optional.of("hash-" + locator),
            Optional.of("SHA-256")),
        sessionKey,
        "test-project",
        metadata);
  }

  // ===== 测试用适配器 =====

  /** 返回空候选项列表的适配器。 */
  private static class EmptyAdapter implements SourceAdapter {
    private final SourceId sourceId;

    EmptyAdapter(SourceId sourceId) {
      this.sourceId = sourceId;
    }

    @Override
    public SourceId sourceId() {
      return sourceId;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          List.of(), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), sourceId, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 0, List.of(), null, null);
    }
  }

  /** 返回不安全根目录的适配器。 */
  private static class UnsafeRootAdapter implements SourceAdapter {
    private final SourceId sourceId;

    UnsafeRootAdapter(SourceId sourceId) {
      this.sourceId = sourceId;
    }

    @Override
    public SourceId sourceId() {
      return sourceId;
    }

    @Override
    public SourceRoot checkRoot(Path rootPath) {
      return new SourceRoot(rootPath, rootPath, false, true, false);
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          List.of(), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), sourceId, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      throw new UnsupportedOperationException();
    }
  }

  /** 返回致命错误的适配器。 */
  private static class FatalAdapter implements SourceAdapter {
    private final List<Candidate> candidates;

    FatalAdapter(List<Candidate> candidates) {
      this.candidates = List.copyOf(candidates);
    }

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Fatal(List.of(), "Test fatal error");
    }
  }

  /** 返回跳过结果的适配器。 */
  private static class SkippedAdapter implements SourceAdapter {
    private final List<Candidate> candidates;

    SkippedAdapter(List<Candidate> candidates) {
      this.candidates = List.copyOf(candidates);
    }

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Skipped(List.of(), "Test skip reason");
    }
  }

  /** 返回成功结果的适配器。 */
  private static class SuccessfulAdapter implements SourceAdapter {
    private final SourceId sourceId;
    private final Candidate candidate;

    SuccessfulAdapter(SourceId sourceId, Candidate candidate) {
      this.sourceId = sourceId;
      this.candidate = candidate;
    }

    @Override
    public SourceId sourceId() {
      return sourceId;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          List.of(candidate), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return candidate.fingerprint();
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 1, List.of(), candidate.fingerprint(), null);
    }
  }
}
