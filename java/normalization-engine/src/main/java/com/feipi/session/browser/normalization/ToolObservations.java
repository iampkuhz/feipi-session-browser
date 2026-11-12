package com.feipi.session.browser.normalization;

import com.feipi.session.browser.domain.source.SourceToolObservation;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/** 聚合已通过作用域身份计划的观测；冲突不可静默选择某条记录。 */
final class ToolObservations {
  private final Map<String, SourceToolObservation> values = new LinkedHashMap<>();

  void accept(SourceToolObservation value) {
    values.merge(value.toolCallId(), value, ToolObservations::merge);
  }

  Optional<SourceToolObservation> get(String id) {
    return Optional.ofNullable(values.get(id));
  }

  private static SourceToolObservation merge(SourceToolObservation a, SourceToolObservation b) {
    String source = a.source().compareTo(b.source()) <= 0 ? a.source() : b.source();
    if ("conflicting_observations".equals(a.issue())
        || "conflicting_observations".equals(b.issue())
        || conflict(a.durationNanos(), b.durationNanos())
        || conflict(a.exitCode(), b.exitCode())
        || conflict(a.status(), b.status())
        || conflict(a.processId(), b.processId())
        || conflict(a.issue(), b.issue())
        || !a.kind().equals(b.kind())) {
      return new SourceToolObservation(
          a.toolCallId(), null, null, null, null, a.kind(), source, "conflicting_observations");
    }
    String issue = a.issue() == null ? b.issue() : a.issue();
    return new SourceToolObservation(
        a.toolCallId(),
        "invalid_duration".equals(issue) || "duration_overflow".equals(issue)
            ? null
            : first(a.durationNanos(), b.durationNanos()),
        first(a.exitCode(), b.exitCode()),
        first(a.status(), b.status()),
        first(a.processId(), b.processId()),
        a.kind(),
        source,
        issue);
  }

  private static boolean conflict(Object a, Object b) {
    return a != null && b != null && !Objects.equals(a, b);
  }

  private static <T> T first(T a, T b) {
    return a == null ? b : a;
  }
}
