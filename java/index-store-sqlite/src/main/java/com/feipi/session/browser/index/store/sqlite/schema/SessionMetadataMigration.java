package com.feipi.session.browser.index.store.sqlite.schema;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

/** V2：仅放宽未知项目和结束时间，保留现存扩展列、关联、索引和触发器。 */
final class SessionMetadataMigration {
  private SessionMetadataMigration() {}

  static void apply(Connection conn) throws SQLException {
    String sessions = tableSql(conn, "sessions");
    String artifacts = tableSql(conn, "session_artifacts");
    List<String> objects = new ArrayList<>();
    try (var statement = conn.createStatement();
        var result =
            statement.executeQuery(
                "SELECT sql FROM sqlite_master WHERE tbl_name IN ('sessions', 'session_artifacts')"
                    + " AND type IN ('index', 'trigger') AND sql IS NOT NULL")) {
      while (result.next()) objects.add(result.getString(1));
    }
    String replacement =
        sessions
            .replaceFirst(
                "(?i)CREATE\\s+TABLE\\s+(?:IF\\s+NOT\\s+EXISTS\\s+)?(?:sessions|\"sessions\"|`sessions`|\\[sessions\\])",
                "CREATE TABLE sessions_metadata_v2")
            .replaceAll("(?i)CHECK\\s*\\(\\s*(?:project_key|ended_at)\\s*<>\\s*''\\s*\\)", "");
    // 先保存并移除子表，防止 DROP 父表触发 ON DELETE CASCADE。
    execute(conn, "CREATE TEMP TABLE artifacts_metadata_v2 AS SELECT * FROM session_artifacts");
    execute(conn, "DROP TABLE session_artifacts");
    execute(conn, replacement);
    execute(conn, "INSERT INTO sessions_metadata_v2 SELECT * FROM sessions");
    execute(conn, "DROP TABLE sessions");
    execute(conn, "ALTER TABLE sessions_metadata_v2 RENAME TO sessions");
    execute(conn, artifacts);
    execute(conn, "INSERT INTO session_artifacts SELECT * FROM artifacts_metadata_v2");
    execute(conn, "DROP TABLE artifacts_metadata_v2");
    for (String object : objects) execute(conn, object);
    try (var statement = conn.createStatement();
        var result = statement.executeQuery("PRAGMA foreign_key_check")) {
      if (result.next()) throw new SQLException("V2 migration foreign key check failed");
    }
  }

  private static String tableSql(Connection conn, String table) throws SQLException {
    try (var statement =
        conn.prepareStatement("SELECT sql FROM sqlite_master WHERE type='table' AND name=?")) {
      statement.setString(1, table);
      try (var result = statement.executeQuery()) {
        if (!result.next()) throw new SQLException("Missing migration table: " + table);
        return result.getString(1);
      }
    }
  }

  private static void execute(Connection conn, String sql) throws SQLException {
    try (var statement = conn.createStatement()) {
      statement.execute(sql);
    }
  }
}
