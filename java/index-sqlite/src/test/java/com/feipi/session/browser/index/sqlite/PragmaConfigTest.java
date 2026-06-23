package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link PragmaConfig} 测试，覆盖默认值、自定义值、PRAGMA 应用和验证。 */
@DisplayName("PragmaConfig 测试")
class PragmaConfigTest {

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
  @DisplayName("默认值")
  class Defaults {

    @Test
    @DisplayName("默认 PRAGMA 配置值正确")
    void defaultValues() {
      PragmaConfig config = PragmaConfig.DEFAULTS;
      assertThat(config.journalMode()).isEqualTo("wal");
      assertThat(config.synchronous()).isEqualTo("normal");
      assertThat(config.busyTimeoutMs()).isEqualTo(30_000);
      assertThat(config.foreignKeys()).isTrue();
    }
  }

  @Nested
  @DisplayName("自定义配置")
  class Custom {

    @Test
    @DisplayName("自定义配置值正确")
    void customValues() {
      PragmaConfig config = new PragmaConfig("wal", "full", 5000, false);
      assertThat(config.journalMode()).isEqualTo("wal");
      assertThat(config.synchronous()).isEqualTo("full");
      assertThat(config.busyTimeoutMs()).isEqualTo(5000);
      assertThat(config.foreignKeys()).isFalse();
    }

    @Test
    @DisplayName("空 journalMode 抛异常")
    void emptyJournalMode() {
      assertThatThrownBy(() -> new PragmaConfig("", "normal", 30000, true))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("无效 journalMode 抛异常")
    void invalidJournalMode() {
      assertThatThrownBy(() -> new PragmaConfig("invalid", "normal", 30000, true))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("空 synchronous 抛异常")
    void emptySynchronous() {
      assertThatThrownBy(() -> new PragmaConfig("wal", "", 30000, true))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("无效 synchronous 抛异常")
    void invalidSynchronous() {
      assertThatThrownBy(() -> new PragmaConfig("wal", "invalid", 30000, true))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("负 busyTimeout 抛异常")
    void negativeBusyTimeout() {
      assertThatThrownBy(() -> new PragmaConfig("wal", "normal", -1, true))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("busyTimeout 为 0 合法")
    void zeroBusyTimeout() {
      PragmaConfig config = new PragmaConfig("wal", "normal", 0, true);
      assertThat(config.busyTimeoutMs()).isZero();
    }
  }

  @Nested
  @DisplayName("PRAGMA 应用")
  class Apply {

    @Test
    @DisplayName("apply 在文件数据库上设置 WAL 模式")
    void applyJournalMode(@TempDir Path tempDir) throws SQLException {
      Path dbFile = tempDir.resolve("pragma-test.db");
      try (Connection fileConn =
          DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath())) {
        PragmaConfig config = new PragmaConfig("wal", "normal", 30000, true);
        config.apply(fileConn);

        try (Statement stmt = fileConn.createStatement();
            ResultSet rs = stmt.executeQuery("PRAGMA journal_mode")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getString(1).toLowerCase()).isEqualTo("wal");
        }
      }
    }

    @Test
    @DisplayName("apply 设置 busy_timeout")
    void applyBusyTimeout() throws SQLException {
      PragmaConfig config = new PragmaConfig("wal", "normal", 15000, true);
      config.apply(conn);

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("PRAGMA busy_timeout")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(15000);
      }
    }

    @Test
    @DisplayName("apply 设置 foreign_keys ON")
    void applyForeignKeysOn() throws SQLException {
      PragmaConfig config = new PragmaConfig("wal", "normal", 30000, true);
      config.apply(conn);

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("PRAGMA foreign_keys")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(1);
      }
    }

    @Test
    @DisplayName("apply 设置 foreign_keys OFF")
    void applyForeignKeysOff() throws SQLException {
      PragmaConfig config = new PragmaConfig("wal", "normal", 30000, false);
      config.apply(conn);

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("PRAGMA foreign_keys")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(0);
      }
    }

    @Test
    @DisplayName("apply 设置 synchronous")
    void applySynchronous() throws SQLException {
      PragmaConfig config = new PragmaConfig("wal", "full", 30000, true);
      config.apply(conn);

      try (Statement stmt = conn.createStatement();
          ResultSet rs = stmt.executeQuery("PRAGMA synchronous")) {
        assertThat(rs.next()).isTrue();
        // synchronous=full 返回 2
        assertThat(rs.getInt(1)).isEqualTo(2);
      }
    }
  }

  @Nested
  @DisplayName("PRAGMA 验证")
  class Verify {

    @Test
    @DisplayName("默认配置在文件数据库上验证通过")
    void verifyDefaults(@TempDir Path tempDir) throws SQLException {
      Path dbFile = tempDir.resolve("verify-defaults.db");
      try (Connection fileConn =
          DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath())) {
        PragmaConfig config = PragmaConfig.DEFAULTS;
        config.apply(fileConn);
        assertThat(config.verify(fileConn)).isTrue();
      }
    }

    @Test
    @DisplayName("foreign_keys 关闭时在文件数据库上验证通过")
    void verifyForeignKeysOff(@TempDir Path tempDir) throws SQLException {
      Path dbFile = tempDir.resolve("verify-fk-off.db");
      try (Connection fileConn =
          DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath())) {
        PragmaConfig config = new PragmaConfig("wal", "normal", 30000, false);
        config.apply(fileConn);
        assertThat(config.verify(fileConn)).isTrue();
      }
    }

    @Test
    @DisplayName("foreign_keys 不匹配时验证失败")
    void verifyMismatchFails(@TempDir Path tempDir) throws SQLException {
      Path dbFile = tempDir.resolve("verify-mismatch.db");
      try (Connection fileConn =
          DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath())) {
        // 应用默认配置（foreign_keys ON, WAL）
        PragmaConfig.DEFAULTS.apply(fileConn);
        // 用 foreign_keys OFF 的配置验证
        PragmaConfig mismatch = new PragmaConfig("wal", "normal", 30000, false);
        assertThat(mismatch.verify(fileConn)).isFalse();
      }
    }
  }
}
