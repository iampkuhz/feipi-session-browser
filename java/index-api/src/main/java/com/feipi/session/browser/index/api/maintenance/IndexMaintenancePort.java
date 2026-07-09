package com.feipi.session.browser.index.api.maintenance;

/** 索引 schema 与生命周期操作的维护端口。 */
public interface IndexMaintenancePort {

  /** 确保底层索引 schema 已可读写。 */
  void ensureSchema();

  /** 返回当前抽象索引 schema 版本。 */
  int schemaVersion();

  /** 重建前清空已索引的 session 与 artifact 数据。 */
  void clearExistingIndex();
}
