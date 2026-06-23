package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

/**
 * SQLite 连接工厂。
 *
 * <p>创建 JDBC 连接并统一应用 {@link PragmaConfig}。 每个新连接独立配置，互不共享 PRAGMA 状态。
 *
 * <p>校验位于连接创建边界：工厂负责确保每个产出的连接已配置正确 PRAGMA。 下游不重复检查 PRAGMA。
 */
public final class ConnectionFactory {

  private final String jdbcUrl;
  private final PragmaConfig pragmaConfig;

  /**
   * 创建连接工厂。
   *
   * @param jdbcUrl SQLite JDBC URL，例如 {@code "jdbc:sqlite:/path/to/db.sqlite"} 或 {@code
   *     "jdbc:sqlite::memory:"}
   * @param pragmaConfig PRAGMA 配置
   */
  public ConnectionFactory(String jdbcUrl, PragmaConfig pragmaConfig) {
    if (jdbcUrl == null || jdbcUrl.isBlank()) {
      throw new IllegalArgumentException("jdbcUrl 不能为空");
    }
    if (pragmaConfig == null) {
      throw new IllegalArgumentException("pragmaConfig 不能为 null");
    }
    this.jdbcUrl = jdbcUrl;
    this.pragmaConfig = pragmaConfig;
  }

  /**
   * 创建使用默认 PRAGMA 的连接工厂。
   *
   * @param jdbcUrl SQLite JDBC URL
   * @return 新连接工厂
   */
  public static ConnectionFactory withDefaults(String jdbcUrl) {
    return new ConnectionFactory(jdbcUrl, PragmaConfig.DEFAULTS);
  }

  /**
   * 创建并配置新的 SQLite 连接。
   *
   * <p>打开连接后立即应用全部 PRAGMA。调用方负责关闭返回的连接。
   *
   * @return 已配置 PRAGMA 的新连接
   * @throws SQLException 连接打开或 PRAGMA 配置失败
   */
  public Connection create() throws SQLException {
    Connection conn = DriverManager.getConnection(jdbcUrl);
    try {
      pragmaConfig.apply(conn);
      return conn;
    } catch (SQLException e) {
      conn.close();
      throw e;
    }
  }

  /** 获取数据库连接地址。 */
  public String jdbcUrl() {
    return jdbcUrl;
  }

  /** 获取 PRAGMA 配置。 */
  public PragmaConfig pragmaConfig() {
    return pragmaConfig;
  }
}
