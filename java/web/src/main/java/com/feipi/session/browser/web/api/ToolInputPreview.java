package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;

/** 命令摘要与完整输入共用一个内容来源；摘要不修改原文。 */
final class ToolInputPreview {
  private static final ObjectMapper MAPPER = new ObjectMapper();

  private ToolInputPreview() {}

  static String from(ToolInputContents.Input input) {
    if (input == null || input.input().isEmpty()) return "";
    String preview = input.input();
    try {
      if (preview.length() > 64 * 1024) return "长参数 · 打开 Input 查看完整内容";
      JsonNode node = MAPPER.readTree(preview);
      if (node != null && node.isObject()) {
        String command = first(node, "command", "cmd");
        String path = first(node, "file_path", "path", "filename");
        String query = first(node, "pattern", "query", "regex");
        String waiting = waitingPreview(input.name(), node);
        if (!waiting.isEmpty()) preview = waiting;
        else if (!command.isEmpty()) preview = command;
        else if (!query.isEmpty()) preview = query + (path.isEmpty() ? "" : " · " + path);
        else if (!path.isEmpty()) preview = path;
      }
    } catch (JsonProcessingException ignored) {
      // Freeform 工具参数不是 JSON，直接保留安全纯文本预览。
    }
    preview = SensitiveFieldPolicy.DEFAULT.applyMasking(preview).replaceAll("\\s+", " ").trim();
    return preview.length() <= 180 ? preview : preview.substring(0, 179) + "…";
  }

  private static String waitingPreview(String name, JsonNode node) {
    JsonNode session = node.path("session_id");
    JsonNode chars = node.path("chars");
    if ("write_stdin".equals(name)
        && session.isIntegralNumber()
        && session.canConvertToLong()
        && session.longValue() > 0
        && chars.isTextual()
        && chars.textValue().isEmpty()) {
      return "等待读取输出 · session " + session.asText();
    }
    JsonNode cell = node.path("cell_id");
    JsonNode terminate = node.path("terminate");
    if ("wait".equals(name)
        && cell.isTextual()
        && !cell.textValue().isBlank()
        && (!node.has("terminate") || (terminate.isBoolean() && !terminate.booleanValue()))) {
      return "等待脚本返回 · " + cell.textValue();
    }
    return "";
  }

  static String executionKind(String name, String preview) {
    String tool = name.toLowerCase(java.util.Locale.ROOT);
    if (tool.matches("(?:.*__)?(?:python|python3)")) return "python";
    if (tool.matches("(?:.*__)?(?:exec|js|javascript|node_repl)") && !preview.isEmpty()) {
      return "javascript";
    }
    if (tool.matches("(?:.*__)?(?:exec_command|shell|bash|terminal|local_shell)")) {
      if (preview.matches("(?:[^ ]*/)?python(?:[23](?:\\.\\d+)?)?(?:\\s.*)?")) return "python";
      if (preview.matches("(?:[^ ]*/)?(?:node|deno)(?:\\s.*)?")) return "javascript";
      return "shell";
    }
    return "tool";
  }

  private static String first(JsonNode node, String... names) {
    for (String name : names) {
      if (node.path(name).isTextual() && !node.path(name).asText().isEmpty()) {
        return node.path(name).asText();
      }
    }
    return "";
  }
}
