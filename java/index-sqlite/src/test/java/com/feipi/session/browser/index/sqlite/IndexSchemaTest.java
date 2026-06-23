package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/** {@link IndexSchema} 入口测试，覆盖空 DB、当前 DB、旧列缺失、重复 migration 和验证。 */
@DisplayName("IndexSchema 测试")
class IndexSchemaTest {

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Nested
  @DisplayName("空数据库")
  class EmptyDatabase {

    @Test
    @DisplayName("ensureSchema 在空数据库上创建全部表并返回 V1")
    void ensureSchemaOnEmptyDb() throws SQLException {
      IndexSchema schema = IndexSchema.withDefaults();
      List<SchemaVersion> applied = schema.ensureSchema(conn);

      assertThat(applied).hasSize(1);
      assertThat(applied.get(0).version()).isEqualTo(1);

      // 验证所有表存在
      IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);
      assertThat(result.isComplete()).isTrue();
    }

    @Test
    @DisplayName("sessions 表包含全部 28 列")
    void sessionsTableHasAllColumns() throws SQLException {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);

      Set<String> columns = getTableColumns("sessions");
      assertThat(columns).hasSize(28);
      assertThat(columns)
          .contains(
              "session_key",
              "agent",
              "session_id",
              "title",
              "project_key",
              "ended_at",
              "model",
              "total_tokens",
              "file_path");
    }

    @Test
    @DisplayName("session_artifacts 外键指向 sessions 且 ON DELETE CASCADE")
    void foreignKeyConstraint() throws SQLException {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);

      // 插入 session 和关联 artifact
      try (Statement stmt = conn.createStatement()) {
        stmt.execute(
            "INSERT INTO sessions (session_key, agent, session_id, ended_at, project_key)"
                + " VALUES ('sk1', 'claude', 'sid1', '2024-01-01', 'proj1')");
        stmt.execute(
            "INSERT INTO session_artifacts (session_key, artifact_type, path)"
                + " VALUES ('sk1', 'normalized', '/path/to/artifact')");
      }

      // 删除 session 时 artifact 应被级联删除
      try (Statement stmt = conn.createStatement()) {
        stmt.execute("DELETE FROM sessions WHERE session_key = 'sk1'");
      }

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM session_artifacts")) {
        rs.next();
        assertThat(rs.getInt(1)).isZero();
      }
    }
  }

  @Nested
  @DisplayName("当前数据库（重复调用）")
  class CurrentDatabase {

    @Test
    @DisplayName("两次 ensureSchema 第二次返回空列表")
    void secondEnsureSchemaNoOp() throws SQLException {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);

      List<SchemaVersion> secondApply = schema.ensureSchema(conn);
      assertThat(secondApply).isEmpty();
    }
  }

  @Nested
  @DisplayName("旧列缺失修复")
  class MissingColumns {

    @Test
    @DisplayName("sessions 表缺少列时 validateSchema 报告缺失")
    void validateDetectsMissingColumns() throws SQLException {
      // 创建只有部分列的 sessions 表
      try (Statement stmt = conn.createStatement()) {
        stmt.execute(
            "CREATE TABLE sessions ("
                + "session_key TEXT PRIMARY KEY, "
                + "agent TEXT NOT NULL, "
                + "session_id TEXT NOT NULL"
                + ")");
      }

      IndexSchema schema = IndexSchema.withDefaults();
      IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);

      assertThat(result.isComplete()).isFalse();
      assertThat(result.missingColumns()).containsKey("sessions");
      assertThat(result.missingColumns().get("sessions")).contains("title", "ended_at", "model");
    }

    @Test
    @DisplayName("repairMissingColumns 补充缺失列")
    void repairFillsMissingColumns() throws SQLException {
      // 创建缺少多列的 sessions 表
      try (Statement stmt = conn.createStatement()) {
        stmt.execute(
            "CREATE TABLE sessions ("
                + "session_key TEXT PRIMARY KEY, "
                + "agent TEXT NOT NULL CHECK(agent <> ''), "
                + "session_id TEXT NOT NULL CHECK(session_id <> ''), "
                + "ended_at TEXT NOT NULL CHECK(ended_at <> ''), "
                + "project_key TEXT NOT NULL CHECK(project_key <> '')"
                + ")");
      }

      IndexSchema schema = IndexSchema.withDefaults();

      // 修复缺失列
      schema.repairMissingColumns(conn);

      // 验证全部列已存在
      Set<String> columns = getTableColumns("sessions");
      assertThat(columns).hasSize(28);
      assertThat(columns).contains("title", "model", "total_tokens", "file_path", "indexed_at");
    }

    @Test
    @DisplayName("ensureSchema 在部分列数据库中自动修复并标记 V1 已应用")
    void ensureSchemaRepairsAndApplies() throws SQLException {
      // 创建只有部分列的旧数据库
      try (Statement stmt = conn.createStatement()) {
        stmt.execute(
            "CREATE TABLE sessions ("
                + "session_key TEXT PRIMARY KEY, "
                + "agent TEXT NOT NULL CHECK(agent <> ''), "
                + "session_id TEXT NOT NULL CHECK(session_id <> ''), "
                + "ended_at TEXT NOT NULL CHECK(ended_at <> ''), "
                + "project_key TEXT NOT NULL CHECK(project_key <> '')"
                + ")");
      }

      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);

      // V001 用 IF NOT EXISTS 不报错，repairMissingColumns 补充缺失列
      Set<String> columns = getTableColumns("sessions");
      assertThat(columns).hasSize(28);

      // schema_migrations 记录 V1
      assertThat(schema.currentVersion(conn).version()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("Schema 验证")
  class SchemaValidation {

    @Test
    @DisplayName("完整 schema 验证通过")
    void completeSchemaPassesValidation() throws SQLException {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);

      IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);
      assertThat(result.isComplete()).isTrue();
      assertThat(result.missingColumns()).isEmpty();
    }

    @Test
    @DisplayName("空数据库验证不完整")
    void emptyDatabaseFailsValidation() throws SQLException {
      IndexSchema schema = IndexSchema.withDefaults();
      // 只创建 tracking 表，不运行 migration
      schema.currentVersion(conn);

      IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);
      assertThat(result.isComplete()).isFalse();
    }
  }

  @Nested
  @DisplayName("CURRENT_VERSION 常量")
  class CurrentVersionConstant {

    @Test
    @DisplayName("CURRENT_VERSION 与已注册 migration 数量一致")
    void currentVersionMatchesMigrationCount() {
      assertThat(IndexSchema.CURRENT_VERSION.version()).isEqualTo(Migration.allMigrations().size());
    }
  }

  /** 获取指定表的列名集合（小写）。 */
  private Set<String> getTableColumns(String tableName) throws SQLException {
    Set<String> columns = new java.util.HashSet<>();
    try (ResultSet rs = conn.getMetaData().getColumns(null, null, tableName, "%")) {
      while (rs.next()) {
        columns.add(rs.getString("COLUMN_NAME").toLowerCase());
      }
    }
    return columns;
  }
}
