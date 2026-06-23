package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

/**
 * 批量写入辅助。
 *
 * <p>累积 INSERT/UPDATE/DELETE 语句，{@link #flush} 在单个事务中一次性执行。 也可通过 {@link #execute} 提交任意 JDBC lambda
 * 操作。
 *
 * <p>批量大小有上限（{@link #DEFAULT_MAX_ENTRIES} = 5000），防止单次事务过大导致 WAL 膨胀。 达到上限时 {@link #addInsert} 等方法抛出
 * {@link IllegalStateException}，调用方应先 flush 再继续。
 *
 * <p>仅由 {@link WriteQueue} 的 writer 线程使用，不需要线程安全。
 */
public final class WriteBatch {

  /** 单批次最大语句数。 */
  public static final int DEFAULT_MAX_ENTRIES = 5000;

  private final List<String> statements = new ArrayList<>();
  private final int maxEntries;
  private final Connection conn;

  /**
   * 创建批量写入器。
   *
   * @param conn 写连接（由 WriteQueue 独占管理）
   * @param maxEntries 最大语句数，超过时拒绝添加
   */
  public WriteBatch(Connection conn, int maxEntries) {
    this.conn = conn;
    this.maxEntries = maxEntries;
  }

  /**
   * 添加 INSERT 语句。
   *
   * @param sql INSERT SQL
   * @throws IllegalStateException 超过批量上限
   */
  public void addInsert(String sql) {
    checkCapacity();
    statements.add(sql);
  }

  /**
   * 添加 UPDATE 语句。
   *
   * @param sql UPDATE SQL
   * @throws IllegalStateException 超过批量上限
   */
  public void addUpdate(String sql) {
    checkCapacity();
    statements.add(sql);
  }

  /**
   * 添加 DELETE 语句。
   *
   * @param sql DELETE SQL
   * @throws IllegalStateException 超过批量上限
   */
  public void addDelete(String sql) {
    checkCapacity();
    statements.add(sql);
  }

  /**
   * 在单事务中执行所有累积语句并清空缓冲区。
   *
   * <p>无待执行语句时直接返回，不开启事务。 失败时回滚，不留下半写入。
   *
   * @throws SQLException SQL 执行失败
   */
  public void flush() throws SQLException {
    if (statements.isEmpty()) {
      return;
    }
    runInTransaction(
        c -> {
          try (Statement stmt = c.createStatement()) {
            for (String sql : statements) {
              stmt.execute(sql);
            }
          }
        });
    statements.clear();
  }

  /**
   * 在事务中执行任意 JDBC 操作。
   *
   * <p>关闭 auto-commit，执行操作，成功后提交。 失败时回滚。
   *
   * @param op JDBC 操作
   * @throws SQLException SQL 执行失败
   */
  public void execute(WriteOperation op) throws SQLException {
    runInTransaction(op);
  }

  /**
   * 在事务中执行操作的公共辅助方法。
   *
   * <p>保存当前 auto-commit 状态，关闭 auto-commit 开启事务， 执行操作后提交；失败时回滚并恢复原始状态。
   *
   * @param op JDBC 操作
   * @throws SQLException SQL 执行失败
   */
  private void runInTransaction(WriteOperation op) throws SQLException {
    executeInTransaction(conn, op);
  }

  /**
   * 在指定连接上执行事务的包级静态辅助方法。
   *
   * <p>供同包类（如 {@link MigrationRunner}）复用相同的事务管理模式， 避免各自重复 auto-commit 切换和回滚逻辑。
   *
   * @param conn JDBC 连接
   * @param op JDBC 操作
   * @throws SQLException SQL 执行失败
   */
  static void executeInTransaction(Connection conn, WriteOperation op) throws SQLException {
    boolean originalAutoCommit = conn.getAutoCommit();
    try {
      conn.setAutoCommit(false);
      op.execute(conn);
      conn.commit();
    } catch (SQLException e) {
      conn.rollback();
      throw e;
    } finally {
      conn.setAutoCommit(originalAutoCommit);
    }
  }

  /** 当前缓冲的语句数。 */
  public int pendingCount() {
    return statements.size();
  }

  /** 检查是否还有添加空间。 */
  private void checkCapacity() {
    if (statements.size() >= maxEntries) {
      throw new IllegalStateException("写入批次已满（" + maxEntries + " 条），请先 flush");
    }
  }

  /**
   * 写操作函数接口。
   *
   * <p>用于 {@link WriteBatch#execute} 提交任意 JDBC 操作。
   */
  @FunctionalInterface
  public interface WriteOperation {
    /**
     * 在事务上下文中执行 JDBC 操作。
     *
     * @param conn 已关闭 auto-commit 的连接
     * @throws SQLException SQL 执行失败
     */
    void execute(Connection conn) throws SQLException;
  }
}
