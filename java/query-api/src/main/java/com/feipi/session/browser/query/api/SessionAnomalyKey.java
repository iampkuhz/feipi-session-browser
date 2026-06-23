package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 会话级异常注册键枚举。
 *
 * <p>定义会话异常检测器支持的所有异常类型键。与 Python 端
 * {@code SESSION_ANOMALY_DEFINITIONS} 注册表的键对应。
 * 值为稳定外部协议契约。
 */
@RequiredArgsConstructor
public enum SessionAnomalyKey {
  /** 活跃时长超过阈值。 */
  LONG_DURATION("long_duration"),

  /** 工具调用失败率超过阈值。 */
  FAILED_RUN("failed_run"),

  /** 缓存创建 token 超过阈值。 */
  CACHE_WRITE_SPIKE("cache_write_spike");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 异常键字符串
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static SessionAnomalyKey fromValue(String value) {
    for (SessionAnomalyKey key : values()) {
      if (key.value.equals(value)) {
        return key;
      }
    }
    throw new IllegalArgumentException("无法识别的会话异常键: " + value);
  }
}
