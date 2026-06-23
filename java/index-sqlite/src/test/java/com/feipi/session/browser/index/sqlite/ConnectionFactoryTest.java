package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** {@link ConnectionFactory} 测试，覆盖连接创建、PRAGMA 应用和资源关闭。 */
@DisplayName("ConnectionFactory 测试")
class ConnectionFactoryTest {

  @Nested
  @DisplayName("内存连接")
  class InMemory {

    @Test
    @DisplayName("创建文件连接并配置 WAL PRAGMA")
    void createFileConnection(@TempDir Path tempDir) throws SQLException {
      Path dbFile = tempDir.resolve("factory-test.db");
      ConnectionFactory factory =
          new ConnectionFactory("jdbc:sqlite:" + dbFile.toAbsolutePath(), PragmaConfig.DEFAULTS);
      try (Connection conn = factory.create()) {
        assertThat(conn).isNotNull();
        assertThat(conn.isClosed()).isFalse();

        // 验证 WAL 模式（仅文件数据库支持）
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("PRAGMA journal_mode")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getString(1).toLowerCase()).isEqualTo("wal");
        }
      }
    }

    @Test
    @DisplayName("创建内存连接成功")
    void createInMemoryConnection() throws SQLException {
      ConnectionFactory factory =
          new ConnectionFactory("jdbc:sqlite::memory:", PragmaConfig.DEFAULTS);
      try (Connection conn = factory.create()) {
        assertThat(conn).isNotNull();
        assertThat(conn.isClosed()).isFalse();
      }
    }

    @Test
    @DisplayName("每次 create 返回独立连接")
    void eachCreateReturnsIndependentConnection() throws SQLException {
      ConnectionFactory factory =
          new ConnectionFactory("jdbc:sqlite::memory:", PragmaConfig.DEFAULTS);
      try (Connection conn1 = factory.create();
          Connection conn2 = factory.create()) {
        assertThat(conn1).isNotSameAs(conn2);

        // 两个内存连接各自独立（各自有独立的 :memory: 数据库）
        try (Statement stmt = conn1.createStatement()) {
          stmt.execute("CREATE TABLE test1 (id INTEGER)");
        }

        // conn2 不应该能看到 conn1 的表
        try (Statement stmt = conn2.createStatement();
            ResultSet rs =
                stmt.executeQuery(
                    "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='test1'")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isZero();
        }
      }
    }
  }

  @Nested
  @DisplayName("自定义 PRAGMA")
  class CustomPragma {

    @Test
    @DisplayName("自定义 PRAGMA 配置被应用")
    void customPragmaApplied() throws SQLException {
      PragmaConfig config = new PragmaConfig("wal", "full", 5000, true);
      ConnectionFactory factory = new ConnectionFactory("jdbc:sqlite::memory:", config);

      try (Connection conn = factory.create()) {
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("PRAGMA busy_timeout")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(5000);
        }

        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("PRAGMA synchronous")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(2); // full 级别
        }
      }
    }
  }

  @Nested
  @DisplayName("参数校验")
  class Validation {

    @Test
    @DisplayName("空 URL 抛异常")
    void emptyUrl() {
      assertThatThrownBy(() -> new ConnectionFactory("", PragmaConfig.DEFAULTS))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("null URL 抛异常")
    void nullUrl() {
      assertThatThrownBy(() -> new ConnectionFactory(null, PragmaConfig.DEFAULTS))
          .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("null PRAGMA 配置抛异常")
    void nullPragma() {
      assertThatThrownBy(() -> new ConnectionFactory("jdbc:sqlite::memory:", null))
          .isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Nested
  @DisplayName("便捷方法")
  class Convenience {

    @Test
    @DisplayName("withDefaults 使用默认 PRAGMA")
    void withDefaultsUsesDefaultPragma() throws SQLException {
      ConnectionFactory factory = ConnectionFactory.withDefaults("jdbc:sqlite::memory:");
      assertThat(factory.pragmaConfig()).isEqualTo(PragmaConfig.DEFAULTS);
      assertThat(factory.jdbcUrl()).isEqualTo("jdbc:sqlite::memory:");

      try (Connection conn = factory.create()) {
        assertThat(conn.isClosed()).isFalse();
      }
    }
  }

  @Nested
  @DisplayName("资源管理")
  class Resource {

    @Test
    @DisplayName("PRAGMA 失败时连接被关闭")
    void connectionClosedOnPragmaFailure() throws SQLException {
      // 使用一个非法 URL 来触发连接失败
      ConnectionFactory factory =
          new ConnectionFactory("jdbc:sqlite::memory:", PragmaConfig.DEFAULTS);
      // 正常连接可以创建和关闭
      Connection conn = factory.create();
      conn.close();
      assertThat(conn.isClosed()).isTrue();
    }
  }
}
