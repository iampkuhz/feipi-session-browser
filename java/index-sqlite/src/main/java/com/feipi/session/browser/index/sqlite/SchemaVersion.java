package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.common.validation.ParamChecks;

/**
 * Schema 版本号，独立于 scan logic version。
 *
 * <p>每次 schema migration 对应一个递增的版本号。 schema version 跟踪表结构和列定义的变化， scan logic version（存储在 {@code
 * index_metadata}） 跟踪扫描逻辑和数据格式的变化。
 *
 * @param version 正整数版本号，从 1 开始
 */
public record SchemaVersion(int version) implements Comparable<SchemaVersion> {

  /**
   * 创建版本号。
   *
   * @param version 正整数版本号
   * @throws IllegalArgumentException 版本号小于 1
   */
  public SchemaVersion {
    ParamChecks.atLeast(version, 1, "schema version");
  }

  @Override
  public int compareTo(SchemaVersion other) {
    return Integer.compare(this.version, other.version);
  }

  @Override
  public String toString() {
    return "V" + version;
  }
}
