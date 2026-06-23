package com.feipi.session.browser.source.spi;

/**
 * Source SPI 共享常量。
 *
 * <p>集中定义源适配器和相关类型使用的常量值， 避免硬编码和魔法数字散落在各实现类中。
 */
public final class SourceConstants {

  /** 单次发现操作的最大候选项数量。 */
  public static final int MAX_CANDIDATES_PER_DISCOVERY = 10_000;

  /** 单个候选项的元数据条目上限。 */
  public static final int MAX_METADATA_ENTRIES = 100;

  /** 单次解析操作的最大诊断条目数。 */
  public static final int MAX_DIAGNOSTICS_PER_PARSE = 1000;

  /** 诊断预览文本的最大长度（字符数）。 */
  public static final int MAX_PREVIEW_LENGTH = 200;

  /** 默认内容哈希算法。 */
  public static final String DEFAULT_HASH_ALGORITHM = "SHA-256";

  private SourceConstants() {
    // 禁止实例化
  }
}
