package com.feipi.session.browser.normalization;

/**
 * 归一化引擎常量。
 *
 * <p>集中定义归一化引擎使用的字符串常量，包括调用作用域和用量来源标识。 这些常量补充 {@link
 * com.feipi.session.browser.domain.normalized.NormalizedConstants} 中定义的 schema 级常量。
 */
public final class NormalizationConstants {

  /** 精确用量来源标识，表示数据直接来自 provider 报告。 */
  public static final String USAGE_SOURCE_EXACT = "exact";

  /** 估算用量来源标识，表示数据为推断或补全。 */
  public static final String USAGE_SOURCE_ESTIMATED = "estimated";

  /** 防止实例化。 */
  private NormalizationConstants() {}
}
