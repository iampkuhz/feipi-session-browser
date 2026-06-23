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
}
