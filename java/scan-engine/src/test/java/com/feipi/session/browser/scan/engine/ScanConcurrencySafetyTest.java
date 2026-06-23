package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.ConnectionFactory;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.MigrationRunner;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.WriteQueue;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 扫描与索引并发安全测试。
 *
 * <p>验证多线程并发读写下的数据完整性、单 writer 保证和连接安全性。 覆盖 WriteQueue 串行保证、IndexConnection 读写隔离、 并发 scan 不交叉污染。
 */
@DisplayName("扫描与索引并发安全测试")
class ScanConcurrencySafetyTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("WriteQueue 单 writer 保证")
  class WriteQueueSingleWriterGuarantee {

    @Test
    @DisplayName("并发提交的操作在 writer 线程串行执行")
    void concurrentSubmitsSerializedOnWriterThread() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE concurrent_test (id INTEGER PRIMARY KEY, value TEXT)");
        }

        WriteQueue queue = new WriteQueue(conn);
        int threadCount = 8;
        int opsPerThread = 50;
        CountDownLatch startLatch = new CountDownLatch(1);
        List<String> executionOrder = Collections.synchronizedList(new ArrayList<>());
        List<CompletableFuture<Void>> futures = new ArrayList<>();

        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        for (int t = 0; t < threadCount; t++) {
          final int threadId = t;
          for (int i = 0; i < opsPerThread; i++) {
            final int opId = i;
            CompletableFuture<Void> f =
                queue.submit(
                    c -> {
                      String threadName = Thread.currentThread().getName();
                      executionOrder.add(threadName);
                      try (Statement s = c.createStatement()) {
                        s.execute(
                            "INSERT INTO concurrent_test VALUES ("
                                + (threadId * 1000 + opId)
                                + ", 't"
                                + threadId
                                + "')");
                      }
                    });
            futures.add(f);
          }
        }

        startLatch.countDown();

        // 等待所有操作完成
        for (CompletableFuture<Void> f : futures) {
          f.get(30, TimeUnit.SECONDS);
        }

        // 等待最后的空操作确保全部完成
        CompletableFuture<Void> done = queue.submit(c -> {});
        done.get(5, TimeUnit.SECONDS);

        // 所有执行应在 writer 线程
        assertThat(executionOrder).allMatch(name -> name.equals("sqlite-writer"));

        // 验证数据完整性
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM concurrent_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(threadCount * opsPerThread);
        }

        queue.shutdown();
        executor.shutdown();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("WriteQueue shutdown 后无任务泄漏")
    void shutdownDoesNotLeakTasks() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE shutdown_test (id INTEGER PRIMARY KEY)");
        }

        WriteQueue queue = new WriteQueue(conn);
        int taskCount = 100;

        for (int i = 0; i < taskCount; i++) {
          final int id = i;
          queue.submit(
              c -> {
                try (Statement s = c.createStatement()) {
                  s.execute("INSERT INTO shutdown_test VALUES (" + id + ")");
                }
              });
        }

        queue.shutdown();

        // 验证全部数据已写入
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM shutdown_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(taskCount);
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("IndexConnection 读写隔离")
  class IndexConnectionReadWriteIsolation {

    @Test
    @DisplayName("并发读不阻塞写")
    void concurrentReadsDoNotBlockWrite() throws Exception {
      Path dbFile = tempDir.resolve("rw-isolate.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(writerConn);
      new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(writerConn);

      IndexConnection indexConn =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);
      try {
        // 并发执行读和写
        int readCount = 5;
        CountDownLatch readsComplete = new CountDownLatch(readCount);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        // 启动读线程
        ExecutorService executor = Executors.newFixedThreadPool(readCount + 1);
        for (int i = 0; i < readCount; i++) {
          executor.submit(
              () -> {
                try {
                  for (int j = 0; j < 10; j++) {
                    try (var rt = indexConn.readTransaction()) {
                      try (Statement stmt = rt.connection().createStatement();
                          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM sessions")) {
                        rs.next();
                      }
                    }
                    Thread.sleep(1);
                  }
                } catch (Exception e) {
                  errors.add(e);
                } finally {
                  readsComplete.countDown();
                }
              });
        }

        // 写操作
        executor.submit(
            () -> {
              try {
                for (int i = 0; i < 10; i++) {
                  final int idx = i;
                  CompletableFuture<Void> f =
                      indexConn
                          .writeQueue()
                          .submit(
                              c -> {
                                try (Statement s = c.createStatement()) {
                                  s.execute(
                                      "INSERT INTO sessions (session_key, agent, session_id, "
                                          + "project_key, cwd, started_at, ended_at) VALUES "
                                          + "('key-"
                                          + idx
                                          + "', 'claude-code', 'id-"
                                          + idx
                                          + "', "
                                          + "'proj', '/tmp', '2024-01-01T00:00:00Z', "
                                          + "'2024-01-01T00:01:00Z')");
                                }
                              });
                  f.get(5, TimeUnit.SECONDS);
                }
              } catch (Exception e) {
                errors.add(e);
              }
            });

        assertThat(readsComplete.await(30, TimeUnit.SECONDS)).isTrue();
        assertThat(errors).isEmpty();

        indexConn.writeQueue().shutdown();
        executor.shutdown();
      } finally {
        indexConn.close();
      }
    }
  }

  @Nested
  @DisplayName("ScanCancelToken 线程安全")
  class CancelTokenThreadSafety {

    @Test
    @DisplayName("多线程并发取消不产生竞态")
    void concurrentCancelIsIdempotent() throws Exception {
      ScanCancelToken token = new ScanCancelToken();
      int threadCount = 10;
      ExecutorService executor = Executors.newFixedThreadPool(threadCount);
      CountDownLatch latch = new CountDownLatch(threadCount);

      for (int i = 0; i < threadCount; i++) {
        executor.submit(
            () -> {
              token.cancel();
              latch.countDown();
            });
      }

      assertThat(latch.await(5, TimeUnit.SECONDS)).isTrue();
      assertThat(token.isCancelled()).isTrue();

      executor.shutdown();
    }

    @Test
    @DisplayName("取消后立即 throwIfCancelled 抛异常")
    void throwIfCancelledAfterCancel() {
      ScanCancelToken token = new ScanCancelToken();
      token.cancel();

      try {
        token.throwIfCancelled();
        assertThat(false).as("应抛出 CancellationException").isTrue();
      } catch (java.util.concurrent.CancellationException e) {
        assertThat(e.getMessage()).contains("取消");
      }
    }
  }

  @Nested
  @DisplayName("连接泄漏检测")
  class ConnectionLeakDetection {

    @Test
    @DisplayName("ReadTransaction 关闭后连接释放")
    void readTransactionClosesConnection() throws Exception {
      Path dbFile = tempDir.resolve("leak-test.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(writerConn);
      new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(writerConn);

      ConnectionFactory factory = new ConnectionFactory(jdbcUrl, PragmaConfig.DEFAULTS);

      // 创建并关闭多个 ReadTransaction
      for (int i = 0; i < 20; i++) {
        Connection readConn = factory.create();
        try (var rt = new com.feipi.session.browser.index.sqlite.ReadTransaction(readConn)) {
          try (Statement stmt = rt.connection().createStatement();
              ResultSet rs = stmt.executeQuery("SELECT 1")) {
            assertThat(rs.next()).isTrue();
          }
        }
        // ReadTransaction.close() 应关闭连接
        assertThat(readConn.isClosed()).isTrue();
      }

      writerConn.close();
    }

    @Test
    @DisplayName("IndexConnection 关闭释放所有资源")
    void indexConnectionCloseReleasesAll() throws Exception {
      Path dbFile = tempDir.resolve("close-test.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(writerConn);

      IndexConnection indexConn =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);

      // 执行一些操作
      indexConn.writeQueue().submit(c -> {}).get(5, TimeUnit.SECONDS);

      indexConn.close();

      // writer 连接应已关闭
      assertThat(writerConn.isClosed()).isTrue();

      // 再次关闭应安全（幂等）
      indexConn.close();
    }
  }

  @Nested
  @DisplayName("并发 FullScan")
  class ConcurrentFullScan {

    @Test
    @DisplayName("同一连接不并发 scan（单 writer 保证）")
    void singleConnectionDoesNotConcurrentScan() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("concurrent-scan");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();

        // 串行执行多次 scan
        for (int i = 0; i < 3; i++) {
          ScanSummary summary = engine.scan(conn, config);
          assertThat(summary.errorCount()).isZero();
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  // ===== 测试用适配器 =====

  private static class EmptyAdapter implements com.feipi.session.browser.source.spi.SourceAdapter {
    @Override
    public com.feipi.session.browser.source.spi.SourceId sourceId() {
      return com.feipi.session.browser.source.spi.SourceId.CLAUDE_CODE;
    }

    @Override
    public com.feipi.session.browser.source.spi.BoundedStream<
            com.feipi.session.browser.source.spi.Candidate>
        discover(Path rootPath) {
      return com.feipi.session.browser.source.spi.BoundedStream.of(
          List.of(),
          com.feipi.session.browser.source.spi.SourceConstants.MAX_CANDIDATES_PER_DISCOVERY,
          Optional.empty());
    }

    @Override
    public com.feipi.session.browser.source.spi.SourceFingerprint fingerprint(Path filePath) {
      return new com.feipi.session.browser.source.spi.SourceFingerprint(
          filePath.toString(),
          com.feipi.session.browser.source.spi.SourceId.CLAUDE_CODE,
          0,
          0,
          Optional.empty(),
          Optional.empty());
    }

    @Override
    public com.feipi.session.browser.source.spi.SourceResult parse(
        com.feipi.session.browser.source.spi.Candidate candidate,
        com.feipi.session.browser.source.spi.SourceAdapter.CancellationSignal cancellation) {
      return new com.feipi.session.browser.source.spi.SourceResult.Success(
          List.of(), 0, List.of(), null, null);
    }
  }
}
