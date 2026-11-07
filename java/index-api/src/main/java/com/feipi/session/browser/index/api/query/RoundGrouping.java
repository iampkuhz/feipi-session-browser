package com.feipi.session.browser.index.api.query;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import java.util.HashMap;
import java.util.Map;

/** 按遍历顺序执行共享分组，只保留稳定身份。 */
final class RoundGrouping {
  private final Map<String, Integer> calls = new HashMap<>();
  private final Map<String, Integer> turns = new HashMap<>();
  private int count;

  int add(NormalizedCall call) {
    Integer round;
    if (call.scope() == CallScope.MAIN) {
      String turn = call.turnId().orElse("");
      round = turn.isEmpty() ? null : turns.get(turn);
      if (round == null) {
        round = ++count;
        if (!turn.isEmpty()) turns.put(turn, round);
      }
    } else {
      round = calls.get(call.parentCallId().orElse(""));
      if (round == null) round = ++count;
    }
    if (calls.putIfAbsent(call.callId(), round) != null)
      throw new IllegalArgumentException("Duplicate call identity");
    return round;
  }

  int count() {
    return count;
  }

  Map<String, Integer> calls() {
    return calls;
  }
}
