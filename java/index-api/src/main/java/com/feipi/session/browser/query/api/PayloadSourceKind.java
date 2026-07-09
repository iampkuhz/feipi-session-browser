package com.feipi.session.browser.query.api;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * payload 来源类型分类。
 *
 * <p>标识 payload 内容的语义类别，对应 Python {@code _build_payload_lookup} 中生成的不同 payload 种类。
 */
@RequiredArgsConstructor
public enum PayloadSourceKind {

  /** LLM 请求正文。 */
  LLM_REQUEST("llm_request"),

  /** LLM 响应正文。 */
  LLM_RESPONSE("llm_response"),

  /** 工具调用结果。 */
  TOOL_RESULT("tool_result"),

  /** 子 agent 请求正文。 */
  SUBAGENT_REQUEST("subagent_request"),

  /** 子 agent 响应正文。 */
  SUBAGENT_RESPONSE("subagent_response");

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析 payload 来源类型。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的 payload 来源类型枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知类型
   * @throws NullPointerException 如果值为 null
   */
  public static PayloadSourceKind fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("Payload 来源类型值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (PayloadSourceKind kind : values()) {
      if (kind.value.equals(normalized)) {
        return kind;
      }
    }
    throw new IllegalArgumentException("非法的 payload 来源类型值: '" + value + "'");
  }
}
