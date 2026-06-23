package com.feipi.session.browser.index.sqlite;

import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * SQLite index schema 入口。
 *
 * <p>组合 {@link MigrationRunner} 和 schema 验证，提供：
 *
 * <ul>
 *   <li>{@link #ensureSchema} — 运行所有 migration 并验证表结构完整性。
 *   <li>{@link #validateSchema} — 只验证不修改，检测缺失的表或列。
 *   <li>{@link #repairMissingColumns} — 补充旧数据库中缺失的列。
 * </ul>
 *
 * <p>schema version 独立于 scan logic version。 scan logic version 存储在 {@code index_metadata} 表中， 由
 * scan 生命周期管理，不在本模块维护。
 */
public final class IndexSchema {

  private static final Logger log = LoggerFactory.getLogger(IndexSchema.class);

  /** 当前 schema 版本，与已注册 migration 数量一致。 */
  public static final SchemaVersion CURRENT_VERSION = new SchemaVersion(1);

  /** sessions 表期望的全部列（列名 -> 类型定义），用于验证和修复旧数据库。 */
  private static final Map<String, String> SESSIONS_COLUMNS = buildSessionsColumns();

  /** 所有索引定义，在 migration 后统一创建。 */
  private static final String[] INDEX_STATEMENTS = {
    "CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_key)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_ended_at ON sessions(ended_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_model ON sessions(model)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title)",
    "CREATE INDEX IF NOT EXISTS idx_session_artifacts_type ON session_artifacts(artifact_type)",
    "CREATE INDEX IF NOT EXISTS idx_session_artifacts_path ON session_artifacts(path)"
  };

  private final MigrationRunner runner;

  /**
   * 使用指定 migration runner 创建 schema 入口。
   *
   * @param runner migration 执行器
   */
  public IndexSchema(MigrationRunner runner) {
    this.runner = runner;
  }

  /**
   * 使用全部已注册 migration 创建 schema 入口。
   *
   * @return 新 IndexSchema 实例
   */
  public static IndexSchema withDefaults() {
    return new IndexSchema(MigrationRunner.withAllMigrations());
  }

  /**
   * 运行所有 migration 并确保表结构完整。
   *
   * <p>先应用未执行的 migration，再检测旧数据库中可能缺失的列并修复。 适用于从 Python 旧版数据库升级的场景。
   *
   * @param conn SQLite 连接
   * @return 本次应用的 migration 列表
   * @throws SQLException schema 操作失败
   */
  public List<SchemaVersion> ensureSchema(Connection conn) throws SQLException {
    List<SchemaVersion> applied = runner.applyAll(conn);
    repairMissingColumns(conn);
    ensureIndexes(conn);
    return applied;
  }

  /**
   * 查询当前 schema 版本。
   *
   * @param conn SQLite 连接
   * @return 当前版本，无 migration 时返回 null
   * @throws SQLException 查询失败
   */
  public SchemaVersion currentVersion(Connection conn) throws SQLException {
    return runner.currentVersion(conn);
  }

  /**
   * 验证 schema 完整性，返回缺失的表和列。
   *
   * <p>只读操作，不修改数据库。
   *
   * @param conn SQLite 连接
   * @return 验证结果，包含缺失表和列信息
   * @throws SQLException 查询失败
   */
  public SchemaValidationResult validateSchema(Connection conn) throws SQLException {
    Map<String, Set<String>> missingColumns = new LinkedHashMap<>();
    Set<String> existingTables = getExistingTables(conn);

    // 检查 sessions 表列完整性
    if (existingTables.contains("sessions")) {
      Set<String> actualColumns = getTableColumns(conn, "sessions");
      Set<String> missing = new HashSet<>();
      for (String expected : SESSIONS_COLUMNS.keySet()) {
        if (!actualColumns.contains(expected.toLowerCase())) {
          missing.add(expected);
        }
      }
      if (!missing.isEmpty()) {
        missingColumns.put("sessions", missing);
      }
    }

    return new SchemaValidationResult(existingTables, missingColumns);
  }

  /**
   * 修复旧数据库中 sessions 表缺失的列。
   *
   * <p>对 sessions 表中定义存在但实际缺失的列执行 {@code ALTER TABLE ADD COLUMN}。 SQLite 不支持 DROP COLUMN（低版本）和
   * MODIFY COLUMN， 因此只处理新增列场景。
   *
   * @param conn SQLite 连接
   * @throws SQLException 修复失败
   */
  void repairMissingColumns(Connection conn) throws SQLException {
    Set<String> existingTables = getExistingTables(conn);
    if (!existingTables.contains("sessions")) {
      return;
    }
    Set<String> actualColumns = getTableColumns(conn, "sessions");
    for (Map.Entry<String, String> entry : SESSIONS_COLUMNS.entrySet()) {
      String col = entry.getKey();
      if (!actualColumns.contains(col.toLowerCase())) {
        log.info("补充 sessions 表缺失列: {} {}", col, entry.getValue());
        String alterSql = "ALTER TABLE sessions ADD COLUMN " + col + " " + entry.getValue();
        conn.createStatement().execute(alterSql);
      }
    }
  }

  /**
   * 确保所有索引存在。
   *
   * <p>在 migration 和缺失列修复后调用。使用 {@code CREATE INDEX IF NOT EXISTS}， 对已存在的索引无副作用。
   *
   * @param conn SQLite 连接
   * @throws SQLException 索引创建失败
   */
  void ensureIndexes(Connection conn) throws SQLException {
    try (java.sql.Statement stmt = conn.createStatement()) {
      for (String indexSql : INDEX_STATEMENTS) {
        stmt.execute(indexSql);
      }
    }
  }

  /** 获取数据库中已存在的表名集合。 */
  private static Set<String> getExistingTables(Connection conn) throws SQLException {
    Set<String> tables = new HashSet<>();
    try (ResultSet rs = conn.getMetaData().getTables(null, null, "%", new String[] {"TABLE"})) {
      while (rs.next()) {
        tables.add(rs.getString("TABLE_NAME").toLowerCase());
      }
    }
    return tables;
  }

  /** 获取指定表的列名集合（小写）。 */
  private static Set<String> getTableColumns(Connection conn, String tableName)
      throws SQLException {
    Set<String> columns = new HashSet<>();
    DatabaseMetaData meta = conn.getMetaData();
    try (ResultSet rs = meta.getColumns(null, null, tableName, "%")) {
      while (rs.next()) {
        columns.add(rs.getString("COLUMN_NAME").toLowerCase());
      }
    }
    return columns;
  }

  /**
   * 构建 sessions 表期望列定义。
   *
   * <p>列名和类型与 Python schema.py init_schema 保持一致。 顺序不影响功能，但保持与原始 SQL 一致的排列便于对照。
   */
  private static Map<String, String> buildSessionsColumns() {
    Map<String, String> cols = new LinkedHashMap<>();
    cols.put("session_key", "TEXT PRIMARY KEY");
    cols.put("agent", "TEXT NOT NULL CHECK(agent <> '')");
    cols.put("session_id", "TEXT NOT NULL CHECK(session_id <> '')");
    cols.put("title", "TEXT NOT NULL DEFAULT ''");
    cols.put("project_key", "TEXT NOT NULL CHECK(project_key <> '')");
    cols.put("project_name", "TEXT NOT NULL DEFAULT ''");
    cols.put("cwd", "TEXT NOT NULL DEFAULT ''");
    cols.put("started_at", "TEXT NOT NULL DEFAULT ''");
    cols.put("ended_at", "TEXT NOT NULL CHECK(ended_at <> '')");
    cols.put("duration_seconds", "REAL NOT NULL DEFAULT 0");
    cols.put("model_execution_seconds", "REAL NOT NULL DEFAULT 0");
    cols.put("tool_execution_seconds", "REAL NOT NULL DEFAULT 0");
    cols.put("model", "TEXT NOT NULL DEFAULT ''");
    cols.put("git_branch", "TEXT NOT NULL DEFAULT ''");
    cols.put("source", "TEXT NOT NULL DEFAULT ''");
    cols.put("user_message_count", "INTEGER NOT NULL DEFAULT 0");
    cols.put("assistant_message_count", "INTEGER NOT NULL DEFAULT 0");
    cols.put("tool_call_count", "INTEGER NOT NULL DEFAULT 0");
    cols.put("output_tokens", "INTEGER NOT NULL DEFAULT 0");
    cols.put("fresh_input_tokens", "INTEGER NOT NULL DEFAULT 0");
    cols.put("cache_read_tokens", "INTEGER NOT NULL DEFAULT 0");
    cols.put("cache_write_tokens", "INTEGER NOT NULL DEFAULT 0");
    cols.put("total_tokens", "INTEGER NOT NULL DEFAULT 0");
    cols.put("failed_tool_count", "INTEGER NOT NULL DEFAULT 0");
    cols.put("subagent_instance_count", "INTEGER NOT NULL DEFAULT 0");
    cols.put("indexed_at", "REAL NOT NULL DEFAULT 0");
    cols.put("file_mtime", "REAL NOT NULL DEFAULT 0");
    cols.put("file_path", "TEXT NOT NULL DEFAULT ''");
    return Map.copyOf(cols);
  }

  /**
   * schema 验证结果。
   *
   * @param existingTables 已存在的表名集合（小写）
   * @param missingColumns 缺失列映射：表名 -> 缺失列名集合
   */
  public record SchemaValidationResult(
      Set<String> existingTables, Map<String, Set<String>> missingColumns) {

    /** 判断 schema 是否完整（无缺失表或列）。 */
    public boolean isComplete() {
      return missingColumns.isEmpty() && hasAllRequiredTables();
    }

    /** 判断是否包含全部必需表。 */
    private boolean hasAllRequiredTables() {
      Set<String> required = Set.of("sessions", "scan_log", "index_metadata", "session_artifacts");
      return existingTables.containsAll(required);
    }
  }
}
