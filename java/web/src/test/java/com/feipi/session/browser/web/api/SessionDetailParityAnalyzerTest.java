package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.CallRound;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Session Detail parity analyzer 的回归测试。 */
@DisplayName("SessionDetailParityAnalyzer")
class SessionDetailParityAnalyzerTest {

  @TempDir Path tempDir;

  @Test
  @DisplayName("Codex raw rollout 补齐 trace，工具总量保留索引行口径")
  void codexRawRolloutCompletesParityMetrics() throws Exception {
    Path parent = tempDir.resolve("rollout-2026-07-06T10-00-00-parent.jsonl");
    Path child = tempDir.resolve("rollout-2026-07-06T10-01-00-child-00000001.jsonl");
    Files.writeString(parent, parentRollout(child));
    Files.writeString(child, childRollout());

    SessionRow row =
        new SessionRow(
            "codex:parent-session",
            "codex",
            "parent-session",
            "Parity fixture",
            "/repo",
            "repo",
            "/repo",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:05:00Z",
            300,
            0,
            0,
            "gpt-test",
            "main_java",
            "codex",
            1,
            2,
            4,
            30,
            70,
            100,
            0,
            200,
            1,
            1,
            1,
            1,
            parent.toString());
    SessionDetail detail =
        new SessionDetail(
            row,
            List.of(
                new CallRound(1, List.of("call-1"), List.of("tool-failed"), null, 50, 0, 0, 10, 60),
                new CallRound(
                    2, List.of("call-2"), List.of("tool-custom"), null, 20, 100, 0, 20, 140)),
            List.of(),
            PayloadVisibility.STANDARD,
            "",
            "",
            "cache");

    SessionDetailParityAnalyzer.Result result = SessionDetailParityAnalyzer.analyze(detail);

    assertThat(result.meta).containsEntry("sessionFilePath", parent.toString());
    assertThat(result.metrics)
        .containsEntry("toolCalls", 4L)
        .containsEntry("failedTools", 1L)
        .containsEntry("subagentCalls", 1L)
        .containsEntry("mainCalls", 2L)
        .containsEntry("workloadCalls", 3L)
        .containsEntry("subagentRuns", 1L);
    // 非零退出码是执行失败，不表示请求或结果载荷缺失。
    assertThat(result.diagnostics).containsEntry("payloadGaps", 0L);
    assertThat(result.diagnostics).containsEntry("issueRounds", 1);
    assertThat(result.round(1).failedToolIds).containsExactly("tool-failed");
    assertThat(result.round(1).signals).contains("Failed").doesNotContain("Payload Gap");
    assertThat(result.round(1).toMap())
        .containsEntry("summary", "/goal 修复失败工具展示")
        .containsEntry("isUserInput", true);
    assertThat(result.round(2).toMap())
        .containsEntry("summary", "继续检查 subagent 成功状态")
        .containsEntry("isUserInput", true);

    @SuppressWarnings("unchecked")
    List<java.util.Map<String, Object>> agents =
        (List<java.util.Map<String, Object>>) result.diagnostics.get("agents");
    assertThat(agents).hasSize(2);
    assertThat(agents.get(1)).containsEntry("agent", "repo-mapper");
    assertThat(agents.get(1)).containsEntry("tools", 2L);

    @SuppressWarnings("unchecked")
    java.util.Map<String, Object> toolImpact =
        (java.util.Map<String, Object>) result.diagnostics.get("toolImpact");
    @SuppressWarnings("unchecked")
    List<java.util.Map<String, Object>> toolRows =
        (List<java.util.Map<String, Object>>) toolImpact.get("rows");
    assertThat(toolRows).anySatisfy(tool -> assertThat(tool).containsEntry("failureRate", "50.0%"));
  }

