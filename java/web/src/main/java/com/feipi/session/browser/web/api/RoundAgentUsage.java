package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 按真实上下文汇总同一个逻辑轮次，不混合主、子 Agent 的用量。 */
final class RoundAgentUsage {
  static final String UNIDENTIFIED_SUBAGENT = "subagent_unknown";

  private final Map<String, SessionContentUsage> usage = new LinkedHashMap<>();
  private final Set<String> failures = new HashSet<>();

  void add(NormalizedCall call) {
    String owner = owner(call.scope(), call.subagentId().orElse(""));
    usage.computeIfAbsent(owner, key -> new SessionContentUsage()).add(call);
  }

  void markFailure(NormalizedToolExecution tool) {
    String owner = owner(tool.scope(), tool.subagentId().orElse(""));
    usage.computeIfAbsent(owner, key -> new SessionContentUsage());
    failures.add(owner);
  }

  List<Map<String, Object>> snapshot() {
    return usage.entrySet().stream()
        .map(
            entry ->
                Map.<String, Object>of(
                    "owner", entry.getKey(),
                    "tokens", entry.getValue().segments(),
                    "failed", failures.contains(entry.getKey())))
        .toList();
  }

  static String owner(CallScope scope, String subagentId) {
    if (scope == CallScope.MAIN) return "main";
    return subagentId.isBlank() ? UNIDENTIFIED_SUBAGENT : "subagent:" + subagentId;
  }
}
