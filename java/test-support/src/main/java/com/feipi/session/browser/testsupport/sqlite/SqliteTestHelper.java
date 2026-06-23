package com.feipi.session.browser.testsupport.sqlite;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * SQLite 测试辅助工具。
 *
 * <p>提供临时数据库创建、配置 PRAGMA 和清理的便捷方法， 供 {@code index-sqlite} 和 {@code contract-tests} 模块使用。
 */
public final class SqliteTestHelper {

  /** 防止实例化。 */
  private SqliteTestHelper() {}

  /**
   * 创建临时内存 SQLite 连接，启用标准 PRAGMA。
   *
   * <p>PRAGMA 配置与生产环境一致：WAL 模式、30s busy timeout、外键开启。 内存数据库在连接关闭后自动销毁，适合隔离测试。
   *
   * @return 配置好的 SQLite 连接
   * @throws SQLException 连接创建失败
   */
  public static Connection createInMemoryConnection() throws SQLException {
    Connection conn = DriverManager.getConnection("jdbc:sqlite::memory:");
    configureConnection(conn);
    return conn;
  }

  /**
   * 创建临时文件 SQLite 数据库连接。
   *
   * <p>数据库文件在临时目录中创建，调用方负责在测试结束后清理。
   *
   * @return 配置好的 SQLite 连接
   * @throws SQLException 连接创建失败
   * @throws java.io.IOException 临时文件创建失败
   */
  public static Connection createTempFileConnection() throws SQLException, java.io.IOException {
    Path tempFile = Files.createTempFile("feipi-test-", ".db");
    Connection conn = DriverManager.getConnection("jdbc:sqlite:" + tempFile.toAbsolutePath());
    configureConnection(conn);
    return conn;
  }

  /**
   * 为标准 SQLite 连接启用 PRAGMA。
   *
   * <p>设置 WAL journal mode、30 秒 busy timeout 和 foreign_keys。 与 Python {@code _get_connection} 配置一致。
   *
   * @param conn 待配置的 SQLite 连接
   * @throws SQLException PRAGMA 设置失败
   */
  public static void configureConnection(Connection conn) throws SQLException {
    try (Statement stmt = conn.createStatement()) {
      stmt.execute("PRAGMA journal_mode=WAL");
      stmt.execute("PRAGMA busy_timeout=30000");
      stmt.execute("PRAGMA foreign_keys=ON");
    }
  }

  /**
   * 安全关闭连接，忽略异常。
   *
   * @param conn 待关闭的连接，可为 null
   */
  public static void closeQuietly(Connection conn) {
    if (conn != null) {
      try {
        conn.close();
      } catch (SQLException ignored) {
        // 测试清理阶段忽略关闭异常
      }
    }
  }
}
