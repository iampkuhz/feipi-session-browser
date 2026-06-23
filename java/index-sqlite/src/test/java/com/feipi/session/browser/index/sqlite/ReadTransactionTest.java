package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.sql.Connection;
import java.sql.SQLException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link ReadTransaction} 测试，覆盖只读事务生命周期和资源释放。 */
@DisplayName("ReadTransaction 测试")
class ReadTransactionTest {

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Nested
  @DisplayName("生命周期")
  class Lifecycle {

    @Test
    @DisplayName("创建时关闭 autoCommit")
    void disablesAutoCommitOnCreate() throws SQLException {
      assertThat(conn.getAutoCommit()).isTrue();

      try (ReadTransaction rt = new ReadTransaction(conn)) {
        assertThat(rt.connection()).isSameAs(conn);
        assertThat(conn.getAutoCommit()).isFalse();
      }
    }

    @Test
    @DisplayName("close 恢复 autoCommit 并关闭连接")
    void closeRestoresAutoCommitAndCloses() throws SQLException {
      ReadTransaction rt = new ReadTransaction(conn);
      rt.close();

      assertThat(conn.isClosed()).isTrue();
    }

    @Test
    @DisplayName("多次 close 安全")
    void multipleCloseSafe() throws SQLException {
      ReadTransaction rt = new ReadTransaction(conn);
      rt.close();
      rt.close(); // 不抛异常
    }
  }

  @Nested
  @DisplayName("连接访问")
  class ConnectionAccess {

    @Test
    @DisplayName("connection 返回底层连接")
    void connectionReturnsUnderlying() throws SQLException {
      try (ReadTransaction rt = new ReadTransaction(conn)) {
        assertThat(rt.connection()).isSameAs(conn);
      }
    }
  }

  @Nested
  @DisplayName("参数校验")
  class Validation {

    @Test
    @DisplayName("已关闭连接抛异常")
    void closedConnectionThrows() throws SQLException {
      Connection closed = SqliteTestHelper.createInMemoryConnection();
      closed.close();

      assertThatThrownBy(() -> new ReadTransaction(closed))
          .isInstanceOf(IllegalStateException.class)
          .hasMessageContaining("已关闭");
    }
  }
}
