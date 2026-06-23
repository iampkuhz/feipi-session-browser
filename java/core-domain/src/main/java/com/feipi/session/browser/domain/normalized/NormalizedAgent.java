package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * 归一化 agent 来源枚举。
 *
 * <p>标识产生归一化制品的源适配器类型。与 Python 端 {@code _AGENT_VALUES} 集合对应， 仅允许 {@code claude_code}、{@code codex}
 * 和 {@code qoder} 三个合法值。
 */
@DomainModel
@RequiredArgsConstructor
public enum NormalizedAgent {
  /** {@code Claude Code} 产生的 JSONL 格式日志适配器。 */
  CLAUDE_CODE("claude_code"),

  /** {@code Codex} 产生的展开格式日志适配器。 */
  CODEX("codex"),

  /** {@code Qoder} 产生的日志适配器。 */
  QODER("qoder");

  /** 稳定外部协议值。 */
  @Getter private final String value;

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
