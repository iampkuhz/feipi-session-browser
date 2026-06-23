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
}
