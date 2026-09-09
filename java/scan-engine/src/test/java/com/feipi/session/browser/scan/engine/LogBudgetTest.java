package com.feipi.session.browser.scan.engine;

import static org.assertj.core.api.Assertions.assertThat;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

/**
 * 验证正常扫描的 INFO 日志预算。
 *
 * <p>设计目标：纯时间限频，快速扫描（无时间流逝）只产生末条候选日志； 慢扫描通过心跳协调，同一窗口内不重复输出。 阶段开始/结束和源开始/结束均为 DEBUG。
 */
class LogBudgetTest {

  private final Logger progressLogger = (Logger) LoggerFactory.getLogger(LoggingScanProgress.class);
  private final RecordingAppender appender = new RecordingAppender();
  private Level previousLevel;

  @BeforeEach
  void captureLogs() {
    previousLevel = progressLogger.getLevel();
    progressLogger.setLevel(Level.INFO);
    appender.start();
    progressLogger.addAppender(appender);
  }

  @AfterEach
  void restoreLogs() {
    progressLogger.detachAppender(appender);
    appender.stop();
    progressLogger.setLevel(previousLevel);
  }

  @Test
  void fastScanProducesNoPhaseOrSourceInfoMessages() {
    try (var progress = new LoggingScanProgress(60_000)) {
      progress.onPhaseStart("schema");
      progress.onPhaseEnd("schema", 5);
      progress.onPhaseStart("load_fingerprints");
      progress.onPhaseEnd("load_fingerprints", 10);
      progress.onPhaseStart("discover:codex");
      progress.onPhaseEnd("discover:codex", 20);

      progress.onSourceStart("codex", 10);
      for (int i = 1; i <= 10; i++) {
        progress.onCandidateProcessed("codex", i, 10);
      }
      progress.onSourceEnd("codex", 10);

      progress.onPhaseStart("flush_final");
      progress.onPhaseEnd("flush_final", 3);
    }

    List<String> infoMessages = appender.messages();

    // 阶段开始/结束不应出现在 INFO 中
    assertThat(infoMessages).noneMatch(m -> m.startsWith("扫描阶段开始:"));
    assertThat(infoMessages).noneMatch(m -> m.startsWith("扫描阶段完成:"));

    // 源开始/结束不应出现在 INFO 中
    assertThat(infoMessages).noneMatch(m -> m.startsWith("开始处理源:"));
    assertThat(infoMessages).noneMatch(m -> m.startsWith("源处理完成:"));

    // 候选进度已降为 DEBUG，INFO 级别无候选日志
    List<String> progressMessages =
        infoMessages.stream().filter(m -> m.startsWith("扫描进度:")).toList();
    assertThat(progressMessages).isEmpty();
  }

  @Test
  void largeFastScanProducesNoProgressInfo() {
    // 候选进度已降为 DEBUG，1000 和 10000 候选的快速扫描在 INFO 级别均无进度日志
    for (int candidateCount : new int[] {1000, 10000}) {
      appender.messages.clear();
      try (var progress = new LoggingScanProgress(60_000)) {
        progress.onSourceStart("codex", candidateCount);
        for (int i = 1; i <= candidateCount; i++) {
          progress.onCandidateProcessed("codex", i, candidateCount);
        }
        progress.onSourceEnd("codex", candidateCount);
      }
      List<String> infoMessages = appender.messages();
      long progressCount = infoMessages.stream().filter(m -> m.startsWith("扫描进度:")).count();
      assertThat(progressCount).as("%d 候选快速扫描不应产生进度 INFO", candidateCount).isZero();
    }
  }

  @Test
  void multiSourceFastScanProducesNoProgressInfo() {
    // 候选进度已降为 DEBUG，多源快速扫描在 INFO 级别无进度日志
    try (var progress = new LoggingScanProgress(60_000)) {
      for (String source : List.of("codex", "claude_code", "qoder")) {
        progress.onSourceStart(source, 5000);
        for (int i = 1; i <= 5000; i++) {
          progress.onCandidateProcessed(source, i, 5000);
        }
        progress.onSourceEnd(source, 5000);
      }
    }
    List<String> progressMessages =
        appender.messages().stream().filter(m -> m.startsWith("扫描进度:")).toList();
    assertThat(progressMessages).isEmpty();
  }

  @Test
  void heartbeatFiresForSlowPhaseAtDebugLevel() throws Exception {
    // 心跳已降为 DEBUG 级别
    progressLogger.setLevel(Level.DEBUG);
    try (var progress = new LoggingScanProgress(20)) {
      progress.onSourceStart("codex", 1);
      long deadline = System.nanoTime() + 3_000_000_000L;
      while (System.nanoTime() < deadline) {
        boolean hasHeartbeat = appender.messages().stream().anyMatch(m -> m.contains("扫描阶段心跳:"));
        if (hasHeartbeat) break;
        Thread.sleep(5);
      }
      progress.onSourceEnd("codex", 1);
    }

    List<String> debugMessages = appender.messages();
    assertThat(debugMessages).anyMatch(m -> m.contains("扫描阶段心跳:"));
  }

  private static final class RecordingAppender extends AppenderBase<ILoggingEvent> {
    private final List<String> messages = new CopyOnWriteArrayList<>();

    @Override
    protected void append(ILoggingEvent event) {
      messages.add(event.getFormattedMessage());
    }

    List<String> messages() {
      return List.copyOf(messages);
    }
  }
}
