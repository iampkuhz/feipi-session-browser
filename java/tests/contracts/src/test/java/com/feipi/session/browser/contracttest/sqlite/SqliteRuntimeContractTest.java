package com.feipi.session.browser.contracttest.sqlite;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.ConnectionFactory;
import com.feipi.session.browser.index.sqlite.IndexConnection;
import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.PragmaConfig;
import com.feipi.session.browser.index.sqlite.WriteBatch;
import com.feipi.session.browser.index.sqlite.WriteQueue;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * SQLite 运行时契约测试。
 *
 * <p>验证连接管理、PRAGMA 配置、单 writer 和 schema 集成。
 */
@DisplayName("SQLite 运行时契约：连接、PRAGMA、单 Writer 与 Schema 集成")
class SqliteRuntimeContractTest {

  @Test
  @DisplayName("PRAGMA 默认配置与 Python _get_connection 一致")
  void pragmaDefaultsMatchPython() throws SQLException {
    PragmaConfig config = PragmaConfig.DEFAULTS;
    assertThat(config.journalMode()).isEqualTo("wal");
    assertThat(config.busyTimeoutMs()).isEqualTo(30_000);
    assertThat(config.foreignKeys()).isTrue();
  }

  @Test
  @DisplayName("ConnectionFactory 创建的连接 PRAGMA 验证通过")
  void connectionFactoryPragmaVerified(@TempDir Path tempDir) throws SQLException {
    Path dbFile = tempDir.resolve("contract-pragma.db");
    ConnectionFactory factory =
        new ConnectionFactory("jdbc:sqlite:" + dbFile.toAbsolutePath(), PragmaConfig.DEFAULTS);
    try (Connection conn = factory.create()) {
      assertThat(PragmaConfig.DEFAULTS.verify(conn)).isTrue();
    }
  }

  @Test
  @DisplayName("IndexConnection + Schema 集成：migration 后数据可写可读")
  void indexConnectionWithSchema(@TempDir Path tempDir) throws Exception {
    Path dbFile = tempDir.resolve("contract.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);

    try (IndexConnection ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl)) {
      // 运行 schema migration
      IndexSchema schema = IndexSchema.withDefaults();
      schema.ensureSchema(ic.writerConnection());

      // 通过 WriteQueue 写入数据
      ic.writeQueue()
          .submit(
              c -> {
                try (Statement stmt = c.createStatement()) {
                  stmt.execute(
                      "INSERT INTO sessions (session_key, agent, session_id, ended_at, project_key)"
                          + " VALUES ('test-key', 'claude', 'test-id', '2024-01-01', 'proj1')");
                }
              })
          .get(5, TimeUnit.SECONDS);

      // 验证数据
      try (Statement stmt = writerConn.createStatement();
          ResultSet rs =
              stmt.executeQuery("SELECT agent FROM sessions WHERE session_key = 'test-key'")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getString(1)).isEqualTo("claude");
      }
    }
  }

  @Test
  @DisplayName("单 Writer 保证：WriteQueue 串行执行")
  void singleWriterSerialExecution(@TempDir Path tempDir) throws Exception {
    Path dbFile = tempDir.resolve("writer.db");
    String jdbcUrl = "jdbc:sqlite:" + dbFile.toAbsolutePath();

    Connection writerConn = DriverManager.getConnection(jdbcUrl);
    PragmaConfig.DEFAULTS.apply(writerConn);
    try (Statement stmt = writerConn.createStatement()) {
      stmt.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, seq TEXT)");
    }

    try (IndexConnection ic = IndexConnection.create(writerConn, PragmaConfig.DEFAULTS, jdbcUrl)) {
      WriteQueue queue = ic.writeQueue();

      // 提交 100 个写入
      for (int i = 0; i < 100; i++) {
        final int id = i;
        queue
            .submit(
                c -> {
                  try (Statement stmt = c.createStatement()) {
                    stmt.execute("INSERT INTO test_data VALUES (" + id + ", 'seq-" + id + "')");
                  }
                })
            .get(5, TimeUnit.SECONDS);
      }

      // 验证全部写入成功
      try (Statement stmt = writerConn.createStatement();
          ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_data")) {
        assertThat(rs.next()).isTrue();
        assertThat(rs.getInt(1)).isEqualTo(100);
      }
    }
  }

  @Test
  @DisplayName("WriteBatch 批量大小上限有效")
  void writeBatchLimitEffective() {
    assertThat(WriteBatch.DEFAULT_MAX_ENTRIES).isGreaterThan(0);
    assertThat(WriteBatch.DEFAULT_MAX_ENTRIES).isLessThanOrEqualTo(10_000);
  }

  @Test
  @DisplayName("WriteQueue 默认容量合理")
  void writeQueueDefaultCapacityReasonable() {
    assertThat(WriteQueue.DEFAULT_QUEUE_CAPACITY).isGreaterThan(0);
    assertThat(WriteQueue.DEFAULT_QUEUE_CAPACITY).isLessThanOrEqualTo(256);
  }
}
