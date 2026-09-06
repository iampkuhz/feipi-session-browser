package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.api.write.IndexWriterPort;
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
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 扫描重建进度可观测性测试。
 *
 * <p>验证阶段计时回调、合成大索引重建、取消、第二轮 UNCHANGED 等行为。 不使用真实数据，全部基于合成索引和 fake 适配器。
 */
class ScanRebuildProgressTest {

  @TempDir Path tempDir;

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    conn.setAutoCommit(false);
    new com.feipi.session.browser.index.store.sqlite.schema.IndexSchema(
            com.feipi.session.browser.index.store.sqlite.schema.MigrationRunner.withAllMigrations())
        .ensureSchema(conn);
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  void phaseCallbacksAreFiredDuringRebuild() throws Exception {
    Path root = tempDir.resolve("phase-rebuild");
    Files.createDirectories(root);

    insertStoredSession("s1", "/p1.jsonl", 1000.0, "claude_code", "2025-01-01T00:00:00Z");
    insertStoredSession("s2", "/p2.jsonl", 2000.0, "claude_code", "2025-01-01T00:00:00Z");

    List<String> phaseEvents = new ArrayList<>();
    ScanProgress progress =
        new ScanProgress() {
          @Override
          public void onPhaseStart(String phaseName) {
            phaseEvents.add("start:" + phaseName);
          }

          @Override
          public void onPhaseEnd(String phaseName, long durationMs) {
            phaseEvents.add("end:" + phaseName + ":" + durationMs);
          }

          @Override
          public void onSourceStart(String sourceName, int candidateCount) {}

          @Override
          public void onCandidateProcessed(String sourceName, int processed, int total) {}

          @Override
          public void onSourceEnd(String sourceName, int successCount) {}
        };

    // scan logic version 不设置（默认 0），触发 rebuild
    IncrementalScanEngine engine = new IncrementalScanEngine();
    IncrementalScanSummary summary =
        engine.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, List.of()),
            null,
            null,
            progress);

    assertThat(summary.rebuildTriggered()).isTrue();
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("start:schema"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("end:schema:"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("start:load_fingerprints"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("end:load_fingerprints:"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("start:clear_index"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("end:clear_index:"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("start:discover:"));
    assertThat(phaseEvents).anyMatch(e -> e.startsWith("end:discover:"));
  }

  @Test
  void syntheticLargeIndexRebuildClearsAllRows() throws Exception {
    Path root = tempDir.resolve("large-rebuild");
    Files.createDirectories(root);

    int sessionCount = 500;
    for (int i = 0; i < sessionCount; i++) {
      insertStoredSession(
          "session-" + i,
          "/path/file-" + i + ".jsonl",
          1000.0 + i,
          "claude_code",
          "2025-01-01T00:00:00Z");
    }
    conn.commit();

    assertThat(countRows("sessions")).isEqualTo(sessionCount);

    List<String> phaseEvents = new ArrayList<>();
    ScanProgress progress = recordingProgress(phaseEvents);

    IncrementalScanEngine engine = new IncrementalScanEngine();
    IncrementalScanSummary summary =
        engine.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, List.of()),
            null,
            null,
            progress);

    assertThat(summary.rebuildTriggered()).isTrue();
    assertThat(countRows("sessions")).isEqualTo(0);
    assertThat(countRows("session_artifacts")).isEqualTo(0);

    long clearIndexDuration = extractPhaseDuration(phaseEvents, "clear_index");
    assertThat(clearIndexDuration).isGreaterThanOrEqualTo(0);
  }

  @Test
  void cancelTokenStopsScanDuringProcessing() throws Exception {
    Path root = tempDir.resolve("cancel-test");
    Files.createDirectories(root);

    List<Candidate> candidates = new ArrayList<>();
    for (int i = 0; i < 20; i++) {
      candidates.add(
          new Candidate(
              new SourceFingerprint(
                  "file-" + i + ".jsonl",
                  SourceId.CLAUDE_CODE,
                  100,
                  1000L + i,
                  Optional.of("hash-" + i),
                  Optional.of("SHA-256")),
              "session-" + i,
              "proj",
              Map.of()));
    }

    ScanCancelToken token = new ScanCancelToken();
    token.cancel();

    IncrementalScanEngine engine = new IncrementalScanEngine();
    assertThatThrownBy(
            () ->
                engine.scan(
                    SqliteTestHelper.createIndexWriter(conn),
                    testConfig(root, candidates),
                    null,
                    token))
        .isInstanceOf(CancellationException.class);
  }

  @Test
  void secondRunAfterRebuildReportsUnchanged() throws Exception {
    Path root = tempDir.resolve("second-run");
    Files.createDirectories(root);

    List<Candidate> candidates = new ArrayList<>();
    for (int i = 0; i < 5; i++) {
      candidates.add(
          new Candidate(
              new SourceFingerprint(
                  "file-" + i + ".jsonl",
                  SourceId.CLAUDE_CODE,
                  100,
                  1000L + i,
                  Optional.of("hash-" + i),
                  Optional.of("SHA-256")),
              "session-" + i,
              "proj",
              Map.of()));
    }

    for (int i = 0; i < 5; i++) {
      insertStoredSession(
          "session-" + i,
          "file-" + i + ".jsonl",
          (1000L + i) / 1000.0,
          "claude_code",
          "2025-01-01T00:00:00Z");
    }
    setScanLogicVersion(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);

    IncrementalScanEngine engine = new IncrementalScanEngine();
    IndexWriterPort writer = SqliteTestHelper.createIndexWriter(conn);
    IncrementalScanSummary secondRun =
        engine.scan(writer, testConfig(root, candidates), null, null, null);

    assertThat(secondRun.rebuildTriggered()).isFalse();
    assertThat(secondRun.unchangedCount()).isEqualTo(5);
    assertThat(secondRun.changedCount()).isZero();
    assertThat(secondRun.newCount()).isZero();
  }

  @Test
  void noPhaseCallbacksWhenProgressIsNull() throws Exception {
    Path root = tempDir.resolve("null-progress");
    Files.createDirectories(root);

    IncrementalScanEngine engine = new IncrementalScanEngine();
    IncrementalScanSummary summary =
        engine.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, List.of()),
            null,
            null,
            null);

    assertThat(summary.totalCandidates()).isZero();
    assertThat(summary.errorCount()).isZero();
  }

  @Test
  void loggingScanProgressImplementsAllCallbacks() {
    LoggingScanProgress progress = new LoggingScanProgress();

    progress.onPhaseStart("schema");
    progress.onPhaseEnd("schema", 42);
    progress.onSourceStart("claude_code", 100);
    progress.onCandidateProcessed("claude_code", 1, 100);
    progress.onCandidateProcessed("claude_code", 50, 100);
    progress.onCandidateProcessed("claude_code", 100, 100);
    progress.onSourceEnd("claude_code", 95);
    progress.close();

    // 不抛异常即通过 — LoggingScanProgress 只做日志输出
  }

  @Test
  void flushPhaseIsReportedWhenBatchExceedsInterval() throws Exception {
    Path root = tempDir.resolve("flush-test");
    Files.createDirectories(root);

    List<Candidate> candidates = new ArrayList<>();
    for (int i = 0; i < 150; i++) {
      candidates.add(
          new Candidate(
              new SourceFingerprint(
                  "file-" + i + ".jsonl",
                  SourceId.CLAUDE_CODE,
                  100,
                  1000L + i,
                  Optional.of("hash-" + i),
                  Optional.of("SHA-256")),
              "session-" + i,
              "proj",
              Map.of()));
    }

    List<String> phaseEvents = new ArrayList<>();
    ScanProgress progress = recordingProgress(phaseEvents);

    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(
        SqliteTestHelper.createIndexWriter(conn),
        testConfig(root, candidates),
        null,
        null,
        progress);

    long flushCount = phaseEvents.stream().filter(e -> e.equals("start:flush")).count();
    long flushFinalCount = phaseEvents.stream().filter(e -> e.equals("start:flush_final")).count();

    assertThat(flushCount + flushFinalCount).isGreaterThanOrEqualTo(1);
  }

  @Test
  void cancelDuringRunMarksScanLogAsFailure() throws Exception {
    Path root = tempDir.resolve("cancel-during-run");
    Files.createDirectories(root);

    List<Candidate> candidates = new ArrayList<>();
    for (int i = 0; i < 10; i++) {
      candidates.add(
          new Candidate(
              new SourceFingerprint(
                  "file-" + i + ".jsonl",
                  SourceId.CLAUDE_CODE,
                  100,
                  1000L + i,
                  Optional.of("hash-" + i),
                  Optional.of("SHA-256")),
              "session-" + i,
              "proj",
              Map.of()));
    }

    ScanCancelToken token = new ScanCancelToken();
    IncrementalScanEngine engine = new IncrementalScanEngine();

    var started = new java.util.concurrent.CountDownLatch(1);
    var release = new java.util.concurrent.CountDownLatch(1);
    var failure = new java.util.concurrent.atomic.AtomicReference<Throwable>();
    ScanProgress progress =
        new ScanProgress() {
          public void onSourceStart(String source, int count) {
            started.countDown();
            try {
              if (!release.await(5, java.util.concurrent.TimeUnit.SECONDS)) {
                throw new IllegalStateException("synthetic barrier timeout");
              }
            } catch (InterruptedException e) {
              Thread.currentThread().interrupt();
              throw new IllegalStateException(e);
            }
          }

          public void onCandidateProcessed(String source, int count, int total) {}

          public void onSourceEnd(String source, int count) {}
        };
    Thread scanThread =
        new Thread(
            () -> {
              try {
                engine.scan(
                    SqliteTestHelper.createIndexWriter(conn),
                    testConfig(root, candidates),
                    null,
                    token,
                    progress);
              } catch (Throwable e) {
                failure.set(e);
              }
            });
    scanThread.start();
    try {
      assertThat(started.await(5, java.util.concurrent.TimeUnit.SECONDS)).isTrue();
      token.cancel();
    } finally {
      release.countDown();
      scanThread.join(5000);
    }
    assertThat(scanThread.isAlive()).isFalse();
    assertThat(failure.get()).isInstanceOf(CancellationException.class);

    assertThat(loadScanLogStatus()).isEqualTo("failure");
  }

  @Test
  void recoveryAfterFailureSucceeds() throws Exception {
    Path root = tempDir.resolve("recovery-test");
    Files.createDirectories(root);

    List<Candidate> candidates = new ArrayList<>();
    for (int i = 0; i < 3; i++) {
      candidates.add(
          new Candidate(
              new SourceFingerprint(
                  "file-" + i + ".jsonl",
                  SourceId.CLAUDE_CODE,
                  100,
                  1000L + i,
                  Optional.of("hash-" + i),
                  Optional.of("SHA-256")),
              "session-" + i,
              "proj",
              Map.of()));
    }

    IncrementalScanEngine engine = new IncrementalScanEngine();

    IncrementalScanSummary firstRun =
        engine.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, candidates),
            null,
            null,
            null);

    assertThat(firstRun.errorCount()).isZero();
    assertThat(loadScanLogicVersion()).isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);

    IncrementalScanSummary secondRun =
        engine.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, candidates),
            null,
            null,
            null);

    assertThat(secondRun.errorCount()).isZero();
    assertThat(secondRun.unchangedCount()).isEqualTo(3);
  }

  @Test
  void largeIndexRebuildTimingIsMeasured() throws Exception {
    Path root = tempDir.resolve("large-timing");
    Files.createDirectories(root);

    int sessionCount = 1000;
    long insertStart = System.nanoTime();
    for (int i = 0; i < sessionCount; i++) {
      insertStoredSession(
          "session-" + i,
          "/path/file-" + i + ".jsonl",
          1000.0 + i,
          "claude_code",
          "2025-01-01T00:00:00Z");
    }
    conn.commit();
    long insertDurationMs = (System.nanoTime() - insertStart) / 1_000_000;

    List<String> phaseEvents = new ArrayList<>();
    ScanProgress progress = recordingProgress(phaseEvents);

    IncrementalScanEngine engine = new IncrementalScanEngine();
    long scanStart = System.nanoTime();
    IncrementalScanSummary summary =
        engine.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, List.of()),
            null,
            null,
            progress);
    long scanDurationMs = (System.nanoTime() - scanStart) / 1_000_000;

    assertThat(summary.rebuildTriggered()).isTrue();
    assertThat(countRows("sessions")).isEqualTo(0);

    long clearIndexDuration = extractPhaseDuration(phaseEvents, "clear_index");
    long loadFingerprintsDuration = extractPhaseDuration(phaseEvents, "load_fingerprints");

    assertThat(clearIndexDuration).isGreaterThanOrEqualTo(0);
    assertThat(loadFingerprintsDuration).isGreaterThanOrEqualTo(0);
    assertThat(scanDurationMs).isLessThan(insertDurationMs * 10);
  }

  @Test
  void lockCanBeAcquiredAndReleased() throws Exception {
    Path lockFile = tempDir.resolve("scan.lock");
    ScanLock lock = new ScanLock(lockFile);

    try (ScanLock.ScanLockHandle handle = lock.tryLock("test-holder")) {
      assertThat(handle).isNotNull();
    }

    try (ScanLock.ScanLockHandle handle = lock.tryLock("test-holder-2")) {
      assertThat(handle).isNotNull();
    }
  }

  @Test
  void errorDuringScanMarksScanLogAsFailureAndSkipsLogicVersion() throws Exception {
    Path root = tempDir.resolve("error-scan");
    Files.createDirectories(root);

    // 第一次正常扫描，建立基线
    IncrementalScanEngine engine = new IncrementalScanEngine();
    engine.scan(
        SqliteTestHelper.createIndexWriter(conn), testConfig(root, List.of()), null, null, null);
    assertThat(loadScanLogicVersion()).isEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);

    // 清除 logic version，准备测试 Error 路径
    clearScanLogicVersion();

    // 第二次扫描：adapter 在 discover 时抛 Error
    List<Candidate> candidates =
        List.of(
            new Candidate(
                new SourceFingerprint(
                    "file.jsonl",
                    SourceId.CLAUDE_CODE,
                    100,
                    1000L,
                    Optional.of("hash"),
                    Optional.of("SHA-256")),
                "session",
                "proj",
                Map.of()));

    IncrementalScanEngine engine2 = new IncrementalScanEngine();
    org.assertj.core.api.Assertions.assertThatThrownBy(
            () ->
                engine2.scan(
                    SqliteTestHelper.createIndexWriter(conn),
                    testConfigWithErrorAdapter(root, candidates),
                    null,
                    null,
                    null))
        .isInstanceOf(AssertionError.class);

    // scan_log 应标记为 failure
    assertThat(loadScanLogStatus()).isEqualTo("failure");
    // logic version 不应被更新（仍为 0）
    assertThat(loadScanLogicVersion()).isZero();
  }

  @Test
  void realLockContentionBlocksSecondThread() throws Exception {
    ScanLock lock = new ScanLock(tempDir);
    CountDownLatch thread1Acquired = new CountDownLatch(1);
    CountDownLatch thread1Release = new CountDownLatch(1);
    java.util.concurrent.atomic.AtomicBoolean thread2GotLock =
        new java.util.concurrent.atomic.AtomicBoolean(false);

    Thread thread1 =
        new Thread(
            () -> {
              try (ScanLock.ScanLockHandle handle = lock.acquire("thread1", 5000)) {
                assertThat(handle).isNotNull();
                thread1Acquired.countDown();
                thread1Release.await();
              } catch (Exception e) {
                // 忽略
              }
            });

    Thread thread2 =
        new Thread(
            () -> {
              try {
                thread1Acquired.await();
                ScanLock.ScanLockHandle handle = lock.tryLock("thread2");
                if (handle != null) {
                  thread2GotLock.set(true);
                  handle.close();
                }
              } catch (Exception e) {
                // 忽略
              }
            });

    thread1.start();
    thread1Acquired.await();
    thread2.start();
    thread2.join(1000);

    // thread2 在 thread1 持有锁时无法获取
    assertThat(thread2GotLock.get()).isFalse();

    thread1Release.countDown();
    thread1.join(1000);

    // thread1 释放后 thread2 可以获取（但 thread2 已结束，所以重新测试）
    try (ScanLock.ScanLockHandle handle = lock.tryLock("after-release")) {
      assertThat(handle).isNotNull();
    }
  }

  @Test
  void recoveryAfterRealFailureSucceeds() throws Exception {
    Path root = tempDir.resolve("real-recovery");
    Files.createDirectories(root);

    List<Candidate> candidates =
        List.of(
            new Candidate(
                new SourceFingerprint(
                    "file.jsonl",
                    SourceId.CLAUDE_CODE,
                    100,
                    1000L,
                    Optional.of("hash"),
                    Optional.of("SHA-256")),
                "session-1",
                "proj",
                Map.of()));

    // 第一次扫描：adapter 在 discover 时抛 Error，扫描真正失败
    IncrementalScanEngine engine1 = new IncrementalScanEngine();
    assertThatThrownBy(
            () ->
                engine1.scan(
                    SqliteTestHelper.createIndexWriter(conn),
                    testConfigWithErrorAdapter(root, candidates),
                    null,
                    null,
                    null))
        .isInstanceOf(AssertionError.class);

    // scan_log 应标记为 failure
    assertThat(loadScanLogStatus()).isEqualTo("failure");

    // 第二次扫描：正常 adapter，应成功
    IncrementalScanEngine engine2 = new IncrementalScanEngine();
    IncrementalScanSummary secondRun =
        engine2.scan(
            SqliteTestHelper.createIndexWriter(conn),
            testConfig(root, candidates),
            null,
            null,
            null);

    assertThat(secondRun.errorCount()).isZero();
    assertThat(secondRun.newCount()).isEqualTo(1);
    assertThat(loadScanLogStatus()).isEqualTo("success");
  }

  // ===== 辅助方法（新增） =====

  @Test
  void discoveryFailureDoesNotFinalizeUpgradeAsSuccess() throws Exception {
    Path root = Files.createDirectory(tempDir.resolve("failed-discovery"));
    setScanLogicVersion(4);
    SourceAdapter adapter =
        new TestAdapter(List.of()) {
          @Override
          public BoundedStream<Candidate> discover(Path sourceRoot) {
            throw new IllegalStateException("synthetic discovery failure");
          }
        };
    var config =
        ScanConfig.defaults(
            List.of(new ScanConfig.SourceEntry(adapter, root)), tempDir.resolve("artifacts"));
    var summary =
        new IncrementalScanEngine().scan(SqliteTestHelper.createIndexWriter(conn), config);
    assertThat(summary.issues()).isNotEmpty();
    assertThat(loadScanLogStatus()).isEqualTo("failure");
    assertThat(loadScanLogicVersion()).isEqualTo(4);
  }

  @Test
  void fatalVersionWriteDoesNotLeaveSuccessfulScanLog() throws Exception {
    Path root = Files.createDirectory(tempDir.resolve("fatal-version"));
    var delegate = SqliteTestHelper.createIndexWriter(conn);
    var writer =
        (com.feipi.session.browser.index.api.write.IndexWriterPort)
            java.lang.reflect.Proxy.newProxyInstance(
                getClass().getClassLoader(),
                new Class<?>[] {com.feipi.session.browser.index.api.write.IndexWriterPort.class},
                (proxy, method, args) -> {
                  if (method.getName().equals("saveScanLogicVersion")) {
                    throw new AssertionError("synthetic metadata write failure");
                  }
                  try {
                    return method.invoke(delegate, args);
                  } catch (java.lang.reflect.InvocationTargetException e) {
                    throw e.getCause();
                  }
                });
    assertThatThrownBy(() -> new IncrementalScanEngine().scan(writer, testConfig(root, List.of())))
        .isInstanceOf(AssertionError.class);
    assertThat(loadScanLogStatus()).isEqualTo("failure");
    assertThat(loadScanLogicVersion())
        .isNotEqualTo(IncrementalScanEngine.CURRENT_SCAN_LOGIC_VERSION);
  }

  private ScanConfig testConfigWithErrorAdapter(Path root, List<Candidate> candidates) {
    return ScanConfig.defaults(
        List.of(new ScanConfig.SourceEntry(new ErrorAdapter(candidates), root)),
        tempDir.resolve("artifacts"));
  }

  private void clearScanLogicVersion() throws SQLException {
    String sql = "DELETE FROM index_metadata WHERE key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, "scan_logic_version");
      stmt.executeUpdate();
    }
    conn.commit();
  }

  /** 在 discover 时抛 AssertionError 的适配器。 */
  private static class ErrorAdapter implements SourceAdapter {
    private final List<Candidate> candidates;

    ErrorAdapter(List<Candidate> candidates) {
      this.candidates = List.copyOf(candidates);
    }

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      throw new AssertionError("synthetic discover error");
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 1, List.of(), null, null);
    }
  }

  // ===== 辅助方法 =====

  private ScanConfig testConfig(Path root, List<Candidate> candidates) {
    return ScanConfig.defaults(
        List.of(new ScanConfig.SourceEntry(new TestAdapter(candidates), root)),
        tempDir.resolve("artifacts"));
  }

  private static ScanProgress recordingProgress(List<String> events) {
    return new ScanProgress() {
      @Override
      public void onPhaseStart(String phaseName) {
        events.add("start:" + phaseName);
      }

      @Override
      public void onPhaseEnd(String phaseName, long durationMs) {
        events.add("end:" + phaseName + ":" + durationMs);
      }

      @Override
      public void onSourceStart(String sourceName, int candidateCount) {}

      @Override
      public void onCandidateProcessed(String sourceName, int processed, int total) {}

      @Override
      public void onSourceEnd(String sourceName, int successCount) {}
    };
  }

  private static long extractPhaseDuration(List<String> events, String phaseName) {
    for (String event : events) {
      if (event.startsWith("end:" + phaseName + ":")) {
        return Long.parseLong(event.substring(("end:" + phaseName + ":").length()));
      }
    }
    return -1;
  }

  private void insertStoredSession(
      String sessionKey, String filePath, double fileMtime, String agent, String endedAt)
      throws SQLException {
    String sql =
        "INSERT INTO sessions (session_key, agent, session_id, title, project_key, "
            + "ended_at, file_mtime, file_path) VALUES (?, ?, ?, '', ?, ?, ?, ?)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, sessionKey);
      stmt.setString(2, agent);
      String sessionId =
          sessionKey.contains(":") ? sessionKey.substring(sessionKey.indexOf(':') + 1) : sessionKey;
      stmt.setString(3, sessionId);
      stmt.setString(4, "proj");
      stmt.setString(5, endedAt);
      stmt.setDouble(6, fileMtime);
      stmt.setString(7, filePath);
      stmt.executeUpdate();
    }
    conn.commit();
  }

  private int countRows(String table) throws SQLException {
    try (Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT COUNT(*) FROM " + table)) {
      assertThat(rs.next()).isTrue();
      return rs.getInt(1);
    }
  }

  private int loadScanLogicVersion() throws SQLException {
    String sql = "SELECT value FROM index_metadata WHERE key = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, "scan_logic_version");
      try (ResultSet rs = stmt.executeQuery()) {
        if (rs.next()) {
          return Integer.parseInt(rs.getString("value"));
        }
      }
    }
    return 0;
  }

  private void setScanLogicVersion(int version) throws SQLException {
    String sql = "INSERT OR REPLACE INTO index_metadata (key, value, updated_at) VALUES (?, ?, 0)";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setString(1, "scan_logic_version");
      stmt.setString(2, String.valueOf(version));
      stmt.executeUpdate();
    }
    conn.commit();
  }

  private String loadScanLogStatus() throws SQLException {
    String sql = "SELECT status FROM scan_log ORDER BY id DESC LIMIT 1";
    try (PreparedStatement stmt = conn.prepareStatement(sql);
        ResultSet rs = stmt.executeQuery()) {
      if (rs.next()) {
        return rs.getString("status");
      }
    }
    return null;
  }

  private static class TestAdapter implements SourceAdapter {
    private final List<Candidate> candidates;

    TestAdapter(List<Candidate> candidates) {
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
      return new SourceResult.Success(List.of(), 1, List.of(), null, null);
    }
  }
}
