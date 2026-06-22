package com.feipi.session.browser.artifact.normalized;

/**
 * 归一化制品常量。
 *
 * <p>集中定义 artifact 序列化与文件写入使用的常量，包括生成器标识、文件后缀和临时文件前缀。
 */
public final class ArtifactConstants {

  /** 生成器标识，写入 meta 文件的 {@code generator} 字段。 */
  public static final String GENERATOR = "feipi-session-browser-java";

  /** meta 文件后缀。 */
  public static final String META_FILE_SUFFIX = ".meta.json";

  /** 数据文件后缀。 */
  public static final String DATA_FILE_SUFFIX = ".json";

  /** 临时文件前缀，用于失败安全写入。 */
  public static final String TEMP_FILE_PREFIX = ".tmp.";

  /** 禁止实例化。 */
  private ArtifactConstants() {}
}
