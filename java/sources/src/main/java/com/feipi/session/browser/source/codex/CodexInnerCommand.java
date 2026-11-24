package com.feipi.session.browser.source.codex;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.Set;

/** 仅在同一非重叠工具区间内，以命令、输出和结果 ID 交叉绑定子命令。 */
final class CodexInnerCommand {
  static final String PROJECTED = "_feipi_inner_command";
  static final int MAX_RETAINED_BYTES = 128 * 1024;
  private static final Set<String> BOUNDARIES =
      Set.of("task_started", "task_complete", "turn_aborted");
  private String pendingId = "";
  private String input = "";
  private boolean ambiguous;
  private Evidence evidence;

  void project(String type, String subtype, ObjectNode payload, int ordinal) {
    payload.remove(PROJECTED);
    if ("compacted".equals(type) || ("event_msg".equals(type) && BOUNDARIES.contains(subtype))) {
      pendingId = "";
      ambiguous = false;
      clearEvidence();
    } else if ("response_item".equals(type)) {
      switch (subtype) {
        case "custom_tool_call", "function_call" -> declare(subtype, payload);
        case "custom_tool_call_output", "function_call_output" -> finish(subtype, payload);
        default -> {}
      }
    } else if ("event_msg".equals(type) && "item_completed".equals(subtype) && !input.isEmpty()) {
      collect(payload.path("item"), ordinal);
    }
  }

  private void declare(String subtype, ObjectNode payload) {
    ambiguous |= !pendingId.isEmpty();
    pendingId = payload.path("call_id").asText("");
    clearEvidence();
    if (!ambiguous
        && !pendingId.isBlank()
        && "custom_tool_call".equals(subtype)
        && "exec".equals(payload.path("name").asText())) {
      String text = payload.path("input").asText("");
      if (text.length() <= MAX_RETAINED_BYTES) input = text;
    }
  }

  private void collect(JsonNode item, int ordinal) {
    if (evidence != null
        || !"CommandExecution".equals(item.path("type").asText())
        || !"unified_exec_startup".equals(item.path("source").asText())) {
      clearEvidence();
      return;
    }
    var argv = item.path("command");
    String command = argv.isArray() && !argv.isEmpty() ? argv.get(argv.size() - 1).asText("") : "";
    String output = item.path("aggregated_output").asText("").strip();
    String status = item.path("status").asText("");
    if (command.length() < 12
        || !input.contains(command)
        || output.length() < 16
        || output.length() > MAX_RETAINED_BYTES
        || !Set.of("completed", "failed").contains(status)) {
      clearEvidence();
      return;
    }
    evidence = new Evidence(ordinal, output, status, item.path("exit_code"), item.path("duration"));
  }

  private void finish(String subtype, ObjectNode payload) {
    if ("custom_tool_call_output".equals(subtype)
        && evidence != null
        && pendingId.equals(payload.path("call_id").asText(""))
        && containsOutput(payload.path("output"), evidence.output())) {
      var projection = payload.putObject(PROJECTED);
      projection.put("ordinal", evidence.ordinal());
      projection.put("status", evidence.status());
      projection.set("exit_code", integralOrInvalid(evidence.exit()));
      // 观测只保留固定标量，不保存用于交叉核对的命令和输出正文。
      if (!evidence.duration().isMissingNode() && !evidence.duration().isNull()) {
        var duration = projection.putObject("duration");
        duration.set("secs", integralOrInvalid(evidence.duration().path("secs")));
        duration.set("nanos", integralOrInvalid(evidence.duration().path("nanos")));
      }
    }
    pendingId = "";
    clearEvidence();
  }

  private static JsonNode integralOrInvalid(JsonNode node) {
    return node.isIntegralNumber() ? node : com.fasterxml.jackson.databind.node.NullNode.instance;
  }

  private static boolean containsOutput(JsonNode value, String output) {
    if (value.isTextual()) return value.asText().contains(output);
    if (value.isArray()) {
      for (JsonNode part : value) {
        if (part.path("text").asText("").contains(output)) return true;
      }
    }
    return false;
  }

  private void clearEvidence() {
    input = "";
    evidence = null;
  }

  /**
   * 当前工具区间中唯一待核对的子命令。
   *
   * @param ordinal 子命令事件的源序号
   * @param output 仅用于匹配同一调用结果的输出
   * @param status 结构化命令状态
   * @param exit 原始退出码字段
   * @param duration 原始耗时字段
   */
  private record Evidence(
      int ordinal, String output, String status, JsonNode exit, JsonNode duration) {}
}
