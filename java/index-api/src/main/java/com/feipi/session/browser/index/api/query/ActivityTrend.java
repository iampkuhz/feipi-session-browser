package com.feipi.session.browser.index.api.query;

/**
 * UTC 开始日 cohort 的会话累计 prompt 活动趋势行。
 *
 * <p>各项为该日开始会话的整段累计量，而非消息或工具的实际发生日；未知或无效开始日期不参与。
 */
public interface ActivityTrend {
  /** 返回有效会话开始时间对应的 UTC 日期，格式为 {@code YYYY-MM-DD}。 */
  String date();

  /** 返回 该日开始的 Claude Code 会话累计用户 prompt 数。 */
  long claudePrompts();

  /** 返回 该日开始的 Codex 会话累计用户 prompt 数。 */
  long codexPrompts();

  /** 返回 该日开始的 Qoder 会话累计用户 prompt 数。 */
  long qoderPrompts();

  /** 返回该日开始会话的累计用户 prompt 总数。 */
  long totalPrompts();

  /** 返回该日开始会话的累计助手消息总数。 */
  long assistantTurns();

  /** 返回该日开始会话的累计工具调用总数。 */
  long toolCalls();
}
