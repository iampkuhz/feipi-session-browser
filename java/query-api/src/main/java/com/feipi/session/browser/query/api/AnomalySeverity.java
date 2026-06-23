package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 异常严重度枚举。
 *
 * <p>标识检测到的会话异常的严重程度级别。与 Python 端常量 {@code SEVERITY_CRITICAL}、
 * {@code SEVERITY_WARNING}、{@code SEVERITY_INFO} 对应。
 */
@RequiredArgsConstructor
public enum AnomalySeverity {
  /** 严重异常，需要立即关注。 */
  CRITICAL("critical"),

  /** 警告级异常，可能影响会话质量。 */
  WARNING("warning"),

  /** 信息级异常，不影响会话功能。 */
  INFO("info");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 严重度字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static AnomalySeverity fromValue(String value) {
    for (AnomalySeverity severity : values()) {
      if (severity.value.equals(value)) {
        return severity;
      }
    }
    throw new IllegalArgumentException("无法识别的异常严重度: " + value);
  }

  /**
   * 比较两个严重度的优先级。
   *
   * <p>CRITICAL 优先级最高，INFO 最低。用于确定会话最高严重度。
   *
   * @param other 另一个严重度
   * @return 当前实例优先级更高时返回负数
   */
  public int comparePriority(AnomalySeverity other) {
    return Integer.compare(this.ordinal(), other.ordinal());
  }
}
