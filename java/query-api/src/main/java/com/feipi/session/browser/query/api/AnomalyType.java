package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 会话级异常类型枚举。
 *
 * <p>标识会话诊断检测中发现的异常类别。与 Python 端 {@code anomalies.py} 检测规则对应。
 * 值为稳定外部协议契约，过滤器和模板依赖这些值。
 */
@RequiredArgsConstructor
public enum AnomalyType {
  /** 活跃时长（模型推理 + 工具执行）超过阈值。 */
  LONG_DURATION("long_duration"),

  /** 缓存创建 token 超过阈值。 */
  CACHE_WRITE_SPIKE("cache_write_spike"),

  /** 工具调用失败率超过阈值。 */
  FAILED_RUN("failed_run"),

  /** payload 可见性不匹配，由会话详情路由检测。 */
  PAYLOAD_VISIBILITY_MISMATCH("payload_visibility_mismatch");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 异常类型字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static AnomalyType fromValue(String value) {
    for (AnomalyType type : values()) {
      if (type.value.equals(value)) {
        return type;
      }
    }
    throw new IllegalArgumentException("无法识别的异常类型: " + value);
  }
}
