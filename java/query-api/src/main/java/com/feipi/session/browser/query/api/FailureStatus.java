package com.feipi.session.browser.query.api;

/**
 * 失败状态过滤器。
 *
 * <p>按工具调用失败状态过滤会话。支持三种模式：不过滤、仅失败、仅成功。
 */
public enum FailureStatus {
  /** 不过滤（匹配所有会话）。 */
  ALL,

  /** 仅包含至少有一次工具调用失败的会话。 */
  FAILED_ONLY,

  /** 仅包含零工具调用失败的会话。 */
  SUCCESS_ONLY;

  /**
   * 将字符串解析为失败状态过滤器。
   *
   * <p>不区分大小写，支持枚举名。
   *
   * @param value 状态字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值无法识别时
   */
  public static FailureStatus fromString(String value) {
    if ("all".equalsIgnoreCase(value) || value == null || value.isEmpty()) {
      return ALL;
    }
    if ("failed".equalsIgnoreCase(value) || "failed_only".equalsIgnoreCase(value)) {
      return FAILED_ONLY;
    }
    if ("success".equalsIgnoreCase(value) || "success_only".equalsIgnoreCase(value)) {
      return SUCCESS_ONLY;
    }
    throw new IllegalArgumentException("无法识别的失败状态: " + value);
  }
}
