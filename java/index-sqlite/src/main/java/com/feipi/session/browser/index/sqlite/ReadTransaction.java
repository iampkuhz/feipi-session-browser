package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.SQLException;

/**
 * 短生命周期只读事务。
 *
 * <p>在 WAL 模式下，读事务以 REPEATABLE READ 隔离级别提供一致性快照。 本类关闭 auto-commit 开始读事务，{@link #close}
 * 时恢复原始状态并关闭连接。
 *
 * <p>设计为 try-with-resources 使用，确保读锁及时释放， 避免 WAL checkpoint starvation。
 */
public final class ReadTransaction implements AutoCloseable {

  private final Connection conn;
  private final boolean originalAutoCommit;
  private boolean closed;

  /**
   * 在指定连接上开启只读事务。
   *
   * <p>关闭 auto-commit 开始 REPEATABLE READ 事务。 连接必须已配置正确的 PRAGMA（由 {@link ConnectionFactory} 保证）。
   *
   * @param conn 已配置 PRAGMA 的只读连接
   * @throws SQLException 关闭 auto-commit 失败
   */
  public ReadTransaction(Connection conn) throws SQLException {
    if (conn.isClosed()) {
      throw new IllegalStateException("连接已关闭");
    }
    this.conn = conn;
    this.originalAutoCommit = conn.getAutoCommit();
    conn.setAutoCommit(false);
  }

  /**
   * 获取底层连接。
   *
   * @return 只读事务关联的连接
   */
  public Connection connection() {
    return conn;
  }

  /**
   * 关闭读事务，恢复 auto-commit 状态并关闭连接。
   *
   * <p>连接关闭失败时只记录警告，不抛出异常。
   */
  @Override
  public void close() {
    if (closed) {
      return;
    }
    closed = true;
    try {
      conn.setAutoCommit(originalAutoCommit);
    } catch (SQLException e) {
      // 恢复状态失败时只记录，不抛出
      org.slf4j.LoggerFactory.getLogger(ReadTransaction.class).warn("恢复 auto-commit 状态失败", e);
    }
    try {
      conn.close();
    } catch (SQLException e) {
      org.slf4j.LoggerFactory.getLogger(ReadTransaction.class).warn("关闭读连接失败", e);
    }
  }
}
