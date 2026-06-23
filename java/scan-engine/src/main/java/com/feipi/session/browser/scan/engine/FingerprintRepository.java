package com.feipi.session.browser.scan.engine;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 从 sessions 表加载已索引会话指纹的仓库。
 *
 * <p>增量扫描启动时通过 {@link #loadAll} 一次性读取全部已索引会话的指纹数据， 构建 session_key 到指纹的映射供后续比较。
 *
 * <p>该类是只读仓库，不修改数据库。查询在调用方提供的事务上下文中执行。
 */
final class FingerprintRepository {

  /** 防止实例化。 */
  private FingerprintRepository() {}

  /**
   * 加载全部已索引会话的指纹数据。
   *
   * <p>查询 sessions 表的 session_key、file_path、file_mtime、agent 和 ended_at 字段， 以 session_key 为键构建映射。
   *
   * @param conn SQLite 读连接
   * @return session_key 到指纹的不可变映射
   * @throws SQLException 查询失败时
   */
  static Map<String, StoredSessionFingerprint> loadAll(Connection conn) throws SQLException {
    String sql = "SELECT session_key, file_path, file_mtime, agent, ended_at FROM sessions";
    Map<String, StoredSessionFingerprint> result = new LinkedHashMap<>();
    try (PreparedStatement stmt = conn.prepareStatement(sql);
        ResultSet rs = stmt.executeQuery()) {
      while (rs.next()) {
        String sessionKey = rs.getString("session_key");
        String filePath = rs.getString("file_path");
        double fileMtime = rs.getDouble("file_mtime");
        String agent = rs.getString("agent");
        String endedAt = rs.getString("ended_at");
        result.put(
            sessionKey,
            new StoredSessionFingerprint(sessionKey, filePath, fileMtime, agent, endedAt));
      }
    }
    return Map.copyOf(result);
  }
}
