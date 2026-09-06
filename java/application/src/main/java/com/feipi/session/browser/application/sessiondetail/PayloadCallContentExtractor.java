package com.feipi.session.browser.application.sessiondetail;

import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

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

  private PayloadCallContentExtractor() {}

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
    Objects.requireNonNull(call, "call 不得为 null");
    Objects.requireNonNull(artifact, "artifact 不得为 null");
    String catalogContent = resolveFromCatalog(call, artifact, false);
    if (!catalogContent.isEmpty()) {
      return catalogContent;
    }
    return resolveInline(call.sourceUnits(), ROLE_ASSISTANT, null, null);
  }

  /**
   * 提取 assistant 可见文本预览，用于 round 摘要。
   *
   * <p>从 response 内容中提取可读文本，截断到安全长度。
   */
  public static String extractAssistantText(
      NormalizedCall call, NormalizedSessionArtifact artifact) {
    String responseContent = extractResponseContent(call, artifact);
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
  private static String resolveInline(
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
    Map<String, SourceUnitCatalogEntry> catalog = artifact.sourceUnitCatalog();
    if (catalog.isEmpty() || call.sourceUnitRefRanges().isEmpty()) {
      return "";
    }
    StringBuilder sb = new StringBuilder();
    for (SourceUnitRefRange range : call.sourceUnitRefRanges()) {
      Optional<String> rangeRole = range.role();
      List<String> refs = range.refs();
      if (refs.isEmpty() && range.sequence().isPresent()) {
        String seqKey = range.sequence().get();
        List<String> sequence = artifact.sourceUnitSequences().getOrDefault(seqKey, List.of());
        int start = Math.min(range.start(), sequence.size());
        int end = Math.min(range.end(), sequence.size());
        refs = sequence.subList(start, end);
      }
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
      if (!"response".equalsIgnoreCase(entry.direction().getValue())) {
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
  private static String catalogEntryText(SourceUnitCatalogEntry entry) {
    Optional<String> text = entry.text();
    if (text.isPresent() && !text.get().isEmpty()) {
      return text.get();
    }
    Optional<String> preview = entry.preview();
    if (preview.isPresent() && !preview.get().isEmpty()) {
      return preview.get();
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
