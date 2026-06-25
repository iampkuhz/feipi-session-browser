package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 解析诊断严重度枚举。
 *
 * <p>标识解析级别问题的严重程度。与 Python 端 {@code ParseSeverity} 对应。 Source adapter 创建 reader 层严重度后，映射到此域枚举。
 */
@RequiredArgsConstructor
public enum DiagnosticSeverity {
  /** 信息级问题，不影响数据完整性。 */
  INFO("info"),

  /** 警告级问题，可能影响显示质量。 */
  WARNING("warning"),

  /** 严重问题，解析失败或数据丢失。 */
  CRITICAL("critical");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析诊断严重度。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的诊断严重度枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知严重度
   * @throws NullPointerException 如果值为 null
   */
  public static DiagnosticSeverity fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("诊断严重度值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (DiagnosticSeverity severity : values()) {
      if (severity.value.equals(normalized)) {
        return severity;
      }
    }
    throw new IllegalArgumentException("非法的诊断严重度值: '" + value + "'。允许值: info, warning, critical");
  }
}
