package com.feipi.session.browser.contracttest.distribution;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.cli.PathResolver;
import com.feipi.session.browser.cli.RuntimePaths;
import com.feipi.session.browser.index.sqlite.DatabaseUpgrader;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 发行可移植性门禁测试。
 *
 * <p>验证发行包在非常规路径和受限权限环境下可正常工作：
 *
 * <ul>
 *   <li>只读安装目录：安装目录设为只读后，数据目录仍可写入。
 *   <li>路径含空格和非 ASCII 字符：所有路径解析和目录创建正常。
 *   <li>升级崩溃/回滚：升级失败后可从备份恢复。
 * </ul>
 *
 * <p>校验放置：路径解析在 {@link PathResolver} 边界执行一次； 目录创建和权限检查在 {@link RuntimePaths#ensureDirectories()}
 * 边界执行一次。
 */
@DisplayName("发行可移植性门禁")
class PortabilityGateTest {

  @TempDir Path tempDir;

  /**
   * 只读安装目录场景。
   *
   * <p>模拟清洁机上安装目录为只读（例如 /opt 或 /Applications）， 数据目录位于用户主目录下可写区域。
   */
  @Nested
  @DisplayName("只读安装目录")
  class ReadOnlyInstallDirectory {

    @Test
    @DisplayName("安装目录只读时，数据目录仍可创建和写入")
    void readOnlyInstallDataDirStillWritable() throws IOException {
      // 模拟只读安装目录
      Path installDir = tempDir.resolve("opt").resolve("session-browser");
      Files.createDirectories(installDir);
      installDir.toFile().setWritable(false);

      // 数据目录位于可写区域
      Path dataDir = tempDir.resolve("user-data").resolve("session-browser");
      RuntimePaths paths =
          new RuntimePaths(dataDir, dataDir.resolve("logs"), dataDir.resolve("cache"));

      try {
        paths.ensureDirectories();

        assertThat(paths.dataDir()).isDirectory();
        assertThat(paths.logDir()).isDirectory();
        assertThat(paths.cacheDir()).isDirectory();

        // 数据目录可写
        Path probe = paths.dataDir().resolve(".write-test");
        Files.writeString(probe, "test");
        assertThat(probe).hasContent("test");
        Files.deleteIfExists(probe);
      } finally {
        installDir.toFile().setWritable(true);
      }
    }

    @Test
    @DisplayName("只读安装目录不影响路径解析")
    void readOnlyInstallDoesNotAffectPathResolution() {
      Path explicitDataDir = tempDir.resolve("data");
      Path result = PathResolver.resolveDataDir(explicitDataDir.toString(), "INDEX_DIR");
      assertThat(result).isEqualTo(explicitDataDir);
    }

    @Test
    @DisplayName("数据目录不可写时 ensureDirectories 明确失败")
    void unwritableDataDirFailsExplicitly() throws IOException {
      Path dataDir = tempDir.resolve("readonly-data");
      Files.createDirectories(dataDir);
      boolean writableChanged = dataDir.toFile().setWritable(false);
      if (!writableChanged || Files.isWritable(dataDir)) {
        // 某些环境（如 root 用户）无法限制写权限，跳过
        return;
      }

      try {
        RuntimePaths paths =
            new RuntimePaths(dataDir, tempDir.resolve("logs"), tempDir.resolve("cache"));

        assertThatThrownBy(paths::ensureDirectories).isInstanceOf(IOException.class);
      } finally {
        dataDir.toFile().setWritable(true);
      }
    }
  }

  /**
   * 路径含空格和非 ASCII 字符场景。
   *
   * <p>模拟 Windows 用户目录含空格（如 "C:\Users\John Doe"）或非 ASCII 字符（如中文用户名）。
   */
  @Nested
  @DisplayName("路径含空格和非 ASCII 字符")
  class SpaceAndNonAsciiPaths {

    @Test
    @DisplayName("安装路径含空格时路径解析正确")
    void spaceInInstallPath() throws IOException {
      Path base = tempDir.resolve("Program Files").resolve("session-browser");
      Path dataDir = base.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir, base.resolve("logs"), base.resolve("cache"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
      assertThat(paths.dbPath()).isAbsolute();
      assertThat(paths.pidFile()).isAbsolute();
    }

    @Test
    @DisplayName("安装路径含中文用户名时路径解析正确")
    void chineseUserDir() throws IOException {
      Path base = tempDir.resolve("用户").resolve("会话浏览器");
      Path dataDir = base.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir, base.resolve("logs"), base.resolve("cache"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
      assertThat(paths.dbPath().toString()).contains("用户");
    }

    @Test
    @DisplayName("安装路径含日文和韩文字符时路径解析正确")
    void japaneseAndKoreanUserDir() throws IOException {
      Path base = tempDir.resolve("テスト").resolve("데이터");
      Path dataDir = base.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir, base.resolve("logs"), base.resolve("cache"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
    }

    @Test
    @DisplayName("多层嵌套空格和 Unicode 路径")
    void nestedSpaceAndUnicodePath() throws IOException {
      Path base = tempDir.resolve("my app").resolve("données").resolve("缓存");
      Path dataDir = base.resolve("data");
      RuntimePaths paths = new RuntimePaths(dataDir, base.resolve("logs"), base.resolve("cache"));

      paths.ensureDirectories();

      assertThat(paths.dataDir()).isDirectory();
      assertThat(paths.artifactDir()).isDirectory();
      assertThat(paths.backupDir()).isDirectory();
    }
  }

  /**
   * 升级崩溃和回滚场景。
   *
   * <p>模拟升级过程中崩溃（如进程被 kill、磁盘满），验证可从备份恢复。
   */
  @Nested
  @DisplayName("升级崩溃与回滚")
  class UpgradeCrashRollback {

    @Test
    @DisplayName("升级前自动创建备份，崩溃后可从备份恢复")
    void backupCreatedBeforeUpgradeRecoverable() throws Exception {
      Path dbPath = tempDir.resolve("index.sqlite");
      Path backupDir = tempDir.resolve("backups");

      // 创建有效数据库
      createValidDatabase(dbPath);

      // 升级（会自动创建备份）
      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);

      // 验证备份存在
      assertThat(backupDir).isDirectory();
      try (var stream = Files.list(backupDir)) {
        assertThat(stream).isNotEmpty();
      }

      // 模拟崩溃后从备份恢复
      Path backupFile = findLatestBackup(backupDir);
      assertThat(backupFile).isNotNull();
      assertThat(backupFile).isRegularFile();

      // 恢复后的数据库可正常连接
      try (Connection conn = openConnection(backupFile)) {
        assertThat(conn.isValid(5)).isTrue();
      }
    }

    @Test
    @DisplayName("重复升级幂等，不会产生多个备份")
    void repeatedUpgradeIdempotent() throws Exception {
      Path dbPath = tempDir.resolve("index.sqlite");
      Path backupDir = tempDir.resolve("backups");

      createValidDatabase(dbPath);

      DatabaseUpgrader upgrader = DatabaseUpgrader.withDefaults("0.4", backupDir);
      upgrader.upgrade(dbPath);

      int backupCountAfterFirst;
      try (var stream = Files.list(backupDir)) {
        backupCountAfterFirst = (int) stream.count();
      }

      // 重复升级
      upgrader.upgrade(dbPath);
      upgrader.upgrade(dbPath);

      int backupCountAfterRepeated;
      try (var stream = Files.list(backupDir)) {
        backupCountAfterRepeated = (int) stream.count();
      }

      // 幂等升级不应产生额外备份
      assertThat(backupCountAfterRepeated).isEqualTo(backupCountAfterFirst);
    }
  }

  // ===== 辅助方法 =====

  private void createValidDatabase(Path dbPath) throws SQLException {
    try (Connection conn = openConnection(dbPath)) {
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(conn);
    }
  }

  private Connection openConnection(Path db) throws SQLException {
    Connection conn = DriverManager.getConnection("jdbc:sqlite:" + db.toAbsolutePath());
    SqliteTestHelper.configureConnection(conn);
    return conn;
  }

  private Path findLatestBackup(Path backupDir) throws IOException {
    try (var stream = Files.list(backupDir)) {
      return stream
          .filter(Files::isRegularFile)
          .filter(p -> p.toString().endsWith(".sqlite") || p.toString().endsWith(".db"))
          .findFirst()
          .orElse(null);
    }
  }
}
