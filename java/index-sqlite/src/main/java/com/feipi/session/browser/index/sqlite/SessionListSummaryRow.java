package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.common.validation.ParamChecks;
import com.feipi.session.browser.common.validation.TokenChecks;

/**
 * 会话列表过滤后的完整聚合行。
 *
 * <p>用于 API-first 列表契约，直接暴露 contract test 可校验的原始数值，避免从 HTML 文本反推数据口径。
 *
 * @param sessionCount 当前过滤条件下的 session 数量。
 * @param projectCount 当前过滤条件下的项目数量。
 * @param freshInputTokens fresh input token 数量。
 * @param cacheReadTokens cache read token 数量。
 * @param cacheWriteTokens cache write token 数量。
 * @param outputTokens output token 数量。
 * @param totalTokens token 汇总数量。
 * @param failedToolCount 失败工具数量。
 */
public record SessionListSummaryRow(
    long sessionCount,
    long projectCount,
    long freshInputTokens,
    long cacheReadTokens,
    long cacheWriteTokens,
    long outputTokens,
    long totalTokens,
    long failedToolCount) {

  /** 验证所有聚合数值非负，且 total 与四段 token 一致。 */
  public SessionListSummaryRow {
    ParamChecks.nonNegative(sessionCount, "sessionCount");
    ParamChecks.nonNegative(projectCount, "projectCount");
    TokenChecks.requireTokenSegments(
        freshInputTokens, cacheReadTokens, cacheWriteTokens, outputTokens, totalTokens);
    ParamChecks.nonNegative(failedToolCount, "failedToolCount");
  }
}
