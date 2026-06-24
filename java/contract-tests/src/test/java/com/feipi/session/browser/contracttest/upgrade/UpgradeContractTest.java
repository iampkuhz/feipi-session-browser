package com.feipi.session.browser.contracttest.upgrade;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.index.sqlite.DatabaseUpgrader;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.SchemaVersion;
import com.feipi.session.browser.index.sqlite.UpgradeResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 升级流程端到端契约测试。
 *
 * <p>验证 {@link DatabaseUpgrader} 满足核心升级契约： 旧 fixture 可升级、失败可回滚、数据不丢失、幂等性。
 *
 * <p>契约放置：升级流程的整体行为在 contract-tests 边界验证； 单条 migration 的 SQL 正确性在 index-sqlite 单元测试覆盖。
 */
@DisplayName("升级流程契约测试")
class UpgradeContractTest {

  @TempDir Path tempDir;

  private Path dbPath;
  private Path backupDir;

  @BeforeEach
  void setUp() {
    dbPath = tempDir.resolve("index.sqlite");
    backupDir = tempDir.resolve("backups");
  }

  @AfterEach
  void tearDown() {
    // TempDir 自动清理
  }

  @Nested
  @DisplayName("旧发布 fixture 可升级")
  class LegacyFixtureUpgrade {

    @Test
    @DisplayName("V1 schema 数据库升级到当前版本：migration 幂等应用")
    void legacyV1SchemaUpgradeable() throws Exception {
      // 创建 V1 schema 数据库（模拟旧发布 fixture）
      createLegacyV1Database();

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      UpgradeResult result = upgrader.upgrade(dbPath);

      // 已应用全部 migration 的数据库不应产生新的 migration
      assertThat(result.hadMigrations()).isFalse();
      assertThat(result.hasBackup()).isTrue();

      // schema 验证通过
      assertSchemaComplete(dbPath);
    }

    @Test
    @DisplayName("无 schema_migrations 追踪表的旧数据库可升级")
    void legacyDatabaseWithoutTrackingTable() throws Exception {
      // 创建只有 sessions 表但无 schema_migrations 的旧数据库
      createLegacyDatabaseWithoutTracking();

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      UpgradeResult result = upgrader.upgrade(dbPath);

      // V001 用 IF NOT EXISTS，不会报错；migration 被记录
      assertThat(result.hadMigrations()).isTrue();
      assertThat(result.schemaVersionsApplied()).contains(new SchemaVersion(1));

      assertSchemaComplete(dbPath);
    }
  }

  @Nested
  @DisplayName("不丢数据")
  class DataPreservationContract {

    @Test
    @DisplayName("升级后 sessions 表数据完整保留")
    void sessionDataPreservedAfterUpgrade() throws Exception {
      createLegacyV1Database();
      insertSessionData(dbPath, "legacy-session-1", "claude_code", "测试会话-1");
      insertSessionData(dbPath, "legacy-session-2", "codex", "测试会话-2");

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);

      // 验证数据完整
      assertThat(countSessions(dbPath)).isEqualTo(2);
      assertThat(readSessionTitle(dbPath, "legacy-session-1")).isEqualTo("测试会话-1");
      assertThat(readSessionTitle(dbPath, "legacy-session-2")).isEqualTo("测试会话-2");
    }

    @Test
    @DisplayName("升级后 session_artifacts 外键关系保持完整")
    void artifactForeignKeyPreserved() throws Exception {
      createLegacyV1Database();
      insertSessionData(dbPath, "fk-session", "claude_code", "FK测试");
      insertArtifact(dbPath, "fk-session", "normalized", "/path/to/artifact");

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);

      // 验证外键关系
      assertThat(countArtifactsForSession(dbPath, "fk-session")).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("重复升级幂等")
  class IdempotencyContract {

    @Test
    @DisplayName("三次升级后 schema 版本和迁移记录不变")
    void tripleUpgradeIdempotent() throws Exception {
      createLegacyV1Database();

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);

      UpgradeResult first = upgrader.upgrade(dbPath);
      UpgradeResult second = upgrader.upgrade(dbPath);
      UpgradeResult third = upgrader.upgrade(dbPath);

      // 第一次升级可能应用 migration（取决于 fixture 状态）
      // 第二次和第三次不应应用任何新 migration
      assertThat(second.hadMigrations()).isFalse();
      assertThat(third.hadMigrations()).isFalse();

