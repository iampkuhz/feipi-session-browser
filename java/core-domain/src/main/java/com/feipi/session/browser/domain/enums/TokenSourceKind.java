package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * Token 数据来源分类枚举。
 *
 * <p>标识 token 计数数据来自哪种 agent 的哪种数据管道。 用于归一化管线选择正确的解析策略和精度标注。
 */
@DomainModel
public enum TokenSourceKind {
  /** Claude Code JSONL 日志中的 usage 块。 */
  CLAUDE_CODE_JSONL_USAGE("claude_code_jsonl_usage"),

  /** Codex 推出的 token 计数。 */
  CODEX_ROLLOUT_TOKEN_COUNT("codex_rollout_token_count"),

  /** OpenAI 响应 API 的用量数据。 */
  OPENAI_RESPONSES_USAGE("openai_responses_usage"),

  /** Qoder 分段模型响应完成事件。 */
  QODER_SEGMENT_MODEL_RESPONSE_COMPLETED("qoder_segment_model_response_completed"),

  /** Qoder SQLite 数据库中的 token 信息表。 */
  QODER_SQLITE_TOKEN_INFO("qoder_sqlite_token_info"),

  /** Qoder 轮次完成事件的备用计数。 */
  QODER_TURN_FINISHED_FALLBACK("qoder_turn_finished_fallback"),

  /** Qoder 会话转录文本的估算计数。 */
  QODER_TRANSCRIPT_ESTIMATED("qoder_transcript_estimated"),

  /** 仅有会话级别总计的备用来源。 */
  SESSION_TOTAL_ONLY_FALLBACK("session_total_only_fallback"),

  /** 未知或无法识别的来源。 */
  UNKNOWN("unknown");

  private final String value;

  /**
   * 构造数据来源分类枚举常量。
   *
   * @param value 与 Python 兼容的字符串值
   */
  TokenSourceKind(String value) {
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
