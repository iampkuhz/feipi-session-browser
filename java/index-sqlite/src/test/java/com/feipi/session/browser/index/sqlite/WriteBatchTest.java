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

/** {@link WriteBatch} 测试，覆盖批量写入、事务原子性和上限控制。 */
@DisplayName("WriteBatch 测试")
class WriteBatchTest {

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
  @DisplayName("批量写入")
  class BatchWrite {

    @Test
    @DisplayName("flush 在单事务中执行所有语句")
    void flushExecutesAllInTransaction() throws SQLException {
      WriteBatch batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
      batch.addInsert("INSERT INTO test_data VALUES (1, 'a')");
      batch.addInsert("INSERT INTO test_data VALUES (2, 'b')");
      batch.addInsert("INSERT INTO test_data VALUES (3, 'c')");

      batch.flush();

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(3);
      }
    }

    @Test
    @DisplayName("空 flush 不开启事务")
    void emptyFlushIsNoOp() throws SQLException {
      WriteBatch batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
      // 空 flush 应该不抛异常
      batch.flush();

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isZero();
      }
    }

    @Test
    @DisplayName("flush 后 pendingCount 归零")
    void pendingCountAfterFlush() throws SQLException {
      WriteBatch batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
      batch.addInsert("INSERT INTO test_data VALUES (1, 'a')");
      assertThat(batch.pendingCount()).isEqualTo(1);

      batch.flush();
      assertThat(batch.pendingCount()).isZero();
    }

    @Test
    @DisplayName("flush 失败时回滚（原子性）")
    void flushRollsBackOnFailure() throws SQLException {
      WriteBatch batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
      batch.addInsert("INSERT INTO test_data VALUES (1, 'a')");
      // 重复主键会导致失败
      batch.addInsert("INSERT INTO test_data VALUES (1, 'b')");

      try {
        batch.flush();
      } catch (SQLException e) {
        // 期望异常
      }

      // 回滚后应无数据
      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isZero();
      }
    }
  }

  @Nested
  @DisplayName("上限控制")
  class Limit {

    @Test
    @DisplayName("超过上限抛异常")
    void exceedLimit() {
      WriteBatch batch = new WriteBatch(conn, 2);
      batch.addInsert("INSERT INTO test_data VALUES (1, 'a')");
      batch.addInsert("INSERT INTO test_data VALUES (2, 'b')");

      assertThatThrownBy(() -> batch.addInsert("INSERT INTO test_data VALUES (3, 'c')"))
          .isInstanceOf(IllegalStateException.class)
          .hasMessageContaining("已满");
    }

    @Test
    @DisplayName("addUpdate 受上限约束")
    void updateCountsTowardLimit() {
      WriteBatch batch = new WriteBatch(conn, 1);
      assertThatThrownBy(
              () -> {
                batch.addInsert("INSERT INTO test_data VALUES (1, 'a')");
                batch.addUpdate("UPDATE test_data SET value='b' WHERE id=1");
              })
          .isInstanceOf(IllegalStateException.class);
    }

    @Test
    @DisplayName("addDelete 受上限约束")
    void deleteCountsTowardLimit() {
      WriteBatch batch = new WriteBatch(conn, 1);
      assertThatThrownBy(
              () -> {
                batch.addInsert("INSERT INTO test_data VALUES (1, 'a')");
                batch.addDelete("DELETE FROM test_data WHERE id=1");
              })
          .isInstanceOf(IllegalStateException.class);
    }
  }

  @Nested
  @DisplayName("execute 方法")
  class Execute {

    @Test
    @DisplayName("execute 在事务中执行 lambda")
    void executeLambdaInTransaction() throws SQLException {
      WriteBatch batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
      batch.execute(
          c -> {
            try (Statement stmt = c.createStatement()) {
              stmt.execute("INSERT INTO test_data VALUES (1, 'lambda')");
            }
          });

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT value FROM test_data WHERE id = 1")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getString(1)).isEqualTo("lambda");
      }
    }

    @Test
    @DisplayName("execute 失败时回滚")
    void executeRollsBackOnFailure() throws SQLException {
      WriteBatch batch = new WriteBatch(conn, WriteBatch.DEFAULT_MAX_ENTRIES);
      try {
        batch.execute(
            c -> {
              try (Statement stmt = c.createStatement()) {
                stmt.execute("INSERT INTO test_data VALUES (1, 'a')");
                stmt.execute("INSERT INTO test_data VALUES (1, 'b')"); // 重复主键
              }
            });
      } catch (SQLException e) {
        // 期望异常
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isZero();
      }
    }
  }
}
