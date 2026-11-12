package com.feipi.session.browser.web.api;

import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import java.io.IOException;
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
  private final Map<String, String> tools = new HashMap<>();
  private final Map<String, Integer> firstUserRound = new HashMap<>();
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
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        for (var call : unit.calls()) {
          for (var source : call.sourceUnits()) result.observeResult(source, null, null);
        }
        for (var chunk : unit.sourceUnitSequences()) {
          result.sequences.computeIfAbsent(chunk.name(), key -> new ArrayList<>()).add(chunk);
        }
        for (var entry : unit.sourceUnitCatalog().entrySet()) {
          var value = entry.getValue();
          result.observeResult(value.payload(), value.unitType(), value.label().orElse(null));
          boolean request = "request".equals(value.direction().getValue());
          String role = request ? "user" : "assistant";
          result.entries.put(
              entry.getKey(),
              new Entry(
                  request,
                  PayloadCallContentExtractor.catalogPreview(
                      value, Optional.empty(), request, result.codex),
                  PayloadCallContentExtractor.catalogPreview(
                      value, Optional.of(role), request, result.codex),
                  request ? "" : value.timestamp().orElse("")));
          ToolInputContents.catalog(value)
              .forEach((id, input) -> result.tools.putIfAbsent(id, ToolInputPreview.from(input)));
        }
      }
    }
    return result;
  }

  boolean hasToolResult(String id) {
    return resultIds.contains(id);
  }

  private void observeResult(Object value, String type, String label) {
    Map<?, ?> payload = value instanceof Map<?, ?> map ? map : Map.of();
    var types = List.of("tool_result", "function_call_output", "custom_tool_call_output");
    if (!(type != null && types.contains(type))
        && !types.contains(String.valueOf(payload.get("type")))) return;
    for (String field : List.of("tool_call_id", "tool_use_id", "call_id")) {
      if (payload.get(field) instanceof String id && !id.isBlank()) {
        resultIds.add(id);
        break;
      }
    }
    if (label != null && !label.isBlank()) resultIds.add(label);
  }

  String text(NormalizedCall call, boolean request) {
    String role = request ? "user" : "assistant";
    for (var range : call.sourceUnitRefRanges()) {
      if (range.role().isPresent() && !role.equalsIgnoreCase(range.role().get())) continue;
      for (String ref : refs(range)) {
        var entry = entries.get(ref);
        if (entry == null || entry.request() != request) continue;
        String text = range.role().isPresent() ? entry.roleText() : entry.text();
        if (!text.isEmpty()) return text;
      }
    }
    return PayloadCallContentExtractor.inlinePreview(call, request, request && codex);
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

  Map<String, String> toolInputs(NormalizedCall call) {
    var previews = new LinkedHashMap<String, String>();
    var inline = ToolInputContents.inline(call);
    for (String id : call.response().toolCallIds()) {
      String preview = tools.getOrDefault(id, "");
      if (preview.isEmpty()) preview = ToolInputPreview.from(inline.get(id));
      previews.put(id, preview);
    }
    return previews;
  }

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
   */
  private record Entry(boolean request, String text, String roleText, String timestamp) {}
}
