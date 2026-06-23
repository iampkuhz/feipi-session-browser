package com.feipi.session.browser.index.sqlite;

import com.feipi.session.browser.query.api.AnomalySeverity;
import com.feipi.session.browser.query.api.RoundSignalKey;
import com.feipi.session.browser.query.api.SessionAnomalyKey;
import java.util.Collections;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 诊断定义注册表。
 *
 * <p>提供会话级异常和轮次级信号的稳定定义。与 Python 端 {@code SESSION_ANOMALY_DEFINITIONS} 和 {@code
 * ROUND_SIGNAL_DEFINITIONS} 对应。
 *
 * <p>注册表只暴露检测逻辑所需的键和严重度，不包含显示文案（label/description）。 显示逻辑在 presentation 层处理。
 */
public final class DiagnosticRegistry {

  private static final Map<SessionAnomalyKey, AnomalyDefinition> SESSION_ANOMALIES;
  private static final Map<RoundSignalKey, SignalDefinition> ROUND_SIGNALS;

  static {
    Map<SessionAnomalyKey, AnomalyDefinition> sessionMap = new EnumMap<>(SessionAnomalyKey.class);

    sessionMap.put(
        SessionAnomalyKey.LONG_DURATION,
        new AnomalyDefinition(
            SessionAnomalyKey.LONG_DURATION,
            EnumSet.of(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL)));

    sessionMap.put(
        SessionAnomalyKey.FAILED_RUN,
        new AnomalyDefinition(
            SessionAnomalyKey.FAILED_RUN,
            EnumSet.of(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL)));

    sessionMap.put(
        SessionAnomalyKey.CACHE_WRITE_SPIKE,
        new AnomalyDefinition(
            SessionAnomalyKey.CACHE_WRITE_SPIKE,
            EnumSet.of(AnomalySeverity.INFO, AnomalySeverity.WARNING)));

    SESSION_ANOMALIES = Collections.unmodifiableMap(sessionMap);

    Map<RoundSignalKey, SignalDefinition> roundMap = new EnumMap<>(RoundSignalKey.class);

    roundMap.put(
        RoundSignalKey.FAILED_TOOL,
        new SignalDefinition(
            RoundSignalKey.FAILED_TOOL,
            EnumSet.of(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL)));

    roundMap.put(
        RoundSignalKey.LLM_ERROR,
        new SignalDefinition(
            RoundSignalKey.LLM_ERROR,
            EnumSet.of(AnomalySeverity.WARNING, AnomalySeverity.CRITICAL)));

    roundMap.put(
        RoundSignalKey.LONG_TOOL,
        new SignalDefinition(RoundSignalKey.LONG_TOOL, EnumSet.of(AnomalySeverity.WARNING)));

    roundMap.put(
        RoundSignalKey.TOOL_BURST,
        new SignalDefinition(RoundSignalKey.TOOL_BURST, EnumSet.of(AnomalySeverity.WARNING)));

    roundMap.put(
        RoundSignalKey.HIGH_WRITE,
        new SignalDefinition(RoundSignalKey.HIGH_WRITE, EnumSet.of(AnomalySeverity.WARNING)));

    roundMap.put(
        RoundSignalKey.LARGE_INPUT,
        new SignalDefinition(RoundSignalKey.LARGE_INPUT, EnumSet.of(AnomalySeverity.WARNING)));

    ROUND_SIGNALS = Collections.unmodifiableMap(roundMap);
  }

  private DiagnosticRegistry() {}

  /**
   * 获取所有已注册的会话级异常键。
   *
   * @return 不可变的会话异常键集合
   */
  public static Set<SessionAnomalyKey> sessionAnomalyKeys() {
    return SESSION_ANOMALIES.keySet();
  }

  /**
   * 获取所有已注册的轮次级信号键。
   *
   * @return 不可变的轮次信号键集合
   */
  public static Set<RoundSignalKey> roundSignalKeys() {
    return ROUND_SIGNALS.keySet();
  }

  /**
   * 获取会话异常定义。
   *
   * @param key 异常键
   * @return 异常定义，不存在时返回 null
   */
  public static AnomalyDefinition sessionAnomaly(SessionAnomalyKey key) {
    Objects.requireNonNull(key, "key 不得为 null");
    return SESSION_ANOMALIES.get(key);
  }

  /**
   * 获取轮次信号定义。
   *
   * @param key 信号键
   * @return 信号定义，不存在时返回 null
   */
  public static SignalDefinition roundSignal(RoundSignalKey key) {
    Objects.requireNonNull(key, "key 不得为 null");
    return ROUND_SIGNALS.get(key);
  }

  /**
   * 检查会话异常键是否已注册。
   *
   * @param key 异常键
   * @return 已注册时返回 true
   */
  public static boolean isKnownSessionAnomaly(SessionAnomalyKey key) {
    return key != null && SESSION_ANOMALIES.containsKey(key);
  }

  /**
   * 检查轮次信号键是否已注册。
   *
   * @param key 信号键
   * @return 已注册时返回 true
   */
  public static boolean isKnownRoundSignal(RoundSignalKey key) {
    return key != null && ROUND_SIGNALS.containsKey(key);
  }

  /**
   * 会话级异常定义。
   *
   * @param key 异常键
   * @param severityLevels 支持的严重度级别集合
   */
  public record AnomalyDefinition(SessionAnomalyKey key, Set<AnomalySeverity> severityLevels) {
    /**
     * 紧凑构造器，验证定义不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     * @throws IllegalArgumentException 当严重度集合为空时
     */
    public AnomalyDefinition {
      Objects.requireNonNull(key, "key 不得为 null");
      Objects.requireNonNull(severityLevels, "severityLevels 不得为 null");
      if (severityLevels.isEmpty()) {
        throw new IllegalArgumentException("severityLevels 不得为空");
      }
      severityLevels = Collections.unmodifiableSet(EnumSet.copyOf(severityLevels));
    }

    /**
     * 检查是否支持指定严重度。
     *
     * @param severity 严重度
     * @return 支持该严重度时返回 true
     */
    public boolean supportsSeverity(AnomalySeverity severity) {
      return severityLevels.contains(severity);
    }
  }

  /**
   * 轮次级信号定义。
   *
   * @param key 信号键
   * @param severityLevels 支持的严重度级别集合
   */
  public record SignalDefinition(RoundSignalKey key, Set<AnomalySeverity> severityLevels) {
    /**
     * 紧凑构造器，验证定义不变量。
     *
     * @throws NullPointerException 当必填字段为 null 时
     * @throws IllegalArgumentException 当严重度集合为空时
     */
    public SignalDefinition {
      Objects.requireNonNull(key, "key 不得为 null");
      Objects.requireNonNull(severityLevels, "severityLevels 不得为 null");
      if (severityLevels.isEmpty()) {
        throw new IllegalArgumentException("severityLevels 不得为空");
      }
      severityLevels = Collections.unmodifiableSet(EnumSet.copyOf(severityLevels));
    }

    /**
     * 检查是否支持指定严重度。
     *
     * @param severity 严重度
     * @return 支持该严重度时返回 true
     */
    public boolean supportsSeverity(AnomalySeverity severity) {
      return severityLevels.contains(severity);
    }
  }
}
