package com.feipi.session.browser.scan.engine;

import java.time.Clock;
import java.util.Objects;
import java.util.concurrent.CancellationException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
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

  /** 引导扫描最大重试次数。 */
  private static final int MAX_BOOTSTRAP_RETRIES = 3;

  /** 引导扫描重试间隔（毫秒）。 */
  private static final long BOOTSTRAP_RETRY_DELAY_MS = 5000;

  private final TierConfig hotTier;
  private final TierConfig warmTier;
  private final ScanLock scanLock;
  private final Consumer<ScanCancelToken> hotAction;
  private final Consumer<ScanCancelToken> warmAction;
  private final Consumer<ScanCancelToken> bootstrapAction;
  private final Clock clock;

  private final ScheduledExecutorService scheduler;
  private volatile java.util.concurrent.ScheduledFuture<?> scheduledFuture;
  private volatile long lastHotScanMs;
  private volatile long lastWarmScanMs;
  private volatile boolean running;
  private volatile boolean bootstrapDone;
  private volatile int bootstrapRetryCount;
  private volatile boolean bootstrapFinished;
  private volatile long nextBootstrapMs;
  private volatile ScanCancelToken currentCancelToken;
  private volatile boolean fatalError;

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
    this(
        hotTier,
        warmTier,
        scanLock,
        ignoreCancelToken(hotAction, "hotAction 不得为 null"),
        ignoreCancelToken(warmAction, "warmAction 不得为 null"),
        clock);
  }

  /**
   * 创建支持协作取消的后台扫描调度器。
   *
   * @param hotTier hot 层级配置
   * @param warmTier warm 层级配置
   * @param scanLock 跨进程扫描锁
   * @param hotAction 接收当前取消令牌的 hot 层级扫描动作
   * @param warmAction 接收当前取消令牌的 warm 层级扫描动作
   * @param clock 时间源
   */
  public BackgroundScanner(
      TierConfig hotTier,
      TierConfig warmTier,
      ScanLock scanLock,
      Consumer<ScanCancelToken> hotAction,
      Consumer<ScanCancelToken> warmAction,
      Clock clock) {
    this(hotTier, warmTier, scanLock, hotAction, warmAction, null, clock);
  }

  /**
   * 创建支持引导扫描和协作取消的后台扫描调度器。
   *
   * <p>引导动作在首次 {@link #start()} 时异步执行一次（无年龄窗口），完成后按 hot/warm 间隔正常调度。
   *
   * @param hotTier hot 层级配置
   * @param warmTier warm 层级配置
   * @param scanLock 跨进程扫描锁
   * @param hotAction 接收当前取消令牌的 hot 层级扫描动作
   * @param warmAction 接收当前取消令牌的 warm 层级扫描动作
   * @param bootstrapAction 可选的引导扫描动作，null 表示无引导
   * @param clock 时间源
   */
  public BackgroundScanner(
      TierConfig hotTier,
      TierConfig warmTier,
      ScanLock scanLock,
      Consumer<ScanCancelToken> hotAction,
      Consumer<ScanCancelToken> warmAction,
      Consumer<ScanCancelToken> bootstrapAction,
      Clock clock) {
    this.hotTier = Objects.requireNonNull(hotTier, "hotTier 不得为 null");
    this.warmTier = Objects.requireNonNull(warmTier, "warmTier 不得为 null");
    this.scanLock = Objects.requireNonNull(scanLock, "scanLock 不得为 null");
    this.hotAction = Objects.requireNonNull(hotAction, "hotAction 不得为 null");
    this.warmAction = Objects.requireNonNull(warmAction, "warmAction 不得为 null");
    this.bootstrapAction = bootstrapAction;
    this.bootstrapFinished = bootstrapAction == null;
    this.bootstrapDone = bootstrapAction == null;
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

  /**
   * 使用默认系统时钟创建支持协作取消的后台扫描调度器。
   *
   * @param hotTier hot 层级配置
   * @param warmTier warm 层级配置
   * @param scanLock 跨进程扫描锁
   * @param hotAction 接收当前取消令牌的 hot 层级扫描动作
   * @param warmAction 接收当前取消令牌的 warm 层级扫描动作
   */
  public BackgroundScanner(
      TierConfig hotTier,
      TierConfig warmTier,
      ScanLock scanLock,
      Consumer<ScanCancelToken> hotAction,
      Consumer<ScanCancelToken> warmAction) {
    this(hotTier, warmTier, scanLock, hotAction, warmAction, Clock.systemUTC());
  }

  /** 启动后台调度。有引导动作时先异步执行引导，再按间隔调度 hot/warm。 */
  public synchronized void start() {
    if (running || scheduler.isShutdown()) {
      return;
    }
    running = true;
    scheduledFuture =
        scheduler.scheduleWithFixedDelay(this::checkAndScanSafe, 0, TICK_MS, TimeUnit.MILLISECONDS);
    log.info(
        "后台扫描调度器已启动: bootstrap={} hotInterval={}s warmInterval={}s",
        bootstrapAction != null,
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

  /**
   * 查询调度器是否正在运行。
   *
   * <p>同时检查 running 标志和调度 Future 状态。若调度任务因未捕获的 Error 终止， Future 会标记为 done， 此方法返回 false，避免假装仍在运行。
   */
  public boolean isRunning() {
    java.util.concurrent.ScheduledFuture<?> future = scheduledFuture;
    return running && (future == null || !future.isDone());
  }

  private void doShutdown(Long timeout, TimeUnit unit) {
    synchronized (this) {
      running = false;
      cancelCurrentScan();
      scheduler.shutdown();
    }
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

  /** 引导扫描：获取锁 → 执行一次 → 启动常规调度。失败时有界重试。 */
  private void runBootstrap() {
    log.info("开始引导扫描 (尝试 {}/{})", bootstrapRetryCount + 1, MAX_BOOTSTRAP_RETRIES + 1);
    boolean success = false;
    try (ScanLock.ScanLockHandle handle = scanLock.tryLock("bootstrap scan")) {
      if (handle == null) {
        log.info("引导扫描跳过：另一个扫描持有锁");
      } else {
        ScanCancelToken token = new ScanCancelToken();
        currentCancelToken = token;
        if (scheduler.isShutdown()) {
          token.cancel();
        }
        token.throwIfCancelled();
        bootstrapAction.accept(token);
        token.throwIfCancelled();
        log.info("引导扫描完成");
        success = true;
      }
    } catch (CancellationException e) {
      log.info("引导扫描已取消");
    } catch (Exception e) {
      log.warn("引导扫描失败", e);
    } finally {
      currentCancelToken = null;
    }

    scheduleBootstrapRetryOrFinish(success);
  }

  /** 引导扫描成功或耗尽重试后，延迟一个完整层级间隔再开始周期扫描。 */
  private void scheduleBootstrapRetryOrFinish(boolean success) {
    if (scheduler.isShutdown()) {
      return;
    }
    if (success || bootstrapRetryCount >= MAX_BOOTSTRAP_RETRIES) {
      bootstrapDone = success;
      bootstrapFinished = true;
      updateTimestamps(true, true);
      if (!success) {
        log.warn("引导扫描重试已耗尽，后续按 hot/warm 间隔恢复");
      }
    } else {
      bootstrapRetryCount++;
      nextBootstrapMs = clock.millis() + BOOTSTRAP_RETRY_DELAY_MS;
      log.info("引导扫描将在 {}ms 后重试", BOOTSTRAP_RETRY_DELAY_MS);
    }
  }

  /**
   * 调度任务安全包装。捕获 Throwable 确保致命错误可见：RuntimeException 记录 WARN 并继续调度； Error（OOM、StackOverflowError
   * 等）记录 ERROR 后设置 {@code fatalError} 标志并重新抛出， 由 {@link #isRunning()} 通过 Future 状态感知调度终止。
   */
  void checkAndScanSafe() {
    try {
      checkAndScan();
    } catch (RuntimeException e) {
      log.warn("调度检查异常，后续调度继续: {}", e.getMessage(), e);
    } catch (Error e) {
      fatalError = true;
      log.error("调度任务致命错误 [{}]: {}", e.getClass().getName(), e.getMessage(), e);
      throw e;
    }
  }

  /** 调度 tick：检查是否有层级需要扫描。致命错误后跳过。 */
  void checkAndScan() {
    if (fatalError) {
      return;
    }
    if (bootstrapAction != null && scheduler.isShutdown()) {
      return;
    }
    long now = clock.millis();
    if (!bootstrapFinished) {
      if (now >= nextBootstrapMs) {
        runBootstrap();
      }
      return;
    }
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
      log.info("开始 hot 层级扫描");
      try {
        hotAction.accept(token);
        log.info("hot 层级扫描完成");
      } catch (CancellationException e) {
        log.info("hot 层级扫描已取消");
      } catch (RuntimeException e) {
        log.warn("hot 层级扫描失败", e);
      }
      lastHotScanMs = clock.millis();
    }

    if (needsWarm && !token.isCancelled()) {
      log.info("开始 warm 层级扫描");
      try {
        warmAction.accept(token);
        log.info("warm 层级扫描完成");
      } catch (CancellationException e) {
        log.info("warm 层级扫描已取消");
      } catch (RuntimeException e) {
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

  private static Consumer<ScanCancelToken> ignoreCancelToken(Runnable action, String message) {
    Objects.requireNonNull(action, message);
    return ignored -> action.run();
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
    } catch (RuntimeException e) {
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

  boolean bootstrapDone() {
    return bootstrapDone;
  }

  boolean isSchedulerFutureDone() {
    java.util.concurrent.ScheduledFuture<?> future = scheduledFuture;
    return future != null && future.isDone();
  }

  boolean hasFatalError() {
    return fatalError;
  }
}
