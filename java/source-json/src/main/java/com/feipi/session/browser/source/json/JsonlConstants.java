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

  /** 字节顺序标记字符（Unicode {@code U+FEFF}）。 */
  static final char BOM = '﻿';

  /** 诊断代码：括号类型不匹配（如 {@code {}]} 或混用不同类型的括号）。 */
  static final String CODE_BRACKET_MISMATCH = "BAD_JSON:BRACKET_MISMATCH";

  /** 诊断代码：括号深度变为负数（多余的闭合括号）。 */
  static final String CODE_NEGATIVE_DEPTH = "BAD_JSON:NEGATIVE_DEPTH";

  /** 诊断代码：文件读取期间被修改，数据可能不完整。 */
  static final String CODE_RETRYABLE_INCOMPLETE = "RETRYABLE_INCOMPLETE";

  /** 诊断代码：缓冲区超限，单条记录过大。 */
  static final String CODE_BUFFER_OVERFLOW = "BAD_JSON:BUFFER_OVERFLOW";

  /** 诊断代码：达到最大记录数限制后停止。 */
  static final String CODE_STOPPED_BY_LIMIT = "STOPPED_BY_LIMIT";

  /** 单条记录允许累积的最大行数（防止超大记录无界占用内存）。 */
  static final int MAX_LINES_PER_RECORD = 5_000;

  private JsonlConstants() {
    // 禁止实例化
  }
}
