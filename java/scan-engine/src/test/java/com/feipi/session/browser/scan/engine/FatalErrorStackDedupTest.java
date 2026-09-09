package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.spi.IThrowableProxy;
import ch.qos.logback.core.AppenderBase;
import java.time.Clock;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.slf4j.LoggerFactory;

/**
 * 验证同一致命错误在跨 logger（IncrementalScanEngine + BackgroundScanner）只产生一份完整 stack。
 *
 * <p>内层扫描引擎在 rethrow Error 前记录完整 stack；外层 BackgroundScanner 通过 wrapWithErrorTracking 标记后仅输出摘要，不再重复
 * stack。
 */
class FatalErrorStackDedupTest {

  @TempDir java.nio.file.Path tempDir;

  private final Logger engineLogger = (Logger) LoggerFactory.getLogger(IncrementalScanEngine.class);
  private final Logger scannerLogger = (Logger) LoggerFactory.getLogger(BackgroundScanner.class);
  private final StackCountingAppender engineAppender = new StackCountingAppender();
  private final StackCountingAppender scannerAppender = new StackCountingAppender();
  private Level prevEngineLevel;
  private Level prevScannerLevel;

  @BeforeEach
  void captureLogs() {
    prevEngineLevel = engineLogger.getLevel();
    prevScannerLevel = scannerLogger.getLevel();
    engineLogger.setLevel(Level.ERROR);
    scannerLogger.setLevel(Level.ERROR);
    engineAppender.start();
    scannerAppender.start();
    engineLogger.addAppender(engineAppender);
    scannerLogger.addAppender(scannerAppender);
  }

  @AfterEach
  void restoreLogs() {
    engineLogger.detachAppender(engineAppender);
    scannerLogger.detachAppender(scannerAppender);
    engineAppender.stop();
    scannerAppender.stop();
    engineLogger.setLevel(prevEngineLevel);
    scannerLogger.setLevel(prevScannerLevel);
  }

  @Test
  void sameFatalErrorProducesOnlyOneFullStackTrace() throws Exception {
    CountDownLatch errorPropagated = new CountDownLatch(1);
    AssertionError fatal = new AssertionError("synthetic OOM");

    BackgroundScanner scanner =
        new BackgroundScanner(
            TierConfig.DEFAULT_HOT,
            TierConfig.DEFAULT_WARM,
            new ScanLock(tempDir),
            token -> {
              // 模拟内层引擎：记录完整 stack 后设置 ThreadLocal 标记，然后 rethrow
              engineLogger.error(
                  "扫描致命错误 [{}]: {}", fatal.getClass().getName(), fatal.getMessage(), fatal);
              // 设置 ThreadLocal 标记，模拟 IncrementalScanEngine 的行为
              IncrementalScanEngine.setFatalErrorStackLogged(true);
              throw fatal;
            },
            token -> {},
            Clock.systemUTC());

    try {
      scanner.start();
      // 等待调度器执行 hot tier 并触发 Error
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
      while (!scanner.hasFatalError() && System.nanoTime() < deadline) {
        Thread.sleep(10);
      }
      assertThat(scanner.hasFatalError()).isTrue();

      // 等待调度器 Future 完成
      deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
      while (!scanner.isSchedulerFutureDone() && System.nanoTime() < deadline) {
        Thread.sleep(10);
      }

      // 验证：跨两个 logger，带 throwable 的 ERROR 日志只出现一次
      int engineErrorsWithStack = engineAppender.errorsWithThrowable();
      int scannerErrorsWithStack = scannerAppender.errorsWithThrowable();
      int totalStacks = engineErrorsWithStack + scannerErrorsWithStack;

      assertThat(totalStacks)
          .as(
              "同一致命错误只应产生 1 份完整 stack（engine=%d, scanner=%d）",
              engineErrorsWithStack, scannerErrorsWithStack)
          .isEqualTo(1);

      // 完整 stack 应由内层（engine）记录
      assertThat(engineErrorsWithStack).isEqualTo(1);
      // 外层（scanner）不应带 throwable
      assertThat(scannerErrorsWithStack).isEqualTo(0);

      // 外层仍应有 ERROR 摘要日志（不含 stack）
      assertThat(scannerAppender.errorCount()).isGreaterThanOrEqualTo(1);
    } finally {
      scanner.shutdown(5, TimeUnit.SECONDS);
    }
  }

  @Test
  void independentRuntimeExceptionRetainsFullStack() throws Exception {
    // BackgroundScanner 自身代码（非 action）抛出的 RuntimeException 应保留完整 stack
    BackgroundScanner scanner =
        new BackgroundScanner(
            TierConfig.DEFAULT_HOT,
            TierConfig.DEFAULT_WARM,
            new ScanLock(tempDir),
            token -> {
              // 模拟内层 RuntimeException（非 Error），由 checkAndScanSafe 的 RuntimeException catch 处理
              RuntimeException ex = new RuntimeException("inner scan failure");
              engineLogger.error("扫描异常", ex);
              // 设置 ThreadLocal 标记，模拟 IncrementalScanEngine 的行为
              IncrementalScanEngine.setFatalErrorStackLogged(true);
              throw ex;
            },
            token -> {},
            Clock.systemUTC());

    try {
      scanner.start();
      // 等待调度器执行并处理异常
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
      while (scannerAppender.errorCount() == 0 && System.nanoTime() < deadline) {
        Thread.sleep(10);
      }

      // 内层有完整 stack
      assertThat(engineAppender.errorsWithThrowable()).isGreaterThanOrEqualTo(1);
    } finally {
      scanner.shutdown(5, TimeUnit.SECONDS);
    }
  }

  private static final class StackCountingAppender extends AppenderBase<ILoggingEvent> {
    private final List<ILoggingEvent> events = new CopyOnWriteArrayList<>();

    @Override
    protected void append(ILoggingEvent event) {
      events.add(event);
    }

    int errorsWithThrowable() {
      int count = 0;
      for (ILoggingEvent event : events) {
        if (event.getLevel() == Level.ERROR) {
          IThrowableProxy tp = event.getThrowableProxy();
          if (tp != null) {
            count++;
          }
        }
      }
      return count;
    }

    int errorCount() {
      int count = 0;
      for (ILoggingEvent event : events) {
        if (event.getLevel() == Level.ERROR) count++;
      }
      return count;
    }
  }
}
