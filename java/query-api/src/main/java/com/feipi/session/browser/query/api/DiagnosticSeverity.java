package com.feipi.session.browser.query.api;

/**
 * 解析诊断严重度枚举。
 *
 * <p>标识解析级别问题的严重程度。与 Python 端 {@code ParseSeverity} 对应。 Source adapter 创建 reader 层严重度后，映射到此域枚举。
 */
public enum DiagnosticSeverity {
  /** 信息级问题，不影响数据完整性。 */
  INFO,

  /** 警告级问题，可能影响显示质量。 */
  WARNING,

  /** 严重问题，解析失败或数据丢失。 */
  CRITICAL
}
