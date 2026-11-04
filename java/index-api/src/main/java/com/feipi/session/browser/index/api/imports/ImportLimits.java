package com.feipi.session.browser.index.api.imports;

/**
 * 单文件导入的资源策略，所有上限均为正数。
 *
 * @param maxFileBytes 单次上传的最大字节数
 * @param maxRecords 文件允许的最大 JSON 记录数
 * @param maxRecordChars 单条记录允许的最大字符数
 * @param maxImports 同时保留的最大导入数
 * @param maxStoredBytes 保留制品的最大规范 JSON 字节数
 */
public record ImportLimits(
    long maxFileBytes, int maxRecords, int maxRecordChars, int maxImports, long maxStoredBytes) {

  /** 校验资源策略，避免无界或不可用的服务。 */
  public ImportLimits {
    if (maxFileBytes < 1
        || maxRecords < 1
        || maxRecordChars < 1
        || maxImports < 1
        || maxStoredBytes < 1) {
      throw new IllegalArgumentException("导入资源上限必须为正数");
    }
  }

  /** 返回默认策略：32 MiB 文件、万条记录、百万字符、8 个导入和 64 MiB 制品。 */
  public static ImportLimits defaults() {
    return new ImportLimits(32L * 1024 * 1024, 10_000, 1_000_000, 8, 64L * 1024 * 1024);
  }
}
