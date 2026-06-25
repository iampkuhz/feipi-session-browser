package com.feipi.session.browser.domain.enums;

import com.feipi.session.browser.domain.annotation.DomainModel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Token 数据来源分类枚举。
 *
 * <p>标识 token 计数数据来自哪种 agent 的哪种数据管道。 用于归一化管线选择正确的解析策略和精度标注。
 */
@DomainModel
@RequiredArgsConstructor
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

  /** 稳定外部协议值。 */
  @Getter private final String value;

  /**
   * 从外部协议值解析 token 数据来源分类。
   *
   * <p>匹配规则：大小写不敏感，前后空白自动修剪。
   *
   * @param value 外部协议字符串值
   * @return 对应的 token 数据来源分类枚举
   * @throws IllegalArgumentException 如果值无法匹配任何已知来源
   * @throws NullPointerException 如果值为 null
   */
  public static TokenSourceKind fromValue(String value) {
    if (value == null) {
      throw new NullPointerException("Token 数据来源值不得为 null");
    }
    String normalized = value.trim().toLowerCase();
    for (TokenSourceKind kind : values()) {
      if (kind.value.equals(normalized)) {
        return kind;
      }
    }
    throw new IllegalArgumentException("非法的 Token 数据来源值: '" + value + "'");
  }
}
