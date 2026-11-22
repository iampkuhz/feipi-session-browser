package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;

/** 命令摘要与完整输入共用一个内容来源；摘要不修改原文。 */
final class ToolInputPreview {
  private static final ObjectMapper MAPPER =
      new ObjectMapper().enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);

  private ToolInputPreview() {}

  /**
   * 仅携带显示和分类所需的有界信息，不保存完整输入。
   *
   * @param preview 已脱敏、限长的显示文本
   * @param category 依据工具名与结构化输入识别的动作类别
   */
  record Summary(String preview, String category) {}

  static String from(ToolInputContents.Input input) {
    return input == null ? "" : summarize(input).preview();
  }

  static String category(String name, Summary input) {
    return input == null || input.category().isEmpty()
        ? ToolActionCategory.kind(name, null, "")
        : input.category();
  }

  static Summary summarize(ToolInputContents.Input input) {
    String preview = input.input();
    JsonNode node = null;
    String command = "";
    if (preview.length() > 64 * 1024)
      return new Summary("长参数 · 打开 Input 查看完整内容", category(input.name(), null));

    try {
      if (!preview.isEmpty()) node = MAPPER.readTree(preview);
      if (node != null && node.isObject()) {
        command = first(node, "command", "cmd");
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
    String actionInput = command.isEmpty() ? input.input().stripLeading() : command.stripLeading();
    String category =
        input.name().isBlank() ? "" : ToolActionCategory.kind(input.name(), node, actionInput);
    preview = SensitiveFieldPolicy.DEFAULT.applyMasking(preview).replaceAll("\\s+", " ").trim();
    return new Summary(
        preview.length() <= 180 ? preview : preview.substring(0, 179) + "…", category);
  }

  private static String waitingPreview(String name, JsonNode node) {
    if ("write_stdin".equals(name) && polls(node)) {
      return "等待读取输出 · session " + node.path("session_id").asText();
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

  static boolean polls(JsonNode node) {
    if (node == null) return false;
    JsonNode session = node.path("session_id");
    JsonNode chars = node.path("chars");
    return session.isIntegralNumber()
        && session.canConvertToLong()
        && session.longValue() > 0
        && chars.isTextual()
        && chars.textValue().isEmpty();
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
