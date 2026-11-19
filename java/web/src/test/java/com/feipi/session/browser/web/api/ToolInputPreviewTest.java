package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import java.util.List;
import org.junit.jupiter.api.Test;

class ToolInputPreviewTest {
  @Test
  void extractsOnlyLiteralCommandsFromExplicitWrappersWithoutSplittingScripts() {
    assertThat(
            preview(
                "exec",
                "const receipt = await tools.exec_command({cmd:'git push origin synthetic',yield_time_ms:1000}); text(JSON.stringify(receipt));"))
        .isEqualTo("git push origin synthetic");
    assertThat(
            preview(
                "exec",
                "let arbitrary = await tools.exec_command({command:\"printf one; printf two\"}); text(arbitrary.output);"))
        .isEqualTo("printf one; printf two");
    assertThat(
            preview(
                "exec",
                "{\"parameters\":{\"arguments\":{\"script\":\"echo first\\necho second\"}}}"))
        .isEqualTo("echo first echo second");
    assertThat(
            preview(
                "exec",
                "{\"code\":\"const item = await tools.exec_command({cmd:'printf wrapped'}); text(item);\"}"))
        .isEqualTo("printf wrapped");
    assertThat(
            preview(
                "exec",
                "const item = await tools.exec_command({cmd:'echo token=synthetic-private-value'});"))
        .isEqualTo("echo token=[REDACTED]");
  }

  @Test
  void retainsUnknownDynamicAmbiguousAndMultipleCallWrappers() {
    for (String input :
        List.of(
            "const x = await tools.exec_command({cmd:buildCommand()});",
            "const x = await tools.exec_command({cmd:`git push ${branch}`});",
            "const x = await tools.exec_command({cmd:'first',cmd:'second'});",
            "const x = await tools.exec_command({cmd:'first',command:'second'});",
            "const x = await tools.exec_command({cmd:'first'}); await tools.exec_command({cmd:'second'});",
            "const x = await tools.other({cmd:'not an execution wrapper'});",
            "{\"cmd\":\"first\",\"script\":\"second\"}",
            "{\"cmd\":\"first\"}; otherWork();")) {
      assertThat(preview("exec", input)).isEqualTo(input);
    }
  }

  @Test
  void previewsPathsQueriesAndCommandsFromTheFullInput() {
    assertThat(preview("Read", "{\"file_path\":\"/synthetic/a.md\"}")).isEqualTo("/synthetic/a.md");
    assertThat(preview("Grep", "{\"pattern\":\"needle\",\"path\":\"src\"}"))
        .isEqualTo("needle · src");
    assertThat(preview("Bash", "{\"command\":\"echo one\\necho two\"}"))
        .isEqualTo("echo one echo two");
    assertThat(preview("Bash", "echo " + "x".repeat(200))).hasSize(180).endsWith("…");
    assertThat(ToolInputPreview.from(null)).isEmpty();
  }

  @Test
  void classifiesOnlyTheRecordedTopLevelExecutionSurface() {
    assertThat(ToolInputPreview.executionKind("exec", "const r = await tools.exec_command(...)"))
        .isEqualTo("javascript");
    assertThat(ToolInputPreview.executionKind("functions__exec_command", "printf x"))
        .isEqualTo("shell");
    assertThat(ToolInputPreview.executionKind("Bash", "/usr/bin/python3 -c 'print(1)'"))
        .isEqualTo("python");
    assertThat(ToolInputPreview.executionKind("Read", "/synthetic/example.py")).isEqualTo("tool");
    assertThat(ToolInputPreview.executionKind("exec", "")).isEqualTo("tool");
  }

  @Test
  void previewsOnlyExplicitEmptyInputPollsWithPositiveIntegralSessionIds() {
    for (String id : List.of("1", "61001", "9223372036854775807")) {
      assertThat(preview("write_stdin", "{\"session_id\":" + id + ",\"chars\":\"\"}"))
          .isEqualTo("等待读取输出 · session " + id);
    }
  }

