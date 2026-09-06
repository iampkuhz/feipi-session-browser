package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class LoggingScanProgressTest {

  private final Logger logger = (Logger) LoggerFactory.getLogger(LoggingScanProgress.class);
  private final RecordingAppender appender = new RecordingAppender();
  private Level previousLevel;

  @BeforeEach
  void captureLogs() {
    previousLevel = logger.getLevel();
    logger.setLevel(Level.INFO);
    appender.start();
    logger.addAppender(appender);
  }

  @AfterEach
  void restoreLogs() {
    logger.detachAppender(appender);
    appender.stop();
    logger.setLevel(previousLevel);
  }

  @Test
  void slowCandidateHasHeartbeatAndFlushResumesSourceOnSameThread() throws Exception {
    var progress = new LoggingScanProgress(10);
    try {
      progress.onSourceStart("codex", 1);
      Event processing = appender.await(e -> e.message().contains("心跳: process:codex"));
      assertThat(processing.thread().isDaemon()).isTrue();
      progress.onPhaseStart("flush");
      Event flushing = appender.await(e -> e.message().contains("心跳: flush "));
      assertThat(flushing.thread()).isSameAs(processing.thread());
      progress.onPhaseEnd("flush", 1);
      appender.await(e -> e.message().startsWith("扫描阶段完成: flush"));
      Event resumed = appender.await(e -> e.message().contains("心跳: process:codex"));
      assertThat(resumed.thread()).isSameAs(processing.thread());
      progress.onSourceEnd("codex", 1);
      int end = appender.messages().indexOf("源处理完成: codex (成功 1)");
      progress.close();
      assertThat(processing.thread().isAlive()).isFalse();
      assertThat(appender.messages().subList(end + 1, appender.messages().size())).isEmpty();
    } finally {
      progress.close();
    }
  }

  @Test
  void closeWaitsForActualThreadAndSuppressesAllLaterCallbacks() throws Exception {
    var progress = new LoggingScanProgress(10);
    Thread heartbeat;
    try {
      progress.onPhaseStart("clear_index");
      heartbeat = appender.await(e -> e.message().contains("心跳: clear_index")).thread();
      assertThat(heartbeat.isAlive()).isTrue();
      Thread.currentThread().interrupt();
      try {
        progress.close();
        assertThat(Thread.currentThread().isInterrupted()).isTrue();
      } finally {
        Thread.interrupted();
      }
      assertThat(heartbeat.isAlive()).isFalse();
      assertThat(progress.isHeartbeatAlive()).isFalse();
      int count = appender.events.size();
      progress.onPhaseStart("schema");
      progress.onPhaseEnd("clear_index", 10);
      progress.onSourceStart("codex", 1);
      progress.onCandidateProcessed("codex", 1, 1);
      progress.onSourceEnd("codex", 1);
      progress.close();
      assertThat(appender.events).hasSize(count);
    } finally {
      progress.close();
    }
    assertThat(heartbeat.isAlive()).isFalse();
  }

  @Test
  void exceptionAlsoClosesActualHeartbeat() throws Exception {
    Thread[] heartbeat = new Thread[1];
    assertThatThrownBy(
            () -> {
              try (var progress = new LoggingScanProgress(10)) {
                progress.onPhaseStart("schema");
                heartbeat[0] = appender.await(e -> e.message().contains("心跳: schema")).thread();
                throw new IllegalStateException("synthetic failure");
              }
            })
        .isInstanceOf(IllegalStateException.class)
        .hasMessage("synthetic failure");
    assertThat(heartbeat[0]).isNotNull();
    assertThat(heartbeat[0].isAlive()).isFalse();
  }

  @Test
  void candidateCountsResetForEverySourceAndAreRateLimited() {
    try (var progress = new LoggingScanProgress(60_000)) {
      for (String source : List.of("codex", "qoder")) {
        progress.onSourceStart(source, 53);
        for (int i = 1; i <= 53; i++) progress.onCandidateProcessed(source, i, 53);
        progress.onSourceEnd(source, 53);
      }
      assertThat(appender.messages().stream().filter(m -> m.startsWith("扫描进度:")))
          .containsExactly(
              "扫描进度: 1/53 (codex)",
              "扫描进度: 51/53 (codex)",
              "扫描进度: 53/53 (codex)",
              "扫描进度: 1/53 (qoder)",
              "扫描进度: 51/53 (qoder)",
              "扫描进度: 53/53 (qoder)");
    }
  }

  @Test
  void candidateProgressAlsoLogsByElapsedTime() throws Exception {
    try (var progress = new LoggingScanProgress(20)) {
      progress.onSourceStart("codex", 100);
      progress.onCandidateProcessed("codex", 1, 100);
      // 两次真实心跳构成时间屏障，不以固定 sleep 猜测调度完成。
      CountDownLatch heartbeats = new CountDownLatch(2);
      appender.onHeartbeat = heartbeats::countDown;
      assertThat(heartbeats.await(3, TimeUnit.SECONDS)).isTrue();
      progress.onCandidateProcessed("codex", 2, 100);
      assertThat(appender.messages()).contains("扫描进度: 2/100 (codex)");
    }
  }

  @Test
  void phasesAreSafeAndEndedPhaseDoesNotReappear() throws Exception {
    var progress = new LoggingScanProgress(10);
    try {
      progress.onPhaseStart("schema");
      appender.await(e -> e.message().contains("心跳: schema"));
      progress.onPhaseEnd("schema", 5);
      progress.onPhaseStart("discover:/synthetic/private/path");
      appender.await(e -> e.message().contains("心跳: discover:unknown"));
      progress.onPhaseEnd("discover:/synthetic/private/path", 1);
      progress.onPhaseStart("  ");
      appender.await(e -> e.message().contains("心跳: unknown"));
      progress.onPhaseEnd("  ", 1);
      progress.close();
      List<String> messages = appender.messages();
      assertThat(messages).noneMatch(m -> m.contains("/synthetic/private/path"));
      int end = messages.indexOf("扫描阶段完成: schema (5ms)");
      assertThat(messages.subList(end + 1, messages.size())).noneMatch(m -> m.contains("schema"));
    } finally {
      progress.close();
    }
  }

  private record Event(String message, Thread thread) {}

  private static final class RecordingAppender extends AppenderBase<ILoggingEvent> {
    private final List<Event> events = new CopyOnWriteArrayList<>();
    private final LinkedBlockingQueue<Event> pending = new LinkedBlockingQueue<>();
    private volatile Runnable onHeartbeat = () -> {};

    @Override
    protected void append(ILoggingEvent event) {
      var captured = new Event(event.getFormattedMessage(), Thread.currentThread());
      events.add(captured);
      pending.add(captured);
      if (captured.message().contains("扫描阶段心跳:")) onHeartbeat.run();
    }

    List<String> messages() {
      return events.stream().map(Event::message).toList();
    }

    Event await(Predicate<Event> predicate) throws InterruptedException {
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
      while (true) {
        Event event = pending.poll(Math.max(0, deadline - System.nanoTime()), TimeUnit.NANOSECONDS);
        assertThat(event).as("等待真实 SLF4J 日志，已有: %s", messages()).isNotNull();
        if (predicate.test(event)) return event;
      }
    }
  }
}
