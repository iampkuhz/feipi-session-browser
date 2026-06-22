package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 调用作用域枚举。
 *
 * <p>标识一次 LLM 调用发生在主线程还是子 agent 上下文中。 用于区分主会话调用和子 agent 委托调用的 token 计量与归因路径。
 */
@DomainModel
public enum CallScope {
  /** 主会话线程调用。 */
  MAIN("main"),

  /** 子 agent 委托调用。 */
  SUBAGENT("subagent");

  private final String value;

  /**
   * 构造调用作用域枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   */
  CallScope(String value) {
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
