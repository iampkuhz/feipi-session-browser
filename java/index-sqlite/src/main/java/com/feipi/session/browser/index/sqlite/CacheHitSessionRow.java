package com.feipi.session.browser.index.sqlite;

/**
 * 高缓存命中率会话行。
 *
 * <p>对应 Python {@code get_high_cache_read_sessions} 查询结果。包含计算的缓存命中百分比。
 *
 * @param sessionKey 会话主键
 * @param title 会话标题
 * @param agent agent 标识
 * @param model 模型名称
 * @param cacheReadTokens 缓存读取 token 数
 * @param freshInputTokens 非缓存输入 token 数
 * @param projectName 项目名称
 * @param cacheHitPercent 缓存命中百分比（0.0–100.0）
 */
public record CacheHitSessionRow(
    String sessionKey,
    String title,
    String agent,
    String model,
    long cacheReadTokens,
    long freshInputTokens,
    String projectName,
    double cacheHitPercent) {

  /**
   * 紧凑构造器，验证缓存命中百分比范围。
   *
   * @throws IllegalArgumentException 当 cacheHitPercent 不在 [0, 100] 范围内时
   */
  public CacheHitSessionRow {
    projectName = projectName == null ? "" : projectName;
    if (cacheHitPercent < 0.0 || cacheHitPercent > 100.0) {
      throw new IllegalArgumentException(
          "cacheHitPercent 必须在 [0, 100] 范围内; got " + cacheHitPercent);
    }
  }
}
