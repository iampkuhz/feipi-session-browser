package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.validation.Finite;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * Top-N 会话排行行。
 *
 * <p>对应 Python {@code get_slowest_sessions} 和 {@code get_failed_tool_sessions} 查询结果。
 * 统一两种会话排行查询的公共字段结构。
 *
 * @param sessionKey 会话主键
 * @param title 会话标题
 * @param agent agent 标识
 * @param model 模型名称
 * @param projectName 项目名称
 * @param durationSeconds 时长（秒）
 * @param failedToolCount 失败工具调用数
 * @param toolCallCount 工具调用总数
 */
public record TopSessionRow(
    /* 会话主键。 */ @NotBlank String sessionKey,
    /* 会话标题。 */ String title,
    /* 代理类型标识。 */ @NotBlank String agent,
    /* 模型名称。 */ @NotBlank String model,
    /* 项目名称。 */ String projectName,
    /* 持续时长秒数。 */ @Finite @PositiveOrZero double durationSeconds,
    /* 失败工具调用数。 */ @PositiveOrZero long failedToolCount,
    /* 工具调用总数。 */ @PositiveOrZero long toolCallCount) {

  /** 紧凑构造器，校验 record component 约束。 */
  public TopSessionRow {
    ValidationSupport.validateCanonicalConstructor(
        TopSessionRow.class,
        sessionKey,
        title,
        agent,
        model,
        projectName,
        durationSeconds,
        failedToolCount,
        toolCallCount);
  }
}
