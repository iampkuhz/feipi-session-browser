package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** 请求内按完整上下文首次出现顺序登记原有显示编号，不读取内容或推断关系。 */
final class SessionContextLabels {
  private final Map<String, String> labels = new LinkedHashMap<>();

  static String context(NormalizedCall call) {
    if (call.scope() == CallScope.MAIN) return "main";
    return call.subagentId().map(id -> "subagent:" + id).orElse("unknown:" + call.callId());
  }

  /** 只判定过程可达范围；已知模型归属优先，独立工具不因此获得模型或累计资格。 */
  static String executionContext(NormalizedToolExecution tool, String owner) {
    if (owner != null) return owner;
    if (tool.scope() == CallScope.MAIN) return "main";
    String id = tool.subagentId().orElse("");
    if (tool.scope() != CallScope.SUBAGENT
        || id.isBlank()
        || "unknown".equals(id)
        || id.startsWith("unknown:")
        || id.startsWith("unknown-sidechain:")) return "";
    return "subagent:" + id;
  }

  static String reference(String scope, String id, String callId) {
    if ("main".equalsIgnoreCase(scope)) return "main";
    if (!"subagent".equalsIgnoreCase(scope)) return "";
    return !id.isEmpty() ? "subagent:" + id : callId.isEmpty() ? "" : "unknown:" + callId;
  }

  String register(NormalizedCall call) {
    return register(context(call));
  }

  String register(String key) {
    return labels.computeIfAbsent(key, unused -> label(key, labels.size()));
  }

  Map<String, String> subset(Iterable<String> keys) {
    var result = new LinkedHashMap<String, String>();
    for (String key : keys) {
      if (labels.containsKey(key)) result.put(key, labels.get(key));
    }
    return Collections.unmodifiableMap(result);
  }

  private static String label(String key, int ordinal) {
    if ("main".equals(key)) return "主 Agent";
    if (key.startsWith("unknown:") || key.startsWith("subagent:unknown-sidechain:"))
      return "匿名上下文 " + ordinal;
    return "Agent " + ordinal;
  }
}
