package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.normalized.SessionTiming;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceTiming;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** 只组合源显式计时；消息之间的无事件时段不属于模型执行。 */
final class SessionTimingCalculator {
  private SessionTimingCalculator() {}

  static SessionTiming calculate(List<? extends SourceRecord> records, Double wallSeconds) {
    Map<TaskKey, List<SourceTiming>> tasks = new LinkedHashMap<>();
    List<Interval> intervals = new ArrayList<>();
    Set<String> seenTurns = new HashSet<>();
    long incomplete = 0;
    long completed = 0;
    long aborted = 0;
    long missingTurnDurations = 0;
    long measuredTurns = 0;
    long mainUsers = 0;
    double workloadMs = 0;
    double taskWorkloadMs = 0;
    long unplacedTasks = 0;
    double modelMs = 0;
    double toolMs = 0;
    long modelMeasurements = 0;
    long toolMeasurements = 0;
    for (SourceRecord record : records) {
      if (!mainRecord(record)) {
        continue;
      }
      if ("user".equals(record.eventType())) {
        mainUsers++;
      }
      SourceTiming timing = record.timing();
      String scope = scope(record);
      if ("turn_duration".equals(timing.kind())) {
        String id = timing.eventId().isBlank() ? "event:" + record.eventIndex() : timing.eventId();
        if (!seenTurns.add(scope + "#" + id)) {
          continue;
        }
        if (timing.durationMs().isPresent()) {
          workloadMs += timing.durationMs().getAsLong();
          measuredTurns++;
        } else {
          missingTurnDurations++;
        }
      } else if (List.of("task_started", "task_complete", "turn_aborted").contains(timing.kind())) {
        if (timing.turnId().isBlank()) {
          if (seenTurns.add(scope + "#missing:" + record.eventIndex())) {
            incomplete++;
          }
        } else {
          tasks
              .computeIfAbsent(new TaskKey(scope, timing.turnId()), ignored -> new ArrayList<>())
              .add(timing);
        }
      }
    }
    for (List<SourceTiming> evidence : tasks.values()) {
      List<SourceTiming> ends =
          evidence.stream()
              .filter(t -> !"task_started".equals(t.kind()))
              .map(SessionTimingCalculator::withoutEventId)
              .distinct()
              .toList();
      if (ends.size() != 1) {
        incomplete++;
        continue;
      }
      SourceTiming end = ends.getFirst();
      if ("turn_aborted".equals(end.kind())) {
        aborted++;
      } else {
        completed++;
      }
      List<Instant> starts =
          evidence.stream()
              .filter(t -> "task_started".equals(t.kind()))
              .flatMap(t -> t.startedAt().stream())
              .map(SessionTimingCalculator::instant)
              .flatMap(Optional::stream)
              .distinct()
              .toList();
      Optional<Instant> start = end.startedAt().flatMap(SessionTimingCalculator::instant);
      if (start.isEmpty() && starts.size() == 1) {
        start = Optional.of(starts.getFirst());
      }
      Optional<Instant> finish = end.completedAt().flatMap(SessionTimingCalculator::instant);
      if (end.durationMs().isPresent()) {
        long durationMs = end.durationMs().getAsLong();
        if (start.isPresent()) {
          finish = Optional.of(start.get().plusMillis(durationMs));
        } else if (finish.isPresent()) {
          start = Optional.of(finish.get().minusMillis(durationMs));
        } else {
          taskWorkloadMs += durationMs;
          unplacedTasks++;
        }
      }
      boolean incompleteTask =
          evidence.stream().noneMatch(t -> "task_started".equals(t.kind())) || starts.size() > 1;
      if (start.isPresent() && finish.isPresent() && !finish.get().isBefore(start.get())) {
        intervals.add(new Interval(start.get(), finish.get()));
      } else {
        incompleteTask = true;
      }
      if (incompleteTask) {
        incomplete++;
      }
      if (end.modelDurationMs().isPresent()) {
        modelMs += end.modelDurationMs().getAsLong();
        modelMeasurements++;
      }
      if (end.toolDurationMs().isPresent()) {
        toolMs += end.toolDurationMs().getAsLong();
        toolMeasurements++;
      }
    }
    Double active = intervals.isEmpty() ? null : unionMillis(intervals) / 1000.0;
    long closed = completed + aborted;
    boolean workloadPartial = missingTurnDurations > 0 || mainUsers > measuredTurns;
    Double agentTurn = null;
    if (measuredTurns > 0) {
      agentTurn = workloadMs / 1000.0;
    } else if (unplacedTasks > 0) {
      agentTurn = taskWorkloadMs / 1000.0;
    }
    String workloadBasis =
        measuredTurns > 0
            ? "main_agent_turn_duration"
            : unplacedTasks > 0 ? "main_task_duration_sum" : "";
    return new SessionTiming(
        wallSeconds,
        wallSeconds == null ? "unknown" : "measured",
        active,
        active == null ? "unknown" : incomplete > 0 ? "partial" : "measured",
        "main_task_windows",
        agentTurn,
        agentTurn == null
            ? "unknown"
            : workloadPartial || unplacedTasks > 0 ? "partial" : "measured",
        workloadBasis,
        modelMeasurements == 0 ? null : modelMs / 1000.0,
        measurementPrecision(modelMeasurements, closed, incomplete),
        toolMeasurements == 0 ? null : toolMs / 1000.0,
        measurementPrecision(toolMeasurements, closed, incomplete),
        completed,
        incomplete,
        aborted);
  }

  private static String measurementPrecision(long measurements, long closed, long incomplete) {
    return measurements == 0
        ? "unknown"
        : measurements == closed && incomplete == 0 ? "measured" : "partial";
  }

  private static SourceTiming withoutEventId(SourceTiming timing) {
    return new SourceTiming(
        timing.kind(),
        timing.turnId(),
        timing.startedAt(),
        timing.completedAt(),
        timing.durationMs(),
        timing.modelDurationMs(),
        timing.toolDurationMs(),
        "");
  }

  private static boolean mainRecord(SourceRecord record) {
    return !record.relation().hasSubagentEvidence()
        && !record.locator().replace('\\', '/').contains("/subagents/");
  }

  private static String scope(SourceRecord record) {
    int event = record.locator().indexOf("#event[");
    return event < 0 ? record.locator() : record.locator().substring(0, event);
  }

  private static Optional<Instant> instant(String value) {
    try {
      return Optional.of(Instant.parse(value));
    } catch (java.time.DateTimeException e) {
      return Optional.empty();
    }
  }

  private static double unionMillis(List<Interval> intervals) {
    List<Interval> sorted =
        intervals.stream().sorted(Comparator.comparing(Interval::start)).toList();
    Instant start = sorted.getFirst().start();
    Instant finish = sorted.getFirst().end();
    double total = 0;
    for (Interval interval : sorted.subList(1, sorted.size())) {
      if (interval.start().isAfter(finish)) {
        total += Duration.between(start, finish).toMillis();
        start = interval.start();
        finish = interval.end();
      } else if (interval.end().isAfter(finish)) {
        finish = interval.end();
      }
    }
    return total + Duration.between(start, finish).toMillis();
  }

  /**
   * 同文件作用域内的精确任务身份。
   *
   * @param scope 主会话或子会话作用域
   * @param turnId 上游显式任务身份
   */
  private record TaskKey(String scope, String turnId) {}

  /**
   * 可求并集的显式任务边界。
   *
   * @param start 任务起始时刻
   * @param end 任务结束时刻
   */
  private record Interval(Instant start, Instant end) {}
}