  @Test
  @DisplayName("Claude raw 用户输入轮次也输出 userInput parity")
  void claudeRawUserMessagesMarkUserInputRounds() throws Exception {
    Path source = tempDir.resolve("claude-session.jsonl");
    Files.writeString(source, claudeRollout());

    SessionRow row =
        new SessionRow(
            "claude_code:claude-session",
            "claude_code",
            "claude-session",
            "Claude fixture",
            "/repo",
            "repo",
            "/repo",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:03:00Z",
            180,
            0,
            0,
            "claude-test",
            "main_java",
            "claude_code",
            2,
            3,
            0,
            15,
            60,
            0,
            0,
            75,
            0,
            0,
            1,
            1,
            source.toString());
    SessionDetail detail =
        new SessionDetail(
            row,
            List.of(
                new CallRound(1, List.of("call-1"), List.of(), null, 10, 0, 0, 5, 15),
                new CallRound(2, List.of("call-2"), List.of(), null, 20, 0, 0, 5, 25),
                new CallRound(3, List.of("call-3"), List.of(), null, 30, 0, 0, 5, 35)),
            List.of(),
            PayloadVisibility.STANDARD,
            "",
            "",
            "cache");

    SessionDetailParityAnalyzer.Result result = SessionDetailParityAnalyzer.analyze(detail);

    assertThat(result.round(1).toMap())
        .containsEntry("summary", "First manual prompt")
        .containsEntry("isUserInput", true);
    assertThat(result.round(2).toMap())
        .containsEntry("summary", "Assistant-only continuation")
        .containsEntry("isUserInput", false);
    assertThat(result.round(3).toMap())
        .containsEntry("summary", "Second manual prompt")
        .containsEntry("isUserInput", true);
  }

  @Test
  @DisplayName("Codex 内部上下文和 subagent 通知不标记为用户输入轮次")
  void codexInternalMessagesDoNotMarkUserInputRounds() throws Exception {
    Path source = tempDir.resolve("codex-internal.jsonl");
    Files.writeString(source, codexInternalRollout());

    SessionRow row =
        new SessionRow(
            "codex:codex-internal",
            "codex",
            "codex-internal",
            "Codex internal fixture",
            "/repo",
            "repo",
            "/repo",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:03:00Z",
            180,
            0,
            0,
            "gpt-test",
            "main_java",
            "codex",
            1,
            3,
            0,
            18,
            60,
            0,
            0,
            78,
            0,
            0,
            1,
            1,
            source.toString());
    SessionDetail detail =
        new SessionDetail(
            row,
            List.of(
                new CallRound(1, List.of("call-1"), List.of(), null, 10, 0, 0, 5, 15),
                new CallRound(2, List.of("call-2"), List.of(), null, 20, 0, 0, 6, 26),
                new CallRound(3, List.of("call-3"), List.of(), null, 30, 0, 0, 7, 37)),
            List.of(),
            PayloadVisibility.STANDARD,
            "",
            "",
            "cache");

    SessionDetailParityAnalyzer.Result result = SessionDetailParityAnalyzer.analyze(detail);

    assertThat(result.round(1).toMap()).containsEntry("isUserInput", false);
    assertThat(result.round(2).toMap()).containsEntry("isUserInput", false);
    assertThat(result.round(3).toMap())
        .containsEntry("summary", "真正的用户输入")
        .containsEntry("isUserInput", true);
  }

  @Test
  @DisplayName("Qoder raw rollout 使用 stop_reason 识别 round 边界且 tool_result 不冒充用户输入")
  void qoderStopReasonDetectsRoundBoundariesAndToolResultNotUserInput() throws Exception {
    Path source = tempDir.resolve("qoder-session.jsonl");
    Files.writeString(source, qoderRollout());

    SessionRow row =
        new SessionRow(
            "qoder:qoder-session",
            "qoder",
            "qoder-session",
            "Qoder fixture",
            "/repo",
            "repo",
            "/repo",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:03:00Z",
            180,
            0,
            0,
            "claude-test",
            "main_java",
            "qoder",
            2,
            2,
            1,
            20,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            source.toString());
    SessionDetail detail =
        new SessionDetail(
            row,
            List.of(
                new CallRound(1, List.of("call-1"), List.of("tool-1"), null, 0, 0, 0, 0, 0),
                new CallRound(2, List.of("call-2"), List.of(), null, 0, 0, 0, 0, 0)),
            List.of(),
            PayloadVisibility.STANDARD,
            "",
            "",
            "cache");

    SessionDetailParityAnalyzer.Result result = SessionDetailParityAnalyzer.analyze(detail);

    assertThat(result.round(1).toMap())
        .containsEntry("summary", "请帮我修复这个 bug")
        .containsEntry("time", "10:00:02")
        .containsEntry("isUserInput", true);
    assertThat(result.round(2).toMap())
        .containsEntry("summary", "已找到问题并修复")
        .containsEntry("time", "10:00:04")
        .containsEntry("isUserInput", false);
  }

