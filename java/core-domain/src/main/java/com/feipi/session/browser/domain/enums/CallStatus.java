package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 调用状态枚举。
 *
 * <p>标识一次 LLM 调用的最终执行结果状态。 用于 token 归因、错误统计和会话质量分析。
 */
@DomainModel
public enum CallStatus {
  /** 调用成功完成。 */
  OK("ok"),

  /** 调用执行出错。 */
  ERROR("error"),

  /** 调用已正常完成（与 OK 语义相近，保留兼容）。 */
  COMPLETED("completed");

  private final String value;

  /**
   * 构造调用状态枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   */
  CallStatus(String value) {
    this.value = value;
  }

  /**
   * 获取枚举值的字符串表示。
   *
   * @return 与 Python {@code DomainStrEnum} 兼容的字符串值
   */
  public String getValue() {
    return value;
  }
}
