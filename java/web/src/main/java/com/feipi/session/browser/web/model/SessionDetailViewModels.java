package com.feipi.session.browser.web.model;

import com.feipi.session.browser.index.sqlite.SessionDetail;
import com.feipi.session.browser.index.sqlite.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.DetectedAnomaly;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.query.api.SessionAnomalySummary;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Session Detail 与导出页共享的视图模型构造器。 */
public final class SessionDetailViewModels {

  private SessionDetailViewModels() {}

  /** 构建 Session Detail 页面与导出页共享的基础模板上下文。 */
  public static Map<String, Object> baseContext(
      SessionDetail detail, String agent, String sessionId, PayloadVisibility visibility) {
    SessionRow row = detail.sessionRow();
    Map<String, Object> context = new LinkedHashMap<>();
    context.put("session", row);
    context.put("current_agent", agent);
    context.put("session_id", sessionId);
    context.put("session_key", row.sessionKey());
    context.put("has_artifact", detail.hasArtifact());
    context.put("artifact_path", detail.artifactPath());
    context.put("artifact_schema_version", detail.artifactSchemaVersion());
    context.put("cache_key", detail.cacheKey());
    context.put("visibility", visibility.name().toLowerCase());
    context.put("payload_hidden", visibility == PayloadVisibility.STANDARD);
    return context;
  }

  /** 构建异常展示列表。 */
  public static List<Map<String, String>> anomalyList(SessionAnomalySummary anomalies) {
    List<Map<String, String>> result = new ArrayList<>();
    for (DetectedAnomaly anomaly : anomalies.anomalies()) {
      Map<String, String> entry = new LinkedHashMap<>();
      entry.put("type", anomaly.type().getValue());
      entry.put("severity", anomaly.severity().name().toLowerCase());
      entry.put("reason", anomaly.reason());
      entry.put("tone", anomaly.severity().getValue());
      result.add(entry);
    }
    return result;
  }

  /** 构建 round 基础展示字段。 */
  public static Map<String, Object> roundBase(CallRound round) {
    Map<String, Object> entry = new LinkedHashMap<>();
    entry.put("round_index", round.roundIndex());
    entry.put("call_count", round.callCount());
    entry.put("tool_call_count", round.toolCallCount());
    entry.put("is_subagent", !round.parentCallId().isEmpty());
    entry.put("parent_call_id", round.parentCallId());
    entry.put("calls", round.calls());
    entry.put("tool_call_ids", round.toolCallIds());
    return entry;
  }

  /** 构建完整导出使用的 round 列表。 */
  public static List<Map<String, Object>> exportRounds(List<CallRound> rounds) {
    List<Map<String, Object>> result = new ArrayList<>(rounds.size());
    for (CallRound round : rounds) {
      Map<String, Object> entry = roundBase(round);
      entry.put("is_empty", round.isEmpty());
      result.add(entry);
    }
    return result;
  }

  /** 构建 session 基础指标 map。 */
  public static Map<String, Object> baseMetrics(SessionRow row) {
    Map<String, Object> metrics = new LinkedHashMap<>();
    metrics.put("total_tokens", row.totalTokens());
    metrics.put("output_tokens", row.outputTokens());
    metrics.put("fresh_input_tokens", row.freshInputTokens());
    metrics.put("cache_read_tokens", row.cacheReadTokens());
    metrics.put("cache_write_tokens", row.cacheWriteTokens());
    metrics.put("duration_seconds", row.durationSeconds());
    metrics.put("model_execution_seconds", row.modelExecutionSeconds());
    metrics.put("tool_execution_seconds", row.toolExecutionSeconds());
    metrics.put("tool_call_count", row.toolCallCount());
    metrics.put("failed_tool_count", row.failedToolCount());
    metrics.put("user_message_count", row.userMessageCount());
    metrics.put("assistant_message_count", row.assistantMessageCount());
    metrics.put("subagent_instance_count", row.subagentInstanceCount());
    return metrics;
  }
}
