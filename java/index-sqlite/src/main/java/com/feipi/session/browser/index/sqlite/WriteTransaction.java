package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * 显式写事务。
 *
 * <p>关闭 auto-commit 开启事务，{@link #commit} 提交，{@link #rollback} 回滚。 {@link #close} 在未提交时自动回滚， 可作为
 * {@code try-with-resources} 使用。
 *
 * <p>事务边界在本类管理；下游不重复控制 commit/rollback。
 */
public final class WriteTransaction implements AutoCloseable {

  private final Connection conn;
  private boolean committed;
  private boolean closed;

  /**
   * 在指定连接上开启写事务。
   *
   * <p>关闭 auto-commit 开始事务。调用方必须通过 {@link #commit} 或 {@link #rollback} 结束事务， 或在 {@code
   * try-with-resources} 中使用本类。
   *
   * @param conn SQLite 连接
   * @throws SQLException 关闭 auto-commit 失败
   */
  public WriteTransaction(Connection conn) throws SQLException {
    this.conn = conn;
    conn.setAutoCommit(false);
  }

  /**
   * 获取底层连接。
   *
   * @return 事务关联的连接
   */
  public Connection connection() {
    return conn;
  }

  /**
   * 提交事务。
   *
   * @throws SQLException 提交失败
   */
  public void commit() throws SQLException {
    if (committed || closed) {
      throw new IllegalStateException("事务已结束");
    }
    conn.commit();
    committed = true;
  }

  /**
   * 回滚事务。
   *
   * @throws SQLException 回滚失败
   */
  public void rollback() throws SQLException {
    if (committed || closed) {
      throw new IllegalStateException("事务已结束");
    }
    conn.rollback();
    closed = true;
  }

  /**
   * 关闭事务，未提交时自动回滚。
   *
   * <p>回滚失败时只记录警告，不抛出异常，避免掩盖原始错误。
   */
  @Override
  public void close() {
    if (!committed && !closed) {
      try {
        conn.rollback();
      } catch (SQLException e) {
        // 关闭阶段回滚失败只记日志，不抛出
        org.slf4j.LoggerFactory.getLogger(WriteTransaction.class).warn("事务自动回滚失败", e);
      }
    }
    closed = true;
  }

  /**
   * 在连接上执行单条 SQL。
   *
   * <p>事务内便捷方法，避免调用方自行管理 {@link Statement} 生命周期。
   *
   * @param sql SQL 语句
   * @throws SQLException 执行失败
   */
  public void execute(String sql) throws SQLException {
    try (Statement stmt = conn.createStatement()) {
      stmt.execute(sql);
    }
  }
}
