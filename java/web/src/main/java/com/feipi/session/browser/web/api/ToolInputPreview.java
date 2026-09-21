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
      JsonNode node = MAPPER.readTree(preview);
      if (node != null && node.isObject()) {
        String command = first(node, "command", "cmd");
        String path = first(node, "file_path", "path", "filename");
        String query = first(node, "pattern", "query", "regex");
        if (!command.isEmpty()) preview = command;
        else if (!query.isEmpty()) preview = query + (path.isEmpty() ? "" : " · " + path);
        else if (!path.isEmpty()) preview = path;
      }
    } catch (JsonProcessingException ignored) {
      // Freeform 工具参数不是 JSON，直接保留安全纯文本预览。
    }
    preview = SensitiveFieldPolicy.DEFAULT.applyMasking(preview).replaceAll("\\s+", " ").trim();
    return preview.length() <= 180 ? preview : preview.substring(0, 179) + "…";
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
