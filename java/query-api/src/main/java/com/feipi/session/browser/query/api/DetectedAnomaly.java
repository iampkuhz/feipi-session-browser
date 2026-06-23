package com.feipi.session.browser.query.api;

import java.util.Objects;

/**
 * 检测到的单个会话异常。
 *
 * <p>异常检测器在评估会话行数据后创建此值对象。包含异常类型、严重度和人类可读的检测原因。 注意：此类不包含显示文案（如 CSS class），显示逻辑在 presentation 层。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code type} 不得为 null。
 *   <li>{@code severity} 不得为 null。
 *   <li>{@code reason} 不得为 null，空字符串表示原因缺失。
 * </ul>
 *
 * @param type 异常类型分类
 * @param severity 异常严重度级别
 * @param reason 人类可读的检测原因说明
 */
public record DetectedAnomaly(AnomalyType type, AnomalySeverity severity, String reason) {

  /**
   * 紧凑构造器，验证异常值对象不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public DetectedAnomaly {
    Objects.requireNonNull(type, "type 不得为 null");
    Objects.requireNonNull(severity, "severity 不得为 null");
    reason = reason == null ? "" : reason;
  }

  /**
   * 创建严重级异常。
   *
   * @param type 异常类型
   * @param reason 检测原因
   * @return 新的严重级异常实例
   */
  public static DetectedAnomaly critical(AnomalyType type, String reason) {
    return new DetectedAnomaly(type, AnomalySeverity.CRITICAL, reason);
  }

  /**
   * 创建警告级异常。
   *
   * @param type 异常类型
   * @param reason 检测原因
   * @return 新的警告级异常实例
   */
  public static DetectedAnomaly warning(AnomalyType type, String reason) {
    return new DetectedAnomaly(type, AnomalySeverity.WARNING, reason);
  }

  /**
   * 创建信息级异常。
   *
   * @param type 异常类型
   * @param reason 检测原因
   * @return 新的信息级异常实例
   */
  public static DetectedAnomaly info(AnomalyType type, String reason) {
    return new DetectedAnomaly(type, AnomalySeverity.INFO, reason);
  }
}
