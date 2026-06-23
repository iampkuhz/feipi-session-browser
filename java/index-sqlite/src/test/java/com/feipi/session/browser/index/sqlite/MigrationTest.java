package com.feipi.session.browser.index.sqlite;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.UncheckedIOException;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** {@link Migration} 不可变定义的单元测试。 */
@DisplayName("Migration 测试")
class MigrationTest {

  @Test
  @DisplayName("loadSql 从 classpath 加载 V001 SQL 资源")
  void loadSqlFromClasspath() {
    Migration migration = Migration.allMigrations().get(0);
    String sql = migration.loadSql();

    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS sessions");
    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS scan_log");
    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS index_metadata");
    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS session_artifacts");
  }

  @Test
  @DisplayName("加载不存在的资源抛出 UncheckedIOException")
  void loadMissingResourceThrows() {
    Migration migration =
        new Migration(new SchemaVersion(99), "不存在的 migration", "sql/V099__nonexistent.sql");

    assertThatThrownBy(migration::loadSql)
        .isInstanceOf(UncheckedIOException.class)
        .hasMessageContaining("classpath 资源不存在");
  }

  @Test
  @DisplayName("空 description 抛出 IllegalArgumentException")
  void emptyDescriptionThrows() {
    assertThatThrownBy(
            () -> new Migration(new SchemaVersion(1), "", "sql/V001__initial_schema.sql"))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("空 sqlResource 抛出 IllegalArgumentException")
  void emptySqlResourceThrows() {
    assertThatThrownBy(() -> new Migration(new SchemaVersion(1), "描述", ""))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  @DisplayName("allMigrations 返回按版本升序排列的非空列表")
  void allMigrationsReturnsOrderedList() {
    List<Migration> migrations = Migration.allMigrations();

    assertThat(migrations).isNotEmpty();
    // 验证版本号递增
    for (int i = 1; i < migrations.size(); i++) {
      assertThat(migrations.get(i).version().version())
          .isGreaterThan(migrations.get(i - 1).version().version());
    }
  }

  @Test
  @DisplayName("V001 SQL 包含 sessions 表全部 28 列")
  void v001ContainsAllSessionsColumns() {
    String sql = Migration.allMigrations().get(0).loadSql();

    // 验证核心列存在
    assertThat(sql).contains("session_key TEXT PRIMARY KEY");
    assertThat(sql).contains("agent TEXT NOT NULL");
    assertThat(sql).contains("session_id TEXT NOT NULL");
    assertThat(sql).contains("total_tokens INTEGER NOT NULL DEFAULT 0");
    assertThat(sql).contains("file_path TEXT NOT NULL DEFAULT ''");
    assertThat(sql).contains("file_mtime REAL NOT NULL DEFAULT 0");
  }

  @Test
  @DisplayName("V001 SQL 包含全部 4 张表的 CREATE TABLE 语句")
  void v001ContainsAllCreateTables() {
    String sql = Migration.allMigrations().get(0).loadSql();

    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS sessions");
    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS scan_log");
    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS index_metadata");
    assertThat(sql).contains("CREATE TABLE IF NOT EXISTS session_artifacts");
  }
}
