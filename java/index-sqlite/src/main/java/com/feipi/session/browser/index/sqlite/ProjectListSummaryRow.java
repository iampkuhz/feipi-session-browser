package com.feipi.session.browser.index.sqlite;

/**
 * 表示 ProjectListSummaryRow 数据。
 *
 * @param projectCount 当前过滤条件下的项目数量。
 * @param sessionCount 当前过滤条件下的 session 数量。
 * @param freshInputTokens fresh input token 数量。
 * @param cacheReadTokens cache read token 数量。
 * @param cacheWriteTokens cache write token 数量。
 * @param outputTokens output token 数量。
 * @param totalTokens token 汇总数量。
 * @param toolCallCount 工具调用数量。
 * @param failedToolCount 失败工具数量。
 */
public record ProjectListSummaryRow(
    long projectCount,
    long sessionCount,
    long freshInputTokens,
    long cacheReadTokens,
    long cacheWriteTokens,
    long outputTokens,
    long totalTokens,
    long toolCallCount,
    long failedToolCount) {

  /** 校验计数非负和 token 总和不变量。 */
  public ProjectListSummaryRow {
    RowValidators.requireNonNegative(projectCount, "projectCount");
    RowValidators.requireNonNegative(sessionCount, "sessionCount");
    RowValidators.requireNonNegative(freshInputTokens, "freshInputTokens");
    RowValidators.requireNonNegative(cacheReadTokens, "cacheReadTokens");
    RowValidators.requireNonNegative(cacheWriteTokens, "cacheWriteTokens");
    RowValidators.requireNonNegative(outputTokens, "outputTokens");
    RowValidators.requireNonNegative(totalTokens, "totalTokens");
    RowValidators.requireNonNegative(toolCallCount, "toolCallCount");
    RowValidators.requireNonNegative(failedToolCount, "failedToolCount");
    long componentTotal = freshInputTokens + cacheReadTokens + cacheWriteTokens + outputTokens;
    if (totalTokens != componentTotal) {
      throw new IllegalArgumentException(
          "totalTokens must equal token component sum; totalTokens="
              + totalTokens
              + ", components="
              + componentTotal);
    }
  }
}
