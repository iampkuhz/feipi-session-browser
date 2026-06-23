package com.feipi.session.browser.query.api;

/**
 * payload 来源类型分类。
 *
 * <p>标识 payload 内容的语义类别，对应 Python {@code _build_payload_lookup} 中生成的不同 payload 种类。
 */
public enum PayloadSourceKind {

  /** LLM 请求正文。 */
  LLM_REQUEST,

  /** LLM 响应正文。 */
  LLM_RESPONSE,

  /** 工具调用结果。 */
  TOOL_RESULT,

  /** 子 agent 请求正文。 */
  SUBAGENT_REQUEST,

  /** 子 agent 响应正文。 */
  SUBAGENT_RESPONSE
}
