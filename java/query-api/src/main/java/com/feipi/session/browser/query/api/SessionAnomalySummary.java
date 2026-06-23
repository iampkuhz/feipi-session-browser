package com.feipi.session.browser.query.api;

import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * 单个会话的异常检测结果集合。
 *
 * <p>异常检测器为每个会话创建此对象，包含该会话检测到的所有异常。提供便捷方法获取最高严重度和
 * 异常数量，供 dashboard 和列表展示使用。
 *
 * <p>不变量：
 *
 * <ul>
 *   <li>{@code sessionKey} 不得为 null，空字符串表示会话键缺失。
 *   <li>{@code anomalies} 不得为 null，使用不可变列表。
 * </ul>
 *
 * @param sessionKey 会话主键
 * @param anomalies 检测到的异常列表，按检测顺序排列
 */
public record SessionAnomalySummary(String sessionKey, List<DetectedAnomaly> anomalies) {

  /**
   * 紧凑构造器，验证会话异常集合不变量。
   *
   * @throws NullPointerException 当必填字段为 null 时
   */
  public SessionAnomalySummary {
    Objects.requireNonNull(sessionKey, "sessionKey 不得为 null");
    Objects.requireNonNull(anomalies, "anomalies 不得为 null");
    anomalies = List.copyOf(anomalies);
  }

  /**
   * 创建无异常的会话摘要。
   *
   * @param sessionKey 会话主键
   * @return 空异常列表的会话摘要
   */
  public static SessionAnomalySummary empty(String sessionKey) {
    return new SessionAnomalySummary(sessionKey, Collections.emptyList());
  }

  /**
   * 获取最高严重度。
   *
   * <p>CRITICAL 优先级最高，INFO 最低。无异常时返回 INFO。
   *
   * @return 最高严重度级别
   */
  public AnomalySeverity maxSeverity() {
    if (anomalies.isEmpty()) {
      return AnomalySeverity.INFO;
    }
    return anomalies.stream()
        .map(DetectedAnomaly::severity)
        .min(AnomalySeverity::comparePriority)
        .orElse(AnomalySeverity.INFO);
  }

  /**
   * 获取最高严重度异常的原因。
   *
   * <p>无异常时返回空字符串。多个相同最高严重度异常时返回第一个。
   *
   * @return 最高严重度异常的原因
   */
  public String mainReason() {
    if (anomalies.isEmpty()) {
      return "";
    }
    return anomalies.stream()
        .min((a, b) -> a.severity().comparePriority(b.severity()))
        .map(DetectedAnomaly::reason)
        .orElse("");
  }

  /**
   * 异常数量。
   *
   * @return 检测到的异常数量
   */
  public int anomalyCount() {
    return anomalies.size();
  }

  /**
   * 是否包含指定类型的异常。
   *
   * @param type 异常类型
   * @return 包含该类型时返回 true
   */
  public boolean hasType(AnomalyType type) {
    return anomalies.stream().anyMatch(a -> a.type() == type);
  }
}
