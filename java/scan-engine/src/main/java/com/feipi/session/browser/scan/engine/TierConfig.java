package com.feipi.session.browser.scan.engine;

/**
 * 分层扫描窗口配置。
 *
 * <p>定义单个扫描层级的时间窗口和调度间隔。hot 层级扫描最近活跃的会话， warm 层级扫描稍早但仍可能变化的会话。cold 会话由显式 full scan 负责。
 *
 * <p>不可变、线程安全。
 *
 * @param windowSeconds 层级窗口大小（秒），只扫描此时间范围内的会话
 * @param intervalSeconds 层级扫描间隔（秒），两次扫描之间的最小等待时间
 */
public record TierConfig(long windowSeconds, long intervalSeconds) {

  /** hot 层级默认窗口：30 分钟。 */
  public static final long DEFAULT_HOT_WINDOW = 30 * 60;

  /** hot 层级默认间隔：30 秒。 */
  public static final long DEFAULT_HOT_INTERVAL = 30;

  /** warm 层级默认窗口：24 小时。 */
  public static final long DEFAULT_WARM_WINDOW = 24 * 3600;

  /** warm 层级默认间隔：5 分钟。 */
  public static final long DEFAULT_WARM_INTERVAL = 5 * 60;

  /** 默认 hot 层级配置。 */
  public static final TierConfig DEFAULT_HOT =
      new TierConfig(DEFAULT_HOT_WINDOW, DEFAULT_HOT_INTERVAL);

  /** 默认 warm 层级配置。 */
  public static final TierConfig DEFAULT_WARM =
      new TierConfig(DEFAULT_WARM_WINDOW, DEFAULT_WARM_INTERVAL);

  /**
   * 紧凑构造器，验证参数合法性。
   *
   * @throws IllegalArgumentException 当窗口或间隔非正时
   */
  public TierConfig {
    if (windowSeconds <= 0) {
      throw new IllegalArgumentException("windowSeconds 必须 > 0: " + windowSeconds);
    }
    if (intervalSeconds <= 0) {
      throw new IllegalArgumentException("intervalSeconds 必须 > 0: " + intervalSeconds);
    }
  }
}