  @Test
  void retainsFallbackForMissingInvalidOrOverflowingSessionIds() {
    for (String id :
        List.of(
            "0",
            "-1",
            "1.5",
            "1.0",
            "\"61001\"",
            "null",
            "false",
            "[]",
            "{}",
            "9223372036854775808",
            "-9223372036854775809")) {
      String input = "{\"session_id\":" + id + ",\"chars\":\"\"}";
      assertThat(preview("write_stdin", input)).as("参数 %s", input).isEqualTo(input);
    }
    assertThat(preview("write_stdin", "{\"chars\":\"\"}")).isEqualTo("{\"chars\":\"\"}");
  }

  @Test
  void neverLabelsSentInputInterruptsOrMissingCharsAsWaiting() {
    for (String chars :
        List.of("\"text\"", "\" \"", "\"\\n\"", "\"\\u0003\"", "null", "0", "false", "[]", "{}")) {
      String input = "{\"session_id\":61001,\"chars\":" + chars + "}";
      assertThat(preview("write_stdin", input)).as("参数 %s", input).isEqualTo(input);
    }
    assertThat(preview("write_stdin", "{\"session_id\":61001}"))
        .isEqualTo("{\"session_id\":61001}");
  }

  @Test
  void previewsWaitOnlyWithTextCellIdAndNoTerminationRequest() {
    assertThat(preview("wait", "{\"cell_id\":\"cell-A\"}")).isEqualTo("等待脚本返回 · cell-A");
    assertThat(preview("wait", "{\"cell_id\":\"cell-A\",\"terminate\":false}"))
        .isEqualTo("等待脚本返回 · cell-A");
  }

  @Test
  void neverLabelsTerminationOrInvalidTerminationFlagsAsWaiting() {
    for (String terminate : List.of("true", "\"false\"", "0", "null", "[]", "{}")) {
      String input = "{\"cell_id\":\"cell-A\",\"terminate\":" + terminate + "}";
      assertThat(preview("wait", input)).as("参数 %s", input).isEqualTo(input);
    }
  }

  @Test
  void retainsFallbackForMissingOrInvalidCellIds() {
    for (String cell : List.of("\"\"", "\" \"", "\"\\t\\n\"", "null", "1", "false", "[]", "{}")) {
      String input = "{\"cell_id\":" + cell + "}";
      assertThat(preview("wait", input)).as("参数 %s", input).isEqualTo(input);
    }
    assertThat(preview("wait", "{\"terminate\":false}")).isEqualTo("{\"terminate\":false}");
  }

  @Test
  void matchesOnlyExactToolNamesAndRetainsGenericInputFallbacks() {
    String poll = "{\"session_id\":61001,\"chars\":\"\"}";
    String wait = "{\"cell_id\":\"cell-A\"}";
    for (String name :
        List.of("Write_stdin", "functions.write_stdin", "mcp__write_stdin", "Read", "unknown")) {
      assertThat(preview(name, poll)).isEqualTo(poll);
    }
    for (String name : List.of("Wait", "functions.wait", "mcp__wait", "wait_for", "unknown")) {
      assertThat(preview(name, wait)).isEqualTo(wait);
    }
    assertThat(preview("wait", "{\"command\":\"echo fallback\",\"terminate\":true}"))
        .isEqualTo("echo fallback");
    assertThat(preview("unknown", "{\"cmd\":\"printf fallback\"}")).isEqualTo("printf fallback");
    assertThat(preview("unknown", "{\"path\":\"src\",\"query\":\"needle\"}"))
        .isEqualTo("needle · src");
    assertThat(preview("unknown", "{\"filename\":\"a.md\"}")).isEqualTo("a.md");
    assertThat(preview("unknown", "{\"regex\":\"a.*\"}")).isEqualTo("a.*");
    assertThat(preview("wait", "freeform\n  unchanged")).isEqualTo("freeform unchanged");
  }