  @Test
  @DisplayName("Qoder tool-only round 使用工具名摘要而非 Round N 占位")
  void qoderToolOnlyRoundUsesToolNameSummary() throws Exception {
    Path source = tempDir.resolve("qoder-tool-only.jsonl");
    Files.writeString(source, qoderToolOnlyRollout());

    SessionRow row =
        new SessionRow(
            "qoder:qoder-tool-only",
            "qoder",
            "qoder-tool-only",
            "Qoder tool-only fixture",
            "/repo",
            "repo",
            "/repo",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:03:00Z",
            180,
            0,
            0,
            "claude-test",
            "main_java",
            "qoder",
            1,
            3,
            3,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            source.toString());
    SessionDetail detail =
        new SessionDetail(
            row,
            List.of(
                new CallRound(1, List.of("call-1"), List.of("t1"), null, 0, 0, 0, 0, 0),
                new CallRound(2, List.of("call-2"), List.of("t2", "t3"), null, 0, 0, 0, 0, 0),
                new CallRound(3, List.of("call-3"), List.of(), null, 0, 0, 0, 0, 0)),
            List.of(),
            PayloadVisibility.STANDARD,
            "",
            "",
            "cache");

    SessionDetailParityAnalyzer.Result result = SessionDetailParityAnalyzer.analyze(detail);

    // 第 1 轮存在用户输入，优先使用用户文本。
    assertThat(result.round(1).toMap())
        .containsEntry("summary", "fix it")
        .containsEntry("isUserInput", true);
    assertThat(result.round(1).time).isNotEmpty();

    // 第 2 轮没有用户输入和助手文本，使用多个工具名生成摘要。
    assertThat(result.round(2).toMap())
        .containsEntry("summary", "Tool: Write, Edit")
        .containsEntry("isUserInput", false);
    assertThat(result.round(2).time).isNotEmpty();

    // 第 3 轮存在助手文本，使用该文本而不是工具摘要。
    assertThat(result.round(3).toMap())
        .containsEntry("summary", "Done")
        .containsEntry("isUserInput", false);
  }

  @Test
  @DisplayName("Qoder 纯 tool_use round（无用户输入无 assistant text）使用单工具名摘要")
  void qoderPureToolOnlyRoundUsesSingleToolNameSummary() throws Exception {
    Path source = tempDir.resolve("qoder-pure-tool-only.jsonl");
    Files.writeString(source, qoderPureToolOnlyRollout());

    SessionRow row =
        new SessionRow(
            "qoder:qoder-pure-tool-only",
            "qoder",
            "qoder-pure-tool-only",
            "Qoder pure tool-only fixture",
            "/repo",
            "repo",
            "/repo",
            "2026-07-06T02:00:00Z",
            "2026-07-06T02:03:00Z",
            180,
            0,
            0,
            "claude-test",
            "main_java",
            "qoder",
            0,
            1,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            1,
            1,
            1,
            source.toString());
    SessionDetail detail =
        new SessionDetail(
            row,
            List.of(new CallRound(1, List.of("call-1"), List.of("t1"), null, 0, 0, 0, 0, 0)),
            List.of(),
            PayloadVisibility.STANDARD,
            "",
            "",
            "cache");

    SessionDetailParityAnalyzer.Result result = SessionDetailParityAnalyzer.analyze(detail);

    assertThat(result.round(1).toMap())
        .containsEntry("summary", "Tool: Read")
        .containsEntry("isUserInput", false);
    assertThat(result.round(1).time).isNotEmpty();
  }

  private static String qoderPureToolOnlyRollout() {
    return ""
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"qoder-pure-tool-only\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:01Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"tool_use\",\"id\":\"t1\",\"name\":\"Read\",\"input\":{}}],\"stop_reason\":\"tool_use\"}}\n";
  }

  private static String qoderToolOnlyRollout() {
    return ""
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"qoder-tool-only\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:01Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"fix it\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:02Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"tool_use\",\"id\":\"t1\",\"name\":\"Read\",\"input\":{}}],\"stop_reason\":\"tool_use\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:03Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"t1\",\"content\":\"data\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:04Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"tool_use\",\"id\":\"t2\",\"name\":\"Write\",\"input\":{}},{\"type\":\"tool_use\",\"id\":\"t3\",\"name\":\"Edit\",\"input\":{}}],\"stop_reason\":\"tool_use\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:05Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"t2\",\"content\":\"ok\"},{\"type\":\"tool_result\",\"tool_use_id\":\"t3\",\"content\":\"ok\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:06Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"Done\"}],\"stop_reason\":\"end_turn\"}}\n";
  }

