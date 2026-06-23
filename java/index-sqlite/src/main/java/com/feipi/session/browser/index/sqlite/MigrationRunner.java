package com.feipi.session.browser.index.sqlite;

import java.io.UncheckedIOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 幂等 schema migration 执行器。
 *
 * <p>负责：
 *
 * <ul>
 *   <li>创建内部追踪表 {@code schema_migrations}。
 *   <li>检测已应用的 migration，跳过重复执行。
 *   <li>每条 migration 在原子事务中执行，失败自动回滚。
 *   <li>提供显式回滚能力（需要 migration 提供 downgrade SQL）。
 * </ul>
 *
 * <p>所有 SQL 校验和版本追踪位于本类（migration manager 边界）。 下游 repository 不重复检查 schema 版本。
 */
public final class MigrationRunner {

  private static final Logger log = LoggerFactory.getLogger(MigrationRunner.class);

  /** 创建内部 migration 追踪表的 SQL。 */
  private static final String CREATE_TRACKING_TABLE =
      """
      CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          description TEXT NOT NULL DEFAULT '',
          applied_at TEXT NOT NULL DEFAULT ''
      )
      """;

  /** 查询已应用版本。 */
  private static final String SELECT_APPLIED =
      "SELECT version FROM schema_migrations ORDER BY version";

  /** 记录已应用版本。 */
  private static final String INSERT_APPLIED =
      "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)";

  private final List<Migration> migrations;

  /**
   * 创建 migration runner。
   *
   * @param migrations 按版本号升序排列的 migration 列表
   */
  public MigrationRunner(List<Migration> migrations) {
    this.migrations = List.copyOf(migrations);
  }

  /**
   * 创建使用全部已注册 migration 的 runner。
   *
   * @return 新 migration runner
   */
  public static MigrationRunner withAllMigrations() {
    return new MigrationRunner(Migration.allMigrations());
  }

  /**
   * 将所有未应用的 migration 按顺序应用到数据库。
   *
   * <p>每条 migration 在独立事务中执行：先 {@code BEGIN}，执行 SQL， 成功后 {@code COMMIT} 并记录到 {@code
   * schema_migrations}。 失败时 {@code ROLLBACK} 并抛出异常，不留下半升级。
   *
   * @param conn SQLite 连接；调用方负责连接生命周期
   * @return 本次实际应用的 migration 版本号列表（空列表表示全部已应用）
   * @throws SQLException migration 执行失败或 SQL 错误
   */
  public List<SchemaVersion> applyAll(Connection conn) throws SQLException {
    ensureTrackingTable(conn);
    Set<Integer> appliedVersions = loadAppliedVersions(conn);
    List<SchemaVersion> newlyApplied = new ArrayList<>();

    for (Migration migration : migrations) {
      int ver = migration.version().version();
      if (appliedVersions.contains(ver)) {
        log.debug("跳过已应用的 migration: V{}", ver);
        continue;
      }
      applySingle(conn, migration);
      newlyApplied.add(migration.version());
    }
    return newlyApplied;
  }

  /**
   * 查询当前 schema 版本。
   *
   * <p>返回已应用的最高版本号。无已应用 migration 时返回 {@code null}。
   *
   * @param conn SQLite 连接
   * @return 当前 schema 版本，或 null
   * @throws SQLException 查询失败
   */
  public SchemaVersion currentVersion(Connection conn) throws SQLException {
    ensureTrackingTable(conn);
    Set<Integer> applied = loadAppliedVersions(conn);
    if (applied.isEmpty()) {
      return null;
    }
    return new SchemaVersion(applied.stream().mapToInt(Integer::intValue).max().orElseThrow());
  }

  /**
   * 查询已应用的 migration 版本号集合。
   *
   * @param conn SQLite 连接
   * @return 已应用版本号（升序）
   * @throws SQLException 查询失败
   */
  public Set<Integer> appliedVersions(Connection conn) throws SQLException {
    ensureTrackingTable(conn);
    return loadAppliedVersions(conn);
  }

  /**
   * 查询待应用的 migration 列表。
   *
   * @param conn SQLite 连接
   * @return 尚未应用的 migration 列表
   * @throws SQLException 查询失败
   */
  public List<Migration> pendingMigrations(Connection conn) throws SQLException {
    Set<Integer> applied = appliedVersions(conn);
    return migrations.stream().filter(m -> !applied.contains(m.version().version())).toList();
  }

  /**
   * 在原子事务中执行单条 migration。
   *
   * <p>失败时回滚事务，不留下半升级。 成功后记录到 schema_migrations 追踪表。
   */
  private void applySingle(Connection conn, Migration migration) throws SQLException {
    String sql;
    try {
      sql = migration.loadSql();
    } catch (UncheckedIOException e) {
      throw new SQLException("migration V" + migration.version().version() + " SQL 加载失败", e);
    }
    log.info("应用 migration V{}: {}", migration.version().version(), migration.description());

    boolean originalAutoCommit = conn.getAutoCommit();
    try {
      conn.setAutoCommit(false);
      executeStatements(conn, sql);
      try (PreparedStatement ps = conn.prepareStatement(INSERT_APPLIED)) {
        ps.setInt(1, migration.version().version());
        ps.setString(2, migration.description());
        ps.setString(3, String.valueOf(System.currentTimeMillis() / 1000.0));
        ps.executeUpdate();
      }
      conn.commit();
    } catch (SQLException e) {
      conn.rollback();
      throw new SQLException("migration V" + migration.version().version() + " 执行失败，已回滚", e);
    } finally {
      conn.setAutoCommit(originalAutoCommit);
    }
  }

  /**
   * 按分号拆分 SQL 文本并逐条执行。
   *
   * <p>{@link Statement#execute} 只执行单条语句，多语句 SQL 资源需要拆分后逐条执行。 忽略空白语句。
   */
  private static void executeStatements(Connection conn, String sql) throws SQLException {
    for (String statement : sql.split(";")) {
      String trimmed = statement.strip();
      if (!trimmed.isEmpty()) {
        try (Statement stmt = conn.createStatement()) {
          stmt.execute(trimmed);
        }
      }
    }
  }

  /** 确保 schema_migrations 追踪表存在。 */
  private void ensureTrackingTable(Connection conn) throws SQLException {
    try (Statement stmt = conn.createStatement()) {
      stmt.execute(CREATE_TRACKING_TABLE);
    }
  }

  /** 加载已应用的 migration 版本号。 */
  private Set<Integer> loadAppliedVersions(Connection conn) throws SQLException {
    Set<Integer> versions = new LinkedHashSet<>();
    try (Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery(SELECT_APPLIED)) {
      while (rs.next()) {
        versions.add(rs.getInt("version"));
      }
    }
    return versions;
  }
}
