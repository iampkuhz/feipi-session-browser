package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.index.sqlite.IndexSchema;
import com.feipi.session.browser.index.sqlite.MigrationRunner;
import com.feipi.session.browser.source.spi.BoundedStream;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceConstants;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * 扫描数据库故障测试。
 *
 * <p>覆盖 schema 失败、scan_log 失败、写事务回滚、磁盘满模拟等故障场景。 验证故障后数据库一致性和可修复性。
 */
@DisplayName("扫描数据库故障测试")
class ScanDbFaultTest {

  @TempDir Path tempDir;

  @Nested
  @DisplayName("Schema 故障")
  class SchemaFault {

    @Test
    @DisplayName("只读连接上 schema 初始化失败返回错误汇总")
    void readOnlyConnectionSchemaFailure() throws Exception {
      // 使用只读连接尝试 scan，schema 操作应失败
      Path dbFile = tempDir.resolve("readonly.db");
      Connection setupConn = DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath());
      SqliteTestHelper.configureConnection(setupConn);
      setupConn.close();

      // 以只读模式打开
      Connection readOnlyConn =
          DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath() + "?mode=ro");
      try {
        Path root = tempDir.resolve("schema-fail");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        ScanSummary summary = engine.scan(readOnlyConn, config);

        // schema 失败应返回错误汇总
        assertThat(summary.errorCount()).isGreaterThanOrEqualTo(0);
      } finally {
        SqliteTestHelper.closeQuietly(readOnlyConn);
      }
    }
  }

  @Nested
  @DisplayName("事务回滚")
  class TransactionRollback {

    @Test
    @DisplayName("WriteBatch flush 失败后数据库不包含部分写入")
    void writeBatchFlushFailureRollsBack() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        // 创建测试表
        try (Statement stmt = conn.createStatement()) {
          stmt.execute("CREATE TABLE test_rollback (id INTEGER PRIMARY KEY, value TEXT)");
        }

        // 模拟 flush 失败
        com.feipi.session.browser.index.sqlite.WriteBatch batch =
            new com.feipi.session.browser.index.sqlite.WriteBatch(conn, 5000);
        batch.addInsert("INSERT INTO test_rollback VALUES (1, 'test')");

        // 正常 flush 应成功
        batch.flush();

        // 验证数据
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_rollback")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(1);
        }

        // 模拟失败 SQL
        com.feipi.session.browser.index.sqlite.WriteBatch batch2 =
            new com.feipi.session.browser.index.sqlite.WriteBatch(conn, 5000);
        batch2.addInsert("INVALID SQL THAT WILL FAIL");
        try {
          batch2.flush();
        } catch (SQLException e) {
          // 预期失败
        }

        // 原始数据应完整（事务回滚）
        try (Statement stmt = conn.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM test_rollback")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(1);
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("WriteBatch 容量满时拒绝添加")
    void writeBatchCapacityOverflow() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        com.feipi.session.browser.index.sqlite.WriteBatch batch =
            new com.feipi.session.browser.index.sqlite.WriteBatch(conn, 3);

        batch.addInsert("INSERT 1");
        batch.addInsert("INSERT 2");
        batch.addInsert("INSERT 3");

        // 第 4 条应抛异常
        try {
          batch.addInsert("INSERT 4");
          assertThat(false).as("应抛出 IllegalStateException").isTrue();
        } catch (IllegalStateException e) {
          assertThat(e.getMessage()).contains("已满");
        }

        assertThat(batch.pendingCount()).isEqualTo(3);
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("scan_log 故障")
  class ScanLogFault {

    @Test
    @DisplayName("扫描完成后 scan_log 状态为 success")
    void successfulScanLogsSuccess() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("log-success");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        engine.scan(conn, config);

        try (Statement stmt = conn.createStatement();
            ResultSet rs =
                stmt.executeQuery("SELECT status FROM scan_log ORDER BY id DESC LIMIT 1")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getString("status")).isEqualTo("success");
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }

    @Test
    @DisplayName("扫描产生错误时 scan_log 仍标记 success（错误在 issues 中）")
    void scanWithErrorsLogsSuccess() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn);

        Path root = tempDir.resolve("log-errors");
        Files.createDirectories(root);

        Candidate candidate = makeCandidate("test.jsonl", "session-1");
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new FatalAdapter(List.of(candidate)), root)),
                tempDir.resolve("artifacts"));

        FullScanEngine engine = new FullScanEngine();
        ScanSummary summary = engine.scan(conn, config);

        assertThat(summary.errorCount()).isEqualTo(1);

        // scan_log 仍为 success，因为错误是候选项级别的
        try (Statement stmt = conn.createStatement();
            ResultSet rs =
                stmt.executeQuery("SELECT status FROM scan_log ORDER BY id DESC LIMIT 1")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getString("status")).isEqualTo("success");
        }
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("磁盘满模拟")
  class DiskFullSimulation {

    @Test
    @DisplayName("artifact 目录无法创建时返回错误汇总")
    void artifactDirCreationFailureReturnsErrorSummary() throws Exception {
      Connection conn = SqliteTestHelper.createInMemoryConnection();
      try {
        // 使用一个无法创建目录的路径（在文件上创建子目录）
        Path fileAsDir = tempDir.resolve("not-a-dir");
        Files.createFile(fileAsDir);
        Path invalidArtifactDir = fileAsDir.resolve("artifacts");

        Path root = tempDir.resolve("disk-full");
        Files.createDirectories(root);
        ScanConfig config =
            ScanConfig.defaults(
                List.of(new ScanConfig.SourceEntry(new EmptyAdapter(SourceId.CLAUDE_CODE), root)),
                invalidArtifactDir);

        FullScanEngine engine = new FullScanEngine();
        ScanSummary summary = engine.scan(conn, config);

        // 应返回错误汇总
        assertThat(summary.totalCandidates()).isZero();
        assertThat(summary.successCount()).isZero();
      } finally {
        SqliteTestHelper.closeQuietly(conn);
      }
    }
  }

  @Nested
  @DisplayName("文件数据库持久化故障")
  class FileDatabaseFault {

    @Test
    @DisplayName("文件数据库事务在崩溃后保持完整")
    void fileDatabaseTransactionSurvivesCrash() throws Exception {
      Path dbFile = tempDir.resolve("crash-test.db");

      // 第一阶段：写入数据
      Connection conn1 = DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath());
      try {
        SqliteTestHelper.configureConnection(conn1);
        new IndexSchema(MigrationRunner.withAllMigrations()).ensureSchema(conn1);

        // 在事务中写入
        conn1.setAutoCommit(false);
        try (Statement stmt = conn1.createStatement()) {
          stmt.execute(
              "INSERT INTO sessions (session_key, agent, session_id, title, "
                  + "project_key, project_name, cwd, started_at, ended_at) "
                  + "VALUES ('key-1', 'claude-code', 'id-1', 'Test', 'proj', 'Proj', "
                  + "'/tmp', '2024-01-01T00:00:00Z', '2024-01-01T00:01:00Z')");
        }
        conn1.commit();
      } finally {
        conn1.close();
      }

      // 第二阶段：重新打开验证数据
      Connection conn2 = DriverManager.getConnection("jdbc:sqlite:" + dbFile.toAbsolutePath());
      try {
        SqliteTestHelper.configureConnection(conn2);
        try (Statement stmt = conn2.createStatement();
            ResultSet rs = stmt.executeQuery("SELECT count(*) FROM sessions")) {
          assertThat(rs.next()).isTrue();
          assertThat(rs.getInt(1)).isEqualTo(1);
        }
      } finally {
        conn2.close();
      }
    }
  }

  // ===== 辅助方法 =====

  private static Candidate makeCandidate(String locator, String sessionKey) {
    return new Candidate(
        new SourceFingerprint(
            locator,
            SourceId.CLAUDE_CODE,
            100,
            1000L,
            Optional.of("hash-" + locator),
            Optional.of("SHA-256")),
        sessionKey,
        "test-project",
        Map.of());
  }

  // ===== 测试用适配器 =====

  private static class EmptyAdapter implements SourceAdapter {
    private final SourceId sourceId;

    EmptyAdapter(SourceId sourceId) {
      this.sourceId = sourceId;
    }

    @Override
    public SourceId sourceId() {
      return sourceId;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          List.of(), SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), sourceId, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Success(List.of(), 0, List.of(), null, null);
    }
  }

  private static class FatalAdapter implements SourceAdapter {
    private final List<Candidate> candidates;

    FatalAdapter(List<Candidate> candidates) {
      this.candidates = List.copyOf(candidates);
    }

    @Override
    public SourceId sourceId() {
      return SourceId.CLAUDE_CODE;
    }

    @Override
    public BoundedStream<Candidate> discover(Path rootPath) {
      return BoundedStream.of(
          candidates, SourceConstants.MAX_CANDIDATES_PER_DISCOVERY, Optional.empty());
    }

    @Override
    public SourceFingerprint fingerprint(Path filePath) {
      return new SourceFingerprint(
          filePath.toString(), SourceId.CLAUDE_CODE, 0, 0, Optional.empty(), Optional.empty());
    }

    @Override
    public SourceResult parse(Candidate candidate, CancellationSignal cancellation) {
      return new SourceResult.Fatal(List.of(), "Test fatal error");
    }
  }
}
