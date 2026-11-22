package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.CallReadingEvidence;
import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.io.IOException;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/** 只保留遮蔽后的短文本和引用元数据；不将完整载荷或工具输出物化到首屏。 */
final class SessionContentPreviews {
  private final boolean codex;
  private final Map<String, Entry> entries = new HashMap<>();
  private final Map<String, List<NormalizedSequenceChunk>> sequences = new HashMap<>();
  private final Map<String, ToolInputPreview.Summary> tools = new HashMap<>();
  private final Map<String, Map<String, String>> toolTimestamps = new HashMap<>();
  private final Map<String, Integer> firstUserRound = new HashMap<>();
  private final Set<String> shownUserRefs = new HashSet<>();
  private final Set<String> shownUserRounds = new HashSet<>();
  private final Set<String> resultIds = new HashSet<>();

  private SessionContentPreviews(boolean codex) {
    this.codex = codex;
  }

  static SessionContentPreviews readArtifact(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact) {
    try {
      return read(NormalizedSessionContent.fromArtifact(artifact));
    } catch (IOException exception) {
      throw new IllegalStateException("无法读取已验证的内容预览", exception);
    }
  }

  static SessionContentPreviews read(NormalizedSessionContent content) throws IOException {
    var result = new SessionContentPreviews(content.header().agent() == NormalizedAgent.CODEX);
    var pendingToolDates = new ArrayList<PendingToolDates>();
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        for (var call : unit.calls()) {
          result.observeCall(call, pendingToolDates);
        }
        for (var chunk : unit.sourceUnitSequences()) {
          result.sequences.computeIfAbsent(chunk.name(), key -> new ArrayList<>()).add(chunk);
        }
        for (var entry : unit.sourceUnitCatalog().entrySet()) {
          var value = entry.getValue();
          result.observeResult(value.payload(), value.unitType(), value.label().orElse(null));
          boolean request = "request".equals(value.direction().getValue());
          String role = request ? "user" : "assistant";
          var catalogTools = ToolInputContents.catalog(value);
          result.entries.put(
              entry.getKey(),
              new Entry(
                  request,
                  PayloadCallContentExtractor.catalogPreview(
                      value, Optional.empty(), request, result.codex),
                  PayloadCallContentExtractor.catalogPreview(
                      value, Optional.of(role), request, result.codex),
                  request ? "" : value.timestamp().orElse(""),
                  PayloadCallContentExtractor.hasCatalogPayload(value),
                  List.copyOf(catalogTools.keySet())));
          catalogTools.forEach(
              (id, input) -> result.tools.putIfAbsent(id, ToolInputPreview.summarize(input)));
        }
      }
    }
    pendingToolDates.forEach(result::observeCatalogToolDates);
    return result;
  }

  private void observeCall(NormalizedCall call, List<PendingToolDates> pending) {
    var declared = Set.copyOf(call.response().toolCallIds());
    for (var source : call.sourceUnits()) {
      observeResult(source, null, null);
      if ("tool_use".equals(source.get("type"))
          && "assistant".equals(source.get("role"))
          && source.get("id") instanceof String id
          && declared.contains(id)
          && source.get("timestamp") instanceof String timestamp) {
        observeToolDate(call.callId(), id, timestamp);
      }
    }
    if (!declared.isEmpty() && !call.sourceUnitRefRanges().isEmpty())
      pending.add(new PendingToolDates(call.callId(), declared, call.sourceUnitRefRanges()));
  }

  private void observeCatalogToolDates(PendingToolDates call) {
    for (var range : call.ranges()) {
      if (range.role().filter(value -> !"assistant".equalsIgnoreCase(value)).isPresent()) continue;
      for (String ref : refs(range)) {
        var entry = entries.get(ref);
        if (entry == null || entry.request() || entry.timestamp().isBlank()) continue;
        for (String id : entry.declaredTools()) {
          if (call.declared().contains(id)) observeToolDate(call.callId(), id, entry.timestamp());
        }
      }
    }
  }

  private void observeToolDate(String callId, String id, String timestamp) {
    if (timestamp.isBlank()) return;
    try {
      String iso = Instant.parse(timestamp).toString();
      toolTimestamps
          .computeIfAbsent(callId, key -> new HashMap<>())
          .merge(id, iso, (old, next) -> old.equals(next) ? old : "");
    } catch (DateTimeParseException ignored) {
      // 无法验证的时间不得作为工具声明时间。
    }
  }

  String toolTimestamp(NormalizedToolExecution tool) {
    String timestamp =
        toolTimestamps.getOrDefault(tool.declaredByCallId(), Map.of()).get(tool.toolCallId());
    return timestamp == null || timestamp.isBlank() ? null : timestamp;
  }

  boolean hasToolResult(String id) {
    return resultIds.contains(id);
  }

  boolean hasPayload(NormalizedCall call, boolean request) {
    if (!request
        && (!call.response().toolCallIds().isEmpty()
            || codex && CallReadingEvidence.hasObservedResponse(call))) return true;
    String role = request ? "user" : "assistant";
    for (var range : call.sourceUnitRefRanges()) {
      if (range.role().filter(value -> !role.equalsIgnoreCase(value)).isPresent()) continue;
      for (String ref : refs(range)) {
        var entry = entries.get(ref);
        if (entry != null && entry.request() == request && entry.hasPayload()) return true;
      }
    }
    return PayloadCallContentExtractor.hasInlinePayload(call, request);
  }

  private void observeResult(Object value, String type, String label) {
    Map<?, ?> payload = value instanceof Map<?, ?> map ? map : Map.of();
    if (payload.get("message") instanceof Map<?, ?> message) observeResult(message, null, null);
    if (payload.get("content") instanceof List<?> blocks) {
      for (Object block : blocks) {
        if (block instanceof Map<?, ?>) observeResult(block, null, null);
      }
    }
    var types = List.of("tool_result", "function_call_output", "custom_tool_call_output");
    if (!(type != null && types.contains(type))
        && !types.contains(String.valueOf(payload.get("type")))) return;
    for (String field : List.of("tool_call_id", "tool_use_id", "call_id")) {
      if (payload.get(field) instanceof String id && !id.isBlank()) {
        resultIds.add(id);
        break;
      }
    }
    if (label != null && !label.isBlank()) {
      resultIds.add(label);
    }
  }

  /** 轮次标签与 RoundIndexDto 一致：只有单调用且有模型边界证据时使用 R。 */
  static Map<Integer, String> roundLabels(
      NormalizedSessionContent content,
      com.feipi.session.browser.index.api.query.ContentRoundIndex index)
      throws IOException {
    var counts = new HashMap<Integer, Integer>();
    var evidence = new HashMap<Integer, Boolean>();
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        for (var call : cursor.next().calls()) {
          int round = index.roundIndexForCall(call.callId()).orElse(0);
          counts.merge(round, 1, Integer::sum);
          evidence.putIfAbsent(
              round,
              !com.feipi.session.browser.index.api.query.ContentRoundIndex.modelCallEvidence(
                      content.header().agent(), call)
                  .isBlank());
        }
      }
    }
    var labels = new HashMap<Integer, String>();
    counts.forEach(
        (round, count) ->
            labels.put(
                round, (count == 1 && evidence.getOrDefault(round, false) ? "R" : "G") + round));
    return labels;
  }

  String newUserText(NormalizedCall call, int round) {
    String preview = userText(call, round);
    if (preview.isEmpty()) return "";
    boolean referenced = false;
    boolean fresh = false;
    for (var range : call.sourceUnitRefRanges()) {
      if (range.role().filter(role -> !"user".equalsIgnoreCase(role)).isPresent()) continue;
      for (String ref : refs(range)) {
        var entry = entries.get(ref);
        if (entry == null || !entry.request()) continue;
        String text = range.role().isPresent() ? entry.roleText() : entry.text();
        if (!SessionDetailParityAnalyzer.isVisibleUserInput(text)) continue;
        referenced = true;
        fresh |= shownUserRefs.add(ref);
      }
    }
    String context = call.scope() + ":" + call.subagentId().orElse("") + ":" + round;
    return (referenced ? fresh : shownUserRounds.add(context)) ? preview : "";
  }

  String text(NormalizedCall call, boolean request) {
    return text(call, request, false);
  }

  String latestAssistantText(NormalizedCall call) {
    return text(call, false, true);
  }

  private String text(NormalizedCall call, boolean request, boolean latest) {
    String role = request ? "user" : "assistant";
    var ranges = call.sourceUnitRefRanges();
    for (var range : latest ? ranges.reversed() : ranges) {
      if (range.role().isPresent() && !role.equalsIgnoreCase(range.role().get())) continue;
      var keys = refs(range);
      for (String ref : latest ? keys.reversed() : keys) {
        var entry = entries.get(ref);
        if (entry == null || entry.request() != request) continue;
        String text = range.role().isPresent() ? entry.roleText() : entry.text();
        if (!text.isEmpty()) return text;
      }
    }
    return latest
        ? PayloadCallContentExtractor.latestInlineAssistantPreview(call)
        : PayloadCallContentExtractor.inlinePreview(call, request, request && codex);
  }

  /** 请求可携带历史上下文；摘要只使用本轮首次出现的稳定用户引用，不按文本猜测去重。 */
  String userText(NormalizedCall call, int round) {
    String preview = "";
    boolean hasReferencedText = false;
    for (var range : call.sourceUnitRefRanges()) {
      if (range.role().filter(role -> !"user".equalsIgnoreCase(role)).isPresent()) continue;
      for (String ref : refs(range)) {
        var entry = entries.get(ref);
        if (entry == null || !entry.request()) continue;
        String text = range.role().isPresent() ? entry.roleText() : entry.text();
        if (!SessionDetailParityAnalyzer.isVisibleUserInput(text)) continue;
        hasReferencedText = true;
        Integer owner = firstUserRound.putIfAbsent(ref, round);
        if (preview.isEmpty() && (owner == null || owner == round)) preview = text;
      }
    }
    if (hasReferencedText) return preview;
    String inline = PayloadCallContentExtractor.inlinePreview(call, true, codex);
    return SessionDetailParityAnalyzer.isVisibleUserInput(inline) ? inline : "";
  }

  String timestamp(NormalizedCall call) {
    if (call.timestamp().filter(value -> !value.isBlank()).isPresent())
      return call.timestamp().get();
    for (var range : call.sourceUnitRefRanges()) {
      if (range.role().filter("user"::equalsIgnoreCase).isPresent()) continue;
      for (String ref : refs(range)) {
        var entry = entries.get(ref);
        if (entry != null && !entry.timestamp().isBlank()) return entry.timestamp();
      }
    }
    return "";
  }

  ToolInputPreview.Summary toolInput(String id) {
    return tools.get(id);
  }

  Map<String, ToolInputPreview.Summary> toolInputSummaries(NormalizedCall call) {
    var summaries = new LinkedHashMap<String, ToolInputPreview.Summary>();
    var inline = ToolInputContents.inline(call);
    for (String id : call.response().toolCallIds()) {
      var summary = toolInput(id);
      if ((summary == null || summary.preview().isEmpty()) && inline.containsKey(id))
        summary = ToolInputPreview.summarize(inline.get(id));
      if (summary != null) summaries.put(id, summary);
    }
    return summaries;
  }

  private List<String> refs(SourceUnitRefRange range) {
    if (!range.refs().isEmpty() || range.sequence().isEmpty()) return range.refs();
    var refs = new ArrayList<String>();
    for (var chunk : sequences.getOrDefault(range.sequence().get(), List.of())) {
      long start = Math.max(range.start(), chunk.offset());
      long end = Math.min(range.end(), chunk.offset() + chunk.keys().size());
      for (long i = start; i < end; i++) refs.add(chunk.keys().get((int) (i - chunk.offset())));
    }
    return refs;
  }

  /**
   * 单条目录证据的短文本、方向与响应时间，不持有完整源载荷。
   *
   * @param request 是否为请求方向
   * @param text 不依赖范围角色的可见短预览
   * @param roleText 角色匹配时的可见短预览
   * @param timestamp 响应源时间；请求方向为空
   * @param hasPayload 可读取的原文是否存在
   * @param declaredTools 此条响应里的声明工具 ID
   */
  private record Entry(
      boolean request,
      String text,
      String roleText,
      String timestamp,
      boolean hasPayload,
      List<String> declaredTools) {}

  /**
   * 等待目录构造完毕的声明与引用，避免保留正文。
   *
   * @param callId 声明调用的规范化 ID
   * @param declared 此调用的工具声明 ID
   * @param ranges 此调用的目录引用
   */
  private record PendingToolDates(
      String callId, Set<String> declared, List<SourceUnitRefRange> ranges) {}
}
