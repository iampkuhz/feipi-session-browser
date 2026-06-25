package com.feipi.session.browser.source.spi;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 解析诊断严重级别。
 *
 * <p>对应 JSONL 解析过程中产生的诊断信息严重程度。 该枚举与 Python 端 {@code ParseSeverity} 对齐。
 */
@DomainModel
@RequiredArgsConstructor
public enum ParseSeverity {

  /** 信息级别，不影响解析结果。 */
  @CoreField
  INFO("INFO"),

  /** 警告级别，解析继续但数据可能不完整。 */
  @CoreField
  WARNING("WARNING"),

  /** 错误级别，对应条目无法解析。 */
  @CoreField
  ERROR("ERROR");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析解析诊断严重级别。
   *
   * <p>匹配规则：精确匹配，区分大小写。
   *
   * @param value 外部协议字符串值
   * @return 对应的解析诊断严重级别枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知级别
   * @throws NullPointerException 如果值为 null
   */
  public static ParseSeverity fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("解析诊断严重级别值不得为 null");
    }
    for (ParseSeverity severity : values()) {
      if (severity.value.equals(value)) {
        return severity;
      }
    }
    throw new IllegalArgumentException("非法的解析诊断严重级别值: '" + value + "'");
  }
}
