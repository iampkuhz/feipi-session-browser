package com.feipi.session.browser.index.store.sqlite.schema;

import com.feipi.session.browser.index.store.sqlite.tx.WriteBatch;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

/** 从当前 DDL 初始化空索引；已有索引只接受当前结构，不迁移或修复旧格式。 */
public final class IndexSchema {

  /** 当前建库格式，通过 SQLite user_version 记录。 */
  public static final SchemaVersion CURRENT_VERSION = new SchemaVersion(8);

  private IndexSchema() {}

  /**
   * 在空数据库上一次性创建完整结构；当前数据库保持不变。
   *
   * @param conn 索引连接
   * @throws SQLException 连接错误、建库失败或数据库不是当前格式
   */
  public static void ensureSchema(Connection conn) throws SQLException {
    try (Statement statement = conn.createStatement()) {
      int version;
      try (ResultSet result = statement.executeQuery("PRAGMA user_version")) {
        version = result.getInt(1);
      }
      if (version == CURRENT_VERSION.version()) {
        return;
      }
      try (ResultSet rows =
          statement.executeQuery(
              "SELECT 1 FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' LIMIT 1")) {
        if (version != 0 || rows.next()) {
          throw new SQLException("此索引不是当前格式；请指定全新的索引目录并重新扫描");
        }
      }
    }

    String ddl;
    try (var resource = IndexSchema.class.getResourceAsStream("/sql/schema.sql")) {
      if (resource == null) {
        throw new SQLException("缺少索引结构资源 sql/schema.sql");
      }
      ddl = new String(resource.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException error) {
      throw new SQLException("无法读取索引结构", error);
    }

    WriteBatch.executeInTransaction(
        conn,
        connection -> {
          try (Statement statement = connection.createStatement()) {
            for (String sql : ddl.split(";")) {
              if (!sql.isBlank()) {
                statement.execute(sql);
              }
            }
            statement.execute("PRAGMA user_version = " + CURRENT_VERSION.version());
          }
        });
  }

  /**
   * 初始化当前发行版索引并验证发行归属；不同版本不能复用索引目录。
   *
   * @param conn 索引连接
   * @param releaseVersion 当前应用版本
   * @throws SQLException 不能创建索引或该索引属于其他版本
   */
  public static void prepareRelease(Connection conn, String releaseVersion) throws SQLException {
    ensureSchema(conn);
    try (var bind =
            conn.prepareStatement(
                "INSERT OR IGNORE INTO index_metadata(key, value) VALUES ('app_version', ?)");
        Statement statement = conn.createStatement()) {
      try (ResultSet result =
          statement.executeQuery("SELECT value FROM index_metadata WHERE key = 'app_version'")) {
        if (result.next()) {
          requireRelease(releaseVersion, result.getString(1));
          return;
        }
      }
      bind.setString(1, releaseVersion);
      if (bind.executeUpdate() == 0) {
        try (ResultSet result =
            statement.executeQuery("SELECT value FROM index_metadata WHERE key = 'app_version'")) {
          requireRelease(releaseVersion, result.next() ? result.getString(1) : null);
        }
      }
    }
  }

  private static void requireRelease(String expected, String actual) throws SQLException {
    if (!expected.equals(actual)) {
      throw new SQLException("此索引属于其他发行版；请指定全新的索引目录并重新扫描");
    }
  }
}
