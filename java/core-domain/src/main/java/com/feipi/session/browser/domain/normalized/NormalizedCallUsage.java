package com.feipi.session.browser.domain.normalized;

import com.feipi.session.browser.domain.annotation.CoreField;
import com.feipi.session.browser.domain.annotation.DomainModel;

/**
 * 单次归一化调用的 token 用量。
 *
 * <p>建模一次 LLM 调用的五字段 token 用量，语义构建器和制品验证器为每次调用创建该不可变值对象。 分量计数必须非负，且 {@code total} 必须等于各分量之和。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>所有 token 计数必须非负。
 *   <li>{@code total} 必须等于 {@code fresh + cacheRead + cacheWrite + output}。
 * </ul>
 *
 * @param fresh 归因到该调用的非缓存输入 token 数
 * @param cacheRead 归因到该调用的缓存读取 token 数
 * @param cacheWrite 归因到该调用的缓存写入 token 数
 * @param output 归因到该调用的输出 token 数
 * @param total 所有 token 分量之和
 */
@DomainModel
public record NormalizedCallUsage(
    @CoreField long fresh,
    @CoreField long cacheRead,
    @CoreField long cacheWrite,
    @CoreField long output,
    @CoreField long total) {

  /**
   * 紧凑构造器，验证 token 计数不变量。
   *
   * @throws IllegalArgumentException 当任何计数为负数或 {@code total} 不等于分量之和时
   */
  public NormalizedCallUsage {
    if (fresh < 0) {
      throw new IllegalArgumentException("usage.fresh must be non-negative; got " + fresh);
    }
    if (cacheRead < 0) {
      throw new IllegalArgumentException("usage.cacheRead must be non-negative; got " + cacheRead);
    }
    if (cacheWrite < 0) {
      throw new IllegalArgumentException(
          "usage.cacheWrite must be non-negative; got " + cacheWrite);
    }
    if (output < 0) {
      throw new IllegalArgumentException("usage.output must be non-negative; got " + output);
    }
    if (total < 0) {
      throw new IllegalArgumentException("usage.total must be non-negative; got " + total);
    }
    long expectedTotal = fresh + cacheRead + cacheWrite + output;
    if (total != expectedTotal) {
      throw new IllegalArgumentException(
          "usage.total must equal component sum " + expectedTotal + "; got " + total);
    }
  }

  /**
   * 创建全零的默认 token 用量。
   *
   * @return 所有 token 计数为零的默认实例
   */
  public static NormalizedCallUsage empty() {
    return new NormalizedCallUsage(0, 0, 0, 0, 0);
  }
}
