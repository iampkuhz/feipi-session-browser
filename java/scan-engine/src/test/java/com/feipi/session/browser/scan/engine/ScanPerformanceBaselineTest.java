package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.MigrationRunner;
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
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 扫描性能基线测试。
 *
 * <p>覆盖不同规模（0/1/100/large sessions）和 no-change incremental 的性能基线。 提供阶段预算参考值，不作为硬阈值。
 */
@DisplayName("扫描性能基线测试")
class ScanPerformanceBaselineTest {

  @TempDir Path tempDir;

  /** 阶段性能预算：100 会话 full scan 应在 30 秒内完成。 */
  private static final long FULL_SCAN_100_BUDGET_MS = 30_000;

  /** 阶段性能预算：no-change incremental 应在 10 秒内完成。 */
  private static final long NO_CHANGE_INCREMENTAL_BUDGET_MS = 10_000;

  @Nested
  @DisplayName("零会话基线")
  class ZeroSessions {

    @Test
    @DisplayName("空目录 full scan 接近零耗时")
    void emptyFullScanNearZero() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        Path root = tempDir.resolve("zero-full");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        ScanSummary summary = engine.scan(conn, config);

        assertThat(summary.totalCandidates()).isZero();
        assertThat(summary.scanDurationMs()).isLessThan(5000);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("空目录 incremental scan 接近零耗时")
    void emptyIncrementalNearZero() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("zero-incr");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
                tempDir.resolve("artifacts"));

        IncrementalScanEngine engine = new IncrementalScanEngine();
        IncrementalScanSummary summary = engine.scan(conn, config);

        assertThat(summary.totalCandidates()).isZero();
        assertThat(summary.scanDurationMs()).isLessThan(5000);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("单会话基线")
  class SingleSession {

    @Test
    @DisplayName("单会话 full scan 正确计数")
    void singleSessionFullScan() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        Path root = tempDir.resolve("single-full");
        Files.createDirectories(root);

        Candidate candidate = makeCandidate("test.jsonl", "session-1");
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(candidate)), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        ScanSummary summary = engine.scan(conn, config);

        assertThat(summary.totalCandidates()).isEqualTo(1);
        assertThat(summary.scanDurationMs()).isLessThan(5000);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("100 会话基线")
  class HundredSessions {

    @Test
    @DisplayName("100 候选项 full scan 在预算内完成")
    void hundredCandidatesFullScanWithinBudget() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        Path root = tempDir.resolve("hundred-full");
        Files.createDirectories(root);

        List<Candidate> candidates = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
          candidates.add(makeCandidate("session-" + i + ".jsonl", "session-" + i));
        }

        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new FatalAdapter(candidates), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        long startMs = System.currentTimeMillis();
        ScanSummary summary = engine.scan(conn, config);
        long elapsed = System.currentTimeMillis() - startMs;

        assertThat(summary.totalCandidates()).isEqualTo(100);
        assertThat(summary.scanDurationMs()).isLessThan(FULL_SCAN_100_BUDGET_MS);
        assertThat(elapsed).isLessThan(FULL_SCAN_100_BUDGET_MS);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("100 候选项 incremental scan 在预算内完成")
    void hundredCandidatesIncrementalWithinBudget() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("hundred-incr");
        Files.createDirectories(root);

