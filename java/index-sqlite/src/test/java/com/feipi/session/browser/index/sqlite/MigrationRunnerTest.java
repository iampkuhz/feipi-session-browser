package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

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

/** {@link MigrationRunner} 幂等 migration 执行器测试。 */
@DisplayName("MigrationRunner 测试")
class MigrationRunnerTest {

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
  @DisplayName("空数据库场景")
  class EmptyDatabase {

    @Test
    @DisplayName("applyAll 在空数据库上创建全部表并返回已应用版本")
    void applyAllOnEmptyDatabase() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      List<SchemaVersion> applied = runner.applyAll(conn);

      assertThat(applied).hasSize(1);
      assertThat(applied.get(0).version()).isEqualTo(1);

      // 验证所有表已创建
      assertThat(tableExists("sessions")).isTrue();
      assertThat(tableExists("scan_log")).isTrue();
      assertThat(tableExists("index_metadata")).isTrue();
      assertThat(tableExists("session_artifacts")).isTrue();
      assertThat(tableExists("schema_migrations")).isTrue();
    }

    @Test
    @DisplayName("空数据库上 currentVersion 返回 V1")
    void currentVersionAfterApply() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      runner.applyAll(conn);

      SchemaVersion version = runner.currentVersion(conn);
      assertThat(version).isNotNull();
      assertThat(version.version()).isEqualTo(1);
    }
  }

  @Nested
  @DisplayName("重复 migration（幂等性）")
  class DuplicateMigration {

    @Test
    @DisplayName("第二次 applyAll 返回空列表，不重复执行")
    void secondApplyAllReturnsEmpty() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      runner.applyAll(conn);

      List<SchemaVersion> secondApply = runner.applyAll(conn);
      assertThat(secondApply).isEmpty();
    }

    @Test
    @DisplayName("三次 applyAll 仍然幂等")
    void thirdApplyAllStillIdempotent() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      runner.applyAll(conn);
      runner.applyAll(conn);
      List<SchemaVersion> thirdApply = runner.applyAll(conn);
      assertThat(thirdApply).isEmpty();
    }

    @Test
    @DisplayName("schema_migrations 记录数不变")
    void trackingTableNotDuplicated() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      runner.applyAll(conn);
      runner.applyAll(conn);

      Set<Integer> versions = runner.appliedVersions(conn);
      assertThat(versions).containsExactly(1);
    }
  }

  @Nested
  @DisplayName("当前数据库（已有全部表）")
  class CurrentDatabase {

    @Test
    @DisplayName("已有全部表时 applyAll 正常完成")
    void applyAllWithExistingTables() throws SQLException {
      // 手动创建全部表（模拟已有的完整数据库）
      createAllTablesManually();

      MigrationRunner runner = MigrationRunner.withAllMigrations();
      List<SchemaVersion> applied = runner.applyAll(conn);

      // V001 使用 CREATE TABLE IF NOT EXISTS，不会报错
      assertThat(applied).hasSize(1);
    }
  }

  @Nested
  @DisplayName("失败回滚")
  class FailureRollback {

    @Test
    @DisplayName("无效 SQL 导致回滚，schema_migrations 不记录失败版本")
    void failedMigrationRollsBack() throws SQLException {
      Migration badMigration =
          new Migration(new SchemaVersion(1), "无效 migration", "sql/V999__nonexistent.sql");
      MigrationRunner runner = new MigrationRunner(List.of(badMigration));

      assertThatThrownBy(() -> runner.applyAll(conn)).isInstanceOf(SQLException.class);

      // 回滚后追踪表不应包含失败版本
      assertThat(runner.appliedVersions(conn)).isEmpty();
    }

    @Test
    @DisplayName("失败后数据库表不存在")
    void failedMigrationLeavesNoPartialState() throws SQLException {
      Migration badMigration =
          new Migration(new SchemaVersion(1), "无效 migration", "sql/V999__nonexistent.sql");
      MigrationRunner runner = new MigrationRunner(List.of(badMigration));

      assertThatThrownBy(() -> runner.applyAll(conn)).isInstanceOf(SQLException.class);

      // 失败 migration 不应创建任何表
      assertThat(tableExists("sessions")).isFalse();
    }

    @Test
    @DisplayName("失败后可重新应用正确 migration")
    void retryAfterFailure() throws SQLException {
      Migration badMigration =
          new Migration(new SchemaVersion(1), "无效 migration", "sql/V999__nonexistent.sql");
      MigrationRunner runner = new MigrationRunner(List.of(badMigration));

      assertThatThrownBy(() -> runner.applyAll(conn)).isInstanceOf(SQLException.class);

      // 使用正确的 migration 重试
      MigrationRunner correctRunner = MigrationRunner.withAllMigrations();
      List<SchemaVersion> applied = correctRunner.applyAll(conn);
      assertThat(applied).hasSize(1);
      assertThat(tableExists("sessions")).isTrue();
    }
  }

  @Nested
  @DisplayName("版本查询")
  class VersionQuery {

    @Test
    @DisplayName("空数据库 currentVersion 返回 null")
    void emptyDatabaseReturnsNull() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      assertThat(runner.currentVersion(conn)).isNull();
    }

    @Test
    @DisplayName("pendingMigrations 返回未应用的 migration")
    void pendingMigrationsReturnsUnapplied() throws SQLException {
      MigrationRunner runner = MigrationRunner.withAllMigrations();
      List<Migration> pending = runner.pendingMigrations(conn);
      assertThat(pending).hasSize(1);

      runner.applyAll(conn);
      List<Migration> afterApply = runner.pendingMigrations(conn);
      assertThat(afterApply).isEmpty();
    }
  }

  /** 检查数据库中指定表是否存在。 */
  private boolean tableExists(String tableName) throws SQLException {
    try (Statement stmt = conn.createStatement();
        ResultSet rs =
            stmt.executeQuery(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='"
                    + tableName
                    + "'")) {
      rs.next();
      return rs.getInt(1) > 0;
    }
  }

  /** 手动创建全部表（模拟已有的完整数据库）。 */
  private void createAllTablesManually() throws SQLException {
    String sql = Migration.allMigrations().get(0).loadSql();
    try (Statement stmt = conn.createStatement()) {
      stmt.execute(sql);
    }
  }
}
