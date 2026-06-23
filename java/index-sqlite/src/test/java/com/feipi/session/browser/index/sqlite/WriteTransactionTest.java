package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link WriteTransaction} 测试，覆盖事务提交、回滚、自动回滚和多语句执行。 */
@DisplayName("WriteTransaction 测试")
class WriteTransactionTest {

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
  @DisplayName("事务提交")
  class Commit {

    @Test
    @DisplayName("commit 后数据可见")
    void dataVisibleAfterCommit() throws SQLException {
      try (WriteTransaction tx = new WriteTransaction(conn)) {
        tx.execute("INSERT INTO test_data (id, value) VALUES (1, 'hello')");
        tx.commit();
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT value FROM test_data WHERE id = 1")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getString(1)).isEqualTo("hello");
      }
    }

    @Test
    @DisplayName("多语句在同一事务中提交")
    void multipleStatementsCommitted() throws SQLException {
      try (WriteTransaction tx = new WriteTransaction(conn)) {
        tx.execute("INSERT INTO test_data (id, value) VALUES (1, 'a')");
        tx.execute("INSERT INTO test_data (id, value) VALUES (2, 'b')");
        tx.execute("INSERT INTO test_data (id, value) VALUES (3, 'c')");
        tx.commit();
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(3);
      }
    }
  }

  @Nested
  @DisplayName("事务回滚")
  class Rollback {

    @Test
    @DisplayName("rollback 后数据不可见")
    void dataNotVisibleAfterRollback() throws SQLException {
      try (WriteTransaction tx = new WriteTransaction(conn)) {
        tx.execute("INSERT INTO test_data (id, value) VALUES (1, 'hello')");
        tx.rollback();
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isZero();
      }
    }

    @Test
    @DisplayName("SQL 异常时 try-with-resources 自动回滚")
    void autoRollbackOnSqlError() throws SQLException {
      try (WriteTransaction tx = new WriteTransaction(conn)) {
        tx.execute("INSERT INTO test_data (id, value) VALUES (1, 'hello')");
        // 重复主键导致异常
        try {
          tx.execute("INSERT INTO test_data (id, value) VALUES (1, 'duplicate')");
        } catch (SQLException e) {
          // 期望异常，tx 未 commit
        }
        // close 时因未 commit 自动 rollback
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isZero();
      }
    }
  }

  @Nested
  @DisplayName("自动回滚（try-with-resources）")
  class AutoClose {

    @Test
    @DisplayName("未 commit 时 close 自动回滚")
    void autoRollbackOnClose() throws SQLException {
      try (WriteTransaction tx = new WriteTransaction(conn)) {
        tx.execute("INSERT INTO test_data (id, value) VALUES (1, 'hello')");
        // 没有调用 commit
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isZero();
      }
    }
  }

  @Nested
  @DisplayName("状态管理")
  class State {

    @Test
    @DisplayName("重复 commit 抛异常")
    void doubleCommitThrows() throws SQLException {
      WriteTransaction tx = new WriteTransaction(conn);
      tx.commit();
      assertThatThrownBy(tx::commit).isInstanceOf(IllegalStateException.class);
    }

    @Test
    @DisplayName("commit 后 rollback 抛异常")
    void rollbackAfterCommitThrows() throws SQLException {
      WriteTransaction tx = new WriteTransaction(conn);
      tx.commit();
      assertThatThrownBy(tx::rollback).isInstanceOf(IllegalStateException.class);
    }

    @Test
    @DisplayName("connection 返回底层连接")
    void connectionReturnsUnderlying() throws SQLException {
      try (WriteTransaction tx = new WriteTransaction(conn)) {
        assertThat(tx.connection()).isSameAs(conn);
      }
    }
  }
}
