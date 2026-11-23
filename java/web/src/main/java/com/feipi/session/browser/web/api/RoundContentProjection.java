package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * 展示内容按归一化 call 身份取值，不与 raw 日志的另一套 round 序列按位置对齐。
 *
 * @param summary 当前轮可见输入、工具操作或响应文本摘要
 * @param time 当前轮次首个已记录的调用时间
 * @param userInput 当前轮次是否包含可见用户输入
 */
record RoundContentProjection(String summary, String time, boolean userInput) {
  private static final DateTimeFormatter TIME =
      DateTimeFormatter.ofPattern("HH:mm:ss").withZone(ZoneId.of("Asia/Shanghai"));

  static String observedInputSummary(SessionRecord row) {
    return row.userMessageMeasured() && row.userMessageCount() > 0
        ? "已记录 " + row.userMessageCount() + " 条用户输入"
        : "";
  }

  static String observedInputSummary(SessionRecord row, NormalizedSessionArtifact artifact) {
    try {
      var reader =
          new com.feipi.session.browser.application.sessiondetail.SessionContentReader(
              com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
                  artifact),
              row.userMessageCount());
      String preview = reader.observedInputPreview();
      return preview.isEmpty() ? observedInputSummary(row) : preview;
    } catch (java.io.IOException exception) {
      throw new IllegalStateException("无法读取已验证的观测输入", exception);
    }
  }

  static RoundContentProjection from(CallRound round, NormalizedSessionArtifact artifact) {
    return from(round, artifact, SessionContentPreviews.readArtifact(artifact));
  }

  static RoundContentProjection from(
      CallRound round, NormalizedSessionArtifact artifact, SessionContentPreviews previews) {
    var projection = RoundIndexProjection.project(round, artifact);
    Set<String> ids = Set.copyOf(projection.callIds());
    var toolPreviews = new HashMap<String, ToolInputPreview.Summary>();
    String assistant = "";
    String compaction = "";
    String user = "";
    String time = "";
    ContentRoundIndex.SideTask sideTask = null;
    for (var call : artifact.calls()) {
      if (!ids.contains(call.callId())) continue;
      if (time.isEmpty()) time = displayTime(previews.timestamp(call));
      if (sideTask == null) sideTask = ContentRoundIndex.sideTask(call).orElse(null);
      if (assistant.isEmpty()) assistant = previews.text(call, false);
      if (compaction.isEmpty()) compaction = compactionSummary(call);
      String currentUser = previews.userText(call, round.roundIndex());
      user = preferredUser(user, currentUser, sideTask != null);
      toolPreviews.putAll(previews.toolInputSummaries(call));
    }
    String summary =
        RoundIndexProjection.toolCountSummary(projection.toolCallIds(), artifact, toolPreviews);
    if (summary.isEmpty()) summary = assistant;
    if (summary.isEmpty()) summary = compaction;
    if (!user.isEmpty()) summary = user;
    summary = SensitiveFieldPolicy.DEFAULT.applyMasking(summary).replaceAll("\\s+", " ").trim();
    if (summary.codePointCount(0, summary.length()) > 240)
      summary = summary.substring(0, summary.offsetByCodePoints(0, 240)) + "…";
    return new RoundContentProjection(
        summary.isBlank() ? "内容未记录" : summary, withTaskTime(time, sideTask), !user.isEmpty());
  }

  static String compactionSummary(NormalizedCall call) {
    for (var unit : call.sourceUnits()) {
      if (!"codex_context_response_compaction".equals(unit.get("type"))) continue;
      if ("identity".equals(unit.get("text"))) return "上下文压缩";
      if ("adjacent".equals(unit.get("text"))) return "模型响应 · 相邻压缩事件";
    }
    return "";
  }

  static String preferredUser(String current, String next, boolean sideTask) {
    return current.isEmpty()
            || sideTask
                && current.codePointCount(0, current.length()) == 1
                && next.codePointCount(0, next.length()) > 1
        ? next
        : current;
  }

  static String withTaskTime(String fallback, ContentRoundIndex.SideTask task) {
    if (task == null) return fallback;
    String started = displayTime(task.startedAt());
    return started.isEmpty() ? fallback : started;
  }

  static Map<String, Object> withTask(Map<String, Object> parity, ContentRoundIndex.SideTask task) {
    if (task == null) return parity;
    var result = new LinkedHashMap<>(parity);
    result.put("userTask", true);
    if (!task.startedAt().isBlank()) result.put("taskStartedAt", task.startedAt());
    if (task.durationMs() != null) result.put("taskDurationMs", task.durationMs());
    return result;
  }

  static String displayTime(String timestamp) {
    if (timestamp.isBlank()) return "";
    try {
      return TIME.format(Instant.parse(timestamp));
    } catch (DateTimeParseException ignored) {
      return "";
    }
  }
}
