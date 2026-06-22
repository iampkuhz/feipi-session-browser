package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 归一化 agent 来源枚举。
 *
 * <p>标识产生归一化制品的源适配器类型。与 Python 端 {@code _AGENT_VALUES} 集合对应，
 * 仅允许 {@code claude_code}、{@code codex} 和 {@code qoder} 三个合法值。
 */
@DomainModel
public enum NormalizedAgent {
  /** Claude Code JSONL 日志适配器。 */
  CLAUDE_CODE("claude_code"),

  /** Codex rollout 适配器。 */
  CODEX("codex"),

  /** Qoder 适配器。 */
  QODER("qoder");

  private final String value;

  /**
   * 构造 agent 枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   */
  NormalizedAgent(String value) {
    this.value = value;
  }

  /**
   * 获取枚举值的字符串表示。
   *
   * @return 与 Python 端一致的字符串值
   */
  public String getValue() {
    return value;
  }

  /**
   * 根据字符串值查找对应的枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   * @return 对应的枚举常量
   * @throws IllegalArgumentException 当值不在合法范围内时
   */
  public static NormalizedAgent fromValue(String value) {
    for (NormalizedAgent agent : values()) {
      if (agent.value.equals(value)) {
        return agent;
      }
    }
    throw new IllegalArgumentException("invalid normalized agent: " + value);
  }
}
