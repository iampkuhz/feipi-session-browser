package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.api.query.ContentRoundIndex;
import com.feipi.session.browser.web.api.PageApiDtos.TokenSegments;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 为可重放内容生成精简页面汇总，不将完整会话展开为单个制品。 */
final class SessionContentProjection {
  private SessionContentProjection() {}

  /**
   * 按完整逻辑轮次计算摘要，仅保留标量汇总，不保存全部成员标识符。
   *
   * @param detail 会话基础信息与载荷可见性策略
   * @param content 可独立重放的不可变会话内容
   * @return 保留完整计数的精简逻辑轮次摘要
   * @throws IOException 读取或重放冻结内容失败
   */
  static List<SessionDetailApiResponses.RoundIndexDto> rounds(
      SessionDetail detail, NormalizedSessionContent content) throws IOException {
    var reader = new SessionContentReader(content, detail.sessionRow().userMessageCount());
    var index = reader.roundIndex();
    var summaries = new ArrayList<Summary>();
    for (int i = 0; i < index.roundCount(); i++) summaries.add(new Summary());
    var previews = SessionContentPreviews.read(content);
    var inlineToolPreviews = new HashMap<String, ToolInputPreview.Summary>();
    if (content.header().totals().getOrDefault("calls", 0L) == 0 && !summaries.isEmpty()) {
      summaries.getFirst().userPreview = reader.observedInputPreview();
      summaries.getFirst().observedInputAvailable = reader.hasObservedInput();
    }
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        for (var call : unit.calls()) {
          int round = index.roundIndexForCall(call.callId()).orElseThrow();
          var summary = summaries.get(round - 1);
          summary.calls++;
          if (summary.time.isEmpty()) {
            summary.time = RoundContentProjection.displayTime(previews.timestamp(call));
          }
          if (summary.sideTask == null) {
            summary.sideTask = ContentRoundIndex.sideTask(call).orElse(null);
          }
          if (summary.calls == 1) {
            summary.evidence = ContentRoundIndex.modelCallEvidence(content.header().agent(), call);
            summary.parent = call.parentCallId().orElse("");
          }
          summary.usage.add(call);
          summary.agentUsage.add(call);
          summary.requestAvailable |= previews.hasPayload(call, true);
          summary.responseAvailable |= previews.hasPayload(call, false);
          if (call.scope() == CallScope.MAIN || summary.calls == 1) {
            String userText = previews.userText(call, round);
            summary.userPreview =
                RoundContentProjection.preferredUser(
                    summary.userPreview, userText, summary.sideTask != null);
          }
          if (summary.assistantPreview.isEmpty())
            summary.assistantPreview = previews.text(call, false);
          if (summary.compactionPreview.isEmpty())
            summary.compactionPreview = RoundContentProjection.compactionSummary(call);
          ToolInputContents.inline(call)
              .forEach(
                  (id, input) -> {
                    var catalog = previews.toolInput(id);
                    if (catalog == null || catalog.preview().isEmpty()) {
                      inlineToolPreviews.putIfAbsent(id, ToolInputPreview.summarize(input));
                    }
                  });
          var usage = call.usage();
          summary.fresh += usage.fresh();
          summary.read += usage.cacheRead();
          summary.write += usage.cacheWrite();
          summary.output += usage.output();
          summary.subagent |= call.scope() == CallScope.SUBAGENT;
        }
        for (var tool : unit.toolExecutions()) {
          var round = index.roundIndexForCall(tool.declaredByCallId());
          if (round.isEmpty()) continue;
          var summary = summaries.get(round.getAsInt() - 1);
          summary.tools++;
          var inline = inlineToolPreviews.remove(tool.toolCallId());
          var input = inline == null ? previews.toolInput(tool.toolCallId()) : inline;
          summary.toolCounts.merge(ToolInputPreview.category(tool.name(), input), 1, Integer::sum);
          if (SessionDetailParityAnalyzer.hasFailedStatus(tool)) {
            summary.failed++;
            summary.agentUsage.markFailure(tool);
          }
        }
      }
    }
    long sessionTokens =
        summaries.stream().mapToLong(value -> value.usage.segments().total()).sum();
    var rows = new ArrayList<SessionDetailApiResponses.RoundIndexDto>();
    var freshValues = summaries.stream().map(value -> value.fresh).sorted().toList();
    double medianFresh =
        freshValues.isEmpty()
            ? 0
            : freshValues.size() % 2 == 1
                ? freshValues.get(freshValues.size() / 2)
                : (freshValues.get(freshValues.size() / 2 - 1) / 2.0
                    + freshValues.get(freshValues.size() / 2) / 2.0);
    for (int i = 0; i < summaries.size(); i++) {
      var summary = summaries.get(i);
      var precision = summary.usage.segments().provenance();
      boolean cacheMeasured =
          "provider_reported".equals(precision.freshInput())
              && "provider_reported".equals(precision.cacheRead())
              && "provider_reported".equals(precision.cacheWrite());
      long input = summary.fresh + summary.read + summary.write;
      boolean lowCache = cacheMeasured && input > 0 && summary.read * 100.0 / input < 20.0;
      boolean freshSpike =
          "provider_reported".equals(precision.freshInput())
              && medianFresh > 0
              && summary.fresh > medianFresh * 2.0;
      long tokens = summary.fresh + summary.read + summary.write + summary.output;
      var signals = new ArrayList<String>();
      if (summary.failed > 0) signals.add("Failed");
      if (summary.subagent) signals.add("Subagent");
      String observedInput =
          summary.calls == 0 && summary.tools == 0 && summary.userPreview.isEmpty()
              ? RoundContentProjection.observedInputSummary(detail.sessionRow())
              : "";
      String toolSummary = ToolActionCategory.summary(summary.toolCounts);
      String preview =
          !summary.userPreview.isEmpty()
              ? summary.userPreview
              : !toolSummary.isEmpty() ? toolSummary : summary.assistantPreview;
      if (preview.isEmpty()) preview = summary.compactionPreview;
      if (preview.codePointCount(0, preview.length()) > 240) {
        preview = preview.substring(0, preview.offsetByCodePoints(0, 240)) + "…";
      }
      rows.add(
          new SessionDetailApiResponses.RoundIndexDto(
              i + 1,
              List.of(),
              List.of(),
              summary.parent,
              TokenSegments.of(
                  summary.fresh,
                  summary.read,
                  summary.write,
                  summary.output,
                  summary.usage.segments().provenance()),
              summary.calls,
              summary.tools,
              summary.failed,
              List.of(),
              sessionTokens > 0 ? tokens / (double) sessionTokens : null,
              summary.failed > 0 ? "failed" : "ok",
              signals,
              RoundContentProjection.withTask(
                  Map.ofEntries(
                      Map.entry("summary", observedInput.isEmpty() ? preview : observedInput),
                      Map.entry(
                          "summaryRole",
                          !summary.userPreview.isEmpty()
                              ? "user"
                              : !toolSummary.isEmpty()
                                  ? "tool"
                                  : summary.assistantPreview.isEmpty() ? "" : "assistant"),
                      Map.entry(
                          "time",
                          RoundContentProjection.withTaskTime(summary.time, summary.sideTask)),
                      Map.entry("membersPaged", true),
                      Map.entry("observedInputAvailable", summary.observedInputAvailable),
                      Map.entry(
                          "isUserInput",
                          !observedInput.isEmpty() || !summary.userPreview.isEmpty()),
                      Map.entry("hasIssues", summary.failed > 0),
                      Map.entry("isLowCache", lowCache),
                      Map.entry("isFreshSpike", freshSpike),
                      Map.entry("modelCallEvidence", summary.calls == 1 ? summary.evidence : ""),
                      Map.entry("requestAvailable", summary.requestAvailable),
                      Map.entry("responseAvailable", summary.responseAvailable),
                      Map.entry("agentUsage", summary.agentUsage.snapshot())),
                  summary.sideTask)));
    }
    return List.copyOf(rows);
  }

  /** 保存单个逻辑轮次的标量汇总，不持有成员正文或完整标识符列表。 */
  private static final class Summary {
    final SessionContentUsage usage = new SessionContentUsage();
    final RoundAgentUsage agentUsage = new RoundAgentUsage();
    int calls;
    int tools;
    int failed;
    long fresh;
    long read;
    long write;
    long output;
    boolean subagent;
    boolean observedInputAvailable;
    boolean requestAvailable;
    boolean responseAvailable;
    ContentRoundIndex.SideTask sideTask;
    String evidence = "";
    String parent = "";
    String userPreview = "";
    String assistantPreview = "";
    String compactionPreview = "";
    String time = "";
    final Map<String, Integer> toolCounts = new LinkedHashMap<>();
  }
}
