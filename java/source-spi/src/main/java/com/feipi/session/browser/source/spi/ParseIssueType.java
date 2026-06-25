package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 解析问题类型。
 *
 * <p>标识 JSONL 解析过程中遇到的具体问题类别。 该枚举与 Python 端 {@code ParseIssue} 对齐。
 */
@DomainModel
@RequiredArgsConstructor
public enum ParseIssueType {

  /** JSON 格式损坏，无法解析。 */
  @CoreField
  BAD_JSON("BAD_JSON"),

  /** 合法 JSON 但非对象类型，已跳过。 */
  @CoreField
  NON_OBJECT_SKIPPED("NON_OBJECT_SKIPPED"),

  /** 检测到拼接对象边界（{@code }{ }），已拆分处理。 */
  @CoreField
  CONCATENATED_OBJECTS("CONCATENATED_OBJECTS");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析解析问题类型。
   *
   * <p>匹配规则：精确匹配，区分大小写。
   *
   * @param value 外部协议字符串值
   * @return 对应的解析问题类型枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知类型
   * @throws NullPointerException 如果值为 null
   */
  public static ParseIssueType fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("解析问题类型值不得为 null");
    }
    for (ParseIssueType type : values()) {
      if (type.value.equals(value)) {
        return type;
      }
    }
    throw new IllegalArgumentException("非法的解析问题类型值: '" + value + "'");
  }
}
