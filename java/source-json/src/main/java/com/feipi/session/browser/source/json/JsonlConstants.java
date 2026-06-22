package com.feipi.session.browser.source.json;

/**
 * JSONL 读取器模块级常量。
 *
 * <p>集中定义读取器使用的上限值，避免硬编码和魔法数字散落在实现中。 与 {@link com.feipi.session.browser.source.spi.SourceConstants}
 * 互补， 后者定义 SPI 层共享常量。
 */
public final class JsonlConstants {

  /** 诊断预览文本的默认最大长度（字符数）。 */
  public static final int DEFAULT_PREVIEW_MAX_LENGTH = 120;

  /** 单条记录累积缓冲区的默认最大字符数。 */
  public static final int DEFAULT_MAX_BUFFER_CHARS = 10_000_000;

  /** 单次解析操作的默认最大记录数。 */
  public static final int DEFAULT_MAX_RECORDS = 1_000_000;

  /** 字节顺序标记字符（统一码 {@code U+FEFF}）。 */
  static final char BOM = '﻿';

  private JsonlConstants() {
    // 禁止实例化
  }
}
