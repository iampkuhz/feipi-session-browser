package com.feipi.session.browser.scan.engine;

import com.feipi.session.browser.index.api.write.ScanFailure;
import com.feipi.session.browser.source.spi.SourceId;
import java.time.Clock;
import java.util.ArrayList;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.concurrent.CancellationException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;
import java.util.function.Supplier;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 分层后台增量扫描调度器。
 *
 * <p>支持 hot 和 warm 两个扫描层级，各层有独立的窗口（max age）和间隔配置。 使用 {@link ScheduledExecutorService} 驱动定时检查，不使用
 * while/sleep 循环。
 *
 * <p>每个调度 tick 最多选择一个层级执行：warm 到期时优先 warm，否则 hot。 绝不顺序执行两个层级。
 *
 * <p>通过 {@link ScanLock} 实现跨进程互斥，确保同一时刻最多只有一个扫描在运行。 支持 {@link ScanCancelToken} 取消当前扫描和优雅 shutdown。
 *
 * <p>无引导扫描（bootstrap）：启动后直接按间隔调度 hot/warm。
 *
 * <p>生命周期：{@link #start()} 启动调度 → 定时检查层级需求 → 获取锁 → 执行单层级扫描 → {@link #shutdown()} 停止。
 */
public final class BackgroundScanner {

  private static final Logger log = LoggerFactory.getLogger(BackgroundScanner.class);

  /** 调度检查频率（毫秒）。每 tick 检查一次是否有层级需要扫描。 */
  private static final long TICK_MS = 1000;

  private static final int MAX_FAILURE_SAMPLES = 12;
  private static final Pattern SAFE_LOG_SOURCE = Pattern.compile("[A-Za-z0-9_-]{1,40}");
  private static final Pattern SAFE_LOG_PHASE = Pattern.compile("[A-Z][A-Z0-9_]{0,39}");
  private static final Pattern SAFE_LOG_CODE = Pattern.compile("[A-Z][A-Z0-9_]{0,79}");

  private final TierConfig hotTier;
  private final TierConfig warmTier;
  private final ScanLock scanLock;
  private final Consumer<ScanCancelToken> hotAction;
  private final Consumer<ScanCancelToken> warmAction;
  private final Supplier<IncrementalScanSummary> summarySupplier;
  private final Clock clock;

  private final ScheduledExecutorService scheduler;
  private volatile java.util.concurrent.ScheduledFuture<?> scheduledFuture;
  private volatile long lastHotScanMs;
  private volatile long lastWarmScanMs;
  private volatile boolean running;
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
    this(hotTier, warmTier, scanLock, hotAction, warmAction, () -> null, clock);
  }

  /**
   * 创建支持扫描摘要回调的后台扫描调度器。
   *
   * <p>每次扫描完成后，通过 {@code summarySupplier} 获取最新的 {@link IncrementalScanSummary}， 用于输出 INFO 摘要日志。
   *
   * @param hotTier hot 层级配置
   * @param warmTier warm 层级配置
   * @param scanLock 跨进程扫描锁
   * @param hotAction 接收当前取消令牌的 hot 层级扫描动作
   * @param warmAction 接收当前取消令牌的 warm 层级扫描动作
   * @param summarySupplier 获取最新扫描摘要的提供者
   * @param clock 时间源
   */
  public BackgroundScanner(
      TierConfig hotTier,
      TierConfig warmTier,
      ScanLock scanLock,
      Consumer<ScanCancelToken> hotAction,
      Consumer<ScanCancelToken> warmAction,
      Supplier<IncrementalScanSummary> summarySupplier,
      Clock clock) {
    this.hotTier = Objects.requireNonNull(hotTier, "hotTier 不得为 null");
    this.warmTier = Objects.requireNonNull(warmTier, "warmTier 不得为 null");
    this.scanLock = Objects.requireNonNull(scanLock, "scanLock 不得为 null");
    this.hotAction = Objects.requireNonNull(hotAction, "hotAction 不得为 null");
    this.warmAction = Objects.requireNonNull(warmAction, "warmAction 不得为 null");
    this.summarySupplier = Objects.requireNonNull(summarySupplier, "summarySupplier 不得为 null");
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

  /** 启动后台调度，直接按 hot/warm 间隔调度，无引导扫描。 */
  public synchronized void start() {
    if (running || scheduler.isShutdown()) {
      return;
    }
    running = true;
    long now = clock.millis();
    // hot 立即可执行：设置 lastHotScanMs 使 (now - lastHotScanMs) >= hotInterval
    lastHotScanMs = now - hotTier.intervalSeconds() * 1000;
    // warm 首次约 300 秒后到期：设置 lastWarmScanMs 使 warm 在 start+300s 时到期
    lastWarmScanMs = now - warmTier.intervalSeconds() * 1000 + 300_000;
    scheduledFuture =
        scheduler.scheduleWithFixedDelay(this::checkAndScanSafe, 0, TICK_MS, TimeUnit.MILLISECONDS);
    log.info(
        "后台扫描调度器已启动: hotWindow={}s hotInterval={}s warmWindow={}s warmInterval={}s",
        hotTier.windowSeconds(),
        hotTier.intervalSeconds(),
        warmTier.windowSeconds(),
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

  /**
   * 调度任务安全包装。捕获 Throwable 确保致命错误可见：RuntimeException 记录 WARN 并继续调度； Error（OOM、StackOverflowError
   * 等）记录 ERROR 后设置 {@code fatalError} 标志并重新抛出， 由 {@link #isRunning()} 通过 Future 状态感知调度终止。
   */
  void checkAndScanSafe() {
    ScanFatalDiagnostics.clearReported();
    try {
      checkAndScan();
    } catch (RuntimeException e) {
      log.warn("调度检查异常，后续调度继续: {}", e.getMessage(), e);
    } catch (Error e) {
      fatalError = true;
      ScanFatalDiagnostics.reportAtBoundary(e, "background", "SCHEDULER");
      throw e;
    } finally {
      ScanFatalDiagnostics.clearReported();
    }
  }

  /** 调度 tick：选择唯一一个到期层级执行。warm 到期时优先 warm，否则 hot。 绝不顺序执行两个层级。 */
  void checkAndScan() {
    if (fatalError) {
      return;
    }
    if (scheduler.isShutdown()) {
      return;
    }
    long now = clock.millis();
    boolean needsHot = (now - lastHotScanMs) >= hotTier.intervalSeconds() * 1000;
    boolean needsWarm = (now - lastWarmScanMs) >= warmTier.intervalSeconds() * 1000;

    if (!needsHot && !needsWarm) {
      return;
    }

    // warm 到期时优先 warm，否则 hot；每 tick 只选一个层级
    boolean runWarm = needsWarm;
    boolean runHot = needsHot && !needsWarm;

    executeScan(runHot, runWarm);
  }

  /** 执行扫描：获取锁 → 运行唯一一个层级 → 更新时间戳。 */
  @SuppressWarnings("PMD.CloseResource") // handle 通过 try-with-resources 关闭
  private void executeScan(boolean runHot, boolean runWarm) {
    ScanLock.ScanLockHandle handle;
    try {
      handle = scanLock.tryLock("background scan");
    } catch (Exception e) {
      log.warn("后台扫描获取锁失败", e);
      updateTimestamps(runHot, runWarm);
      return;
    }

    if (handle == null) {
      log.debug("后台扫描跳过：另一个扫描持有锁");
      updateTimestamps(runHot, runWarm);
      return;
    }

    ScanCancelToken token = new ScanCancelToken();
    currentCancelToken = token;
    try (handle) {
      runWithHandle(token, runHot, runWarm);
    } finally {
      currentCancelToken = null;
    }
  }

  /**
   * 在持有锁期间执行唯一一个层级的扫描动作，仅在成功完成时输出 INFO 摘要。
   *
   * @param token 取消令牌
   * @param runHot 是否执行 hot 层级
   * @param runWarm 是否执行 warm 层级
   */
  private void runWithHandle(ScanCancelToken token, boolean runHot, boolean runWarm) {
    String tierName;
    long windowSeconds;
    boolean success = false;
    if (runWarm) {
      tierName = "warm";
      windowSeconds = warmTier.windowSeconds();
      log.debug("开始 warm 层级扫描");
      try {
        warmAction.accept(token);
        success = !token.isCancelled();
      } catch (CancellationException e) {
        log.debug("warm 层级扫描已取消");
      } catch (RuntimeException e) {
        log.warn("warm 层级扫描失败", e);
      }
      long now = clock.millis();
      lastWarmScanMs = now;
      // warm 覆盖 0-24h 范围，已包含 hot 的 0-5min 范围，重置 hot 防止下一 tick 补跑
      lastHotScanMs = now;
    } else {
      tierName = "hot";
      windowSeconds = hotTier.windowSeconds();
      log.debug("开始 hot 层级扫描");
      try {
        hotAction.accept(token);
        success = !token.isCancelled();
      } catch (CancellationException e) {
        log.debug("hot 层级扫描已取消");
      } catch (RuntimeException e) {
        log.warn("hot 层级扫描失败", e);
      }
      lastHotScanMs = clock.millis();
    }

    if (success) {
      IncrementalScanSummary summary = summarySupplier.get();
      if (summary != null && (summary.errorCount() > 0 || !summary.issues().isEmpty())) {
        logScanFailureSummary(tierName, windowSeconds, summary);
      } else {
        log.debug("{} 层级扫描完成", tierName);
        logScanSummary(tierName, windowSeconds, summary);
      }
    }
  }

  /** 输出后台扫描完成 INFO 摘要：实际模式、窗口、成功更新数和按来源计数。 */
  private void logScanSummary(String tierName, long windowSeconds, IncrementalScanSummary summary) {
    if (summary == null) {
      log.info("后台扫描完成: tier={} window={}s", tierName, windowSeconds);
      return;
    }
    StringBuilder perSource = new StringBuilder();
    for (Map.Entry<SourceId, Integer> entry : summary.perSourceCount().entrySet()) {
      if (perSource.length() > 0) {
        perSource.append(' ');
      }
      perSource.append(entry.getKey().getValue()).append(':').append(entry.getValue());
    }
    String groupedUpdates = perSource.length() > 0 ? perSource.toString() : "none";
    if (summary.rebuildTriggered()) {
      log.info(
          "后台扫描完成: tier=full window=all updated={} perSource={}",
          summary.successCount(),
          groupedUpdates);
    } else {
      log.info(
          "后台扫描完成: tier={} window={}s updated={} perSource={}",
          tierName,
          windowSeconds,
          summary.successCount(),
          groupedUpdates);
    }
  }

  /** 输出不含会话键、路径或原始诊断内容的后台失败定位摘要。 */
  private static void logScanFailureSummary(
      String tierName, long windowSeconds, IncrementalScanSummary summary) {
    Map<String, Integer> failureCounts = new TreeMap<>();
    Map<String, String> hints = new TreeMap<>();
    var samples = new ArrayList<String>(MAX_FAILURE_SAMPLES);
    for (ScanFailure failure : ScanDiagnostics.failures(summary.issues())) {
      String label = failureLabel(failure);
      failureCounts.merge(label, 1, Integer::sum);
      if (samples.size() < MAX_FAILURE_SAMPLES) {
        samples.add(label + (failure.line() > 0 ? "@" + failure.line() : ""));
      }
      String hint = ScanDiagnostics.hint(failure.code());
      if (!hint.isEmpty() && hints.size() < MAX_FAILURE_SAMPLES) hints.put(failure.code(), hint);
    }
    log.warn(
        "后台扫描失败结果: tier={} window={}s scanLogId={} candidates={} errors={} issues={}"
            + " failureCounts={} samples={} hints={}",
        tierName,
        windowSeconds,
        summary.scanLogId(),
        summary.totalCandidates(),
        summary.errorCount(),
        summary.issues().size(),
        failureCounts,
        samples,
        hints);
  }

  private static String failureLabel(ScanFailure failure) {
    return safeLogValue(failure.source(), SAFE_LOG_SOURCE, "unknown")
        + "/"
        + safeLogValue(failure.phase(), SAFE_LOG_PHASE, "UNKNOWN")
        + "/"
        + safeLogValue(failure.code(), SAFE_LOG_CODE, "SCAN_FAILED");
  }

  private static String safeLogValue(String value, Pattern allowed, String fallback) {
    return value != null && allowed.matcher(value).matches() ? value : fallback;
  }

  /** 更新层级时间戳（锁不可用时也更新，避免频繁重试）。 */
  private void updateTimestamps(boolean needsHot, boolean needsWarm) {
    long now = clock.millis();
    if (needsHot) {
      lastHotScanMs = now;
    }
    if (needsWarm) {
      lastWarmScanMs = now;
      // warm 覆盖 0-24h 范围，已包含 hot 的 0-5min 范围，重置 hot 防止下一 tick 补跑
      lastHotScanMs = now;
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

  // 仅供测试使用：设置时间戳而不启动调度器
  void setLastHotScanMsForTest(long ms) {
    this.lastHotScanMs = ms;
  }

  void setLastWarmScanMsForTest(long ms) {
    this.lastWarmScanMs = ms;
  }

  boolean isSchedulerFutureDone() {
    java.util.concurrent.ScheduledFuture<?> future = scheduledFuture;
    return future != null && future.isDone();
  }

  boolean hasFatalError() {
    return fatalError;
  }
}