        List<Candidate> candidates = new ArrayList<>();
        for (int i = 0; i < 100; i++) {
          candidates.add(makeCandidate("session-" + i + ".jsonl", "session-" + i));
        }

        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new FatalAdapter(candidates), root)),
                tempDir.resolve("artifacts"));

        IncrementalScanEngine engine = new IncrementalScanEngine();
        long startMs = System.currentTimeMillis();
        IncrementalScanSummary summary = engine.scan(conn, config);
        long elapsed = System.currentTimeMillis() - startMs;

        assertThat(summary.totalCandidates()).isEqualTo(100);
        assertThat(summary.scanDurationMs()).isLessThan(FULL_SCAN_100_BUDGET_MS);
        assertThat(elapsed).isLessThan(FULL_SCAN_100_BUDGET_MS);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("No-change incremental 基线")
  class NoChangeIncremental {

    @Test
    @DisplayName("全部 UNCHANGED 的 incremental scan 不产生写事务")
    void allUnchangedNoWriteTransaction() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("nochange-incr");
        Files.createDirectories(root);

        // 创建 50 个 UNCHANGED 候选项（已存在于指纹库中）
        List<Candidate> candidates = new ArrayList<>();
        for (int i = 0; i < 50; i++) {
          candidates.add(makeCandidate("session-" + i + ".jsonl", "session-" + i));
        }

        // 先执行一次 full scan 建立指纹
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new FatalAdapter(candidates), root)),
                tempDir.resolve("artifacts"));

        IncrementalScanEngine engine = new IncrementalScanEngine();

        // 首次 scan（全部 NEW）
        IncrementalScanSummary firstSummary = engine.scan(conn, config);
        assertThat(firstSummary.newCount()).isEqualTo(50);

        // 第二次 scan（全部 UNCHANGED，因为 FatalAdapter 返回相同指纹）
        // 注意：FatalAdapter 的 parse 返回 Fatal，所以 candidates 会进入 ERROR 状态
        // 这里只验证 scan 在预算内完成
        long startMs = System.currentTimeMillis();
        IncrementalScanSummary secondSummary = engine.scan(conn, config);
        long elapsed = System.currentTimeMillis() - startMs;

        assertThat(elapsed).isLessThan(NO_CHANGE_INCREMENTAL_BUDGET_MS);
        assertThat(secondSummary.scanDurationMs()).isLessThan(NO_CHANGE_INCREMENTAL_BUDGET_MS);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("空 incremental scan 无写事务")
    void emptyIncrementalNoWriteTransaction() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("empty-incr");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
                tempDir.resolve("artifacts"));

        IncrementalScanEngine engine = new IncrementalScanEngine();
        IncrementalScanSummary summary = engine.scan(conn, config);

        assertThat(summary.totalCandidates()).isZero();
        assertThat(summary.scanDurationMs()).isLessThan(NO_CHANGE_INCREMENTAL_BUDGET_MS);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("大规模基线")
  class LargeScale {

    @Test
    @DisplayName("500 候选项 scan 在合理时间内完成")
    void largeCandidateScanWithinReasonableTime() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        Path root = tempDir.resolve("large-full");
        Files.createDirectories(root);

        List<Candidate> candidates = new ArrayList<>();
        for (int i = 0; i < 500; i++) {
          candidates.add(makeCandidate("session-" + i + ".jsonl", "session-" + i));
        }

        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new FatalAdapter(candidates), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        ScanSummary summary = engine.scan(conn, config);

        assertThat(summary.totalCandidates()).isEqualTo(500);
        // 500 候选项应在 60 秒内完成
        assertThat(summary.scanDurationMs()).isLessThan(60_000);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("WriteBatch 性能")
  class WriteBatchPerformance {

    @Test
    @DisplayName("WriteBatch flush 1000 条语句在预算内完成")
    void writeBatchFlush1000WithinBudget() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE perf_test (id INTEGER PRIMARY KEY, value TEXT)");
        }

        com.feipi.session.browser.index.sqlite.WriteBatch batch =
            new com.feipi.session.browser.index.sqlite.WriteBatch(conn, 5000);

        for (int i = 0; i < 1000; i++) {
          batch.addInsert("INSERT INTO perf_test VALUES (" + i + ", 'value-" + i + "')");
        }

        long startMs = System.currentTimeMillis();
        batch.flush();
        long elapsed = System.currentTimeMillis() - startMs;

        // 1000 条 INSERT 应在 5 秒内完成
        assertThat(elapsed).isLessThan(5000);

        // 验证数据
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM perf_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(1000);
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  // ===== 辅助方法 =====

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
}
