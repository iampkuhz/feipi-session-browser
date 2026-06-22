package com.feipi.session.browser.domain.normalized;

/**
 * 归一化领域常量。
 *
 * <p>集中定义归一化管线使用的 schema 版本、集合边界和字符串长度约束。
 * 这些常量与 Python 端 {@code session_browser.normalized.constants} 模块保持对应。
 */
public final class NormalizedConstants {

  /** 归一化制品 schema 版本号，与 Python 端 {@code NORMALIZED_SCHEMA_VERSION} 一致。 */
  public static final String SCHEMA_VERSION = "session-detail.normalized.v3";

  /** 集合类型字段的最大元素数量，防止内存溢出。 */
  public static final int MAX_COLLECTION_SIZE = 10_000;

  /** 字符串字段的最大字符数。 */
  public static final int MAX_STRING_LENGTH = 1_000_000;

  /** 防止实例化。 */
  private NormalizedConstants() {}
}
