package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * Top-N 项目聚合行。
 *
 * <p>对应 Python {@code get_top_projects_by_tokens} 和 {@code get_top_projects_by_tools} 查询结果。
 * 统一两种项目排行查询的公共字段结构。
 *
 * @param projectKey 项目键
 * @param projectName 项目显示名称
 * @param totalTokens token 总量
 * @param totalTools 工具调用总数
 * @param failedTools 失败工具调用总数
 * @param sessionCount 会话数
 */
public record TopProjectRow(
    /* 项目键值。 */ @NotBlank String projectKey,
    /* 项目显示名称。 */ String projectName,
    /* 令牌总数量。 */ @PositiveOrZero long totalTokens,
    /* 工具调用总数。 */ @PositiveOrZero long totalTools,
    /* 失败工具调用总数。 */ @PositiveOrZero long failedTools,
    /* 会话数量。 */ @PositiveOrZero long sessionCount) {

  /** 紧凑构造器，校验 record component 约束。 */
  public TopProjectRow {
    ValidationSupport.validateCanonicalConstructor(
        TopProjectRow.class,
        projectKey,
        projectName,
        totalTokens,
        totalTools,
        failedTools,
        sessionCount);
  }
}
