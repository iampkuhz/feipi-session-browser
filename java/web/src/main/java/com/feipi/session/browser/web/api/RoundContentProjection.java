package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
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
 * @param summary 工具计数或响应文本摘要
 * @param time 当前轮次首个已记录的调用时间
 * @param userInput 当前轮次是否包含可见用户输入
 */
record RoundContentProjection(String summary, String time, boolean userInput) {
  private static final DateTimeFormatter TIME =
      DateTimeFormatter.ofPattern("HH:mm:ss").withZone(ZoneId.of("Asia/Shanghai"));

  static RoundContentProjection from(CallRound round, NormalizedSessionArtifact artifact) {
    var projection = RoundIndexProjection.project(round, artifact);
    Set<String> ids = Set.copyOf(projection.callIds());
    String summary = RoundIndexProjection.toolCountSummary(projection.toolCallIds(), artifact);
    String assistant = "";
    boolean userInput = false;
    String time = "";
    for (var call : artifact.calls()) {
      if (!ids.contains(call.callId())) continue;
      if (time.isEmpty()) time = displayTime(call.timestamp().orElse(""));
      if (assistant.isBlank()) {
        assistant = PayloadCallContentExtractor.extractAssistantText(call, artifact);
      }
      userInput |=
          PayloadCallContentExtractor.extractUserMessageTexts(call, artifact).stream()
              .anyMatch(SessionDetailParityAnalyzer::isVisibleUserInput);
    }
    if (summary.isEmpty()) summary = assistant;
    summary = SensitiveFieldPolicy.DEFAULT.applyMasking(summary).replaceAll("\\s+", " ").trim();
    if (summary.length() > 240) summary = summary.substring(0, 240) + "…";
    return new RoundContentProjection(summary.isBlank() ? "内容未记录" : summary, time, userInput);
  }

  private static String displayTime(String timestamp) {
    if (timestamp.isBlank()) return "";
    try {
      return TIME.format(Instant.parse(timestamp));
    } catch (DateTimeParseException ignored) {
      return timestamp;
    }
  }
}
