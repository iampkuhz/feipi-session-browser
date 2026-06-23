package com.feipi.session.browser.index.sqlite;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

/**
 * 单条 schema migration 定义。
 *
 * <p>每条 migration 包含版本号、描述和升级 SQL。 SQL 语句从 classpath 资源加载， 保证 SQL 作为版本控制资源独立管理，不散落在 Java 代码中。
 *
 * <p>SQL 资源文件路径约定：{@code sql/V{NNN}__<描述>.sql}， 其中 {@code NNN} 为三位版本号补零。
 *
 * @param version migration 版本号
 * @param description 人类可读描述，用于日志和 {@code schema_migrations} 记录
 * @param sqlResource classpath 资源路径，例如 {@code "sql/V001__initial_schema.sql"}
 */
public record Migration(SchemaVersion version, String description, String sqlResource) {

  /**
   * 创建 migration 定义。
   *
   * @param version 版本号
   * @param description 描述
   * @param sqlResource classpath 资源路径
   * @throws IllegalArgumentException 描述或资源路径为空
   */
  public Migration {
    if (description == null || description.isBlank()) {
      throw new IllegalArgumentException("migration description 不能为空");
    }
    if (sqlResource == null || sqlResource.isBlank()) {
      throw new IllegalArgumentException("sqlResource 不能为空");
    }
  }

  /**
   * 从 classpath 加载 SQL 内容。
   *
   * @return SQL 语句文本
   * @throws UncheckedIOException 资源不存在或读取失败
   */
  public String loadSql() {
    try (InputStream in = Migration.class.getClassLoader().getResourceAsStream(sqlResource)) {
      if (in == null) {
        throw new UncheckedIOException(new IOException("classpath 资源不存在: " + sqlResource));
      }
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException("读取 migration SQL 失败: " + sqlResource, e);
    }
  }

  /**
   * 创建 migration 定义列表。
   *
   * <p>按版本号升序排列。当前注册的 migration：
   *
   * <ul>
   *   <li>V001 — 初始 schema（sessions, scan_log, index_metadata, session_artifacts）
   * </ul>
   *
   * @return 不可变 migration 列表
   */
  public static List<Migration> allMigrations() {
    return List.of(
        new Migration(
            new SchemaVersion(1),
            "初始 schema：sessions, scan_log, index_metadata, session_artifacts",
            "sql/V001__initial_schema.sql"));
  }
}
