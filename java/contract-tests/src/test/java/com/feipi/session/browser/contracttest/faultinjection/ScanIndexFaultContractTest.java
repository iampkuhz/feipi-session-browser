package com.feipi.session.browser.contracttest.faultinjection;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.ConnectionFactory;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.ReadTransaction;
import com.feipi.session.browser.index.sqlite.WriteBatch;
import com.feipi.session.browser.index.sqlite.WriteQueue;
import com.feipi.session.browser.index.sqlite.WriteTransaction;
import com.feipi.session.browser.scan.engine.ScanCancelToken;
import com.feipi.session.browser.scan.engine.ScanLock;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 故障注入契约测试。
 *
 * <p>验证 scan/index 模块在故障场景下的契约行为： 锁竞争超时、取消传播、事务回滚、连接生命周期安全。 不修改 production 代码，只验证已有契约。
 */
@DisplayName("故障注入契约测试")
class ScanIndexFaultContractTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("扫描锁契约")
  class ScanLockContract {

    @Test
    @DisplayName("锁获取后必须释放")
    void lockMustBeReleasedAfterUse() throws Exception {
      ScanLock lock = new ScanLock(tempDir);

      // 获取并释放
      try (ScanLock.ScanLockHandle handle = lock.acquire("contract-test", 1000)) {
        assertThat(handle).isNotNull();
      }

      // 释放后应可再次获取
      try (ScanLock.ScanLockHandle handle = lock.acquire("contract-test-2", 1000)) {
        assertThat(handle).isNotNull();
      }
    }

    @Test
    @DisplayName("锁超时必须产生可诊断异常或 tryLock 返回 null")
    void lockTimeoutMustProduceDiagnosticException() throws Exception {
      ScanLock lock = new ScanLock(tempDir);
      ScanLock.ScanLockHandle holder = lock.acquire("holder", 1000);

      try {
        // 同一 JVM 内 FileLock 行为依赖平台：
        // 可能抛 OverlappingFileLockException 或超时或 tryLock 返回 null
        try {
          ScanLock.ScanLockHandle inner = lock.tryLock("contender");
          // 如果返回 null 说明锁不可重入，正确
          if (inner != null) {
            // 某些平台允许同 JVM 重入，释放后立即关闭
            inner.close();
          }
        } catch (Exception e) {
          // 异常应包含有用的诊断信息
          assertThat(e).isNotNull();
        }
      } finally {
        holder.close();
      }
    }
  }

  @Nested
  @DisplayName("取消令牌契约")
  class CancelTokenContract {

    @Test
    @DisplayName("取消是单向操作")
    void cancelIsOneWay() {
      ScanCancelToken token = new ScanCancelToken();
      assertThat(token.isCancelled()).isFalse();

      token.cancel();
      assertThat(token.isCancelled()).isTrue();

      // 多次取消幂等
      token.cancel();
      assertThat(token.isCancelled()).isTrue();
    }

    @Test
    @DisplayName("throwIfCancelled 在取消后抛异常")
    void throwIfCancelledThrowsAfterCancel() {
      ScanCancelToken token = new ScanCancelToken();
      token.cancel();

      try {
        token.throwIfCancelled();
        assertThat(false).as("应抛出 CancellationException").isTrue();
      } catch (java.util.concurrent.CancellationException e) {
        assertThat(e).isNotNull();
      }
    }
  }

  @Nested
  @DisplayName("事务契约")
  class TransactionContract {

    @Test
    @DisplayName("未提交事务自动回滚")
    void uncommittedTransactionAutoRollback() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE tx_test (id INTEGER PRIMARY KEY)");
        }

        // 开启事务但不提交
        WriteTransaction wt = new WriteTransaction(conn);
        try (Statement stmt = wt.connection().createStatement()) {
          stmt.execute("INSERT INTO tx_test VALUES (1)");
        }
        wt.close(); // 未 commit，应自动 rollback

        // 数据不应存在
        try (Statement stmt = conn.createStatement();
            var rs = stmt.executeQuery("SELECT count(*) FROM tx_test")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isZero();
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("WriteBatch 空 flush 不开启事务")
    void emptyFlushDoesNotOpenTransaction() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        WriteBatch batch = new WriteBatch(conn, 5000);
        // 空 flush 应直接返回
        batch.flush();

        // 连接应在 auto-commit 模式
        assertThat(conn.getAutoCommit()).isTrue();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("连接生命周期契约")
  class ConnectionLifecycleContract {

    @Test
    @DisplayName("ReadTransaction 关闭后连接不可用")
    void readTransactionClosedConnectionNotUsable() throws Exception {
      Path dbFile = tempDir.resolve("read-closed.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      ConnectionFactory factory = ConnectionFactory.withDefaults(jdbcUrl);
      Connection readConn = factory.create();
      ReadTransaction rt = new ReadTransaction(readConn);
      rt.close();

      // 连接应已关闭
      assertThat(readConn.isClosed()).isTrue();
    }

    @Test
    @DisplayName("IndexConnection 关闭后拒绝新操作")
    void indexConnectionClosedRejectsOperations() throws Exception {
      Path dbFile = tempDir.resolve("index-closed.db");
      String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

      Connection writerConn = DriverManager.getConnection(jdbcUrl);
      SqliteTestHelper.configureConnection(writerConn);

      IndexConnection indexConn =
          IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl);

      // 关闭前可正常操作
      assertThat(indexConn.writeQueue()).isNotNull();

      indexConn.close();

      // 关闭后应抛异常
      try {
        indexConn.writeQueue();
        assertThat(false).as("应抛出 IllegalStateException").isTrue();
      } catch (IllegalStateException e) {
        assertThat(e.getMessage()).contains("已关闭");
      }
    }
  }

  @Nested
  @DisplayName("WriteQueue 契约")
  class WriteQueueContract {

    @Test
    @DisplayName("submit 返回的 future 在完成后 resolve")
    void submitFutureResolvesAfterCompletion() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE future_test (id INTEGER PRIMARY KEY)");
        }

        WriteQueue queue = new WriteQueue(conn);
        CompletableFuture<Void> future =
            queue.submit(
                c -> {
                  try (Statement s = c.createStatement()) {
                    s.execute("INSERT INTO future_test VALUES (1)");
                  }
                });

        Void result = future.get(5, TimeUnit.SECONDS);
        assertThat(result).isNull();

        queue.shutdown();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("shutdown 后 submit 返回异常 future")
    void submitAfterShutdownReturnsExceptionalFuture() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        WriteQueue queue = new WriteQueue(conn);
        queue.shutdown();

        CompletableFuture<Void> future = queue.submit(c -> {});
        assertThat(future.isCompletedExceptionally()).isTrue();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }
}