  private static String qoderRollout() {
    return ""
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"qoder-session\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:01Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"请帮我修复这个 bug\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:02Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"我来看看代码\"},{\"type\":\"tool_use\",\"id\":\"tool-1\",\"name\":\"read_file\",\"input\":{\"path\":\"main.java\"}}],\"stop_reason\":\"tool_use\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:03Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"tool-1\",\"content\":\"file content here\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:04Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"已找到问题并修复\"}],\"stop_reason\":\"end_turn\"}}\n";
  }

  @Test
  @DisplayName("rollout fixture 保留嵌套 JSON 中的 Windows 路径")
  void parentRolloutPreservesWindowsChildPath() throws Exception {
    Path child = Path.of("C:\\synthetic\\sessions\\child.jsonl");
    ObjectMapper mapper = new ObjectMapper();
    for (String line : parentRollout(child).lines().toList()) {
      var payload = mapper.readTree(line).path("payload");
      if (payload.path("call_id").asText().equals("spawn-child") && payload.has("output")) {
        var output = mapper.readTree(payload.path("output").asText());
        assertThat(output.path("agent_id").asText()).isEqualTo("child-00000001");
        assertThat(output.path("path").asText()).isEqualTo(child.toString());
        return;
      }
    }
    throw new AssertionError("Missing spawn-child output fixture");
  }

  private static String parentRollout(Path child) throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    String spawnOutput =
        mapper.writeValueAsString(Map.of("agent_id", "child-00000001", "path", child.toString()));
    return ""
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"parent-session\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"/goal 修复失败工具展示\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:01Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"tool-failed\",\"name\":\"exec_command\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:02Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"tool-failed\",\"output\":\"Process exited with code 1\\nOutput:\\nboom\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:03Z\",\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":50,\"cached_input_tokens\":0,\"output_tokens\":10,\"total_tokens\":60}}}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:03Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"继续检查 subagent 成功状态\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:04Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"call_id\":\"tool-custom\",\"name\":\"apply_patch\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:05Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool-custom\",\"output\":\"Exit code: 0\\nOutput:\\nok\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:06Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"spawn-child\",\"name\":\"spawn_agent\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:07Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"spawn-child\",\"output\":"
        + mapper.writeValueAsString(spawnOutput)
        + "}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:08Z\",\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":170,\"cached_input_tokens\":100,\"output_tokens\":30,\"total_tokens\":200}}}}\n";
  }

  private static String childRollout() {
    return ""
        + "{\"timestamp\":\"2026-07-06T02:01:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"child-00000001\",\"parent_thread_id\":\"parent-session\",\"agent_role\":\"repo-mapper\",\"source\":{\"subagent\":{\"thread_spawn\":{\"parent_thread_id\":\"parent-session\"}}}}}\n"
        + "{\"timestamp\":\"2026-07-06T02:01:01Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"child-tool\",\"name\":\"exec_command\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:01:02Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"child-tool\",\"output\":\"Exit code: 0\\nOutput:\\nchild ok\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:01:03Z\",\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":40,\"cached_input_tokens\":10,\"output_tokens\":5,\"total_tokens\":45}}}}\n";
  }

  private static String claudeRollout() {
    return ""
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"First manual prompt\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:01Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"Assistant reply\"}],\"usage\":{\"input_tokens\":10,\"output_tokens\":5}}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:02Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"Assistant-only continuation\"}],\"usage\":{\"input_tokens\":20,\"output_tokens\":5}}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:03Z\",\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":\"Second manual prompt\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:04Z\",\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"Second assistant reply\"}],\"usage\":{\"input_tokens\":30,\"output_tokens\":5}}}\n";
  }

  private static String codexInternalRollout() {
    return ""
        + "{\"timestamp\":\"2026-07-06T02:00:00Z\",\"type\":\"session_meta\",\"payload\":{\"id\":\"codex-internal\"}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:01Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"<subagent_notification>\\n{\\\"status\\\":{\\\"completed\\\":\\\"PASS\\\"}}\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:02Z\",\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":10,\"cached_input_tokens\":0,\"output_tokens\":5,\"total_tokens\":15}}}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:03Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"<codex_internal_context source=\\\"goal\\\">hidden</codex_internal_context>\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:04Z\",\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":30,\"cached_input_tokens\":0,\"output_tokens\":11,\"total_tokens\":41}}}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:05Z\",\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"真正的用户输入\"}]}}\n"
        + "{\"timestamp\":\"2026-07-06T02:00:06Z\",\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":60,\"cached_input_tokens\":0,\"output_tokens\":18,\"total_tokens\":78}}}}\n";
  }
}
