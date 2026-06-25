package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 调用作用域枚举。
 *
 * <p>标识一次 LLM 调用发生在主线程还是子 agent 上下文中。 用于区分主会话调用和子 agent 委托调用的 token 计量与归因路径。
 */
@DomainModel
@RequiredArgsConstructor
public enum CallScope {
  /** 主会话线程调用。 */
  MAIN("main"),

  /** 子 agent 委托调用。 */
  SUBAGENT("subagent");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析调用作用域。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的调用作用域枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知作用域
   * @throws NullPointerException 如果值为 null
   */
  public static CallScope fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("调用作用域值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (CallScope scope : values()) {
      if (scope.value.equals(normalized)) {
        return scope;
      }
    }
    throw new IllegalArgumentException("非法的调用作用域值: '" + value + "'。允许值: main, subagent");
  }
}
