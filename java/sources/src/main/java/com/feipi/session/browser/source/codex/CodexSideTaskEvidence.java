package com.feipi.session.browser.source.codex;

import com.feipi.session.browser.domain.source.SourceReadingEvidence;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceTiming;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** 在明确识别的 Side Chat 中按源任务身份绑定逐响应调用和任务计时。 */
final class CodexSideTaskEvidence {
  private final Map<String, Task> tasks = new HashMap<>();
  private boolean side;

  CodexSideTaskEvidence(boolean verifiedSideChat) {
    side = verifiedSideChat;
  }

  void recognizeSide() {
    side = true;
  }

  void accept(SourceRecord record) {
    if (!side) return;
    var timing = record.timing();
    if (timing.turnId().isBlank()) return;
    if ("task_started".equals(timing.kind())) {
      Task existing = tasks.putIfAbsent(timing.turnId(), new Task(record.eventIndex(), timing));
      if (existing != null) existing.ambiguous = true;
    } else if (List.of("task_complete", "turn_aborted").contains(timing.kind())) {
      var task = tasks.get(timing.turnId());
      if (task != null) task.end(record.eventIndex(), timing);
    }
  }

  void append(SourceRecord record, List<SourceReadingEvidence> evidence) {
    if (!"assistant".equals(record.eventType())
        || record.callId().filter(id -> id.startsWith("token_usage_record:")).isEmpty()) return;
    var task = tasks.get(record.turnId().orElse(""));
    if (task == null
        || task.ambiguous
        || record.eventIndex() <= task.startIndex
        || record.eventIndex() >= task.endIndex) return;
    evidence.add(new SourceReadingEvidence("side_task_id", record.turnId().orElseThrow()));
    task.start
        .startedAt()
        .ifPresent(value -> evidence.add(new SourceReadingEvidence("side_task_started_at", value)));
    Long duration = task.duration();
    if (duration != null) {
      evidence.add(new SourceReadingEvidence("side_task_duration_ms", duration.toString()));
    }
  }

  /** 窗口仅用任务边界，不从调用时间或工具执行时间倒推。 */
  private static final class Task {
    private final int startIndex;
    private final SourceTiming start;
    private int endIndex = Integer.MAX_VALUE;
    private SourceTiming finish;
    private boolean ambiguous;

    private Task(int startIndex, SourceTiming start) {
      this.startIndex = startIndex;
      this.start = start;
    }

    private void end(int index, SourceTiming timing) {
      if (finish != null) {
        ambiguous = true;
      } else {
        finish = timing;
        endIndex = index;
      }
    }

    private Long duration() {
      if (finish == null) return null;
      if (finish.durationMs().isPresent()) return finish.durationMs().getAsLong();
      if (start.startedAt().isEmpty() || finish.completedAt().isEmpty()) return null;
      Duration elapsed =
          Duration.between(
              Instant.parse(start.startedAt().orElseThrow()),
              Instant.parse(finish.completedAt().orElseThrow()));
      try {
        return elapsed.isNegative() ? null : elapsed.toMillis();
      } catch (ArithmeticException overflow) {
        return null;
      }
    }
  }
}
