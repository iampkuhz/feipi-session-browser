package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.index.api.query.ActivityTrend;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 每日活动趋势行。
 *
 * <p>对应 Python {@code get_prompt_activity_trend} 查询结果。按日历日分组，包含 prompt、助手轮次和工具调用计数。
 *
 * @param date 日期字符串（YYYY-MM-DD）
 * @param claudePrompts claude_code 当日用户 prompt 数
 * @param codexPrompts codex 当日用户 prompt 数
 * @param qoderPrompts qoder 当日用户 prompt 数
 * @param totalPrompts 当日用户 prompt 总数
 * @param assistantTurns 当日助手消息总数
 * @param toolCalls 当日工具调用总数
 * @param measuredUserMessages 当前范围显式 user 消息测量样本的累计消息数。
 * @param userMessageSampleCount 当前范围 user 消息数已测量的会话数，包含实测零。
 * @param claudeMeasuredUserMessages Claude Code显式 user 消息测量样本的累计消息数。
 * @param claudeUserMessageSampleCount Claude Code user 消息数已测量的会话数，包含实测零。
 * @param codexMeasuredUserMessages Codex显式 user 消息测量样本的累计消息数。
 * @param codexUserMessageSampleCount Codex user 消息数已测量的会话数，包含实测零。
 * @param qoderMeasuredUserMessages Qoder显式 user 消息测量样本的累计消息数。
 * @param qoderUserMessageSampleCount Qoder user 消息数已测量的会话数，包含实测零。
 */
public record ActivityTrendRow(
    /* 日期字符串（YYYY-MM-DD）。 */ @NotBlank String date,
    /* claude_code 当日用户 prompt 数。 */ @PositiveOrZero long claudePrompts,
    /* codex 当日用户 prompt 数。 */ @PositiveOrZero long codexPrompts,
    /* qoder 当日用户 prompt 数。 */ @PositiveOrZero long qoderPrompts,
    /* 当日用户 prompt 总数。 */ @PositiveOrZero long totalPrompts,
    /* 当日助手消息总数。 */ @PositiveOrZero long assistantTurns,
    /* 当日工具调用总数。 */ @PositiveOrZero long toolCalls,
    @PositiveOrZero long measuredUserMessages,
    @PositiveOrZero long userMessageSampleCount,
    @PositiveOrZero long claudeMeasuredUserMessages,
    @PositiveOrZero long claudeUserMessageSampleCount,
    @PositiveOrZero long codexMeasuredUserMessages,
    @PositiveOrZero long codexUserMessageSampleCount,
    @PositiveOrZero long qoderMeasuredUserMessages,
    @PositiveOrZero long qoderUserMessageSampleCount)
    implements ActivityTrend {

  /**
   * 兼容未提供消息测量权重的调用者，不从原始计数推断覆盖。
   *
   * @param date UTC 开始日 cohort 日期。
   * @param claudePrompts Claude Code 累计 user 消息数。
   * @param codexPrompts Codex 累计 user 消息数。
   * @param qoderPrompts Qoder 累计 user 消息数。
   * @param totalPrompts 当前范围累计 user 消息数。
   * @param assistantTurns 累计 assistant 消息数，不是逻辑轮数。
   * @param toolCalls 累计工具调用数。
   */
  public ActivityTrendRow(
      String date,
      long claudePrompts,
      long codexPrompts,
      long qoderPrompts,
      long totalPrompts,
      long assistantTurns,
      long toolCalls) {
    this(
        date,
        claudePrompts,
        codexPrompts,
        qoderPrompts,
        totalPrompts,
        assistantTurns,
        toolCalls,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0);
  }

  /** 紧凑构造器，校验 record component 约束。 */
  public ActivityTrendRow {
    ValidationSupport.validateCanonicalConstructor(
        ActivityTrendRow.class,
        date,
        claudePrompts,
        codexPrompts,
        qoderPrompts,
        totalPrompts,
        assistantTurns,
        toolCalls,
        measuredUserMessages,
        userMessageSampleCount,
        claudeMeasuredUserMessages,
        claudeUserMessageSampleCount,
        codexMeasuredUserMessages,
        codexUserMessageSampleCount,
        qoderMeasuredUserMessages,
        qoderUserMessageSampleCount);
  }
}
