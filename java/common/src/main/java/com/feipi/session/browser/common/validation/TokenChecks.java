package com.feipi.session.browser.common.validation;

/** Token 分段统计不变量校验工具。 */
public final class TokenChecks {

  private TokenChecks() {}

  /**
   * 校验 token breakdown 五个标准字段非负，不强制 total 等于分段和。
   *
   * @param freshInputTokens 非缓存输入 token 数
   * @param cacheReadTokens 缓存读取 token 数
   * @param cacheWriteTokens 缓存写入 token 数
   * @param outputTokens 输出 token 数
   * @param totalTokens token 总数
   */
  public static void requireNonNegativeBreakdown(
      long freshInputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      long outputTokens,
      long totalTokens) {
    ParamChecks.nonNegative(freshInputTokens, "freshInputTokens");
    ParamChecks.nonNegative(cacheReadTokens, "cacheReadTokens");
    ParamChecks.nonNegative(cacheWriteTokens, "cacheWriteTokens");
    ParamChecks.nonNegative(outputTokens, "outputTokens");
    ParamChecks.nonNegative(totalTokens, "totalTokens");
  }

  /**
   * 校验 token breakdown 五个标准字段非负，且 total 等于四段合计。
   *
   * @param freshInputTokens 非缓存输入 token 数
   * @param cacheReadTokens 缓存读取 token 数
   * @param cacheWriteTokens 缓存写入 token 数
   * @param outputTokens 输出 token 数
   * @param totalTokens token 总数
   * @throws IllegalArgumentException 当任一字段为负或 total 与四段合计不一致时
   */
  public static void requireTokenSegments(
      long freshInputTokens,
      long cacheReadTokens,
      long cacheWriteTokens,
      long outputTokens,
      long totalTokens) {
    requireNonNegativeBreakdown(
        freshInputTokens, cacheReadTokens, cacheWriteTokens, outputTokens, totalTokens);
    requireTotalEquals(
        totalTokens,
        componentTotal(freshInputTokens, cacheReadTokens, cacheWriteTokens, outputTokens),
        "totalTokens must equal component sum");
  }

  /**
   * 校验 usage 风格五字段非负，且 total 等于四段合计。
   *
   * @param fresh 非缓存输入 token 数
   * @param cacheRead 缓存读取 token 数
   * @param cacheWrite 缓存写入 token 数
   * @param output 输出 token 数
   * @param total token 总数
   * @param prefix 错误消息前缀，例如 {@code usage}
   * @throws IllegalArgumentException 当任一字段为负或 total 与四段合计不一致时
   */
  public static void requireUsageSegments(
      long fresh, long cacheRead, long cacheWrite, long output, long total, String prefix) {
    String namePrefix = prefix == null || prefix.isBlank() ? "" : prefix + ".";
    ParamChecks.nonNegative(fresh, namePrefix + "fresh");
    ParamChecks.nonNegative(cacheRead, namePrefix + "cacheRead");
    ParamChecks.nonNegative(cacheWrite, namePrefix + "cacheWrite");
    ParamChecks.nonNegative(output, namePrefix + "output");
    ParamChecks.nonNegative(total, namePrefix + "total");
    requireTotalEquals(
        total,
        componentTotal(fresh, cacheRead, cacheWrite, output),
        namePrefix + "total must equal component sum (token segment sum)");
  }

  /**
   * 计算四段 token 合计。
   *
   * @param first 第一段 token
   * @param second 第二段 token
   * @param third 第三段 token
   * @param fourth 第四段 token
   * @return 四段之和
   */
  public static long componentTotal(long first, long second, long third, long fourth) {
    return first + second + third + fourth;
  }

  private static void requireTotalEquals(
      long actualTotal, long expectedTotal, String messagePrefix) {
    if (actualTotal != expectedTotal) {
      throw new IllegalArgumentException(
          messagePrefix + " " + expectedTotal + "; got " + actualTotal);
    }
  }
}
