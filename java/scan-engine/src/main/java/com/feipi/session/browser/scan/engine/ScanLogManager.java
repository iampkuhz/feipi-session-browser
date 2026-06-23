package com.feipi.session.browser.scan.engine;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Map;

/**
 * scan_log 表生命周期管理。
 *
 * <p>提供 scan 开始和结束时对 {@code scan_log} 表的写入操作。 所有方法在调用方提供的事务上下文中执行，不自行管理事务边界。
 */
final class ScanLogManager {

  /** 防止实例化。 */
  private ScanLogManager() {}

  /**
   * 记录一次 full scan 开始。
   *
   * <p>插入 {@code scan_log} 行，状态为 {@code running}，模式为 {@code full}。
   *
   * @param conn 写连接
   * @param startedAt 开始时间戳（epoch 秒）
   * @return 新插入行的 ID
   * @throws SQLException SQL 执行失败
   */
  static long startScan(Connection conn, double startedAt) throws SQLException {
    String sql = "INSERT INTO scan_log (started_at, mode, status) VALUES (?, 'full', 'running')";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, startedAt);
      stmt.executeUpdate();
    }
    return lastInsertRowId(conn);
  }

  /**
   * 记录 scan 成功完成。
   *
   * @param conn 写连接
   * @param scanLogId scan_log 行 ID
   * @param finishedAt 完成时间戳（epoch 秒）
   * @param perSourceCount 各源处理的候选项数
   * @throws SQLException SQL 执行失败
   */
  static void completeScan(
      Connection conn, long scanLogId, double finishedAt, Map<String, Integer> perSourceCount)
      throws SQLException {

    String sql =
        "UPDATE scan_log SET finished_at = ?, status = 'success',"
            + " claude_count = ?, codex_count = ?, qoder_count = ? WHERE id = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, finishedAt);
      stmt.setInt(2, perSourceCount.getOrDefault("claude_code", 0));
      stmt.setInt(3, perSourceCount.getOrDefault("codex", 0));
      stmt.setInt(4, perSourceCount.getOrDefault("qoder", 0));
      stmt.setLong(5, scanLogId);
      stmt.executeUpdate();
    }
  }

  /**
   * 记录 scan 失败。
   *
   * @param conn 写连接
   * @param scanLogId scan_log 行 ID
   * @param finishedAt 完成时间戳（epoch 秒）
   * @param perSourceCount 各源处理的候选项数
   * @throws SQLException SQL 执行失败
   */
  static void failScan(
      Connection conn, long scanLogId, double finishedAt, Map<String, Integer> perSourceCount)
      throws SQLException {

    String sql =
        "UPDATE scan_log SET finished_at = ?, status = 'failure',"
            + " claude_count = ?, codex_count = ?, qoder_count = ? WHERE id = ?";
    try (PreparedStatement stmt = conn.prepareStatement(sql)) {
      stmt.setDouble(1, finishedAt);
      stmt.setInt(2, perSourceCount.getOrDefault("claude_code", 0));
      stmt.setInt(3, perSourceCount.getOrDefault("codex", 0));
      stmt.setInt(4, perSourceCount.getOrDefault("qoder", 0));
      stmt.setLong(5, scanLogId);
      stmt.executeUpdate();
    }
  }

  /** 获取最后插入行的 rowid。 */
  private static long lastInsertRowId(Connection conn) throws SQLException {
    try (PreparedStatement stmt = conn.prepareStatement("SELECT last_insert_rowid()");
        ResultSet rs = stmt.executeQuery()) {
      if (rs.next()) {
        return rs.getLong(1);
      }
      return 0;
    }
  }
}
