package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

/**
 * SQLite 连接 PRAGMA 配置。
 *
 * <p>封装 WAL journal mode、synchronous 级别、busy timeout 和 foreign_keys 开关。 每个新连接打开后由 {@link
 * ConnectionFactory} 统一应用这些 PRAGMA， 保证所有连接行为一致。
 *
 * <p>校验位于连接配置边界（本类 + {@link ConnectionFactory}）。 下游 repository/transaction 不重复检查 PRAGMA 状态。
 *
 * @param journalMode WAL 模式，默认 "wal"
 * @param synchronous 同步级别，WAL 模式下推荐 "normal"
 * @param busyTimeoutMs 锁等待超时毫秒数
 * @param foreignKeys 是否启用外键约束
 */
public record PragmaConfig(
    String journalMode, String synchronous, int busyTimeoutMs, boolean foreignKeys) {

  /** WAL 模式允许值。 */
  private static final List<String> VALID_JOURNAL_MODES =
      List.of("delete", "truncate", "persist", "memory", "wal", "off");

  /** 同步级别允许值。 */
  private static final List<String> VALID_SYNCHRONOUS = List.of("off", "normal", "full", "extra");

  /** 默认配置：WAL、normal synchronous、30s busy timeout、外键开启。 */
  public static final PragmaConfig DEFAULTS = new PragmaConfig("wal", "normal", 30_000, true);

  /**
   * 构造并校验参数。
   *
   * @throws IllegalArgumentException 参数为空或不在允许范围
   */
  public PragmaConfig {
    if (journalMode == null || journalMode.isBlank()) {
      throw new IllegalArgumentException("journalMode 不能为空");
    }
    if (!VALID_JOURNAL_MODES.contains(journalMode.toLowerCase())) {
      throw new IllegalArgumentException("不支持的 journalMode: " + journalMode);
    }
    if (synchronous == null || synchronous.isBlank()) {
      throw new IllegalArgumentException("synchronous 不能为空");
    }
    if (!VALID_SYNCHRONOUS.contains(synchronous.toLowerCase())) {
      throw new IllegalArgumentException("不支持的 synchronous: " + synchronous);
    }
    if (busyTimeoutMs < 0) {
      throw new IllegalArgumentException("busyTimeoutMs 不能为负: " + busyTimeoutMs);
    }
  }

  /**
   * 将全部 PRAGMA 应用到连接。
   *
   * <p>每条 PRAGMA 独立执行；某条失败时后续 PRAGMA 不再执行，异常直接抛出。
   *
   * @param conn 待配置的 SQLite 连接
   * @throws SQLException PRAGMA 执行失败
   */
  public void apply(Connection conn) throws SQLException {
    try (Statement stmt = conn.createStatement()) {
      stmt.execute("PRAGMA journal_mode=" + journalMode);
      stmt.execute("PRAGMA synchronous=" + synchronous);
      stmt.execute("PRAGMA busy_timeout=" + busyTimeoutMs);
      stmt.execute("PRAGMA foreign_keys=" + (foreignKeys ? "ON" : "OFF"));
    }
  }

  /**
   * 验证连接当前 PRAGMA 是否与配置一致。
   *
   * <p>只检查 journal_mode 和 foreign_keys；synchronous 和 busy_timeout 由 SQLite 内部维护， 不同连接上下文可能自动调整。
   *
   * @param conn 已配置的 SQLite 连接
   * @return 全部匹配返回 true
   * @throws SQLException 查询失败
   */
  public boolean verify(Connection conn) throws SQLException {
    try (Statement stmt = conn.createStatement()) {
      // 验证 journal_mode
      try (ResultSet rs = stmt.executeQuery("PRAGMA journal_mode")) {
        if (!rs.next() || !rs.getString(1).equalsIgnoreCase(journalMode)) {
          return false;
        }
      }
      // 验证 foreign_keys
      try (ResultSet rs = stmt.executeQuery("PRAGMA foreign_keys")) {
        if (!rs.next()) {
          return false;
        }
        int fk = rs.getInt(1);
        if (foreignKeys && fk != 1) {
          return false;
        }
        if (!foreignKeys && fk != 0) {
          return false;
        }
      }
    }
    return true;
  }
}