  @Test
  void appliesExistingMaskingWhitespaceAndLengthLimitsAfterWaitingPreview() {
    assertThat(preview("wait", "{\"cell_id\":\"cell-A token=synthetic-private-value\"}"))
        .isEqualTo("等待脚本返回 · cell-A token=[REDACTED]");
    assertThat(preview("wait", "{\"cell_id\":\"cell-A\\n  continuation\"}"))
        .isEqualTo("等待脚本返回 · cell-A continuation");
    assertThat(preview("wait", "{\"cell_id\":\"" + "x".repeat(200) + "\"}"))
        .startsWith("等待脚本返回 · ")
        .hasSize(180)
        .endsWith("…");
    assertThat(preview("wait", "{\"cell_id\":\"" + "x".repeat(64 * 1024) + "\"}"))
        .isEqualTo("长参数 · 打开 Input 查看完整内容");
  }

  @Test
  void qualifiedTextSummariesPreserveLiteralMarkupWhitespaceAndMasking() {
    assertThat(operation("delegate", "{\"prompt\":\"Synthetic <b>task</b>\"}"))
        .isEqualTo("委派任务：Synthetic <b>task</b>");
    assertThat(operation("delegate", "{\"message\":\"Synthetic task\"}"))
        .isEqualTo("委派任务：Synthetic task");
    assertThat(operation("input", "{\"message\":\"one\\n two token=synthetic\"}"))
        .isEqualTo("追加输入：one two token=[REDACTED]");
    assertThat(
            operation(
                "input",
                "{\"items\":[{\"type\":\"text\",\"text\":\"first\"},{\"type\":\"text\",\"text\":\"second\"}]}"))
        .isEqualTo("追加输入：first · second");
  }

  @Test
  void qualifiedTextRejectsAmbiguousMixedInvalidAndUnsupportedInputs() {
    for (String input :
        List.of(
            "{}",
            "[]",
            "null",
            "not json",
            "{\"message\":\"first\",\"message\":\"second\"}",
            "{\"message\":\"first\"} trailing",
            "{\"message\":123}",
            "{\"message\":\"   \"}",
            "{\"message\":\"first\",\"items\":[]}",
            "{\"items\":[]}",
            "{\"items\":[{\"type\":\"image\",\"image_url\":\"synthetic\"}]}",
            "{\"items\":[{\"type\":\"text\",\"text\":\"first\"},{\"type\":\"image\"}]}",
            "{\"items\":[{\"type\":\"text\",\"text\":\"first\",\"image\":\"synthetic\"}]}")) {
      assertThat(operation("input", input)).as(input).isEmpty();
    }
    assertThat(operation("delegate", "{\"message\":\"one\",\"prompt\":\"two\"}")).isEmpty();
    assertThat(operation("wait", "{\"message\":\"one\"}")).isEmpty();
    assertThat(
            operation(
                "input",
                "{\"items\":["
                    + "{\"type\":\"text\",\"text\":\"x\"},".repeat(128)
                    + "{\"type\":\"text\",\"text\":\"x\"}]}"))
        .isEmpty();
  }

  @Test
  void qualifiedSummariesUseTheExistingCharacterBudgets() {
    assertThat(operation("delegate", "{\"message\":\"" + "x".repeat(200) + "\"}"))
        .startsWith("委派任务：")
        .hasSize(180)
        .endsWith("…");
    String full = "{\"message\":\"" + "中".repeat(65522) + "\"}";
    assertThat(full).hasSize(65536);
    assertThat(operation("input", full)).hasSize(180);
    assertThat(operation("input", full + " ")).isEmpty();
  }

  private static String operation(String kind, String input) {
    return ToolInputPreview.collaboration(
        new ToolInputContents.Input("synthetic-tool", "synthetic-name", input), kind);
  }

  private static String preview(String name, String input) {
    return ToolInputPreview.from(new ToolInputContents.Input("synthetic-tool", name, input));
  }
}
