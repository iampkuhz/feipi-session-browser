package com.feipi.session.browser.scan.engine;

import java.time.Clock;
import java.util.Objects;
import java.util.concurrent.CancellationException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 分层后台增量扫描调度器。
 *
 * <p>支持 hot 和 warm 两个扫描层级，各层有独立的窗口（max age）和间隔配置。 使用 {@link ScheduledExecutorService} 驱动定时检查，不使用
 * while/sleep 循环。
 *
 * <p>通过 {@link ScanLock} 实现跨进程互斥，确保同一时刻最多只有一个扫描在运行。 支持 {@link ScanCancelToken} 取消当前扫描和优雅 shutdown。
 *
 * <p>生命周期：{@link #start()} 启动调度 → 定时检查层级需求 → 获取锁 → 执行扫描 → {@link #shutdown()} 停止。
 */
public final class BackgroundScanner {

  private static final Logger log = LoggerFactory.getLogger(BackgroundScanner.class);

  /** 调度检查频率（毫秒）。每 tick 检查一次是否有层级需要扫描。 */
  private static final long TICK_MS = 1000;

  private final TierConfig hotTier;
  private final TierConfig warmTier;
  private final ScanLock scanLock;
  private final Runnable hotAction;
  private final Runnable warmAction;
  private final Clock clock;

  private final ScheduledExecutorService scheduler;
  private volatile long lastHotScanMs;
  private volatile long lastWarmScanMs;
  private volatile boolean running;
  private volatile ScanCancelToken currentCancelToken;

  /**
   * 创建后台扫描调度器。
   *
   * @param hotTier hot 层级配置
   * @param warmTier warm 层级配置
   * @param scanLock 跨进程扫描锁
   * @param hotAction hot 层级扫描动作
   * @param warmAction warm 层级扫描动作
   * @param clock 时间源
   */
  public BackgroundScanner(
      TierConfig hotTier,
      TierConfig warmTier,
      ScanLock scanLock,
      Runnable hotAction,
      Runnable warmAction,
      Clock clock) {
    this.hotTier = Objects.requireNonNull(hotTier, "hotTier 不得为 null");
    this.warmTier = Objects.requireNonNull(warmTier, "warmTier 不得为 null");
    this.scanLock = Objects.requireNonNull(scanLock, "scanLock 不得为 null");
    this.hotAction = Objects.requireNonNull(hotAction, "hotAction 不得为 null");
    this.warmAction = Objects.requireNonNull(warmAction, "warmAction 不得为 null");
    this.clock = Objects.requireNonNull(clock, "clock 不得为 null");

    AtomicInteger threadCount = new AtomicInteger(0);
    ThreadFactory factory =
        r -> {
          Thread t = new Thread(r, "background-scanner-" + threadCount.incrementAndGet());
          t.setDaemon(true);
          return t;
        };
    this.scheduler = Executors.newSingleThreadScheduledExecutor(factory);
  }

  /**
   * 使用默认系统时钟创建。
   *
   * @param hotTier hot 层级配置
   * @param warmTier warm 层级配置
   * @param scanLock 跨进程扫描锁
   * @param hotAction hot 层级扫描动作
   * @param warmAction warm 层级扫描动作
   */
  public BackgroundScanner(
      TierConfig hotTier,
      TierConfig warmTier,
      ScanLock scanLock,
      Runnable hotAction,
      Runnable warmAction) {
    this(hotTier, warmTier, scanLock, hotAction, warmAction, Clock.systemUTC());
  }

  /** 启动后台调度。启动后立即调度首次检查。 */
  public void start() {
    if (running) {
      return;
    }
    running = true;
    lastHotScanMs = 0;
    lastWarmScanMs = 0;
    scheduler.scheduleWithFixedDelay(this::checkAndScan, 0, TICK_MS, TimeUnit.MILLISECONDS);
    log.info(
        "后台扫描调度器已启动: hotInterval={}s warmInterval={}s",
        hotTier.intervalSeconds(),
        warmTier.intervalSeconds());
  }

  /**
   * 无限期优雅关闭。等待当前扫描完成。
   *
   * @see #shutdown(long, TimeUnit)
   */
  public void shutdown() {
    doShutdown(null, null);
  }

  /**
   * 优雅关闭，等待指定超时。
   *
   * <p>取消当前扫描（如果正在执行），等待调度器终止。 超时后强制关闭。
   *
   * @param timeout 最大等待时间
   * @param unit 时间单位
   */
  public void shutdown(long timeout, TimeUnit unit) {
    doShutdown(timeout, unit);
  }

  /** 取消当前正在执行的扫描。 */
  public void cancelCurrentScan() {
    ScanCancelToken token = currentCancelToken;
    if (token != null) {
      token.cancel();
    }
  }

  /** 查询调度器是否正在运行。 */
  public boolean isRunning() {
    return running;
  }

  private void doShutdown(Long timeout, TimeUnit unit) {
    if (!running) {
      return;
    }
    running = false;
    cancelCurrentScan();
    scheduler.shutdown();
    try {
      if (timeout != null && unit != null) {
        if (!scheduler.awaitTermination(timeout, unit)) {
          scheduler.shutdownNow();
          log.warn("后台扫描调度器未在 {} {} 内终止，强制关闭", timeout, unit);
        }
      } else {
        scheduler.awaitTermination(Long.MAX_VALUE, TimeUnit.MILLISECONDS);
      }
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      scheduler.shutdownNow();
    }
    log.info("后台扫描调度器已停止");
  }

  /** 调度 tick：检查是否有层级需要扫描。 */
  void checkAndScan() {
    long now = clock.millis();
    boolean needsHot = (now - lastHotScanMs) >= hotTier.intervalSeconds() * 1000;
    boolean needsWarm = (now - lastWarmScanMs) >= warmTier.intervalSeconds() * 1000;

    if (!needsHot && !needsWarm) {
      return;
    }

    executeScan(needsHot, needsWarm);
  }

  /** 执行扫描：获取锁 → 运行 → 更新时间戳。 */
  @SuppressWarnings("PMD.CloseResource") // handle 通过 try-with-resources 关闭
  private void executeScan(boolean needsHot, boolean needsWarm) {
    ScanLock.ScanLockHandle handle;
    try {
      handle = scanLock.tryLock("background scan");
    } catch (Exception e) {
      log.warn("后台扫描获取锁失败", e);
      updateTimestamps(needsHot, needsWarm);
      return;
    }

    if (handle == null) {
      log.debug("后台扫描跳过：另一个扫描持有锁");
      updateTimestamps(needsHot, needsWarm);
      return;
    }

    ScanCancelToken token = new ScanCancelToken();
    currentCancelToken = token;
    try (handle) {
      runWithHandle(handle, token, needsHot, needsWarm);
    } finally {
      currentCancelToken = null;
    }
  }

  /**
   * 在持有锁期间执行扫描动作。
   *
   * @param handle 扫描锁句柄
   * @param token 取消令牌
   * @param needsHot 是否需要 hot 层级扫描
   * @param needsWarm 是否需要 warm 层级扫描
   */
  private void runWithHandle(
      ScanLock.ScanLockHandle handle, ScanCancelToken token, boolean needsHot, boolean needsWarm) {
    if (needsHot) {
      log.debug("执行 hot 层级扫描: window={}s", hotTier.windowSeconds());
      try {
        hotAction.run();
      } catch (CancellationException e) {
        log.info("hot 层级扫描已取消");
      } catch (Exception e) {
        log.warn("hot 层级扫描失败", e);
      }
      lastHotScanMs = clock.millis();
    }

    if (needsWarm && !token.isCancelled()) {
      log.debug("执行 warm 层级扫描: window={}s", warmTier.windowSeconds());
      try {
        warmAction.run();
      } catch (CancellationException e) {
        log.info("warm 层级扫描已取消");
      } catch (Exception e) {
        log.warn("warm 层级扫描失败", e);
      }
      lastWarmScanMs = clock.millis();
    }
  }

  /** 更新层级时间戳（锁不可用时也更新，避免频繁重试）。 */
  private void updateTimestamps(boolean needsHot, boolean needsWarm) {
    long now = clock.millis();
    if (needsHot) {
      lastHotScanMs = now;
    }
    if (needsWarm) {
      lastWarmScanMs = now;
    }
  }

  /**
   * 执行单次启动扫描。
   *
   * <p>在服务器启动前运行一次增量扫描，使用非阻塞锁。 锁被占用时跳过，不阻塞启动。
   *
   * @param scanAction 扫描动作
   * @param scanLock 跨进程扫描锁
   * @return 是否成功执行
   */
  public static boolean runStartupScan(Runnable scanAction, ScanLock scanLock) {
    Objects.requireNonNull(scanAction, "scanAction 不得为 null");
    Objects.requireNonNull(scanLock, "scanLock 不得为 null");

    ScanLock.ScanLockHandle handle;
    try {
      handle = scanLock.tryLock("startup incremental scan");
    } catch (Exception e) {
      log.warn("启动扫描获取锁失败", e);
      return false;
    }

    if (handle == null) {
      log.info("启动扫描跳过：另一个扫描持有锁");
      return false;
    }

    return runWithLock(handle, scanAction);
  }

  /** 在锁保护下执行扫描动作。 */
  private static boolean runWithLock(ScanLock.ScanLockHandle handle, Runnable scanAction) {
    try (handle) {
      scanAction.run();
      log.info("启动扫描完成");
      return true;
    } catch (Exception e) {
      log.warn("启动扫描失败", e);
      return false;
    }
  }

  // 仅供测试使用
  long lastHotScanMs() {
    return lastHotScanMs;
  }

  long lastWarmScanMs() {
    return lastWarmScanMs;
  }
}