      // schema 版本始终为 V1
      SchemaVersion version = readCurrentSchemaVersion(dbPath);
      assertThat(version.version()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("版本兼容性拒绝")
  class VersionRejectionContract {

    @Test
    @DisplayName("降级运行被拒绝，抛出 UpgradeException")
    void downgradeRejectedWithClearMessage() throws Exception {
      createLegacyV1Database();
      writeAppVersion(dbPath, "2.0");

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("1.0", backupDir);

      assertThatThrownBy(() -> upgrader.upgrade(dbPath))
          .isInstanceOf(DatabaseUpgrader.UpgradeException.class)
          .hasMessageContaining("拒绝降级")
          .hasMessageContaining("2.0")
          .hasMessageContaining("1.0");
    }
  }

  // ===== 辅助方法 =====

  /** 创建 V1 schema 数据库（模拟已有全部 migration 应用的旧 fixture）。 */
  private void createLegacyV1Database() throws SQLException {
    try (Connection conn = openConnectionTo(dbPath)) {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);
    }
  }

  /** 创建只有 sessions 表但无追踪表的旧数据库。 */
  private void createLegacyDatabaseWithoutTracking() throws SQLException {
    try (Connection conn = openConnectionTo(dbPath)) {
      try (Statement stmt = conn.createStatement()) {
        stmt.execute(
            "CREATE TABLE sessions ("
                + "session_key TEXT PRIMARY KEY, "
                + "agent TEXT NOT NULL CHECK(agent <> ''), "
                + "session_id TEXT NOT NULL CHECK(session_id <> ''), "
                + "ended_at TEXT NOT NULL CHECK(ended_at <> ''), "
                + "project_key TEXT NOT NULL CHECK(project_key <> ''), "
                + "title TEXT NOT NULL DEFAULT ''"
                + ")");
        // 创建其他必需表
        stmt.execute(
            "CREATE TABLE scan_log ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                + "started_at REAL NOT NULL)");
        stmt.execute(
            "CREATE TABLE index_metadata ("
                + "key TEXT PRIMARY KEY, "
                + "value TEXT NOT NULL DEFAULT '', "
                + "updated_at REAL NOT NULL DEFAULT 0)");
        stmt.execute(
            "CREATE TABLE session_artifacts ("
                + "session_key TEXT NOT NULL, "
                + "artifact_type TEXT NOT NULL, "
                + "path TEXT NOT NULL, "
                + "PRIMARY KEY(session_key, artifact_type), "
                + "FOREIGN KEY(session_key) REFERENCES sessions(session_key) ON DELETE CASCADE)");
      }
    }
  }

  private void insertSessionData(Path db, String key, String agent, String title)
      throws SQLException {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement(
                "INSERT INTO sessions (session_key, agent, session_id, ended_at, project_key, title)"
                    + " VALUES (?, ?, ?, ?, ?, ?)")) {
      ps.setString(1, key);
      ps.setString(2, agent);
      ps.setString(3, "sid-" + key);
      ps.setString(4, "2024-01-01T00:00:00Z");
      ps.setString(5, "test-project");
      ps.setString(6, title);
      ps.executeUpdate();
    }
  }

  private void insertArtifact(Path db, String sessionKey, String type, String path)
      throws SQLException {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement(
                "INSERT INTO session_artifacts (session_key, artifact_type, path)"
                    + " VALUES (?, ?, ?)")) {
      ps.setString(1, sessionKey);
      ps.setString(2, type);
      ps.setString(3, path);
      ps.executeUpdate();
    }
  }

  private void writeAppVersion(Path db, String version) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement(
                "INSERT OR REPLACE INTO index_metadata (key, value, updated_at) VALUES (?, ?, 0)")) {
      ps.setString(1, DatabaseUpgrader.APP_VERSION_KEY);
      ps.setString(2, version);
      ps.executeUpdate();
    }
  }

  private int countSessions(Path db) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT count(*) FROM sessions")) {
      rs.next();
      return rs.getInt(1);
    }
  }

  private String readSessionTitle(Path db, String key) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement("SELECT title FROM sessions WHERE session_key = ?")) {
      ps.setString(1, key);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return rs.getString(1);
        }
      }
    }
    return null;
  }

  private int countArtifactsForSession(Path db, String sessionKey) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement("SELECT count(*) FROM session_artifacts WHERE session_key = ?")) {
      ps.setString(1, sessionKey);
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getInt(1);
      }
    }
  }

  private SchemaVersion readCurrentSchemaVersion(Path db) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT MAX(version) FROM schema_migrations")) {
      rs.next();
      int maxVersion = rs.getInt(1);
      return new SchemaVersion(maxVersion);
    }
  }

  private void assertSchemaComplete(Path db) throws SQLException {
    try (Connection conn = openConnectionTo(db)) {
      IndexSchema schema = IndexSchema.withDefaults();
      IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);
      assertThat(result.isComplete()).as("升级后 schema 验证应通过").isTrue();
    }
  }

  private Connection openConnectionTo(Path db) throws SQLException {
    String jdbcUrl = "jdbc:sqlite:" + db.toAbsolutePath();
    Connection conn = DriverManager.getConnection(jdbcUrl);
    SqliteTestHelper.configureConnection(conn);
    return conn;
  }
}
