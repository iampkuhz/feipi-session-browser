package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Token 服务提供商枚举。
 *
 * <p>标识产生 token 计数的 LLM 提供商。 用于区分不同 provider 的计量模型和归因策略。
 */
@DomainModel
@RequiredArgsConstructor
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

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析 token 提供商。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的 token 提供商枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知提供商
   * @throws NullPointerException 如果值为 null
   */
  public static TokenProvider fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("Token 提供商值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (TokenProvider provider : values()) {
      if (provider.value.equals(normalized)) {
        return provider;
      }
    }
    throw new IllegalArgumentException(
        "非法的 Token 提供商值: '"
            + value
            + "'。允许值: anthropic, openai, codex, qwen-anthropic-compatible, qoder, unknown");
  }
}
