package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * SQLite 并发故障测试。
 *
 * <p>覆盖 SQLite busy timeout、WAL 模式并发读写、连接故障恢复、 写事务崩溃后的数据完整性。验证只有一个 writer、无连接泄漏、WAL 可控。
 */
@DisplayName("SQLite 并发故障测试")
class SqliteConcurrencyFaultTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("WAL 模式并发读写")
  class WalConcurrentReadWrite {

    @Test
    @DisplayName("WAL 模式下并发读写不产生 SQLITE_BUSY")
    void walModeConcurrentReadWriteNoBusy() throws Exception {
      Path dbFile = tempDir.resolve("wal-concurrent.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(writerConn);
      new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(writerConn);

      int readThreadCount = 4;
      int iterationsPerThread = 50;
      CountDownLatch startLatch = new CountDownLatch(1);
      CountDownLatch doneLatch = new CountDownLatch(readThreadCount + 1);
      List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

      ExecutorService executor = Executors.newFixedThreadPool(readThreadCount + 1);

      // 读线程
      for (int t = 0; t < readThreadCount; t++) {
        executor.submit(
            () -> {
              try {
                startLatch.await();
                for (int i = 0; i < iterationsPerThread; i++) {
                  try (Connection readConn = DriverManager.getConnection(jdbcUrl)) {
                    SqliteTestHelper.configureConnection(readConn);
                    try (Statement stmt = readConn.createStatement();
                        ResultSet rs = stmt.executeQuery("SELECT count(*) FROM sessions")) {
                      rs.next();
                    }
                  }
                }
              } catch (Exception e) {
                errors.add(e);
              } finally {
                doneLatch.countDown();
              }
            });
      }

      // 写线程
      executor.submit(
          () -> {
            try {
              startLatch.await();
              for (int i = 0; i < iterationsPerThread; i++) {
                final int idx = i;
                try (WriteTransaction wt = new WriteTransaction(writerConn)) {
                  try (Statement stmt = wt.connection().createStatement()) {
                    stmt.execute(
                        "INSERT OR REPLACE INTO sessions "
                            + "(session_key, agent, session_id, project_key, cwd, "
                            + "started_at, ended_at) VALUES "
                            + "('key-"
                            + idx
                            + "', 'claude-code', 'id-"
                            + idx
                            + "', "
                            + "'proj', '/tmp', '2024-01-01T00:00:00Z', "
                            + "'2024-01-01T00:01:00Z')");
                  }
                  wt.commit();
                }
              }
            } catch (Exception e) {
              errors.add(e);
            } finally {
              doneLatch.countDown();
            }
          });

      startLatch.countDown();
      assertThat(doneLatch.await(60, TimeUnit.SECONDS)).isTrue();
      assertThat(errors).isEmpty();

      writerConn.close();
      executor.shutdown();
    }

    @Test
    @DisplayName("WAL 文件在正常关闭后可安全重新打开")
    void walFileReopenAfterCleanClose() throws Exception {
      Path dbFile = tempDir.resolve("wal-reopen.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      // 第一阶段：写入数据
      Connection conn1 = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(conn1);
      new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn1);

      try (WriteTransaction wt = new WriteTransaction(conn1)) {
        try (Statement stmt = wt.connection().createStatement()) {
          stmt.execute(
              "INSERT INTO sessions (session_key, agent, session_id, project_key, cwd, "
                  + "started_at, ended_at) VALUES "
                  + "('key-reopen', 'claude-code', 'id-reopen', 'proj', '/tmp', "
                  + "'2024-01-01T00:00:00Z', '2024-01-01T00:01:00Z')");
        }
        wt.commit();
      }
      conn1.close();

      // 验证 WAL 文件存在
      assertThat(Files.exists(dbFile)).isTrue();

      // 第二阶段：重新打开验证数据
      Connection conn2 = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(conn2);

      try (Statement stmt = conn2.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM sessions")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(1);
      }

      conn2.close();
    }
  }

  @Nested
  @DisplayName("写事务故障恢复")
  class WriteTransactionFaultRecovery {

    @Test
    @DisplayName("事务失败后自动回滚")
    void transactionAutoRollbackOnFailure() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE rollback_test (id INTEGER PRIMARY KEY, value TEXT)");
          stmt.execute("INSERT INTO rollback_test VALUES (1, 'original')");
        }

        // 开启事务并尝试插入无效 SQL
        try {
          WriteTransaction wt = new WriteTransaction(conn);
          try {
            try (Statement stmt = wt.connection().createStatement()) {
              stmt.execute("INSERT INTO rollback_test VALUES (2, 'new')");
              stmt.execute("INVALID SQL");
            }
            wt.commit();
          } catch (SQLException e) {
            // 预期失败
          } finally {
            wt.close();
          }
        } catch (Exception e) {
          // 事务关闭可能抛异常
        }

        // 原始数据应完整，新数据不应存在
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM rollback_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(1);
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("双重关闭 WriteTransaction 不抛异常")
    void doubleCloseWriteTransactionSafe() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        WriteTransaction wt = new WriteTransaction(conn);
        wt.close();
        // 第二次关闭应安全
        wt.close();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("提交后关闭不重复 commit")
    void closeAfterCommitDoesNotDoubleCommit() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE commit_test (id INTEGER PRIMARY KEY)");
        }

        WriteTransaction wt = new WriteTransaction(conn);
        try (Statement stmt = wt.connection().createStatement()) {
          stmt.execute("INSERT INTO commit_test VALUES (1)");
        }
        wt.commit();
        wt.close(); // 不应再次 commit

        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM commit_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(1);
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("连接工厂故障")
  class ConnectionFactoryFault {

    @Test
    @DisplayName("无效 JDBC URL 抛异常")
    void invalidJdbcUrlThrows() {
      assertThatThrownBy(() -> ConnectionFactory.withDefaults(""))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("PRAGMA 配置到不存在的路径可创建新数据库")
    void newDatabaseCreatedWithPragma() throws Exception {
      Path dbFile = tempDir.resolve("new-pragmas.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      ConnectionFactory factory = ConnectionFactory.withDefaults(jdbcUrl);
      Connection conn = factory.create();
      try {
        assertThat(Files.exists(dbFile)).isTrue();
        // 验证 PRAGMA 已应用
        PragmaConfig config = PragmaConfig.DEFAULTS;
        assertThat(config.verify(conn)).isTrue();
      } finally {
        conn.close();
      }
    }

    @Test
    @DisplayName("每个新连接独立配置 PRAGMA")
    void eachConnectionHasIndependentPragma() throws Exception {
      Path dbFile = tempDir.resolve("independent-pragma.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      ConnectionFactory factory = ConnectionFactory.withDefaults(jdbcUrl);

      Connection conn1 = factory.create();
      Connection conn2 = factory.create();
      try {
        assertThat(PragmaConfig.DEFAULTS.verify(conn1)).isTrue();
        assertThat(PragmaConfig.DEFAULTS.verify(conn2)).isTrue();
      } finally {
        conn1.close();
        conn2.close();
      }
    }
  }

  @Nested
  @DisplayName("WriteQueue 并发安全")
  class WriteQueueConcurrency {

    @Test
    @DisplayName("大批量并发写入不丢失数据")
    void bulkConcurrentWritesNoDataLoss() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE bulk_test (id INTEGER PRIMARY KEY, value TEXT)");
        }

        WriteQueue queue = new WriteQueue(conn);
        int threadCount = 10;
        int insertsPerThread = 100;
        CountDownLatch startLatch = new CountDownLatch(1);
        List<Throwable> errors = Collections.synchronizedList(new ArrayList<>());

        ExecutorService executor = Executors.newFixedThreadPool(threadCount);
        for (int t = 0; t < threadCount; t++) {
          final int threadId = t;
          executor.submit(
              () -> {
                try {
                  startLatch.await();
                  for (int i = 0; i < insertsPerThread; i++) {
                    final int id = threadId * 10000 + i;
                    queue
                        .submit(
                            c -> {
                              try (Statement s = c.createStatement()) {
                                s.execute("INSERT INTO bulk_test VALUES (" + id + ", 'v')");
                              }
                            })
                        .get(10, TimeUnit.SECONDS);
                  }
                } catch (Exception e) {
                  errors.add(e);
                }
              });
        }

        startLatch.countDown();
        executor.shutdown();
        assertThat(executor.awaitTermination(60, TimeUnit.SECONDS)).isTrue();

        // 等待所有写入完成
        CompletableFuture<Void> done = queue.submit(c -> {});
        done.get(10, TimeUnit.SECONDS);

        assertThat(errors).isEmpty();

        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM bulk_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(threadCount * insertsPerThread);
        }

        queue.shutdown();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }
}
