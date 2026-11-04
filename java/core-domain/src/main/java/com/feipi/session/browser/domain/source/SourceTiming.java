package com.feipi.session.browser.domain.source;

import java.util.Optional;
import java.util.OptionalLong;

/**
 * 源事件显式给出的计时事实；不包含由相邻消息间隔推断的执行时间。
 *
 * @param kind task_started/task_complete/turn_aborted/turn_duration，空串表示无计时事件
 * @param turnId 任务精确标识，不从 event subtype 猜测
 * @param startedAt 显式任务开始时间
 * @param completedAt 显式任务结束时间
 * @param durationMs 显式任务或 agent-turn 时长，合法零保留
 * @param modelDurationMs 显式模型执行时长，缺失与零不同
 * @param toolDurationMs 显式工具执行时长，缺失与零不同
 * @param eventId 用于重复写出事件去重的源标识
 */
public record SourceTiming(
    String kind,
    String turnId,
    Optional<String> startedAt,
    Optional<String> completedAt,
    OptionalLong durationMs,
    OptionalLong modelDurationMs,
    OptionalLong toolDurationMs,
    String eventId) {

  /** 缺失字段保持空值，不将未上报变为零。 */
  public SourceTiming {
    kind = kind == null ? "" : kind;
    turnId = turnId == null ? "" : turnId;
    startedAt = startedAt == null ? Optional.empty() : startedAt;
    completedAt = completedAt == null ? Optional.empty() : completedAt;
    durationMs = durationMs == null ? OptionalLong.empty() : durationMs;
    modelDurationMs = modelDurationMs == null ? OptionalLong.empty() : modelDurationMs;
    toolDurationMs = toolDurationMs == null ? OptionalLong.empty() : toolDurationMs;
    eventId = eventId == null ? "" : eventId;
    if (durationMs.orElse(0) < 0 || modelDurationMs.orElse(0) < 0 || toolDurationMs.orElse(0) < 0) {
      throw new IllegalArgumentException("Explicit timing must be nonnegative");
    }
  }

  /** 未携带计时事实的旧记录。 */
  public static SourceTiming empty() {
    return new SourceTiming(
        "",
        "",
        Optional.empty(),
        Optional.empty(),
        OptionalLong.empty(),
        OptionalLong.empty(),
        OptionalLong.empty(),
        "");
  }
}
