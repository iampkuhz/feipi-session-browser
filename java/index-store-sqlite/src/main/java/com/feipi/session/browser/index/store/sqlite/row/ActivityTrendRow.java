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
 */
public record ActivityTrendRow(
    /* 日期字符串（YYYY-MM-DD）。 */ @NotBlank String date,
    /* claude_code 当日用户 prompt 数。 */ @PositiveOrZero long claudePrompts,
    /* codex 当日用户 prompt 数。 */ @PositiveOrZero long codexPrompts,
    /* qoder 当日用户 prompt 数。 */ @PositiveOrZero long qoderPrompts,
    /* 当日用户 prompt 总数。 */ @PositiveOrZero long totalPrompts,
    /* 当日助手消息总数。 */ @PositiveOrZero long assistantTurns,
    /* 当日工具调用总数。 */ @PositiveOrZero long toolCalls)
    implements ActivityTrend {

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
        toolCalls);
  }
}
