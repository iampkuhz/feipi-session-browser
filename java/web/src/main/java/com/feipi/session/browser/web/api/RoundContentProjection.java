package com.feipi.session.browser.web.api;

import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.index.api.query.SessionRecord;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
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
    String summary = RoundIndexProjection.toolCountSummary(projection.toolCallIds(), artifact);
    String assistant = "";
    String user = "";
    String toolPreview = "";
    String time = "";
    for (var call : artifact.calls()) {
      if (!ids.contains(call.callId())) continue;
      if (time.isEmpty()) time = displayTime(previews.timestamp(call));
      if (assistant.isEmpty()) assistant = previews.text(call, false);
      String currentUser = previews.userText(call, round.roundIndex());
      if (user.isEmpty()) user = currentUser;
      if (toolPreview.isEmpty()) {
        toolPreview =
            previews.toolInputs(call).values().stream()
                .filter(value -> !value.isEmpty())
                .findFirst()
                .orElse("");
      }
    }
    if (!summary.isEmpty() && !toolPreview.isEmpty()) summary += " · " + toolPreview;
    if (summary.isEmpty()) summary = assistant;
    if (!user.isEmpty()) summary = user;
    summary = SensitiveFieldPolicy.DEFAULT.applyMasking(summary).replaceAll("\\s+", " ").trim();
    if (summary.codePointCount(0, summary.length()) > 240)
      summary = summary.substring(0, summary.offsetByCodePoints(0, 240)) + "…";
    return new RoundContentProjection(summary.isBlank() ? "内容未记录" : summary, time, !user.isEmpty());
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
