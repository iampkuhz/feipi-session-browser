package com.feipi.session.browser.source.json;

/**
 * JSONL 解析统计信息。
 *
 * <p>记录一次解析操作的行数和事件计数。不可变 record。
 *
 * <p>此类是读取器级别的统计载体，不属于核心领域模型，因此不使用 {@code @DomainModel} 标注。
 *
 * @param totalLines 文件总行数（最后一个非空行的行号，空文件为 0）
 * @param nonEmptyLines 非空行数（去除尾部空白后不为空的行）
 * @param eventsParsed 成功解析的 JSON 对象数
 * @param eventsSkipped 被跳过的条目数（坏 JSON + 非对象）
 */
public record JsonlStats(int totalLines, int nonEmptyLines, int eventsParsed, int eventsSkipped) {

  /**
   * 警告级别诊断数量（非对象跳过）。
   *
   * @return 需要结合诊断列表计算，此方法仅为便利提供
   */
  public int warningCount() {
    return eventsSkipped;
  }
}
