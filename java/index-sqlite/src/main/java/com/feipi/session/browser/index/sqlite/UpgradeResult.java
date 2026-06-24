package com.feipi.session.browser.index.sqlite;

import java.nio.file.Path;
import java.util.List;

/**
 * 数据库升级流程的结果记录。
 *
 * <p>记录升级过程中各阶段的实际行为，供调用方判断升级状态和日志输出。 不可变 record，线程安全。
 *
 * @param schemaVersionsApplied 本次实际应用的 schema migration 版本列表（空表示全部已应用）
 * @param backupPath 升级前备份文件路径，无备份时（数据库不存在）为 null
 * @param versionChanged schema 版本是否发生变化
 * @param appVersionRecorded 写入 index_metadata 的应用版本，版本不可用时为 null
 */
public record UpgradeResult(
    List<SchemaVersion> schemaVersionsApplied,
    Path backupPath,
    boolean versionChanged,
    String appVersionRecorded) {

  /**
   * 紧凑构造器，防御性拷贝列表。
   *
   * @param schemaVersionsApplied 已应用版本列表
   * @param backupPath 备份路径
   * @param versionChanged 版本是否变化
   * @param appVersionRecorded 记录的应用版本
   */
  public UpgradeResult {
    schemaVersionsApplied = List.copyOf(schemaVersionsApplied);
  }

  /** 是否有 schema migration 被应用。 */
  public boolean hadMigrations() {
    return !schemaVersionsApplied.isEmpty();
  }

  /** 是否创建了备份。 */
  public boolean hasBackup() {
    return backupPath != null;
  }
}
