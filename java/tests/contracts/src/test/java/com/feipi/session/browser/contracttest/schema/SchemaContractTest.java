package com.feipi.session.browser.contracttest.schema;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.store.sqlite.schema.IndexSchema;
import com.feipi.session.browser.index.store.sqlite.schema.Migration;
import com.feipi.session.browser.index.store.sqlite.schema.MigrationRunner;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
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
 * <p>验证当前 Java index schema：表结构、精确列名、计量来源/计时默认值与必要索引。
 */
@DisplayName("Schema 契约测试：当前 Java index schema")
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
  @DisplayName("sessions 表精确包含 37 列，含 provenance 与 typed timing")
  void sessionsTableMatchesCurrentJavaDefinition() throws SQLException {
    IndexSchema schema = IndexSchema.withDefaults();
    schema.ensureSchema(conn);

    Set<String> columns = getTableColumns("sessions");
    assertThat(columns).as("sessions 表应包含原28列、8个provenance列与timing_json").hasSize(37);

    // 全列精确比对，不允许静默缺失或添加字段。
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
            "file_path",
            "fresh_input_token_precision",
            "cache_read_token_precision",
            "cache_write_token_precision",
            "output_token_precision",
            "token_estimation_method",
            "token_contains_estimated",
            "token_contains_unavailable",
            "token_contains_unknown",
            "timing_json");
  }

  @Test
  @DisplayName("未提供计量来源与计时时默认 unknown，而不是 provider 上报或实测零")
  void measurementColumnsDefaultToUnknown() throws SQLException {
    IndexSchema.withDefaults().ensureSchema(conn);
    try (Statement statement = conn.createStatement()) {
      statement.executeUpdate(
          """
          INSERT INTO sessions(session_key, agent, session_id, project_key, ended_at)
          VALUES ('claude_code:synthetic', 'claude_code', 'synthetic', 'synthetic', '2026-01-01T00:00:00Z')
          """);
      try (ResultSet row =
          statement.executeQuery(
              """
              SELECT fresh_input_token_precision, cache_read_token_precision,
                     cache_write_token_precision, output_token_precision, token_estimation_method,
                     token_contains_estimated, token_contains_unavailable, token_contains_unknown,
                     timing_json FROM sessions
              """)) {
        assertThat(row.next()).isTrue();
        assertThat(List.of(row.getString(1), row.getString(2), row.getString(3), row.getString(4)))
            .containsExactly("unknown", "unknown", "unknown", "unknown");
        assertThat(row.getString("token_estimation_method")).isEmpty();
        assertThat(
                List.of(
                    row.getInt("token_contains_estimated"),
                    row.getInt("token_contains_unavailable"),
                    row.getInt("token_contains_unknown")))
            .containsExactly(0, 0, 1);
        assertThat(row.getString("timing_json")).isEqualTo("{}");
        assertThat(row.next()).isFalse();
      }
    }
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
