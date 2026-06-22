package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * Token 服务提供商枚举。
 *
 * <p>标识产生 token 计数的 LLM 提供商。 用于区分不同 provider 的计量模型和归因策略。
 */
@DomainModel
public enum TokenProvider {
  /** Anthropic 公司的 Claude 系列模型接口。 */
  ANTHROPIC("anthropic"),

  /** OpenAI 公司的 GPT 系列模型 API。 */
  OPENAI("openai"),

  /** Codex agent，基于 OpenAI 模型。 */
  CODEX("codex"),

  /** Qwen 模型 Anthropic 兼容接口。 */
  QWEN_ANTHROPIC_COMPATIBLE("qwen-anthropic-compatible"),

  /** Qoder 智能体服务。 */
  QODER("qoder"),

  /** 未知或无法识别的提供商。 */
  UNKNOWN("unknown");

  private final String value;

  /**
   * 构造服务提供商枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   */
  TokenProvider(String value) {
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
