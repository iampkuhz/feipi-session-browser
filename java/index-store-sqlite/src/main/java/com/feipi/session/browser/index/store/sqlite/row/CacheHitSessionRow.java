package com.feipi.session.browser.index.store.sqlite.row;

import com.feipi.session.browser.validation.ValidationSupport;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

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
    /* 会话主键。 */ @NotBlank String sessionKey,
    /* 会话标题。 */ String title,
    /* 代理类型标识。 */ @NotBlank String agent,
    /* 模型名称。 */ String model,
    /* 缓存读取 token 数。 */ @PositiveOrZero long cacheReadTokens,
    /* 非缓存输入 token 数。 */ @PositiveOrZero long freshInputTokens,
    /* 项目名称。 */ String projectName,
    /* 缓存命中百分比（0.0–100.0）。 */ double cacheHitPercent) {

  /**
   * 紧凑构造器，校验 record component 约束并应用默认值。
   *
   * <p>projectName 为 null 时回退为空字符串；cacheHitPercent 范围由后续校验保证。
   *
   * @throws IllegalArgumentException 当 cacheHitPercent 不在 [0, 100] 范围内时
   */
  public CacheHitSessionRow {
    ValidationSupport.validateCanonicalConstructor(
        CacheHitSessionRow.class,
        sessionKey,
        title,
        agent,
        model,
        cacheReadTokens,
        freshInputTokens,
        projectName,
        cacheHitPercent);
    projectName = projectName == null ? "" : projectName;
    if (cacheHitPercent < 0.0 || cacheHitPercent > 100.0) {
      throw new IllegalArgumentException(
          "cacheHitPercent 必须在 [0, 100] 范围内，实际值: " + cacheHitPercent);
    }
  }
}
