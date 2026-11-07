package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.regex.Pattern;

/**
 * 从归一化调用源单元提取 payload 文本内容。
 *
 * <p>支持两种内容寻址路径：
 *
 * <ul>
 *   <li>调用内联 {@code sourceUnits} 列表（向后兼容）。
 *   <li>制品级 {@code sourceUnitCatalog}，通过 {@code sourceUnitRefRanges} 引用。
 * </ul>
 *
 * <p>提取逻辑按 role/direction 分类 request 与 response 侧内容，并对 tool result 按 toolCallId 匹配。
 */
public final class PayloadCallContentExtractor {

  private static final String ROLE_USER = "user";
  private static final String ROLE_ASSISTANT = "assistant";
  private static final String TYPE_TOOL_RESULT = "tool_result";
  private static final String FIELD_ROLE = "role";
  private static final String FIELD_TYPE = "type";
  private static final String FIELD_TEXT = "text";
  private static final String FIELD_CONTENT = "content";
  private static final String FIELD_TOOL_CALL_ID = "tool_call_id";
  private static final String FIELD_OUTPUT = "output";
  private static final int MAX_PREVIEW_LENGTH = 2000;

  private static final Pattern PROJECT_INSTRUCTIONS_OPEN =
      Pattern.compile(
          "\\A# AGENTS\\.md instructions for [^\\r\\n]+\\R(?:[ \\t]*\\R)*[ \\t]*<INSTRUCTIONS>");
  private static final Pattern PROJECT_INSTRUCTIONS_BOUNDARY =
      Pattern.compile("(?m)^([ \\t]*)(`{3,}|~{3,}|</INSTRUCTIONS>)([^\\r\\n]*)");
  private static final List<String> CODEX_CONTEXT_TAGS =
      List.of(
          "environment_context",
          "codex_internal_context",
          "permissions instructions",
          "subagent_notification");

  private PayloadCallContentExtractor() {}

  /** 只提取显式用户消息，不把 request 中的工具结果或系统上下文当用户输入。 */
  public static List<String> extractUserMessageTexts(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    List<String> texts = new ArrayList<>();
    for (Map<String, Object> unit : call.sourceUnits()) {
      if (isReadingInline(unit, ROLE_USER)) {
        texts.add(extractTextValue(unit));
      }
    }
    for (SourceUnitRefRange range : call.sourceUnitRefRanges()) {
      for (String ref : catalogRefs(range, artifact)) {
        SourceUnitCatalogEntry entry = artifact.sourceUnitCatalog().get(ref);
        if (entry != null
            && "request".equals(entry.direction().getValue())
            && isReadingEntry(entry, range.role(), true)) {
          texts.add(catalogEntryText(entry));
        }
      }
    }
    return List.copyOf(texts);
  }

  private static List<String> catalogRefs(
      SourceUnitRefRange range, NormalizedSessionArtifact artifact) {
    if (!range.refs().isEmpty() || range.sequence().isEmpty()) return range.refs();
    List<String> sequence =
        artifact.sourceUnitSequences().getOrDefault(range.sequence().get(), List.of());
    return sequence.subList(
        Math.min(range.start(), sequence.size()), Math.min(range.end(), sequence.size()));
  }

