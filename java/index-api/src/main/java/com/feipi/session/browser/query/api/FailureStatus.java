package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 失败状态过滤器。
 *
 * <p>按工具调用失败状态过滤会话。支持三种模式：不过滤、仅失败、仅成功。
 */
@RequiredArgsConstructor
public enum FailureStatus {
  /** 不过滤（匹配所有会话）。 */
  ALL("all"),

  /** 仅包含至少有一次工具调用失败的会话。 */
  FAILED_ONLY("failed_only"),

  /** 仅包含零工具调用失败的会话。 */
  SUCCESS_ONLY("success_only");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析失败状态过滤器。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的失败状态枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知状态
   * @throws NullPointerException 如果值为 null
   */
  public static FailureStatus fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("失败状态值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (FailureStatus status : values()) {
      if (status.value.equals(normalized)) {
        return status;
      }
    }
    throw new IllegalArgumentException(
        "非法的失败状态值: '" + value + "'。允许值: all, failed_only, success_only");
  }

  /**
   * 将字符串解析为失败状态过滤器。
   *
   * <p>不区分大小写，支持枚举名和多种别名。 委托给 {@link #fromValue(String)}。
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
