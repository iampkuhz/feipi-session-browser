package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.io.IOException;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link DatabaseUpgrader} 升级编排器测试。 */
@DisplayName("DatabaseUpgrader 测试")
class DatabaseUpgraderTest {

  @TempDir Path tempDir;

  private Path dbPath;
  private Path backupDir;

  @BeforeEach
  void setUp() {
    dbPath = tempDir.resolve("test.sqlite");
    backupDir = tempDir.resolve("backups");
  }

  @Nested
  @DisplayName("全新数据库创建")
  class FreshDatabase {

    @Test
    @DisplayName("数据库不存在时创建完整 schema，无备份")
    void createSchemaOnFreshDatabase() {
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);

      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.hadMigrations()).isTrue();
      assertThat(result.hasBackup()).isFalse();
      assertThat(result.versionChanged()).isTrue();
      assertThat(result.appVersionRecorded()).isEqualTo("0.4");
      assertThat(Files.exists(dbPath)).isTrue();

      // 验证 schema 完整
      assertSchemaComplete(dbPath);
    }

    @Test
    @DisplayName("空应用版本时跳过版本追踪")
    void nullAppVersionSkipsTracking() {
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults(null, backupDir);

      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.appVersionRecorded()).isNull();
      assertThat(readMetadataValue(dbPath, DatabaseUpgrader.APP_VERSION_KEY)).isNull();
    }

    @Test
    @DisplayName("空字符串应用版本时跳过版本追踪")
    void blankAppVersionSkipsTracking() {
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("  ", backupDir);

      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.appVersionRecorded()).isNull();
    }
  }

  @Nested
  @DisplayName("幂等升级")
  class IdempotentUpgrade {

    @Test
    @DisplayName("第二次升级不应用新 migration，创建备份")
    void secondUpgradeIsIdempotent() {
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);

      // 首次升级
      UpgradeResult first = upgrader.upgrade(dbPath);
      assertThat(first.hadMigrations()).isTrue();

      // 第二次升级
      UpgradeResult second = upgrader.upgrade(dbPath);
      assertThat(second.hadMigrations()).isFalse();
      assertThat(second.versionChanged()).isFalse();
      assertThat(second.hasBackup()).isTrue();
      assertThat(Files.exists(second.backupPath())).isTrue();
    }

    @Test
    @DisplayName("三次升级仍然幂等")
    void thirdUpgradeStillIdempotent() {
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);
      upgrader.upgrade(dbPath);

      UpgradeResult third = upgrader.upgrade(dbPath);
      assertThat(third.hadMigrations()).isFalse();
      assertThat(third.hasBackup()).isTrue();
    }
  }

  @Nested
  @DisplayName("备份创建与管理")
  class BackupManagement {

    @Test
    @DisplayName("已存在数据库升级时创建备份文件")
    void backupCreatedForExistingDatabase() throws Exception {
      // 先创建数据库
      createMinimalDatabase();

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.hasBackup()).isTrue();
      assertThat(Files.exists(result.backupPath())).isTrue();
      assertThat(result.backupPath().getFileName().toString())
          .startsWith(DatabaseUpgrader.BACKUP_FILE_PREFIX);
    }

    @Test
    @DisplayName("备份保留上限：超过 3 份时清理最旧的")
    void backupRetentionPrunesOld() throws Exception {
      createMinimalDatabase();

      DatabaseUpgrader upgrader =
          new DatabaseUpgrader(IndexSchema.withDefaults(), "0.4", backupDir, 3);

      // 创建 4 次升级，产生 4 个备份
      upgrader.upgrade(dbPath);
      Thread.sleep(1100); // 确保时间戳不同
      upgrader.upgrade(dbPath);
      Thread.sleep(1100);
      upgrader.upgrade(dbPath);
      Thread.sleep(1100);
      upgrader.upgrade(dbPath);

      // 备份数应不超过 3
      int backupCount = countBackups();
      assertThat(backupCount).isLessThanOrEqualTo(3);
    }
  }

  @Nested
  @DisplayName("版本兼容性检查")
  class VersionCompatibility {

    @Test
    @DisplayName("降级被拒绝：DB 中版本高于当前版本")
    void downgradeRejected() throws Exception {
      // 创建数据库并写入高版本
      createMinimalDatabase();
      writeAppVersionToDb(dbPath, "1.0");

      // 用低版本升级
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.3", backupDir);

      assertThatThrownBy(() -> upgrader.upgrade(dbPath))
          .isInstanceOf(DatabaseUpgrader.UpgradeException.class)
          .hasMessageContaining("拒绝降级");
    }

    @Test
    @DisplayName("相同版本允许升级")
    void sameVersionAllowed() throws Exception {
      createMinimalDatabase();
      writeAppVersionToDb(dbPath, "0.4");

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.hasBackup()).isTrue();
    }

    @Test
    @DisplayName("更高版本允许升级")
    void higherVersionAllowed() throws Exception {
      createMinimalDatabase();
      writeAppVersionToDb(dbPath, "0.3");

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.5", backupDir);
      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.hasBackup()).isTrue();
      assertThat(result.appVersionRecorded()).isEqualTo("0.5");
    }

    @Test
    @DisplayName("DB 中无版本记录时允许升级")
    void noExistingVersionAllowed() throws Exception {
      createMinimalDatabase();

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      UpgradeResult result = upgrader.upgrade(dbPath);

      assertThat(result.hasBackup()).isTrue();
    }
  }

  @Nested
  @DisplayName("数据保留")
  class DataPreservation {

    @Test
    @DisplayName("升级后现有数据不丢失")
    void dataPreservedAfterUpgrade() throws Exception {
      // 创建数据库并插入数据
      createMinimalDatabase();
      insertTestData(dbPath);

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);

      // 验证数据完整
      assertTestDataPresent(dbPath);
    }

    @Test
    @DisplayName("重复升级后数据仍然完整")
    void dataPreservedAfterMultipleUpgrades() throws Exception {
      createMinimalDatabase();
      insertTestData(dbPath);

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);
      upgrader.upgrade(dbPath);
      upgrader.upgrade(dbPath);

      assertTestDataPresent(dbPath);
    }
  }

  @Nested
  @DisplayName("应用版本追踪")
  class AppVersionTracking {

    @Test
    @DisplayName("升级后应用版本写入 index_metadata")
    void appVersionWrittenToMetadata() {
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);

      String version = readMetadataValue(dbPath, DatabaseUpgrader.APP_VERSION_KEY);
      assertThat(version).isEqualTo("0.4");
    }

    @Test
    @DisplayName("更新版本后 index_metadata 记录新版本")
    void appVersionUpdated() {
      DatabaseUpgrader upgrader04 = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader04.upgrade(dbPath);

      DatabaseUpgrader upgrader05 = DatabaseUpgrader.withDefaults("0.5", backupDir);
      upgrader05.upgrade(dbPath);

      String version = readMetadataValue(dbPath, DatabaseUpgrader.APP_VERSION_KEY);
      assertThat(version).isEqualTo("0.5");
    }
  }

  @Nested
  @DisplayName("UpgradeResult record")
  class UpgradeResultRecord {

    @Test
    @DisplayName("hadMigrations 正确反映应用状态")
    void hadMigrationsReflectsState() {
      UpgradeResult withMigrations =
          new UpgradeResult(List.of(new SchemaVersion(1)), null, true, "0.4");
      assertThat(withMigrations.hadMigrations()).isTrue();

      UpgradeResult noMigrations = new UpgradeResult(List.of(), null, false, "0.4");
      assertThat(noMigrations.hadMigrations()).isFalse();
    }

    @Test
    @DisplayName("hasBackup 正确反映备份状态")
    void hasBackupReflectsState() {
      UpgradeResult withBackup =
          new UpgradeResult(List.of(), Path.of("/tmp/backup.sqlite"), false, "0.4");
      assertThat(withBackup.hasBackup()).isTrue();

      UpgradeResult noBackup = new UpgradeResult(List.of(), null, false, "0.4");
      assertThat(noBackup.hasBackup()).isFalse();
    }

    @Test
    @DisplayName("schemaVersionsApplied 列表不可变")
    void appliedVersionsListIsImmutable() {
      UpgradeResult result = new UpgradeResult(List.of(new SchemaVersion(1)), null, true, "0.4");
      assertThatThrownBy(() -> result.schemaVersionsApplied().add(new SchemaVersion(2)))
          .isInstanceOf(UnsupportedOperationException.class);
    }
  }

  @Nested
  @DisplayName("参数校验")
  class ParameterValidation {

    @Test
    @DisplayName("backupRetention < 1 抛出 IllegalArgumentException")
    void invalidRetentionThrows() {
      assertThatThrownBy(
              () -> new DatabaseUpgrader(IndexSchema.withDefaults(), "0.4", backupDir, 0))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("backupRetention");
    }

    @Test
    @DisplayName("null schema 抛出 NullPointerException")
    void nullSchemaThrows() {
      assertThatThrownBy(() -> new DatabaseUpgrader(null, "0.4", backupDir, 3))
          .isInstanceOf(NullPointerException.class);
    }

    @Test
    @DisplayName("null backupDir 抛出 NullPointerException")
    void nullBackupDirThrows() {
      assertThatThrownBy(() -> new DatabaseUpgrader(IndexSchema.withDefaults(), "0.4", null, 3))
          .isInstanceOf(NullPointerException.class);
    }
  }

  // ===== 辅助方法 =====

  /** 创建最小可用数据库（含 schema 和基本数据表）。 */
  private void createMinimalDatabase() throws SQLException {
    try (Connection conn = openConnectionTo(dbPath)) {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);
    }
  }

  /** 插入测试数据。 */
  private void insertTestData(Path db) throws SQLException {
    try (Connection conn = openConnectionTo(db)) {
      try (PreparedStatement ps =
          conn.prepareStatement(
              "INSERT INTO sessions (session_key, agent, session_id, ended_at, project_key, title)"
                  + " VALUES (?, ?, ?, ?, ?, ?)")) {
        ps.setString(1, "test-key-1");
        ps.setString(2, "claude_code");
        ps.setString(3, "session-1");
        ps.setString(4, "2024-01-01T00:00:00Z");
        ps.setString(5, "test-project");
        ps.setString(6, "测试会话");
        ps.executeUpdate();
      }
      try (PreparedStatement ps =
          conn.prepareStatement(
              "INSERT INTO sessions (session_key, agent, session_id, ended_at, project_key)"
                  + " VALUES (?, ?, ?, ?, ?)")) {
        ps.setString(1, "test-key-2");
        ps.setString(2, "codex");
        ps.setString(3, "session-2");
        ps.setString(4, "2024-01-02T00:00:00Z");
        ps.setString(5, "test-project-2");
        ps.executeUpdate();
      }
    }
  }

  /** 验证测试数据完整性。 */
  private void assertTestDataPresent(Path db) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        Statement stmt = conn.createStatement();
        ResultSet rs = stmt.executeQuery("SELECT count(*) FROM sessions")) {
      rs.next();
      assertThat(rs.getInt(1)).isEqualTo(2);
    }
    try (Connection conn = openConnectionTo(db);
        Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery("SELECT title FROM sessions WHERE session_key = 'test-key-1'")) {
      rs.next();
      assertThat(rs.getString(1)).isEqualTo("测试会话");
    }
  }

  /** 验证 schema 完整性。 */
  private void assertSchemaComplete(Path db) {
    try (Connection conn = openConnectionTo(db)) {
      IndexSchema schema = IndexSchema.withDefaults();
      IndexSchema.SchemaValidationResult result = schema.validateSchema(conn);
      assertThat(result.isComplete()).isTrue();
    } catch (SQLException e) {
      throw new AssertionError("schema 验证失败", e);
    }
  }

  /** 向 index_metadata 写入应用版本。 */
  private void writeAppVersionToDb(Path db, String version) throws SQLException {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement(
                "INSERT OR REPLACE INTO index_metadata (key, value, updated_at) VALUES (?, ?, 0)")) {
      ps.setString(1, DatabaseUpgrader.APP_VERSION_KEY);
      ps.setString(2, version);
      ps.executeUpdate();
    }
  }

  /** 从 index_metadata 读取指定 key 的值。 */
  private String readMetadataValue(Path db, String key) {
    try (Connection conn = openConnectionTo(db);
        PreparedStatement ps =
            conn.prepareStatement("SELECT value FROM index_metadata WHERE key = ?")) {
      ps.setString(1, key);
      try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
          return rs.getString(1);
        }
      }
    } catch (SQLException e) {
      return null;
    }
    return null;
  }

  /** 统计备份目录中的备份文件数量。 */
  private int countBackups() throws IOException {
    if (!Files.isDirectory(backupDir)) {
      return 0;
    }
    int count = 0;
    try (DirectoryStream<Path> stream =
        Files.newDirectoryStream(
            backupDir,
            DatabaseUpgrader.BACKUP_FILE_PREFIX + "*" + DatabaseUpgrader.BACKUP_FILE_SUFFIX)) {
      for (Path ignored : stream) {
        count++;
      }
    }
    return count;
  }

  /** 打开指向指定文件数据库的连接。 */
  private Connection openConnectionTo(Path db) throws SQLException {
    String jdbcUrl = "jdbc:sqlite:" + db.toAbsolutePath();
    Connection conn = DriverManager.getConnection(jdbcUrl);
    SqliteTestHelper.configureConnection(conn);
    return conn;
  }
}
