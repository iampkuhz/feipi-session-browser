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
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link IndexConnection} 测试，覆盖连接生命周期、并发读写和单 writer 保证。 */
@DisplayName("IndexConnection 测试")
class IndexConnectionTest {

  @Nested
  @DisplayName("连接创建")
  class Creation {

    @Test
    @DisplayName("create 创建可用连接")
    void createConnection() throws SQLException {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      try (IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:")) {
        assertThat(ic.writerConnection()).isSameAs(writerConn);
        assertThat(ic.pragmaConfig()).isEqualTo(PragmaConfig.DEFAULTS);
        assertThat(ic.writeQueue()).isNotNull();
      }
    }

    @Test
    @DisplayName("withDefaults 使用默认 PRAGMA")
    void withDefaultsCreation() throws SQLException {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      try (IndexConnection ic = IndexConnection.withDefaults(writerConn, "jdbc:sqlite::memory:")) {
        assertThat(ic.pragmaConfig()).isEqualTo(PragmaConfig.DEFAULTS);
      }
    }

    @Test
    @DisplayName("null writer 连接抛异常")
    void nullWriterConnection() {
      assertThatThrownBy(
              () -> IndexConnection.create(null, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:"))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Nested
  @DisplayName("读事务")
  class ReadTransactions {

    @Test
    @DisplayName("readTransaction 返回可用的只读事务")
    void readTransactionIsUsable() throws Exception {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      try (IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:")) {
        // 注意：内存数据库每次 create 得到不同的 :memory: DB
        // 读事务在新连接上操作，与 writer 连接的数据不共享
        try (ReadTransaction rt = ic.readTransaction()) {
          assertThat(rt.connection()).isNotNull();
          assertThat(rt.connection().isClosed()).isFalse();
        }
      }
    }
  }

  @Nested
  @DisplayName("写队列")
  class WriteQueueAccess {

    @Test
    @DisplayName("通过 writeQueue 提交写操作")
    void submitToWriteQueue() throws Exception {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      try (Statement stmt = writerConn.createStatement()) {
        stmt.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)");
      }

      try (IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:")) {
        ic.writeQueue()
            .submit(
                c -> {
                  try (Statement stmt = c.createStatement()) {
                    stmt.execute("INSERT INTO test_data VALUES (1, 'hello')");
                  }
                })
            .get(5, TimeUnit.SECONDS);

        // 验证数据
        try (Statement stmt = writerConn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT value FROM test_data WHERE id = 1")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getString(1)).isEqualTo("hello");
        }
      }
    }
  }

  @Nested
  @DisplayName("并发读写")
  class ConcurrentReadWrite {

    @Test
    @DisplayName("并发 reader + 单 writer 通过")
    void concurrentReadersAndSingleWriter(@TempDir Path tempDir) throws Exception {
      Path dbFile = tempDir.resolve("test.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      PragmaConfig.DEFAULTS.apply(writerConn);
      try (Statement stmt = writerConn.createStatement()) {
        stmt.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)");
      }

      try (IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl)) {
        int readerCount = 3;
        int writerCount = 10;
        CountDownLatch readersReady = new CountDownLatch(readerCount);
        CountDownLatch allDone = new CountDownLatch(readerCount + 1);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        // 启动 reader 线程
        for (int r = 0; r < readerCount; r++) {
          new Thread(
                  () -> {
                    try {
                      readersReady.countDown();
                      for (int i = 0; i < 5; i++) {
                        try (ReadTransaction rt = ic.readTransaction()) {
                          try (Statement stmt = rt.connection().createStatement();
                              ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
                            rs.next();
                          }
                        }
                        Thread.sleep(10);
                      }
                    } catch (Exception e) {
                      errors.add(e);
                    } finally {
                      allDone.countDown();
                    }
                  })
              .start();
        }

        // 提交写操作
        new Thread(
                () -> {
                  try {
                    readersReady.await();
                    for (int i = 0; i < writerCount; i++) {
                      final int id = i;
                      ic.writeQueue()
                          .submit(
                              c -> {
                                try (Statement stmt = c.createStatement()) {
                                  stmt.execute(
                                      "INSERT INTO test_data VALUES (" + id + ", 'v" + id + "')");
                                }
                              })
                          .get(5, TimeUnit.SECONDS);
                    }
                  } catch (Exception e) {
                    errors.add(e);
                  } finally {
                    allDone.countDown();
                  }
                })
            .start();

        assertThat(allDone.await(30, TimeUnit.SECONDS)).isTrue();
        assertThat(errors).isEmpty();

        // 验证所有写入
        try (Statement stmt = writerConn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(writerCount);
        }
      }
    }
  }

  @Nested
  @DisplayName("单 writer 保证")
  class SingleWriterGuarantee {

    @Test
    @DisplayName("两个 writer 不会隐式并发")
    void twoWritersNotConcurrent(@TempDir Path tempDir) throws Exception {
      Path dbFile = tempDir.resolve("test.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      PragmaConfig.DEFAULTS.apply(writerConn);
      try (Statement stmt = writerConn.createStatement()) {
        stmt.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)");
      }

      try (IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl)) {
        List<String> executionOrder = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch secondCanProceed = new CountDownLatch(1);

        // 第一个写操作：标记开始，等待第二个操作提交后再完成
        CompletableFuture<Void> first =
            ic.writeQueue()
                .submit(
                    c -> {
                      executionOrder.add("first-start");
                      firstStarted.countDown();
                      try {
                        secondCanProceed.await(5, TimeUnit.SECONDS);
                      } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                      }
                      executionOrder.add("first-end");
                    });

        // 等待第一个操作开始
        firstStarted.await(5, TimeUnit.SECONDS);

        // 第二个写操作
        CompletableFuture<Void> second =
            ic.writeQueue()
                .submit(
                    c -> {
                      executionOrder.add("second");
                    });

        // 等待第二个操作排队
        Thread.sleep(200);

        // 释放第一个操作
        secondCanProceed.countDown();

        // 等待两个操作完成
        first.get(5, TimeUnit.SECONDS);
        second.get(5, TimeUnit.SECONDS);

        // 验证：第一个操作完成后第二个才开始（单 writer 串行）
        assertThat(executionOrder).containsExactly("first-start", "first-end", "second");
      }
    }
  }

  @Nested
  @DisplayName("关闭")
  class Close {

    @Test
    @DisplayName("close 后 writeQueue 抛异常")
    void closedQueueThrows() throws Exception {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:");
      ic.close();

      assertThatThrownBy(ic::writeQueue).isInstanceOf(IllegalStateException.class);
    }

    @Test
    @DisplayName("close 后 readTransaction 抛异常")
    void closedReadTransactionThrows() throws Exception {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:");
      ic.close();

      assertThatThrownBy(ic::readTransaction).isInstanceOf(IllegalStateException.class);
    }

    @Test
    @DisplayName("多次 close 安全")
    void multipleCloseSafe() throws Exception {
      Connection writerConn = SqliteTestHelper.createInMemoryConnection();
      IndexConnection ic =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, "jdbc:sqlite::memory:");
      ic.close();
      ic.close(); // 不抛异常
    }
  }
}
