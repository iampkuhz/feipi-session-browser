package com.feipi.session.browser.web.api;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/** 基于可验证的工具名及有限输入特征分类，不把输入参数写进摘要。 */
final class ToolActionCategory {
  private static final Map<String, String> LABELS =
      Map.ofEntries(
          Map.entry("read", "读取"),
          Map.entry("search", "搜索"),
          Map.entry("write", "写入"),
          Map.entry("edit", "编辑"),
          Map.entry("shell", "Shell"),
          Map.entry("python", "Python"),
          Map.entry("javascript", "JavaScript"),
          Map.entry("wait", "等待"),
          Map.entry("stop", "终止"),
          Map.entry("process-input", "进程输入"),
          Map.entry("agent", "Agent 调度"),
          Map.entry("web", "网页"),
          Map.entry("tool", "其他工具"));

  private static final Pattern EXEC_COMMAND_WRAPPER =
      Pattern.compile("(?:text\\s*\\(\\s*)?await\\s+tools\\.exec_command\\s*\\(");

  private ToolActionCategory() {}

  static String kind(String name, JsonNode fields, String input) {
    String tool = name.toLowerCase(Locale.ROOT);
    int namespace = tool.lastIndexOf("__");
    if (namespace >= 0) tool = tool.substring(namespace + 2);
    return switch (tool) {
      case "read", "read_file", "cat" -> "read";
      case "grep", "glob", "rg", "search", "find_files", "list_directory" -> "search";
      case "write", "write_file" -> "write";
      case "edit", "multiedit", "apply_patch", "replace" -> "edit";
      case "python", "python3" -> "python";
      case "exec", "functions.exec", "tools.exec" ->
          EXEC_COMMAND_WRAPPER.matcher(input).lookingAt() ? "shell" : "javascript";
      case "js", "javascript", "node_repl" -> "javascript";
      case "exec_command",
          "functions.exec_command",
          "tools.exec_command",
          "shell",
          "bash",
          "terminal",
          "local_shell" ->
          shellKind(input);
      case "write_stdin", "tools.write_stdin", "functions.write_stdin" ->
          ToolInputPreview.polls(fields) ? "wait" : "process-input";
      case "wait", "tools.wait", "functions.wait" ->
          fields != null && fields.path("terminate").booleanValue() ? "stop" : "wait";
      case "spawn_agent", "send_input", "followup_task", "close_agent", "interrupt_agent", "task" ->
          "agent";
      case "web_search", "web_fetch", "websearch", "webfetch" -> "web";
      default -> "tool";
    };
  }

  private static String shellKind(String preview) {
    if (preview.matches("(?:[\\w./-]*/)?python(?:[23](?:\\.\\d+)?)?(?:\\s[\\s\\S]*)?"))
      return "python";
    if (preview.matches("(?:[\\w./-]*/)?(?:node|deno)(?:\\s[\\s\\S]*)?")) return "javascript";
    return "shell";
  }

  static String summary(Map<String, Integer> counts) {
    return String.join(
        " · ",
        counts.entrySet().stream()
            .map(
                entry ->
                    LABELS.get(entry.getKey())
                        + (entry.getValue() == 1 ? "" : " × " + entry.getValue()))
            .toList());
  }
}
