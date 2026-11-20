package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.json.JsonReadFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.query.api.SensitiveFieldPolicy;
import java.util.regex.Pattern;

/** 命令摘要与完整输入共用一个内容来源；摘要不修改原文。 */
final class ToolInputPreview {
  private static final ObjectMapper MAPPER =
      JsonMapper.builder()
          .enable(com.fasterxml.jackson.core.StreamReadFeature.STRICT_DUPLICATE_DETECTION)
          .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
          .build();
  private static final ObjectMapper LITERAL_MAPPER =
      JsonMapper.builder()
          .enable(JsonReadFeature.ALLOW_SINGLE_QUOTES, JsonReadFeature.ALLOW_UNQUOTED_FIELD_NAMES)
          .enable(com.fasterxml.jackson.core.StreamReadFeature.STRICT_DUPLICATE_DETECTION)
          .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
          .build();
  // 仅识别单次静态 exec_command 调用及可选 text 转发，不解释一般 JavaScript。
  private static final Pattern EXEC_WRAPPER =
      Pattern.compile(
          "(?s)\\s*(?:const|let|var)\\s+([A-Za-z_$][\\w$]*)\\s*=\\s*await\\s+tools\\.exec_command\\(\\s*(\\{.*})\\s*\\)\\s*;?\\s*"
              + "(?:text\\(\\s*(?:JSON\\.stringify\\(\\s*\\1\\s*\\)|\\1(?:\\.output)?)\\s*\\)\\s*;?)?\\s*");

  private ToolInputPreview() {}

  /** 资格由同冻结内容中的唯一 typed 声明提供；这里不按工具名称猜测。 */
  static String collaboration(ToolInputContents.Input input, String kind) {
    if (input == null || input.input().length() > 64 * 1024) return "";
    try {
      JsonNode node = MAPPER.readTree(input.input());
      if (node == null || !node.isObject()) return "";
      String text = collaborationText(node, kind);
      if (text.isBlank()) return "";
      return safePreview(("delegate".equals(kind) ? "委派任务：" : "追加输入：") + text);
    } catch (JsonProcessingException ignored) {
      // 非严格 JSON 不提取操作意图，调用方保留原安全预览。
      return "";
    }
  }

  private static String collaborationText(JsonNode node, String kind) {
    if ("delegate".equals(kind)) {
      if (node.has("message") == node.has("prompt") || node.has("items")) return "";
      return first(node, "message", "prompt");
    }
    if (!"input".equals(kind) || node.has("message") == node.has("items")) return "";
    if (node.has("message")) return first(node, "message");
    JsonNode items = node.path("items");
    if (!items.isArray() || items.isEmpty() || items.size() > 128) return "";
    var text = new StringBuilder();
    for (JsonNode item : items) {
      if (!item.isObject()
          || !"text".equals(item.path("type").asText())
          || !item.path("text").isTextual()
          || item.path("text").asText().isBlank()
          || item.size() != 2) return "";
      if (!text.isEmpty()) text.append(" · ");
      text.append(item.path("text").asText());
    }
    return text.toString();
  }

  private static String safePreview(String preview) {
    String safe = SensitiveFieldPolicy.DEFAULT.applyMasking(preview).replaceAll("\\s+", " ").trim();
    return safe.length() <= 180 ? safe : safe.substring(0, 179) + "…";
  }

  static String from(ToolInputContents.Input input) {
    if (input == null || input.input().isEmpty()) return "";
    String preview = input.input();
    try {
      if (preview.length() > 64 * 1024) return "长参数 · 打开 Input 查看完整内容";
      JsonNode node = MAPPER.readTree(preview);
      if (node != null && node.isObject()) {
        String command = commandPreview(node, 0);
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
    if (preview.equals(input.input())) {
      String command = wrappedCommand(preview);
      if (!command.isEmpty()) preview = command;
    }
    return safePreview(preview);
  }

  /** 只沿明确包装字段下降；歧义、动态表达式或未知语法保留原始输入。 */
  private static String commandPreview(JsonNode node, int depth) {
    if (depth > 3 || !node.isObject()) return "";
    String command = literalCommand(node);
    if (node.has("cmd") || node.has("command") || node.has("script")) return command;
    String nested = "";
    for (String key : new String[] {"arguments", "parameters", "input"}) {
      JsonNode child = node.path(key);
      if (child.isObject()) {
        if (!nested.isEmpty()) return "";
        nested = commandPreview(child, depth + 1);
      }
    }
    return nested.isEmpty() ? wrappedCommand(first(node, "code")) : nested;
  }

  private static String literalCommand(JsonNode node) {
    String result = "";
    int fields = 0;
    for (String key : new String[] {"cmd", "command", "script"}) {
      if (node.has(key)) {
        fields++;
        result = first(node, key);
      }
    }
    return fields == 1 ? result : "";
  }

  private static String wrappedCommand(String text) {
    var match = EXEC_WRAPPER.matcher(text);
    if (!match.matches()) return "";
    try {
      JsonNode arguments = LITERAL_MAPPER.readTree(match.group(2));
      return literalCommand(arguments);
    } catch (JsonProcessingException ignored) {
      // 不执行变量/插值/函数；不能解析完整静态参数对象时不猜命令。
      return "";
    }
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
