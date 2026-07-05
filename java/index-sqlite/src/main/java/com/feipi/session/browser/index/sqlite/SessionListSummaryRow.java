package com.feipi.session.browser.index.sqlite;

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
    RowValidators.requireNonNegative(sessionCount, "sessionCount");
    RowValidators.requireNonNegative(projectCount, "projectCount");
    RowValidators.requireNonNegative(freshInputTokens, "freshInputTokens");
    RowValidators.requireNonNegative(cacheReadTokens, "cacheReadTokens");
    RowValidators.requireNonNegative(cacheWriteTokens, "cacheWriteTokens");
    RowValidators.requireNonNegative(outputTokens, "outputTokens");
    RowValidators.requireNonNegative(totalTokens, "totalTokens");
    RowValidators.requireNonNegative(failedToolCount, "failedToolCount");
    long segmentTotal = freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    if (totalTokens != segmentTotal) {
      throw new IllegalArgumentException(
          "totalTokens 必须等于 token 四段合计; total=" + totalTokens + ", segments=" + segmentTotal);
    }
  }
}
