package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link WriteQueue} 测试，覆盖单 writer 串行、并发提交、取消和关闭。 */
@DisplayName("WriteQueue 测试")
class WriteQueueTest {

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
    try (Statement stmt = conn.createStatement()) {
      stmt.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)");
    }
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Nested
  @DisplayName("单 writer 串行")
  class SingleWriter {

    @Test
    @DisplayName("写入操作在 writer 线程中执行")
    void executesOnWriterThread() throws Exception {
      WriteQueue queue = new WriteQueue(conn);
      List<String> threadNames = Collections.synchronizedList(new ArrayList<>());

      CompletableFuture<Void> f =
          queue.submit(
              c -> {
                threadNames.add(Thread.currentThread().getName());
              });

      f.get(5, TimeUnit.SECONDS);
      assertThat(threadNames).containsExactly("sqlite-writer");

      queue.shutdown();
    }

    @Test
    @DisplayName("多个写入操作按序执行")
    void operationsExecuteInOrder() throws Exception {
      WriteQueue queue = new WriteQueue(conn);

      for (int i = 0; i < 10; i++) {
        final int val = i;
        queue.submit(
            c -> {
              try (Statement stmt = c.createStatement()) {
                stmt.execute("INSERT INTO test_data VALUES (" + val + ", 'v" + val + "')");
              }
            });
      }

      // 等待所有操作完成
      CompletableFuture<Void> last = queue.submit(c -> {});
      last.get(5, TimeUnit.SECONDS);

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(10);
      }

      queue.shutdown();
    }
  }

  @Nested
  @DisplayName("并发提交")
  class ConcurrentSubmit {

    @Test
    @DisplayName("多线程提交不丢失数据")
    void concurrentSubmitsNoDataLoss() throws Exception {
      WriteQueue queue = new WriteQueue(conn);
      int threadCount = 5;
      int insertsPerThread = 20;
      CountDownLatch startLatch = new CountDownLatch(1);
      CountDownLatch doneLatch = new CountDownLatch(threadCount);
      List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

      for (int t = 0; t < threadCount; t++) {
        final int threadId = t;
        new Thread(
                () -> {
                  try {
                    startLatch.await();
                    for (int i = 0; i < insertsPerThread; i++) {
                      final int id = threadId * 1000 + i;
                      queue
                          .submit(
                              c -> {
                                try (Statement stmt = c.createStatement()) {
                                  stmt.execute(
                                      "INSERT INTO test_data VALUES ("
                                          + id
                                          + ", 't"
                                          + threadId
                                          + "')");
                                }
                              })
                          .get(5, TimeUnit.SECONDS);
                    }
                  } catch (Exception e) {
                    errors.add(e);
                  } finally {
                    doneLatch.countDown();
                  }
                })
            .start();
      }

      startLatch.countDown();
      assertThat(doneLatch.await(30, TimeUnit.SECONDS)).isTrue();

      // 等待最后一个操作完成
      CompletableFuture<Void> last = queue.submit(c -> {});
      last.get(5, TimeUnit.SECONDS);

      assertThat(errors).isEmpty();

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(threadCount * insertsPerThread);
      }

      queue.shutdown();
    }
  }

  @Nested
  @DisplayName("关闭语义")
  class Shutdown {

    @Test
    @DisplayName("shutdown 后拒绝新任务")
    void shutdownRejectsNewTasks() throws Exception {
      WriteQueue queue = new WriteQueue(conn);
      queue.shutdown();

      CompletableFuture<Void> future = queue.submit(c -> {});
      // 等待结果（应该异常完成）
      try {
        future.get(5, TimeUnit.SECONDS);
      } catch (Exception e) {
        // 期望异常
      }
      assertThat(future.isCompletedExceptionally()).isTrue();
    }

    @Test
    @DisplayName("shutdown 等待已排队任务完成")
    void shutdownWaitsForPending() throws Exception {
      WriteQueue queue = new WriteQueue(conn);

      // 提交多个任务
      for (int i = 0; i < 5; i++) {
        final int val = i;
        queue.submit(
            c -> {
              try (Statement stmt = c.createStatement()) {
                stmt.execute("INSERT INTO test_data VALUES (" + val + ", 'v')");
              }
            });
      }

      queue.shutdown();

      // 所有数据应已写入
      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(5);
      }
    }
  }

  @Nested
  @DisplayName("取消")
  class Cancel {

    @Test
    @DisplayName("cancelPending 清空队列")
    void cancelPendingClearsQueue() throws Exception {
      WriteQueue queue = new WriteQueue(conn, 4, WriteQueue.DEFAULT_BATCH_LIMIT);
      // 提交但不让 writer 有机会执行（阻塞 writer）
      CountDownLatch blockLatch = new CountDownLatch(1);

      queue.submit(
          c -> {
            try {
              blockLatch.await(10, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
              Thread.currentThread().interrupt();
            }
          });

      // 让 writer 开始执行阻塞任务
      Thread.sleep(200);

      // 提交更多任务
      for (int i = 0; i < 3; i++) {
        queue.submit(c -> {});
      }

      // 取消
      queue.cancelPending();

      // 释放阻塞
      blockLatch.countDown();

      assertThat(queue.pendingCount()).isZero();
    }
  }

  @Nested
  @DisplayName("错误处理")
  class ErrorHandling {

    @Test
    @DisplayName("SQL 异常传播到 future")
    void sqlExceptionPropagatedToFuture() throws Exception {
      WriteQueue queue = new WriteQueue(conn);

      CompletableFuture<Void> future =
          queue.submit(
              c -> {
                try (Statement stmt = c.createStatement()) {
                  stmt.execute("INVALID SQL");
                }
              });

      try {
        future.get(5, TimeUnit.SECONDS);
      } catch (Exception e) {
        assertThat(future.isCompletedExceptionally()).isTrue();
      }

      queue.shutdown();
    }
  }

  @Nested
  @DisplayName("参数校验")
  class Validation {

    @Test
    @DisplayName("null 连接抛异常")
    void nullConnection() {
      assertThatThrownBy(() -> new WriteQueue(null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("零容量抛异常")
    void zeroCapacity() {
      assertThatThrownBy(() -> new WriteQueue(conn, 0, 100))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("零批量上限抛异常")
    void zeroBatchLimit() {
      assertThatThrownBy(() -> new WriteQueue(conn, 10, 0))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Nested
  @DisplayName("newBatch")
  class NewBatch {

    @Test
    @DisplayName("newBatch 返回 WriteBatch")
    void returnsWriteBatch() {
      WriteQueue queue = new WriteQueue(conn, 10, 500);
      WriteBatch batch = queue.newBatch();
      assertThat(batch).isNotNull();
      assertThat(queue.batchLimit()).isEqualTo(500);
      queue.cancelPending();
    }
  }

  @Nested
  @DisplayName("文件数据库")
  class FileDatabase {

    @Test
    @DisplayName("文件数据库写入持久化")
    void fileDatabasePersistence(@TempDir Path tempDir) throws Exception {
      Path dbFile = tempDir.resolve("test.db");
      Connection fileConn = DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath());
      try {
        PragmaConfig.DEFAULTS.apply(fileConn);
        try (Statement stmt = fileConn.createStatement()) {
          stmt.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)");
        }

        WriteQueue queue = new WriteQueue(fileConn);
        queue
            .submit(
                c -> {
                  try (Statement stmt = c.createStatement()) {
                    stmt.execute("INSERT INTO test_data VALUES (1, 'persisted')");
                  }
                })
            .get(5, TimeUnit.SECONDS);

        queue.shutdown();
      } finally {
        fileConn.close();
      }

      // 重新打开验证数据持久化
      try (Connection reopen =
              DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath());
          Statement stmt = reopen.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT value FROM test_data WHERE id = 1")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getString(1)).isEqualTo("persisted");
      }
    }
  }
}
