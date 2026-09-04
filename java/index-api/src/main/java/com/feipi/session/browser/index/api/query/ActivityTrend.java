package com.feipi.session.browser.index.api.query;

/** 每日 prompt 活动趋势行。 */
public interface ActivityTrend {
  /** 返回日期，格式为 {@code YYYY-MM-DD}。 */
  String date();

  /** 返回 Claude Code 当日用户 prompt 数。 */
  long claudePrompts();

  /** 返回 Codex 当日用户 prompt 数。 */
  long codexPrompts();

  /** 返回 Qoder 当日用户 prompt 数。 */
  long qoderPrompts();

  /** 返回当日用户 prompt 总数。 */
  long totalPrompts();

  /** 返回当日助手消息总数。 */
  long assistantTurns();

  /** 返回当日工具调用总数。 */
  long toolCalls();
}
