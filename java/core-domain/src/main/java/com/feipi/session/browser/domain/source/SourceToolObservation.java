package com.feipi.session.browser.domain.source;

import java.util.Objects;

/**
 * 执行器显式上报的工具观测；不表示生命周期区间，不含输出正文或物理路径。
 *
 * @param toolCallId 来源内稳定工具标识
 * @param durationNanos 精确纳秒耗时，缺失或非法时为空
 * @param exitCode 显式退出码，缺失时为空
 * @param status 显式执行状态，缺失时为空
 * @param processId 辅助进程标识，不用于跨作用域合并
 * @param kind 测量口径
 * @param source 不含路径的来源事件定位符
 * @param issue 非法或冲突原因，正常时为空
 */
public record SourceToolObservation(
    String toolCallId,
    Long durationNanos,
    Integer exitCode,
    String status,
    String processId,
    String kind,
    String source,
    String issue) {
  /** 校验精确耗时及稳定身份。 */
  public SourceToolObservation {
    if (Objects.requireNonNull(toolCallId).isBlank())
      throw new IllegalArgumentException("工具标识不得为空");
    if (durationNanos != null && durationNanos < 0) throw new IllegalArgumentException("耗时不得为负");
    Objects.requireNonNull(kind);
    Objects.requireNonNull(source);
  }

  /** 仅替换归一化身份，保留观测事实。 */
  public SourceToolObservation withToolCallId(String id) {
    return new SourceToolObservation(
        id, durationNanos, exitCode, status, processId, kind, source, issue);
  }

  /** 毫秒摘要向下取整；精确值仍保留在 durationNanos，未知不补零。 */
  public Long durationMs() {
    return durationNanos == null ? null : durationNanos / 1_000_000;
  }

  /** 日志不输出来源标识或进程信息。 */
  @Override
  public String toString() {
    return "SourceToolObservation[measured=" + (durationNanos != null) + "]";
  }
}
