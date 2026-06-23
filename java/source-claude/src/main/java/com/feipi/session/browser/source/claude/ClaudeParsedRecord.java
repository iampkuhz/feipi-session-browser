package com.feipi.session.browser.source.claude;

import com.feipi.session.browser.source.spi.ParsedRecord;
import java.util.Objects;

/**
 * Claude Code 会话事件的源中性已解析记录。
 *
 * <p>每个实例对应 JSONL 会话文件中的一条 JSON 事件。locator 由文件路径和事件在文件中的 序号（从 0 开始）组成，保证稳定性和确定性，不使用随机 UUID。
 *
 * <p>该类不可变，线程安全。
 */
public final class ClaudeParsedRecord implements ParsedRecord {

  /** locator 格式模板：{@code {filePath}#event[{index}]}。 */
  private static final String LOCATOR_FORMAT = "%s#event[%d]";

  private final String locator;
  private final String eventType;
  private final int eventIndex;

  /**
   * 创建一条已解析记录。
   *
   * @param filePath 源文件绝对路径，用于构造稳定 locator
   * @param eventIndex 事件在文件中的序号（从 0 开始）
   * @param eventType 事件类型（对应 JSONL 中 {@code type} 字段），缺失或非法时为 {@code "unknown"}
   */
  public ClaudeParsedRecord(String filePath, int eventIndex, String eventType) {
    Objects.requireNonNull(filePath, "filePath 不得为 null");
    Objects.requireNonNull(eventType, "eventType 不得为 null");
    this.locator = String.format(LOCATOR_FORMAT, filePath, eventIndex);
    this.eventIndex = eventIndex;
    this.eventType = eventType;
  }

  @Override
  public String locator() {
    return locator;
  }

  /**
   * 返回事件类型标识。
   *
   * <p>对应 JSONL 事件中 {@code type} 字段的值。当 {@code type} 字段缺失或非字符串时 返回 {@code "unknown"}。
   *
   * @return 非 null 的事件类型
   */
  public String eventType() {
    return eventType;
  }

  /**
   * 返回事件在源文件中的序号。
   *
   * @return 从 0 开始的事件序号
   */
  public int eventIndex() {
    return eventIndex;
  }
}