  /**
   * 从调用中提取 request 侧文本内容。
   *
   * <p>优先使用 catalog 解析，回退到内联 sourceUnits。
   */
  public static String extractRequestContent(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    Objects.requireNonNull(call, "call 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    String catalogContent = resolveFromCatalog(call, artifact, true);
    if (!catalogContent.isEmpty()) {
      return catalogContent;
    }
    return resolveInline(call.sourceUnits(), ROLE_USER, null, null);
  }

  /**
   * 从调用中提取 response 侧文本内容。
   *
   * <p>优先使用 catalog 解析，回退到内联 sourceUnits。
   */
  public static String extractResponseContent(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    String text = extractResponseText(call, artifact);
    Map<String, ToolInputContents.Input> inputs = ToolInputContents.forCall(call, artifact);
    if (inputs.isEmpty()) return text;
    String commands =
        String.join(
            "\n\n", inputs.values().stream().map(ToolInputContents.Input::display).toList());
    return (text.isEmpty() ? "" : text + "\n\n") + "工具指令\n" + commands;
  }

  private static String extractResponseText(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    Objects.requireNonNull(call, "call 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    String catalogContent = resolveFromCatalog(call, artifact, false);
    if (!catalogContent.isEmpty()) {
      return catalogContent;
    }
    return resolveInline(call.sourceUnits(), ROLE_ASSISTANT, null, null);
  }

  static ReadingText readingText(
      NormalizedCall call, NormalizedSessionArtifact artifact, boolean request) {
    boolean codexRequest = request && artifact.agent() == NormalizedAgent.CODEX;
    var reading = new ReadingText(codexRequest);
    resolveFromCatalog(call, artifact, request, reading);
    return reading.orElse(readingInline(call, request, codexRequest));
  }

  static ReadingText readingInline(NormalizedCall call, boolean request, boolean codexRequest) {
    String role = request ? ROLE_USER : ROLE_ASSISTANT;
    var reading = new ReadingText(codexRequest);
    for (var unit : call.sourceUnits()) {
      if (isReadingInline(unit, role)) reading.add(extractTextValue(unit));
    }
    return reading;
  }

  /**
   * 仅用已读调用的内联可见文本生成短预览，不回读来源目录或调用载荷。
   *
   * @param call 当前已读的归一化调用
   * @param request 是否查找用户侧文本，否则查找助手侧文本
   * @param codexRequest 是否识别 Codex 请求的说明样式
   * @return 经过默认遮蔽的首行短预览，没有证据时为空
   */
  public static String inlinePreview(NormalizedCall call, boolean request, boolean codexRequest) {
    String role = request ? ROLE_USER : ROLE_ASSISTANT;
    for (var unit : call.sourceUnits()) {
      if (!isReadingInline(unit, role)) continue;
      String value = extractTextValue(unit);
      if (codexRequest) {
        String suffix = projectInstructionsSuffix(value);
        if (suffix != null) value = suffix;
        else if (PROJECT_INSTRUCTIONS_OPEN.matcher(value.stripLeading()).find()) continue;
        if (standaloneContext(value)) continue;
      }
      String first = value.stripLeading().lines().findFirst().orElse("").stripTrailing();
      if (first.isEmpty() || first.length() > 4096) continue;
      String masked = SensitiveFieldPolicy.DEFAULT.applyMasking(first);
      int length = masked.codePointCount(0, masked.length());
      return length > 160 ? masked.substring(0, masked.offsetByCodePoints(0, 160)) + "…" : masked;
    }
    return "";
  }

  /** 汇集可归属的对话；无法区分真实引用与上下文注入的独立段落只留在原始记录。 */
  static final class ReadingText {
    private final boolean codexRequest;
    private final StringBuilder text = new StringBuilder();
    private boolean unconfirmedContext;

    ReadingText(boolean codexRequest) {
      this.codexRequest = codexRequest;
    }

    void add(String value) {
      if (value == null || value.isBlank()) return;
      if (codexRequest) {
        String suffix = projectInstructionsSuffix(value);
        if (suffix != null) {
          unconfirmedContext = true;
          value = suffix;
        }
        if (standaloneContext(value)) {
          unconfirmedContext = true;
          return;
        }
        if (value.isBlank()) return;
      }
      if (!text.isEmpty()) text.append('\n');
      text.append(value);
    }

    ReadingText orElse(ReadingText inline) {
      if (text.isEmpty()) {
        inline.unconfirmedContext |= unconfirmedContext;
        return inline;
      }
      return this;
    }

    String text() {
      return text.toString();
    }

    boolean unconfirmedContext() {
      return unconfirmedContext;
    }
  }

  // 只分离具有完整标题与结束边界的前缀；不推断标签内文本的真实归属。
  private static String projectInstructionsSuffix(String value) {
    String text = value.stripLeading();
    var opening = PROJECT_INSTRUCTIONS_OPEN.matcher(text);
    if (!opening.find()) return null;
    int end = projectInstructionsEnd(text, opening.end());
    if (end < 0) return null;
    String suffix = text.substring(end).stripLeading();
    // Codex 有时紧接着序列化环境块，不会在两个标签间写换行。
    for (String tag : CODEX_CONTEXT_TAGS) {
      int contextEnd = contextEnd(suffix, tag);
      if (contextEnd >= 0) suffix = suffix.substring(contextEnd).stripLeading();
    }
    return suffix;
  }

  // 只扫描边界候选行。围栏中的标签是示例；不完整或含糊的边界保留原文。
  private static int projectInstructionsEnd(String text, int from) {
    var boundary = PROJECT_INSTRUCTIONS_BOUNDARY.matcher(text);
    String fence = "";
    for (boolean found = boundary.find(from); found; found = boundary.find()) {
      String indent = boundary.group(1);
      String marker = boundary.group(2);
      String tail = boundary.group(3);
      if (marker.startsWith("<")) {
        if (fence.isEmpty()
            && indent.isEmpty()
            && (tail.isBlank()
                || CODEX_CONTEXT_TAGS.stream()
                    .anyMatch(tag -> tail.stripLeading().startsWith("<" + tag + ">")))) {
          return boundary.end(2);
        }
      } else if (indent.length() <= 3 && indent.indexOf('\t') < 0) {
        if (fence.isEmpty()) {
          if (marker.charAt(0) == '~' || tail.indexOf('`') < 0) fence = marker;
        } else if (marker.charAt(0) == fence.charAt(0)
            && marker.length() >= fence.length()
            && tail.chars().allMatch(c -> c == ' ' || c == '\t')) {
          fence = "";
        }
      }
    }
    return -1;
  }

  private static boolean standaloneContext(String value) {
    String text = value.strip();
    return CODEX_CONTEXT_TAGS.stream().anyMatch(tag -> contextEnd(text, tag) == text.length());
  }

  private static int contextEnd(String text, String tag) {
    String opening = "<" + tag + ">";
    if (!text.startsWith(opening)) return -1;
    String closing = "</" + tag + ">";
    int offset = text.indexOf(closing, opening.length());
    return offset < 0 ? -1 : offset + closing.length();
  }

  private static boolean isReadingInline(Map<?, ?> unit, String role) {
    return role.equals(unit.get(FIELD_ROLE))
        && !Boolean.TRUE.equals(unit.get("isMeta"))
        && !isNonMessage(unit.get(FIELD_TYPE));
  }

  static boolean isReadingEntry(
      SourceUnitCatalogEntry entry, Optional<String> rangeRole, boolean request) {
    Map<?, ?> payload = entry.payload() instanceof Map<?, ?> map ? map : Map.of();
    if (Boolean.TRUE.equals(payload.get("isMeta"))
        || isNonMessage(entry.unitType())
        || isNonMessage(payload.get(FIELD_TYPE))) return false;
    String role = request ? ROLE_USER : ROLE_ASSISTANT;
    if (payload.get(FIELD_ROLE) instanceof String explicit) return role.equalsIgnoreCase(explicit);
    if (rangeRole.filter(role::equalsIgnoreCase).isPresent()) return true;
    return request
        ? List.of("user", "user_message", "user_text", "input_text").contains(entry.unitType())
            || "current_user_message".equals(entry.candidate())
        : List.of("assistant", "assistant_message", "assistant_text", "output_text")
            .contains(entry.unitType());
  }

  private static boolean isNonMessage(Object type) {
    return type instanceof String value
        && List.of(
                TYPE_TOOL_RESULT,
                "tool_use",
                "function_call",
                "custom_tool_call",
                "function_call_output",
                "custom_tool_call_output",
                "reasoning",
                "thinking",
                "system",
                "developer")
            .contains(value);
  }

  /**
   * 提取 assistant 可见文本预览，用于 round 摘要。
   *
   * <p>从 response 内容中提取可读文本，截断到安全长度。
   */
  public static String extractAssistantText(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    String responseContent = readingText(call, artifact, false).text();
    if (responseContent.isEmpty()) {
      return "";
    }
    return truncate(responseContent, MAX_PREVIEW_LENGTH);
  }

  /** 构建调用级 assistant 文本映射，key 为 callId。 */
  public static Map<String, String> buildCallAssistantTextMap(
      List<NormalizedCall> calls, NormalizedSessionArtifact artifact) {
    Map<String, String> result = new LinkedHashMap<>();
    for (NormalizedCall call : calls) {
      String text = extractAssistantText(call, artifact);
      if (!text.isEmpty()) {
        result.put(call.callId(), text);
      }
    }
    return result;
  }

  /** 从制品中提取工具结果文本，按 toolCallId 映射。 */
  public static Map<String, String> extractToolResultContents(NormalizedSessionArtifact artifact) {
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    Map<String, String> result = new LinkedHashMap<>();
    for (NormalizedCall call : artifact.calls()) {
      for (Map<String, Object> unit : call.sourceUnits()) {
        String type = stringField(unit, FIELD_TYPE);
        if (!TYPE_TOOL_RESULT.equals(type)) {
          continue;
        }
        String toolCallId = stringField(unit, FIELD_TOOL_CALL_ID);
        if (toolCallId.isEmpty() || result.containsKey(toolCallId)) {
          continue;
        }
        String text = extractTextValue(unit);
        if (!text.isEmpty()) {
          result.put(toolCallId, text);
        }
      }
    }
    for (NormalizedToolExecution exec : artifact.toolExecutions()) {
      if (result.containsKey(exec.toolCallId())) {
        continue;
      }
      String fromCatalog = resolveToolResultFromCatalog(exec.toolCallId(), artifact);
      if (!fromCatalog.isEmpty()) {
        result.put(exec.toolCallId(), fromCatalog);
      }
    }
    return result;
  }

  /** 从内联 sourceUnits 中提取匹配 role 和 type 的文本。 */
  static String resolveInline(
      List<Map<String, Object>> sourceUnits,
      String targetRole,
      String targetType,
      String toolCallId) {
    StringBuilder sb = new StringBuilder();
    for (Map<String, Object> unit : sourceUnits) {
      if (targetRole != null && !targetRole.equals(stringField(unit, FIELD_ROLE))) {
        continue;
      }
      if (targetType != null && !targetType.equals(stringField(unit, FIELD_TYPE))) {
        continue;
      }
      if (toolCallId != null) {
        String unitToolCallId = stringField(unit, FIELD_TOOL_CALL_ID);
        if (!toolCallId.equals(unitToolCallId)) {
          continue;
        }
      }
      String text = extractTextValue(unit);
      if (ROLE_USER.equals(targetRole)
          && TYPE_TOOL_RESULT.equals(unit.get(FIELD_TYPE))
          && !text.isEmpty()) {
        text = "Tool result [" + stringField(unit, FIELD_TOOL_CALL_ID) + "]\n" + text;
      }
      if (!text.isEmpty()) {
        if (!sb.isEmpty()) {
          sb.append("\n");
        }
        sb.append(text);
      }
    }
    return sb.toString();
  }

  /** 从 sourceUnit 中提取文本值，支持 text、content、output 字段。 */
  private static String extractTextValue(Map<String, Object> unit) {
    Object text = unit.get(FIELD_TEXT);
    if (text instanceof String s && !s.isEmpty()) {
      return s;
    }
    Object content = unit.get(FIELD_CONTENT);
    if (content instanceof String s && !s.isEmpty()) {
      return s;
    }
    if (content instanceof List<?> list) {
      StringBuilder sb = new StringBuilder();
      for (Object item : list) {
        if (item instanceof Map<?, ?> map) {
          Object itemText = map.get(FIELD_TEXT);
          if (itemText instanceof String s && !s.isEmpty()) {
            if (!sb.isEmpty()) {
              sb.append("\n");
            }
            sb.append(s);
          }
        }
      }
      if (!sb.isEmpty()) {
        return sb.toString();
      }
    }
    Object output = unit.get(FIELD_OUTPUT);
    if (output instanceof String s && !s.isEmpty()) {
      return s;
    }
    return "";
  }

  /** 通过 sourceUnitRefRanges 从 catalog 中解析内容。 */
  private static String resolveFromCatalog(
      NormalizedCall call, NormalizedSessionArtifact artifact, boolean requestSide) {
    return resolveFromCatalog(call, artifact, requestSide, null);
  }

  private static String resolveFromCatalog(
      NormalizedCall call,
      NormalizedSessionArtifact artifact,
      boolean requestSide,
      ReadingText reading) {
    Map<String, SourceUnitCatalogEntry> catalog = artifact.sourceUnitCatalog();
    if (catalog.isEmpty() || call.sourceUnitRefRanges().isEmpty()) {
      return "";
    }
    StringBuilder sb = new StringBuilder();
    for (SourceUnitRefRange range : call.sourceUnitRefRanges()) {
      Optional<String> rangeRole = range.role();
      List<String> refs = catalogRefs(range, artifact);
      for (String ref : refs) {
        SourceUnitCatalogEntry entry = catalog.get(ref);
        if (entry == null) {
          continue;
        }
        boolean isRequest = "request".equalsIgnoreCase(entry.direction().getValue());
        if (isRequest != requestSide) {
          continue;
        }
        if (rangeRole.isPresent()
            && !matchesRole(rangeRole.get(), requestSide ? ROLE_USER : ROLE_ASSISTANT)) {
          continue;
        }
        if (List.of("tool_use", "function_call", "custom_tool_call").contains(entry.unitType()))
          continue;
        if (reading != null) {
          if (isReadingEntry(entry, rangeRole, requestSide)) reading.add(catalogEntryText(entry));
          continue;
        }
        String text = catalogEntryText(entry);
        if (!text.isEmpty()) {
          if (!sb.isEmpty()) {
            sb.append("\n");
          }
          sb.append(text);
        }
      }
    }
    return sb.toString();
  }

  /** 从 catalog 中查找指定 toolCallId 的结果内容。 */
  private static String resolveToolResultFromCatalog(
      String toolCallId, NormalizedSessionArtifact artifact) {
    for (SourceUnitCatalogEntry entry : artifact.sourceUnitCatalog().values()) {
      boolean resultUnit =
          TYPE_TOOL_RESULT.equals(entry.unitType())
              || (entry.payload() instanceof Map<?, ?> value
                  && TYPE_TOOL_RESULT.equals(value.get(FIELD_TYPE)));
      if (!resultUnit) {
        continue;
      }
      Optional<String> label = entry.label();
      if (label.isPresent() && toolCallId.equals(label.get())) {
        String text = catalogEntryText(entry);
        if (!text.isEmpty()) {
          return text;
        }
      }
      Object payload = entry.payload();
      if (payload instanceof Map<?, ?> map) {
        Object id = map.get(FIELD_TOOL_CALL_ID);
        if (toolCallId.equals(String.valueOf(id))) {
          Object content = map.get(FIELD_CONTENT);
          if (content instanceof String s && !s.isEmpty()) {
            return s;
          }
        }
      }
    }
    return "";
  }

  /** 从 catalog 条目中提取文本。 */
  static String catalogEntryText(SourceUnitCatalogEntry entry) {
    Optional<String> text = entry.text();
    if (text.isPresent() && !text.get().isEmpty()) {
      return text.get();
    }
    Object payload = entry.payload();
    if (payload instanceof String s && !s.isEmpty()) {
      return s;
    }
    if (payload instanceof Map<?, ?> map) {
      Object content = map.get(FIELD_CONTENT);
      if (content instanceof String s && !s.isEmpty()) {
        return s;
      }
      Object textInPayload = map.get(FIELD_TEXT);
      if (textInPayload instanceof String s && !s.isEmpty()) {
        return s;
      }
    }
    return "";
  }

  private static boolean matchesRole(String rangeRole, String targetRole) {
    return targetRole.equalsIgnoreCase(rangeRole);
  }

  private static String stringField(Map<String, Object> map, String key) {
    Object value = map.get(key);
    return value instanceof String s ? s : "";
  }

  private static String truncate(String text, int maxLength) {
    if (text.length() <= maxLength) {
      return text;
    }
    return text.substring(0, maxLength) + "…";
  }
}
