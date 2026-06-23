package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

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
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
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
    ScanSummary summary = engine.scan(conn, config);

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
    ScanSummary summary = engine.scan(conn, config);

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
    ScanSummary summary = engine.scan(conn, config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.issues()).hasSize(1);
    assertThat(summary.issues().get(0).phase()).isEqualTo(ScanIssue.ScanPhase.ROOT_CHECK);
    verifyScanLogStatus("success");
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
    ScanSummary summary = engine.scan(conn, config);

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
    ScanSummary summary = engine.scan(conn, config);

    assertThat(summary.totalCandidates()).isEqualTo(1);
    assertThat(summary.errorCount()).isEqualTo(1);
    assertThat(summary.successCount()).isZero();
    assertThat(summary.issues()).hasSize(1);
    assertThat(summary.issues().get(0).phase()).isEqualTo(ScanIssue.ScanPhase.PARSE);
    verifyScanLogStatus("success");
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
    ScanSummary summary = engine.scan(conn, config);

    assertThat(summary.totalCandidates()).isEqualTo(1);
    assertThat(summary.skippedCount()).isEqualTo(1);
    assertThat(summary.successCount()).isZero();
    assertThat(summary.errorCount()).isZero();
  }

  @Test
  void scanLogCountsReflectPerSourceCounts() throws Exception {
    Path root = tempDir.resolve("counted");
    Files.createDirectories(root);

    Candidate c1 = makeCandidate("c1", "session-1");
    Candidate c2 = makeCandidate("c2", "session-2");

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(c1, c2)), root)),
            tempDir.resolve("artifacts"));

    FullScanEngine engine = new FullScanEngine();
    engine.scan(conn, config);

    // 验证 scan_log 的 per-source 计数
    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery("SELECT claude_count, codex_count, qoder_count FROM scan_log")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getInt("claude_count")).isEqualTo(2);
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
    ScanSummary summary = engine.scan(conn, config);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.isFullySuccessful()).isTrue();
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

  /** 创建测试候选项。 */
  private static Candidate makeCandidate(String locator, String sessionKey) {
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
        Map.of());
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
}
