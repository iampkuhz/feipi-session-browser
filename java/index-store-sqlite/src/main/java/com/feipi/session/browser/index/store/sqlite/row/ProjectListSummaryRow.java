package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.common.validation.TokenChecks;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.query.ProjectListSummary;
import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.PositiveOrZero;

/**
 * 表示 ProjectListSummaryRow 数据。
 *
 * @param projectCount 当前过滤条件下的项目数量。
 * @param sessionCount 当前过滤条件下的 session 数量。
 * @param freshInputTokens 新鲜输入令牌数量。
 * @param cacheReadTokens 缓存读取令牌数量。
 * @param cacheWriteTokens 缓存写入令牌数量。
 * @param outputTokens 输出令牌数量。
 * @param totalTokens token 汇总数量。
 * @param toolCallCount 工具调用数量。
 * @param failedToolCount 失败工具数量。
 * @param tokenProvenance 相同查询范围的四段计量来源
 */
public record ProjectListSummaryRow(
    /* 当前过滤条件下的项目数量。 */ @PositiveOrZero long projectCount,
    /* 当前过滤条件下的 session 数量。 */ @PositiveOrZero long sessionCount,
    /* 新鲜输入令牌数量。 */ @PositiveOrZero long freshInputTokens,
    /* 缓存读取令牌数量。 */ @PositiveOrZero long cacheReadTokens,
    /* 缓存写入令牌数量。 */ @PositiveOrZero long cacheWriteTokens,
    /* 输出令牌数量。 */ @PositiveOrZero long outputTokens,
    /* token 汇总数量。 */ @PositiveOrZero long totalTokens,
    /* 工具调用数量。 */ @PositiveOrZero long toolCallCount,
    /* 失败工具数量。 */ @PositiveOrZero long failedToolCount,
    /* 相同查询范围的四段计量来源。 */ TokenProvenance tokenProvenance)
    implements ProjectListSummary {

  /** 紧凑构造器，校验 record component 约束和 token 总和不变量。 */
  public ProjectListSummaryRow {
    tokenProvenance =
        tokenProvenance == null
            ? TokenProvenance.unknown(Math.max(0, sessionCount))
            : tokenProvenance;
    ValidationSupport.validateCanonicalConstructor(
        ProjectListSummaryRow.class,
        projectCount,
        sessionCount,
        freshInputTokens,
        cacheReadTokens,
        cacheWriteTokens,
        outputTokens,
        totalTokens,
        toolCallCount,
        failedToolCount,
        tokenProvenance);
    TokenChecks.requireTokenSegments(
        freshInputTokens, cacheReadTokens, cacheWriteTokens, outputTokens, totalTokens);
  }

  /** 兼容未提供精度的旧调用点，不把旧数值推断为上报。 */
  public ProjectListSummaryRow(
      long projectCount,
      long sessionCount,
      long freshInputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      long outputTokens,
      long totalTokens,
      long toolCallCount,
      long failedToolCount) {
    this(
        projectCount,
        sessionCount,
        freshInputTokens,
        cacheReadTokens,
        cacheWriteTokens,
        outputTokens,
        totalTokens,
        toolCallCount,
        failedToolCount,
        TokenProvenance.unknown(Math.max(0, sessionCount)));
  }
}
