package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 异常类型枚举。
 *
 * <p>标识会话诊断中发现的异常类别。与 Python 端 {@code anomalies.py} 检测规则对应。
 */
@RequiredArgsConstructor
public enum AnomalyType {
  /** 单次会话 token 消耗异常偏高。 */
  TOKEN_SPIKE("token_spike"),

  /** 工具调用失败率异常偏高。 */
  HIGH_FAILURE_RATE("high_failure_rate"),

  /** 会话时长异常偏长。 */
  DURATION_OUTLIER("duration_outlier"),

  /** 子 agent 使用量异常偏高。 */
  SUBAGENT_OVERUSE("subagent_overuse");

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
