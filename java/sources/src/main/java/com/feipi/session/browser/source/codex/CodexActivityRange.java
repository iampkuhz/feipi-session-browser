package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.AbstractList;
import java.util.HexFormat;
import java.util.List;

/** 借用事件列表的活动范围；屏蔽继承证据但不重编号原始事件。 */
final class CodexActivityRange {
  private static final JsonNode CONTEXT = JsonNodeFactory.instance.objectNode();
  private static final String SIDE_POLICY_OPEN = "<side_conversation>";
  private static final String SIDE_POLICY_CLOSE = "</side_conversation>";
  // 指纹取自官方侧聊边界的完整文本：标题、空行和正文。
  // 仅匹配整条原文，避免把用户引用、改写或混有提问的消息当成启动边界。
  // 旧版 TUI 固定正文另含临时会话段落（openai/codex@9df200a）。
  private static final String SIDE_EPHEMERAL_BOUNDARY_SHA256 =
      "ffb4e6bfb2c79334079d5d47e09226b0a0e9b4eee5d94bb3cd6cbdb13bf02443";
  private static final String SIDE_BOUNDARY_SHA256 =
      "fa04c84686daa9d52d0f6703dab85bf3db3a3c4976f2fb70d84a8713e779b1d7";
  static final String PARENT_CONFLICT = "CODEX_HISTORY_PARENT_CONFLICT";
  private final List<JsonNode> events;
  private final JsonNode ownSessionMeta;
  private final int start;
  private final boolean sideFork;
  private final boolean verifiedSideChat;
  private final String inheritedModel;
  private final boolean inheritedUsage;

  private CodexActivityRange(
      List<JsonNode> source,
      int start,
      String inheritedModel,
      boolean inheritedUsage,
      boolean verifiedSideChat) {
    this.start = start;
    this.verifiedSideChat = verifiedSideChat;
    JsonNode first = source.isEmpty() ? CONTEXT : source.getFirst();
    this.ownSessionMeta = "session_meta".equals(first.path("type").asText()) ? first : CONTEXT;
    JsonNode meta = first.path("payload");
    String fork = meta.path("forked_from_id").asText("");
    this.sideFork = !fork.isBlank() && !fork.equals(meta.path("id").asText(""));
    this.inheritedModel = inheritedModel;
    this.inheritedUsage = inheritedUsage;
    this.events =
        start == 0
            ? source
            : new AbstractList<>() {
              @Override
              public JsonNode get(int index) {
                java.util.Objects.checkIndex(index, source.size());
                return index < start ? CONTEXT : source.get(index);
              }

              @Override
              public int size() {
                return source.size();
              }
            };
  }

  static CodexActivityRange create(List<JsonNode> source, List<SourceDiagnostic> diagnostics)
      throws IOException {
    if (source.isEmpty()
        || !source.getFirst().path("payload").has("subagent_history_start_ordinal")) {
      return withSideCheckpoint(source, 0, "", false);
    }
    if (diagnostics.stream().anyMatch(d -> !"CODEX_NON_TEXT_PAYLOAD_PROJECTED".equals(d.code()))) {
      throw new InvalidHistoryException(
          "CODEX_HISTORY_READER_INCOMPLETE", "history reader evidence is incomplete");
    }
    JsonNode first = source.getFirst();
    JsonNode header = first.path("payload");
    boolean paginated = "paginated".equals(header.path("history_mode").asText());
    JsonNode boundary = header.path("subagent_history_start_ordinal");
    if (!boundary.isIntegralNumber()
        || !boundary.canConvertToInt()
        || boundary.intValue() < (paginated ? 1 : 2)
        || boundary.intValue() > source.size()) {
      throw new InvalidHistoryException(
          "CODEX_HISTORY_BOUNDARY_INVALID", "boundary is outside the source");
    }
    int start = boundary.intValue();
    String model = "";
    boolean inheritedUsage = false;
    for (int index = 0; index < source.size(); index++) {
      JsonNode event = source.get(index);
      JsonNode ordinal = event.path("ordinal");
      if (!ordinal.isIntegralNumber()
          || !ordinal.canConvertToInt()
          || ordinal.intValue() != index) {
        throw new InvalidHistoryException(
            "CODEX_HISTORY_ORDINAL_INVALID", "ordinal evidence is not continuous");
      }
      if (index >= start) continue;
      inheritedUsage |= isUsageEvent(event);
      JsonNode candidate = event.path("payload").path("model");
      if (candidate.isTextual() && !candidate.asText().isBlank()) model = candidate.asText();
    }
    validateIdentity(first, source, paginated);
    if (inheritedUsage && !paginated) {
      throw new InvalidHistoryException(
          "CODEX_HISTORY_USAGE_UNSUPPORTED", "inherited usage counter lineage is unknown");
    }
    return withSideCheckpoint(source, start, model, inheritedUsage);
  }

  private static CodexActivityRange withSideCheckpoint(
      List<JsonNode> source, int start, String model, boolean inheritedUsage) {
    int checkpoint = sideCheckpoint(source, start);
    for (int index = start; index < checkpoint; index++) {
      JsonNode event = source.get(index);
      inheritedUsage |= isUsageEvent(event);
      JsonNode candidate = event.path("payload").path("model");
      if (candidate.isTextual() && !candidate.asText().isBlank()) model = candidate.asText();
    }
    return new CodexActivityRange(source, checkpoint, model, inheritedUsage, checkpoint > start);
  }

