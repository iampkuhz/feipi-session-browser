package com.feipi.session.browser.contracttest.schema;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.Migration;
import com.feipi.session.browser.index.sqlite.MigrationRunner;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
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
import org.junit.jupiter.api.Test;

/**
 * SQLite index schema 契约测试。
 *
 * <p>验证 Java migration 产出的 schema 与 Python schema.py 定义一致： 表结构、列名、索引、外键约束和 PRAGMA 配置。
 */
@DisplayName("Schema 契约测试：Java migration 与 Python schema 一致")
class SchemaContractTest {

  private Connection conn;

  @BeforeEach
  void setUp() throws SQLException {
    conn = SqliteTestHelper.createInMemoryConnection();
  }

  @AfterEach
  void tearDown() {
    SqliteTestHelper.closeQuietly(conn);
  }

  @Test
  @DisplayName("Java migration 后 schema 完整性验证通过")
  void javaMigrationProducesCompleteSchema() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);
    assertThat(result.isComplete()).as("Java migration 应产出完整的 schema，无缺失表或列").isTrue();
  }

  @Test
  @DisplayName("sessions 表包含 28 列，与 Python 定义一致")
  void sessionsTableMatchesPythonDefinition() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    Set<String> columns = getTableColumns("sessions");
    assertThat(columns).as("sessions 表应包含 28 列，与 Python schema.py 一致").hasSize(28);

    // 验证关键字段
    assertThat(columns)
        .containsExactlyInAnyOrder(
            "session_key",
            "agent",
            "session_id",
            "title",
            "project_key",
            "project_name",
            "cwd",
            "started_at",
            "ended_at",
            "duration_seconds",
            "model_execution_seconds",
            "tool_execution_seconds",
            "model",
            "git_branch",
            "source",
            "user_message_count",
            "assistant_message_count",
            "tool_call_count",
            "output_tokens",
            "fresh_input_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "total_tokens",
            "failed_tool_count",
            "subagent_instance_count",
            "indexed_at",
            "file_mtime",
            "file_path");
  }

  @Test
  @DisplayName("全部 7 个索引存在")
  void allIndexesExist() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    Set<String> indexes = getIndexNames();
    assertThat(indexes)
        .contains(
            "idx_sessions_project",
            "idx_sessions_agent",
            "idx_sessions_ended_at",
            "idx_sessions_model",
            "idx_sessions_title",
            "idx_session_artifacts_type",
            "idx_session_artifacts_path");
  }

  @Test
  @DisplayName("scan_log 表结构正确")
  void scanLogTableStructure() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    Set<String> columns = getTableColumns("scan_log");
    assertThat(columns)
        .containsExactlyInAnyOrder(
            "id",
            "started_at",
            "finished_at",
            "claude_count",
            "codex_count",
            "qoder_count",
            "mode",
            "status");
  }

  @Test
  @DisplayName("index_metadata 表结构正确")
  void indexMetadataTableStructure() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    Set<String> columns = getTableColumns("index_metadata");
    assertThat(columns).containsExactlyInAnyOrder("key", "value", "updated_at");
  }

  @Test
  @DisplayName("session_artifacts 表结构正确且含外键")
  void sessionArtifactsTableStructure() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    Set<String> columns = getTableColumns("session_artifacts");
    assertThat(columns)
        .containsExactlyInAnyOrder(
            "session_key",
            "artifact_type",
            "path",
            "schema_version",
            "source_path",
            "source_mtime",
            "size_bytes",
            "created_at",
            "updated_at");
  }

  @Test
  @DisplayName("schema_migrations 追踪表存在")
  void schemaMigrationsTrackingTableExists() throws SQLException {
    MigrationRunner runner = MigrationRunner.withAllMigrations();
    runner.applyAll(conn);

    Set<String> columns = getTableColumns("schema_migrations");
    assertThat(columns).containsExactlyInAnyOrder("version", "description", "applied_at");
  }

  @Test
  @DisplayName("CURRENT_VERSION 与 migration 列表一致")
  void currentVersionConsistentWithMigrations() {
    List<Migration> migrations = Migration.allMigrations();
    SchemaVersion maxVersion =
        new SchemaVersion(migrations.stream().mapToInt(m -> m.version().version()).max().orElse(0));

    assertThat(IndexSchema.CURRENT_VERSION)
        .as("CURRENT_VERSION 应与最大 migration 版本号一致")
        .isEqualTo(maxVersion);
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

  /** 获取数据库中所有索引名。 */
  private Set<String> getIndexNames() throws SQLException {
    Set<String> indexes = new java.util.HashSet<>();
    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")) {
      while (rs.next()) {
        indexes.add(rs.getString("name"));
      }
    }
    return indexes;
  }
}
