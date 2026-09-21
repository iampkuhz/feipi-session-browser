package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/**
 * {@link BackgroundScanner} 单元测试。
 *
 * <p>覆盖分层调度、唯一 tier 选择（warm 优先）、warm 后 hot 不补跑、启动后 hot 立即执行/warm 延迟 300s、 锁互斥、取消和 shutdown 语义。 使用
 * {@link FixedClock} 控制时间推进，不依赖真实 sleep。
 */
class BackgroundScannerTest {

  @TempDir java.nio.file.Path tempDir;

  @Test
  void hotRunsFirstAtStartup() throws InterruptedException {
    // 启动后 hot 立即可执行，warm 延迟 300s
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    CountDownLatch hotCompleted = new CountDownLatch(1);
    FixedClock clock = new FixedClock(1_000_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 120), // hot: 120 秒间隔
            new TierConfig(86400, 3600), // warm: 3600 秒间隔
            scanLock,
            () -> {
              hotCount.incrementAndGet();
              hotCompleted.countDown();
            },
            warmCount::incrementAndGet,
            clock);

    try {
      scanner.start();
      // 等待启动调度实际执行，不能把异步检查尚在进行误判为未扫描。
      assertThat(hotCompleted.await(2, TimeUnit.SECONDS)).isTrue();
      scanner.checkAndScan();
      assertThat(hotCount.get()).isEqualTo(1);
      assertThat(warmCount.get()).isZero();
    } finally {
      scanner.shutdown(1, TimeUnit.SECONDS);
    }
  }

  @Test
  void warmNotDueAt299sButDueAt300s() {
    // warm 在 299s 不执行，在 300s 执行
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(1_000_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 120),
            new TierConfig(86400, 3600),
            scanLock,
            hotCount::incrementAndGet,
            warmCount::incrementAndGet,
            clock);

    // 使用测试方法设置时间戳，模拟 start() 后的状态，但不启动调度器
    long now = 1_000_000;
    scanner.setLastHotScanMsForTest(now - 120_000); // hot 立即可执行
    scanner.setLastWarmScanMsForTest(now - 3_600_000 + 300_000); // warm 在 300s 后到期

    // 299s：warm 未到期
    clock.setMillis(1_000_000 + 299_000);
    scanner.checkAndScan();
    assertThat(warmCount.get()).isZero();

    // 300s：warm 到期
    clock.setMillis(1_000_000 + 300_000);
    scanner.checkAndScan();
    assertThat(warmCount.get()).isEqualTo(1);
    scanner.shutdown(1, TimeUnit.SECONDS);
  }

  @Test
  void warmCycleIs3600s() {
    // warm 周期 3600s：3599s 不执行，3600s 执行
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(1_000_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 120),
            new TierConfig(86400, 3600),
            scanLock,
            hotCount::incrementAndGet,
            warmCount::incrementAndGet,
            clock);

    // 使用测试方法设置时间戳，模拟 start() 后的状态
    long now = 1_000_000;
    scanner.setLastHotScanMsForTest(now - 120_000);
    scanner.setLastWarmScanMsForTest(now - 3_600_000 + 300_000);

    // 首次 warm 在 300s 执行
    clock.setMillis(1_000_000 + 300_000);
    scanner.checkAndScan();
    assertThat(warmCount.get()).isEqualTo(1);

    // 3599s 后（相对首次 warm）：warm 未到期
    clock.setMillis(1_000_000 + 300_000 + 3599_000);
    scanner.checkAndScan();
    assertThat(warmCount.get()).isEqualTo(1); // 仍为 1

    // 3600s 后：warm 到期
    clock.setMillis(1_000_000 + 300_000 + 3600_000);
    scanner.checkAndScan();
    assertThat(warmCount.get()).isEqualTo(2);
    scanner.shutdown(1, TimeUnit.SECONDS);
  }

  @Test
  void afterWarmRunsHotDoesNotRunOnNextTick() {
    // warm 执行后，下一 tick hot 不补跑
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(1_000_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 120),
            new TierConfig(86400, 3600),
            scanLock,
            hotCount::incrementAndGet,
            warmCount::incrementAndGet,
            clock);

    // 使用测试方法设置时间戳，模拟 start() 后的状态
    long now = 1_000_000;
    scanner.setLastHotScanMsForTest(now - 120_000);
    scanner.setLastWarmScanMsForTest(now - 3_600_000 + 300_000);

    // warm 在 300s 执行
    clock.setMillis(1_000_000 + 300_000);
    scanner.checkAndScan();
    assertThat(warmCount.get()).as("warm should have run").isEqualTo(1);
    assertThat(hotCount.get()).as("hot should not have run (warm priority)").isZero();

    // 下一 tick（+1s）：hot 不应补跑
    clock.setMillis(1_000_000 + 301_000);
    scanner.checkAndScan();
    assertThat(hotCount.get()).as("hot should not run after warm (warm covers hot range)").isZero();
    scanner.shutdown(1, TimeUnit.SECONDS);
  }

  @Test
  void checkAndScanRunsOnlyWarmWhenBothDue() {
    // warm 到期时优先 warm，绝不顺序执行两个 tier
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(600_000); // 10 分钟
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 30), // hot: 30 秒间隔
            new TierConfig(86400, 300), // warm: 300 秒间隔
            scanLock,
            hotCount::incrementAndGet,
            warmCount::incrementAndGet,
            clock);

    // 不调用 start()，lastScanMs=0，两个 tier 都到期
    scanner.checkAndScan();

    // warm 优先：只执行 warm，不执行 hot
    assertThat(warmCount.get()).isEqualTo(1);
    assertThat(hotCount.get()).isZero();
    scanner.shutdown(1, TimeUnit.SECONDS);
  }

  @Test
  void checkAndScanSkipsWhenNotDue() {
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(1_000_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 30), // hot: 30 秒间隔
            new TierConfig(86400, 300), // warm: 300 秒间隔
            scanLock,
            hotCount::incrementAndGet,
            warmCount::incrementAndGet,
            clock);

    // 使用测试方法设置时间戳，模拟 hot 刚执行过的状态
    long now = 1_000_000;
    scanner.setLastHotScanMsForTest(now); // hot 刚执行
    scanner.setLastWarmScanMsForTest(now); // warm 刚执行

    // 5 秒后：hot 未到期（需 30s），warm 未到期（需 300s）
    clock.setMillis(1_000_000 + 5_000);
    scanner.checkAndScan();
    assertThat(hotCount.get()).isZero();
    assertThat(warmCount.get()).isZero();
    scanner.shutdown(1, TimeUnit.SECONDS);
  }

  @Test
  void shutdownStopsScheduler() throws Exception {
    AtomicInteger count = new AtomicInteger();
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            TierConfig.DEFAULT_HOT,
            TierConfig.DEFAULT_WARM,
            scanLock,
            count::incrementAndGet,
            () -> {},
            clock);

    scanner.start();
    assertThat(scanner.isRunning()).isTrue();

    scanner.shutdown(2, TimeUnit.SECONDS);
    assertThat(scanner.isRunning()).isFalse();
  }

  @Test
  void shutdownCancelsRunningTokenAwareActionBeforeTimeout() throws Exception {
    CountDownLatch actionStarted = new CountDownLatch(1);
    CountDownLatch actionExited = new CountDownLatch(1);
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    // hot 在启动时立即可执行，循环动作放在 hot 位置
    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 30),
            new TierConfig(86400, 3600),
            scanLock,
            token -> {
              actionStarted.countDown();
              try {
                while (true) {
                  token.throwIfCancelled();
                  Thread.onSpinWait();
                }
              } finally {
                actionExited.countDown();
              }
            },
            token -> warmCount.incrementAndGet(),
            clock);

    scanner.start();
    assertThat(actionStarted.await(2, TimeUnit.SECONDS)).isTrue();

    scanner.shutdown(2, TimeUnit.SECONDS);

    assertThat(actionExited.getCount()).isZero();
    assertThat(warmCount.get()).isZero();
    assertThat(scanner.isRunning()).isFalse();
  }

  @Test
  void cancelCurrentScanSignalsTokenDuringScan() throws Exception {
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner[] scannerHolder = new BackgroundScanner[1];
    scannerHolder[0] =
        new BackgroundScanner(
            new TierConfig(300, 30),
            new TierConfig(86400, 300),
            scanLock,
            () -> {
              scannerHolder[0].cancelCurrentScan();
            },
            () -> {},
            clock);

    scannerHolder[0].start();
    scannerHolder[0].shutdown(1, TimeUnit.SECONDS);

    scannerHolder[0].checkAndScan();
  }

  @Test
  void startupScanRunsSuccessfully() {
    AtomicInteger count = new AtomicInteger();
    ScanLock scanLock = new ScanLock(tempDir);

    boolean result = BackgroundScanner.runStartupScan(count::incrementAndGet, scanLock);

    assertThat(result).isTrue();
    assertThat(count.get()).isEqualTo(1);
  }

  @Test
  void startupScanSkipsWhenLockHeld() throws Exception {
    AtomicInteger count = new AtomicInteger();
    ScanLock scanLock = new ScanLock(tempDir);

    ScanLock.ScanLockHandle holder = scanLock.acquire("holder", 1000);
    try {
      boolean result = BackgroundScanner.runStartupScan(count::incrementAndGet, scanLock);
      assertThat(result).isFalse();
      assertThat(count.get()).isZero();
    } finally {
      holder.close();
    }
  }

  @Test
  void lockUnavailableSkipsBackgroundScan() throws Exception {
    AtomicInteger hotCount = new AtomicInteger();
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    ScanLock.ScanLockHandle holder = scanLock.acquire("blocker", 1000);
    try {
      BackgroundScanner scanner =
          new BackgroundScanner(
              new TierConfig(300, 30),
              new TierConfig(86400, 300),
              scanLock,
              hotCount::incrementAndGet,
              () -> {},
              clock);

      scanner.checkAndScan();
    } finally {
      holder.close();
    }
  }

  @Test
  void noBootstrapMeansImmediateTierSelection() {
    // 无 bootstrap：首次 checkAndScan 直接选择到期层级
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    // 使用大时钟值确保两个 tier 都到期
    BackgroundScanner scanner =
        new BackgroundScanner(
            TierConfig.DEFAULT_HOT,
            TierConfig.DEFAULT_WARM,
            new ScanLock(tempDir),
            hotCount::incrementAndGet,
            warmCount::incrementAndGet,
            new FixedClock(10_000_000)); // 一万秒已超过一小时的扫描间隔
    try {
      scanner.checkAndScan();
      // 两个 tier 都到期（lastScanMs=0），warm 优先
      assertThat(warmCount.get()).isEqualTo(1);
      assertThat(hotCount.get()).isZero();
    } finally {
      scanner.shutdown(1, TimeUnit.SECONDS);
    }
  }

  @Test
  void runtimeExceptionInCheckAndScanDoesNotKillScheduler() throws Exception {
    CountDownLatch attempts = new CountDownLatch(2);
    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 1),
            new TierConfig(86400, 300),
            new ScanLock(tempDir),
            token -> {
              attempts.countDown();
              throw new IllegalStateException("synthetic recoverable failure");
            },
            token -> {},
            Clock.systemUTC());
    try {
      scanner.start();
      assertThat(attempts.await(5, TimeUnit.SECONDS)).isTrue();
      assertThat(scanner.isRunning()).isTrue();
      assertThat(scanner.hasFatalError()).isFalse();
    } finally {
      scanner.shutdown(5, TimeUnit.SECONDS);
    }
  }

  @Test
  void isRunningReturnsFalseWhenSchedulerFutureIsDone() {
    AtomicInteger hotCount = new AtomicInteger();
    AtomicInteger warmCount = new AtomicInteger();
    FixedClock clock = new FixedClock(60_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 30),
            new TierConfig(86400, 300),
            scanLock,
            token -> hotCount.incrementAndGet(),
            token -> warmCount.incrementAndGet(),
            clock);

    scanner.start();
    assertThat(scanner.isRunning()).isTrue();
    assertThat(scanner.isSchedulerFutureDone()).isFalse();

    scanner.shutdown(1, TimeUnit.SECONDS);
    assertThat(scanner.isRunning()).isFalse();
  }

  @Test
  void errorInActionSetsFatalAndPreventsSubsequentScans() throws Exception {
    AtomicInteger attempts = new AtomicInteger();
    CountDownLatch errorLogged = new CountDownLatch(1);
    var logger =
        (ch.qos.logback.classic.Logger) org.slf4j.LoggerFactory.getLogger(BackgroundScanner.class);
    var appender =
        new ch.qos.logback.core.AppenderBase<ch.qos.logback.classic.spi.ILoggingEvent>() {
          @Override
          protected void append(ch.qos.logback.classic.spi.ILoggingEvent event) {
            if (event.getLevel() == ch.qos.logback.classic.Level.ERROR
                && event.getFormattedMessage().contains("java.lang.AssertionError")) {
              errorLogged.countDown();
            }
          }
        };
    appender.start();
    logger.addAppender(appender);
    // hot 在启动时立即可执行，错误动作放在 hot 位置
    BackgroundScanner scanner =
        new BackgroundScanner(
            TierConfig.DEFAULT_HOT,
            TierConfig.DEFAULT_WARM,
            new ScanLock(tempDir),
            token -> {
              attempts.incrementAndGet();
              throw new AssertionError("synthetic fatal error");
            },
            token -> {},
            Clock.systemUTC());
    try {
      scanner.start();
      assertThat(errorLogged.await(5, TimeUnit.SECONDS)).isTrue();
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
      while (!scanner.isSchedulerFutureDone() && System.nanoTime() < deadline) {
        Thread.onSpinWait();
      }
      assertThat(scanner.isSchedulerFutureDone()).isTrue();
      assertThat(scanner.isRunning()).isFalse();
      assertThat(scanner.hasFatalError()).isTrue();
      scanner.checkAndScan();
      assertThat(attempts.get()).isEqualTo(1);
    } finally {
      scanner.shutdown(5, TimeUnit.SECONDS);
      logger.detachAppender(appender);
      appender.stop();
    }
  }

  @Test
  void summarySupplierIsCalledAfterScan() {
    AtomicInteger summaryCalls = new AtomicInteger();
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 30),
            new TierConfig(86400, 300),
            scanLock,
            token -> {},
            token -> {},
            () -> {
              summaryCalls.incrementAndGet();
              return null;
            },
            clock);

    try {
      scanner.checkAndScan();
      assertThat(summaryCalls.get()).isEqualTo(1);
    } finally {
      scanner.shutdown(1, TimeUnit.SECONDS);
    }
  }

  @Test
  void summarySupplierNotCalledOnActionException() {
    AtomicInteger summaryCalls = new AtomicInteger();
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner scanner =
        new BackgroundScanner(
            new TierConfig(300, 30),
            new TierConfig(86400, 300),
            scanLock,
            token -> {
              throw new IllegalStateException("synthetic failure");
            },
            token -> {},
            () -> {
              summaryCalls.incrementAndGet();
              return null;
            },
            clock);

    scanner.checkAndScan();
    assertThat(summaryCalls.get()).isZero();
    scanner.shutdown(1, TimeUnit.SECONDS);
  }

  @Test
  void summarySupplierNotCalledOnCancellation() {
    AtomicInteger summaryCalls = new AtomicInteger();
    FixedClock clock = new FixedClock(100_000);
    ScanLock scanLock = new ScanLock(tempDir);

    BackgroundScanner[] scannerHolder = new BackgroundScanner[1];
    scannerHolder[0] =
        new BackgroundScanner(
            new TierConfig(300, 30),
            new TierConfig(86400, 300),
            scanLock,
            token -> {
              scannerHolder[0].cancelCurrentScan();
              token.throwIfCancelled();
            },
            token -> {},
            () -> {
              summaryCalls.incrementAndGet();
              return null;
            },
            clock);

    scannerHolder[0].checkAndScan();
    assertThat(summaryCalls.get()).isZero();
    scannerHolder[0].shutdown(1, TimeUnit.SECONDS);
  }

  /** 用于测试的固定时钟。 */
  private static final class FixedClock extends Clock {
    private volatile long millis;

    FixedClock(long initialMillis) {
      this.millis = initialMillis;
    }

    void setMillis(long millis) {
      this.millis = millis;
    }

    @Override
    public ZoneId getZone() {
      return ZoneId.of("UTC");
    }

    @Override
    public Clock withZone(ZoneId zone) {
      return this;
    }

    @Override
    public Instant instant() {
      return Instant.ofEpochMilli(millis);
    }

    @Override
    public long millis() {
      return millis;
    }
  }
}