  private static boolean isUsageEvent(JsonNode event) {
    String type = event.path("type").asText();
    return "token_usage_record".equals(type)
        || ("event_msg".equals(type)
            && "token_count".equals(event.path("payload").path("type").asText()));
  }

  private static int sideCheckpoint(List<JsonNode> source, int start) {
    if (source.isEmpty()) return start;
    JsonNode first = source.getFirst();
    JsonNode meta = first.path("payload");
    String id = meta.path("id").asText("");
    String fork = meta.path("forked_from_id").asText("");
    if (!"session_meta".equals(first.path("type").asText())
        || id.isBlank()
        || id.equals(fork)
        || !meta.path("attached_thread").isBoolean()
        || !meta.path("attached_thread").booleanValue()) return start;
    // 嵌套侧聊会继承更早的边界；只有最后一组属于当前子会话。
    for (int index = source.size() - 1; index > start; index--) {
      if (sideBoundary(source.get(index)) && sidePolicy(source.get(index - 1))) return index + 1;
    }
    return start;
  }

  static boolean sidePolicy(JsonNode event) {
    String text = singleInputText(event, "developer");
    return text.length() <= 8192
        && text.startsWith(SIDE_POLICY_OPEN)
        && text.indexOf(SIDE_POLICY_CLOSE, SIDE_POLICY_OPEN.length())
            == text.length() - SIDE_POLICY_CLOSE.length();
  }

  static boolean sideBoundary(JsonNode event) {
    String text = singleInputText(event, "user");
    return canonicalBoundary(text);
  }

  static boolean canonicalBoundary(String text) {
    if ((text.length() != 1435 && text.length() != 1607)
        || !text.startsWith("Side conversation boundary.\n\n")) return false;
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8));
      String fingerprint = HexFormat.of().formatHex(digest);
      return SIDE_BOUNDARY_SHA256.equals(fingerprint)
          || SIDE_EPHEMERAL_BOUNDARY_SHA256.equals(fingerprint);
    } catch (NoSuchAlgorithmException exception) {
      throw new IllegalStateException("Required SHA-256 algorithm unavailable", exception);
    }
  }

  boolean verifiedSideChat() {
    return verifiedSideChat;
  }

  boolean sideFork() {
    return sideFork;
  }

  private static String singleInputText(JsonNode event, String role) {
    JsonNode payload = event.path("payload");
    JsonNode content = payload.path("content");
    if (!"response_item".equals(event.path("type").asText())
        || !"message".equals(payload.path("type").asText())
        || !role.equals(payload.path("role").asText())
        || !content.isArray()
        || content.size() != 1
        || !"input_text".equals(content.get(0).path("type").asText())) return "";
    return content.get(0).path("text").asText("");
  }

  private static void validateIdentity(JsonNode first, List<JsonNode> source, boolean paginated)
      throws InvalidHistoryException {
    JsonNode header = first.path("payload");
    String child = header.path("id").asText("");
    String directParent = header.path("parent_thread_id").asText("");
    String nestedParent =
        header
            .path("source")
            .path("subagent")
            .path("thread_spawn")
            .path("parent_thread_id")
            .asText("");
    if (!"session_meta".equals(first.path("type").asText())
        || !header.path("id").isTextual()
        || child.isBlank()) {
      throw new InvalidHistoryException(PARENT_CONFLICT, "event[0] requires session_meta with id");
    }
    if (!directParent.isBlank() && !nestedParent.isBlank() && !directParent.equals(nestedParent)) {
      throw new InvalidHistoryException(
          PARENT_CONFLICT, "event[0] direct and nested parent_thread_id disagree");
    }
    String parent = directParent.isBlank() ? nestedParent : directParent;
    String forkParent = header.path("forked_from_id").asText("");
    if (child.equals(parent) || child.equals(forkParent)) {
      throw new InvalidHistoryException(PARENT_CONFLICT, "event[0] parent or fork points to self");
    }
    // Codex 的分页迁移只保留 ordinal 0 的 canonical session_meta，spawn parent 与 fork 来源不是同一字段。
    if (paginated) return;
    if (parent.isBlank() || !parent.equals(forkParent)) {
      throw new InvalidHistoryException(
          PARENT_CONFLICT, "event[0] parent_thread_id and forked_from_id missing or inconsistent");
    }
    JsonNode copied = source.get(1);
    if (!"session_meta".equals(copied.path("type").asText())
        || !parent.equals(copied.path("payload").path("id").asText(""))) {
      throw new InvalidHistoryException(
          PARENT_CONFLICT, "event[1] copied parent session_meta missing or inconsistent");
    }
  }

  /** 继承历史校验失败，携带与异常文本无关的稳定错误码。 */
  static final class InvalidHistoryException extends IOException {
    private static final long serialVersionUID = 1L;
    private final String code;

    InvalidHistoryException(String code, String detail) {
      super(code + ": " + detail);
      this.code = code;
    }

    String code() {
      return code;
    }
  }

  List<JsonNode> events() {
    return events;
  }

  JsonNode ownSessionMeta() {
    return ownSessionMeta;
  }

  int start() {
    return start;
  }

  boolean inheritedUsage() {
    return inheritedUsage;
  }

  String initialModel(String fallback) {
    return inheritedModel.isBlank() ? fallback : inheritedModel;
  }
}
