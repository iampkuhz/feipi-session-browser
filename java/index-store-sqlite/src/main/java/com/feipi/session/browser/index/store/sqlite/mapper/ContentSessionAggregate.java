package com.feipi.session.browser.index.store.sqlite.mapper;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.HashSet;
import java.util.Set;

/** 为旧制品和有界内容映射共用标量累积，不保留正文。 */
final class ContentSessionAggregate {
  long calls;
  long mainCalls;
  long toolCalls;
  long output;
  long fresh;
  long cacheRead;
  long cacheWrite;
  long total;
  long tools;
  long toolDurationMs;
  long failedTools;
  boolean sequenceObserved;
  String firstModel = "";
  String lastTimestamp = "";
  final Set<String> subagentIds = new HashSet<>();

  void add(NormalizedCall call) {
    if (calls++ == 0) firstModel = call.model();
    lastTimestamp = call.timestamp().orElse("");
    if (call.scope() == CallScope.MAIN) mainCalls++;
    else call.parentCallId().ifPresent(subagentIds::add);
    toolCalls += call.response().toolCallIds().size();
    output += call.usage().output();
    fresh += call.usage().fresh();
    cacheRead += call.usage().cacheRead();
    cacheWrite += call.usage().cacheWrite();
    total += call.usage().total();
  }

  void add(NormalizedToolExecution tool) {
    tools++;
    toolDurationMs += tool.durationMs();
    if (tool.status().isPresent()) failedTools++;
  }
}
