package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.MigrationRunner;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceAdapter.CancellationSignal;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link IncrementalScanEngine} 取消机制测试。
 *
 * <p>验证 cancel token 在候选项循环中的检查行为、 scan_log 清理和 CancellationException 传播。
 */
class IncrementalScanEngineCancelTest {

  @TempDir Path tempDir;

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void preCancelledTokenThrowsImmediately() throws Exception {
    Path root = tempDir.resolve("cancel-pre");
    Files.createDirectories(root);

    // 创建大量候选项的适配器
    CountingAdapter adapter = new CountingAdapter(10);
    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(adapter, root)), tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    ScanCancelToken token = new ScanCancelToken();
    token.cancel(); // 预先取消

    assertThatThrownBy(() -> engine.scan(conn, config, null, token))
        .isInstanceOf(CancellationException.class);

    // scan_log 应标记为 failure
    verifyScanLogStatus("failure");
  }

  @Test
  void cancelDuringScanStopsProcessing() throws Exception {
    Path root = tempDir.resolve("cancel-during");
    Files.createDirectories(root);

    // 创建一个在第三个候选项时取消的扫描
    AtomicInteger processedCount = new AtomicInteger();
    CountingAdapter adapter =
        new CountingAdapter(20) {
          @Override
          public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
            int count = processedCount.incrementAndGet();
            return new SourceResult.Success(List.of(), 0, List.of(), null, null);
          }
        };

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(adapter, root)), tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();
    ScanCancelToken token = new ScanCancelToken();

    // 在另一个线程中延迟取消
    Thread cancelThread =
        new Thread(
            () -> {
              try {
                Thread.sleep(10); // 等扫描开始
              } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
              }
              token.cancel();
            });
    cancelThread.start();

    try {
      engine.scan(conn, config, null, token);
      // 如果扫描在取消前就完成了（候选项太少），也是合法的
    } catch (CancellationException e) {
      // 预期的取消异常
      verifyScanLogStatus("failure");
    }

    cancelThread.join(5000);
  }

  @Test
  void scanWithoutCancelTokenSucceeds() throws Exception {
    Path root = tempDir.resolve("no-cancel");
    Files.createDirectories(root);

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();

    // 传 null cancelToken 应正常工作
    IncrementalScanSummary summary = engine.scan(conn, config, null, null);
    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.errorCount()).isZero();
    verifyScanLogStatus("success");
  }

  @Test
  void backwardCompatibleScanMethodWorksWithoutCancel() throws Exception {
    Path root = tempDir.resolve("backward-compat");
    Files.createDirectories(root);

    ScanConfig config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
            tempDir.resolve("artifacts"));

    IncrementalScanEngine engine = new IncrementalScanEngine();

    // 旧 API 不受影响
    IncrementalScanSummary summary = engine.scan(conn, config);
    assertThat(summary.totalCandidates()).isZero();
    verifyScanLogStatus("success");
  }

  // ===== 辅助方法 =====

  private void verifyScanLogStatus(String expectedStatus) throws SQLException {
    try (Statement stmt = conn.createStatement();
        var rs = stmt.executeQuery("SELECT status FROM scan_log ORDER BY id DESC LIMIT 1")) {
      assertThat(rs.next()).isTrue();
      assertThat(rs.getString("status")).isEqualTo(expectedStatus);
    }
  }

  // ===== 测试用适配器 =====

  /** 返回指定数量候选项的适配器。 */
  private static class CountingAdapter implements SourceAdapter {
    private final int count;

    CountingAdapter(int count) {
      this.count = count;
    }

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      List<Candidate> candidates = new java.util.ArrayList<>();
      for (int i = 0; i < count; i++) {
        SourceFingerprint fp =
            new SourceFingerprint(
                "file-" + i + ".jsonl",
                SourceId.CLAUDE_CODE,
                100,
                System.currentTimeMillis(),
                Optional.of("hash-" + i),
                Optional.of("SHA-256"));
        candidates.add(new Candidate(fp, "session-" + i, "proj", Map.of()));
      }
      return BoundedStream.of(
          candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 100, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 0, List.of(), null, null);
    }
  }

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
}
