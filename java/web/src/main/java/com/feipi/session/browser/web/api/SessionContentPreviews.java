package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.CallReadingEvidence;
import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCollaborationAction;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
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
  private Map<String, ToolInputPreview.Summary> independentTools = Map.of();
  private final Set<String> unownedTools = new HashSet<>();
  private final Map<String, Integer> firstUserRound = new HashMap<>();
  private final Set<String> shownUserRefs = new HashSet<>();
  private final Set<String> shownUserRounds = new HashSet<>();
  private final Set<String> resultIds = new HashSet<>();
  private NormalizedToolExecution resultTool;
  private boolean ambiguousResultTool;
  private final Map<String, Origin> origins = new HashMap<>();
  private final Map<String, String> declarations = new HashMap<>();
  private final Map<String, ToolClaim> collaborationTools = new HashMap<>();
  private final Set<String> conflicts = new HashSet<>();
  private final Map<String, Candidate> candidates = new HashMap<>();
  private boolean candidateBudgetExceeded;

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
    return read(content, null);
  }

  static SessionContentPreviews read(NormalizedSessionContent content, String resultToolId)
      throws IOException {
    var result = new SessionContentPreviews(content.header().agent() == NormalizedAgent.CODEX);
    var pendingToolDates = new ArrayList<PendingToolDates>();
    var independent =
        new ToolInputContents.IndependentInputs<ToolInputPreview.Summary>(
            content.header(), ToolInputPreview::summarize);
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        independent.accept(unit);
        if (resultToolId != null) {
          for (var tool : unit.toolExecutions()) {
            if (!resultToolId.equals(tool.toolCallId())) continue;
            result.ambiguousResultTool |=
                result.resultTool != null && !result.resultTool.equals(tool);
            result.resultTool = tool;
          }
        }
        for (var call : unit.calls()) {
          result.observeCall(call, pendingToolDates);
          var origin = new Origin(call.scope(), call.subagentId().orElse(""));
          if (result.origins.putIfAbsent(call.callId(), origin) != null) {
            result.conflicts.add("call:" + call.callId());
          }
          for (String id : call.response().toolCallIds()) {
            if (result.declarations.putIfAbsent(id, call.callId()) != null)
              result.conflicts.add(id);
          }
          for (var source : call.sourceUnits()) {
            if (!"user".equals(source.get("role")))
              result.observeCandidates(source, 0, new int[] {1024});
          }
        }
        for (var tool : unit.toolExecutions()) {
          if ("unknown".equals(tool.declaredByCallId())) result.unownedTools.add(tool.toolCallId());
          var actions =
              tool.collaboration().stream()
                  .filter(action -> "declaration".equals(action.phase()))
                  .toList();
          var claim =
              new ToolClaim(
                  tool.declaredByCallId(),
                  tool.name(),
                  new Origin(tool.scope(), tool.subagentId().orElse("")),
                  actions.size() == 1 ? actions.getFirst() : null);
          if (result.collaborationTools.putIfAbsent(tool.toolCallId(), claim) != null) {
            result.conflicts.add(tool.toolCallId());
          }
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
          if (!request) result.observeCandidates(value.payload(), 0, new int[] {1024});
        }
      }
    }
    result.independentTools = independent.finish();
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

  Map<String, ToolInputPreview.Summary> independentToolInputs() {
    return independentTools;
  }

  boolean hasToolResult(String id) {
    return resultIds.contains(id);
  }

  ApiResponses.ToolResultEvidence toolResultEvidence() {
    if (resultTool == null || ambiguousResultTool) return null;
    return new ApiResponses.ToolResultEvidence(
        SensitiveFieldPolicy.DEFAULT.applyMasking(resultTool.name()),
        toolTimestamp(resultTool),
        resultTool.durationMs(),
        resultTool
            .observation()
            .filter(com.feipi.session.browser.domain.source.SourceToolObservation::measuresTool)
            .map(observation -> observation.durationNanos())
            .orElse(null));
  }

  boolean hasPayload(NormalizedCall call, boolean request) {
    if (request && codex && CallReadingEvidence.hasObservedInputUsage(call)) return true;
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
      if (unownedTools.contains(id)) {
        var independent = independentTools.get(id);
        if (independent != null) summaries.put(id, independent);
        continue;
      }
      var summary = toolInput(id);
      if ((summary == null || summary.preview().isEmpty()) && inline.containsKey(id))
        summary = ToolInputPreview.summarize(inline.get(id));
      String kind = collaborationKind(id, call.callId());
      var candidate = candidates.get(id);
      if (!kind.isEmpty() && candidate != null) {
        String operation = "delegate".equals(kind) ? candidate.delegate() : candidate.input();
        if (!operation.isEmpty())
          summary =
              new ToolInputPreview.Summary(operation, summary == null ? "" : summary.category());
      }
      if (summary != null) summaries.put(id, summary);
    }
    return summaries;
  }

  /** 只验证已归一化 occurrence；未知执行者和跨调用重用不挑 first/last。 */
  private String collaborationKind(String id, String callId) {
    if (candidateBudgetExceeded || conflicts.contains(id) || conflicts.contains("call:" + callId))
      return "";
    var tool = collaborationTools.get(id);
    var origin = origins.get(callId);
    var candidate = candidates.get(id);
    if (tool == null
        || origin == null
        || candidate == null
        || !callId.equals(declarations.get(id))
        || !callId.equals(tool.callId())
        || tool.origin().scope() != origin.scope()
        || !tool.name().equals(candidate.name())) return "";
    var action = tool.action();
    if (action == null || action.sourceLocator().isBlank()) return "";
    boolean delegate = "delegate".equals(action.kind());
    // 独立 spawn 声明的关联实例可为目标 child；执行者仍只取 owner 与 typed actor。
    if (!tool.origin().actor().equals(origin.actor())
        && !(delegate && action.targetId().filter(tool.origin().actor()::equals).isPresent()))
      return "";
    boolean main = origin.scope() == com.feipi.session.browser.domain.enums.CallScope.MAIN;
    if (!(main
            ? origin.actor().isEmpty() && "main_context".equals(action.actorIdentityReason())
            : !origin.actor().isBlank() && "explicit_instance".equals(action.actorIdentityReason()))
        || !action.actorId().orElse("").equals(origin.actor())
        || !(delegate
            ? Set.of(
                    "target_unknown",
                    "child_candidate_available",
                    "child_not_found",
                    "single_file_not_included")
                .contains(action.reason())
            : "input".equals(action.kind())
                && "explicit_target".equals(action.reason())
                && action.targetId().filter(idValue -> !idValue.isBlank()).isPresent())) return "";
    return action.kind();
  }

  /** 当场丢弃原文；仅留指纹和两种至多 180 字符的安全候选，不等待后续资格。 */
  private void observeCandidates(Object value, int depth, int[] budget) {
    if (depth > 8 || budget[0]-- <= 0) {
      candidateBudgetExceeded = true;
      return;
    }
    if (!(value instanceof Map<?, ?> map)) return;
    if (List.of("tool_use", "function_call", "custom_tool_call")
        .contains(String.valueOf(map.get("type")))) {
      String id = "";
      for (String field : List.of("id", "call_id", "tool_call_id")) {
        if (map.get(field) instanceof String text && !text.isEmpty()) {
          id = text;
          break;
        }
      }
      Object raw = map.containsKey("input") ? map.get("input") : map.get("arguments");
      if (!id.isEmpty() && raw != null) {
        String name = map.get("name") instanceof String text ? text : "";
        var input = new ToolInputContents.Input(id, name, String.valueOf(raw));
        if (input.input().length() > 64 * 1024) {
          conflicts.add(id);
          return;
        }
        var candidate =
            new Candidate(
                name,
                fingerprint(input.input()),
                ToolInputPreview.collaboration(input, "delegate"),
                ToolInputPreview.collaboration(input, "input"));
        var previous = candidates.putIfAbsent(id, candidate);
        if (previous != null && !previous.equals(candidate)) conflicts.add(id);
      }
    }
    if (map.get("content") instanceof List<?> blocks) {
      for (var block : blocks) observeCandidates(block, depth + 1, budget);
    }
  }

  private static String fingerprint(String text) {
    try {
      return java.util.HexFormat.of()
          .formatHex(
              java.security.MessageDigest.getInstance("SHA-256")
                  .digest(text.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
    } catch (java.security.NoSuchAlgorithmException exception) {
      throw new IllegalStateException("缺少标准输入指纹算法", exception);
    }
  }

  /**
   * 紧凑执行上下文，不保存调用正文。
   *
   * @param scope 声明调用作用域
   * @param actor 完整执行实例；主上下文为空
   */
  private record Origin(com.feipi.session.browser.domain.enums.CallScope scope, String actor) {}

  /**
   * 工具紧凑身份与唯一声明；不保存完整执行边或正文。
   *
   * @param callId 声明调用标识
   * @param name 原工具名称
   * @param origin 工具执行上下文
   * @param action 唯一声明；不唯一时为空
   */
  private record ToolClaim(
      String callId, String name, Origin origin, NormalizedCollaborationAction action) {}

  /**
   * 输入的有界安全候选；协议原文不会进入缓存。
   *
   * @param name 原工具名称
   * @param fingerprint 输入指纹，用于拒绝不一致声明
   * @param delegate 委派安全短摘要
   * @param input 追加输入安全短摘要
   */
  private record Candidate(String name, String fingerprint, String delegate, String input) {}

  private List<String> refs(com.feipi.session.browser.domain.normalized.SourceUnitRefRange range) {
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
