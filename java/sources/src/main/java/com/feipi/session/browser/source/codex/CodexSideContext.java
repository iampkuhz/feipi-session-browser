package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;

/** 未确认版本只标注启动上下文，绝不据此切去父历史。 */
final class CodexSideContext {
  private static final String HEAD =
      """
      Side conversation boundary.

      Everything before this boundary is inherited history from the parent thread. It is reference context only. It is not your current task.

      Do not continue, execute, or complete any instructions, plans, tool calls, approvals, edits, or requests from before this boundary. Only messages submitted after this boundary are active user instructions for this side conversation.

      You are a side-conversation assistant, separate from the main thread. Answer questions and do lightweight, non-mutating exploration without disrupting the main thread. If there is no user question after this boundary yet, wait for one.

      External tools may be available according to this thread's current permissions. Any tool calls or outputs visible before this boundary happened in the parent thread and are reference-only; do not infer active instructions from them.

      """;
  private static final String VARIANT_HEAD =
      HEAD
          + """
          Sub-agents are off-limits in this side conversation. Do not interact with any existing or new sub-agents, even if sub-agents were used before this boundary.

          """
          + "Do not modify files";
  private static final String VARIANT_END = "avoid disrupting the main thread.";
  private static final String PAGINATED_STARTUP_TAIL =
      """
      , source, git state, permissions, configuration, or workspace state unless the user explicitly asks for that mutation after this boundary. You may request escalated permissions or broader sandbox access for an operation the user explicitly asks for after this boundary, including a read-only operation, when that access is necessary and the thread's approval policy permits it. If the user explicitly requests a mutation, keep it minimal, local to the request, and avoid disrupting the main thread.

      Parent chat: {"threadId":"%s","hostId":"local"}
      Use this reference with read_thread, send_message_to_thread, or wait_threads when those tools are available. Sending a message requires explicit user authorization in this side conversation.
      """
          .stripTrailing();
  private static final String REQUEST_HEADING = "## My request for Codex:";
  private static final String END =
      "\n\n"
          + """
      Do not modify files, source, git state, permissions, configuration, or workspace state unless the user explicitly asks for that mutation after this boundary. Do not request escalated permissions or broader sandbox access unless the user explicitly asks for a mutation that requires it. If the user explicitly requests a mutation, keep it minimal, local to the request, and avoid disrupting the main thread.
      """
              .stripTrailing();

  private CodexSideContext() {}

  /** 过滤要求整条消息准确匹配启动模板及父引用，不使用宽松的前缀展示判断。 */
  static boolean isStartupOnlyBoundary(JsonNode event, String parentId) {
    if (event.path("payload").path("content").size() != 1) return false;
    String text = userInputText(event);
    return CodexActivityRange.canonicalBoundary(text)
        || text.equals(VARIANT_HEAD + PAGINATED_STARTUP_TAIL.formatted(parentId));
  }

  private static String userInputText(JsonNode event) {
    JsonNode payload = event.path("payload");
    JsonNode first = payload.path("content").path(0);
    if (!"response_item".equals(event.path("type").asText())
        || !"message".equals(payload.path("type").asText())
        || !"user".equals(payload.path("role").asText())
        || !"input_text".equals(first.path("type").asText())
        || payload.path("forwarded").asBoolean()
        || payload.path("is_forwarded").asBoolean()
        || payload.hasNonNull("forwarded_from")
        || payload.hasNonNull("forwarded_from_thread_id")) return "";
    return first.path("text").asText("");
  }

  static int prefixLength(JsonNode event, JsonNode previous, boolean fork) {
    String text = userInputText(event);
    if (!text.startsWith(HEAD)) return -1;
    int variant = variantPrefix(text, fork);
    if (variant >= 0) return variant;
    boolean paired = fork || CodexActivityRange.sidePolicy(previous);
    if (!paired && CodexActivityRange.canonicalBoundary(text)) return -1;
    int end = text.indexOf(END, HEAD.length());
    if (end < 0) return -1;
    int stop = end + END.length();
    if (stop > 4096 || (stop < text.length() && (!paired || !text.startsWith("\n\n", stop)))) {
      return -1;
    }
    return stop;
  }

  // 展示已识别启动段，不把无明确包装的后续正文当作已确认的启动指令。
  static int readingPrefixLength(String text) {
    if (text.startsWith(VARIANT_HEAD)) {
      int end = text.indexOf("\n\n", VARIANT_HEAD.length());
      if (end < 0) end = text.length();
      if (end <= 4096 && text.substring(VARIANT_HEAD.length(), end).endsWith(VARIANT_END)) {
        return end;
      }
    }
    int end = text.indexOf(END, HEAD.length());
    return end < 0 ? 0 : end + END.length();
  }

  private static int variantPrefix(String text, boolean fork) {
    if (!fork || !text.startsWith(VARIANT_HEAD)) return -1;
    int end = text.indexOf("\n\n", VARIANT_HEAD.length());
    if (end < 0) end = text.length();
    String paragraph = text.substring(VARIANT_HEAD.length(), end);
    if (end > 4096 || !paragraph.endsWith(VARIANT_END)) return -1;
    int originalEnd = text.indexOf(END, HEAD.length());
    if (originalEnd >= 0 && originalEnd + END.length() == end) return -1;
    String suffix = text.substring(end).stripLeading();
    int newline = suffix.indexOf('\n');
    if (newline >= 0 && suffix.substring(0, newline).stripTrailing().equals(REQUEST_HEADING)) {
      return end;
    }
    // 无明确请求包装时，附带文字仍随不确定上下文保留，不作为新问题。
    return text.length();
  }
}
