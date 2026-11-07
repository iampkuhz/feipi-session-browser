package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** 按遍历顺序执行共享分组，只保留稳定身份。 */
final class RoundGrouping {
  private final NormalizedAgent agent;
  private final Map<String, Integer> calls = new HashMap<>();
  private final Map<String, Integer> turns = new HashMap<>();
  private final Set<Integer> modelRounds = new HashSet<>();
  private int count;

  RoundGrouping(NormalizedAgent agent) {
    this.agent = agent;
  }

  int add(NormalizedCall call) {
    Integer round;
    if (!evidence(agent, call).isEmpty()) {
      round = ++count;
      modelRounds.add(round);
    } else if (call.scope() == CallScope.MAIN) {
      String turn = call.turnId().orElse("");
      round = turn.isEmpty() ? null : turns.get(turn);
      if (round == null) {
        round = ++count;
        if (!turn.isEmpty()) turns.put(turn, round);
      }
    } else {
      round = calls.get(call.parentCallId().orElse(""));
      if (round == null || modelRounds.contains(round)) round = ++count;
    }
    if (calls.putIfAbsent(call.callId(), round) != null)
      throw new IllegalArgumentException("Duplicate call identity");
    return round;
  }

  static String evidence(NormalizedAgent agent, NormalizedCall call) {
    if (agent != NormalizedAgent.CODEX) return "";
    Object evidence = call.attributionCandidates().get("modelCallEvidence");
    // 旧制品在缺少响应身份时使用数字事件序号，因此纯数字尾缀需要额外证据。
    if ("response_usage".equals(evidence)
        || call.callId().matches("token_usage_record:.*[^0-9].*")) {
      return "response_usage";
    }
    if ("closing_counter".equals(evidence) || call.callId().startsWith("token_count:")) {
      return "closing_counter";
    }
    return "";
  }

  int count() {
    return count;
  }

  Map<String, Integer> calls() {
    return calls;
  }
}
