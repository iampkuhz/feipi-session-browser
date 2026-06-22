package com.feipi.session.browser.source.json;

import java.util.Objects;

/**
 * JSONL 读取器配置。
 *
 * <p>控制解析过程中的资源上限，防止异常输入导致内存溢出。 所有字段均为不可变 record component。
 *
 * @param maxRecords 单次解析操作允许的最大记录数
 * @param maxBufferChars 单条记录累积缓冲区的最大字符数
 * @param maxPreviewLength 诊断预览文本的最大长度（字符数）
 */
public record JsonlReaderConfig(int maxRecords, int maxBufferChars, int maxPreviewLength) {

  /** 默认配置实例。 */
  public static final JsonlReaderConfig DEFAULT =
      new JsonlReaderConfig(
          JsonlConstants.DEFAULT_MAX_RECORDS,
          JsonlConstants.DEFAULT_MAX_BUFFER_CHARS,
          JsonlConstants.DEFAULT_PREVIEW_MAX_LENGTH);

  /**
   * 紧凑构造器，验证配置不变量。
   *
   * @throws IllegalArgumentException 当任何上限值为非正数时
   */
  public JsonlReaderConfig {
    if (maxRecords <= 0) {
      throw new IllegalArgumentException("maxRecords 必须为正整数: " + maxRecords);
    }
    if (maxBufferChars <= 0) {
      throw new IllegalArgumentException("maxBufferChars 必须为正整数: " + maxBufferChars);
    }
    if (maxPreviewLength <= 0) {
      throw new IllegalArgumentException("maxPreviewLength 必须为正整数: " + maxPreviewLength);
    }
  }

  /**
   * 创建使用默认值的配置。
   *
   * @return 默认配置实例
   */
  public static JsonlReaderConfig defaults() {
    return DEFAULT;
  }

  /**
   * 创建自定义配置。
   *
   * @param maxRecords 最大记录数
   * @param maxBufferChars 最大缓冲区字符数
   * @param maxPreviewLength 最大预览长度
   * @return 自定义配置实例
   */
  public static JsonlReaderConfig of(int maxRecords, int maxBufferChars, int maxPreviewLength) {
    return new JsonlReaderConfig(maxRecords, maxBufferChars, maxPreviewLength);
  }

  /**
   * 截断预览文本到配置的最大长度。
   *
   * @param text 原始文本
   * @return 截断后的文本
   */
  String truncatePreview(String text) {
    Objects.requireNonNull(text, "text 不得为 null");
    if (text.length() <= maxPreviewLength) {
      return text;
    }
    return text.substring(0, maxPreviewLength);
  }
}
