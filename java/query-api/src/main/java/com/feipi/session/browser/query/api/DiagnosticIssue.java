package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 解析问题类别枚举。
 *
 * <p>标识影响索引会话质量的解析问题类别。与 Python 端 {@code ParseIssue} 对应。
 * 值为稳定外部协议契约。
 */
@RequiredArgsConstructor
public enum DiagnosticIssue {
  /** JSONL 行无法解析为 JSON。 */
  BAD_JSON("BAD_JSON"),

  /** JSONL 行已解析但不是对象事件。 */
  NON_OBJECT_SKIPPED("NON_OBJECT_SKIPPED"),

  /** 发现所需的源文件缺失。 */
  FILE_NOT_FOUND("FILE_NOT_FOUND"),

  /** 源文件无可解析的事件。 */
  EMPTY_FILE("EMPTY_FILE"),

  /** 事件或会话缺少预期的时间戳数据。 */
  MISSING_TIMESTAMP("MISSING_TIMESTAMP"),

  /** token 值为估算而非直接读取。 */
  TOKEN_ESTIMATED("TOKEN_ESTIMATED");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 问题类别字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static DiagnosticIssue fromValue(String value) {
    for (DiagnosticIssue issue : values()) {
      if (issue.value.equals(value)) {
        return issue;
      }
    }
    throw new IllegalArgumentException("无法识别的诊断问题类别: " + value);
  }
}
