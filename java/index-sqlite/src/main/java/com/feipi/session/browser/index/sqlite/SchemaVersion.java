package com.feipi.session.browser.index.sqlite;

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
    if (version < 1) {
      throw new IllegalArgumentException("schema version 必须 >= 1，实际值: " + version);
    }
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
