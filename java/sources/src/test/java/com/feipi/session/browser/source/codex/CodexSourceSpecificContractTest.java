package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceOutcome;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

@DisplayName("Codex source-specific contract")
class CodexSourceSpecificContractTest {

  @TempDir Path tempDir;

  private final CodexSourceAdapter adapter = new CodexSourceAdapter();

  @Test
  @DisplayName("有 token_count 时保留响应正文而不新增 assistant 帧或用量")
  void preservesResponseContentWithoutChangingTokenFrames() throws IOException {
    SourceResult.Success success = parseContentFixture(codexRollout());

    assertThat(success.records()).hasSize(7);
    assertThat(success.records().stream().filter(r -> "assistant".equals(r.eventType())))
        .hasSize(1);
    assertThat(success.records().get(4).content()).isEqualTo("ok");
    assertThat(success.records().get(5).eventType()).isEqualTo("response_item");
    assertThat(success.records().get(5).content()).isEqualTo("done");
    assertThat(success.records().get(5).usage().total()).isZero();
    assertThat(success.records().stream().mapToLong(r -> r.usage().inputTokens()).sum())
        .isEqualTo(60);
    assertThat(success.records().stream().mapToLong(r -> r.usage().cacheReadInputTokens()).sum())
        .isEqualTo(40);
    assertThat(success.records().stream().mapToLong(r -> r.usage().outputTokens()).sum())
        .isEqualTo(20);
    assertThat(success.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(120);
  }

  @Test
  @DisplayName("消息与工具正文保持空白，元数据和工具调用不作为助手正文")
  void preservesTextBlocksAndExcludesNonMessagePayloads() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"  ask\\n"},{"type":"input_image","text":"excluded"},{"type":"text","text":"next  "}]}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"  reply\\n"},{"text":"end  "}]}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"tool-1","name":"shell","content":"excluded"}}
            {"type":"response_item","payload":{"type":"custom_tool_call_output","call_id":"tool-1","output":[{"type":"text","text":"  result\\n"},{"type":"output_text","text":"done  "}]}}
            {"type":"response_item","payload":{"type":"message","role":"developer","content":[{"text":"excluded"}]}}
            {"type":"response_item","payload":{"type":"reasoning","content":[{"text":"excluded"}]}}
            {"type":"session_meta","payload":{"content":"excluded"}}
            """);

    assertThat(eventTypes(success))
        .containsExactly(
            "user",
            "assistant",
            "tool_use",
            "tool_result",
            "response_item",
            "assistant",
            "session_meta");
    assertThat(success.records())
        .extracting(SourceRecord::content)
        .containsExactly("  ask\nnext  ", "  reply\nend  ", "", "  result\ndone  ", "", "", "");
    assertThat(success.records()).allSatisfy(r -> assertThat(r.usage().total()).isZero());
  }

  private SourceResult.Success parseContentFixture(String content) throws IOException {
    Path rollout = tempDir.resolve("content-fixture.jsonl");
    Files.writeString(rollout, content, StandardCharsets.UTF_8);
    Candidate candidate =
        new Candidate(
            adapter.fingerprint(rollout), "codex:content-fixture", "", java.util.Map.of());
    SourceResult result = adapter.parse(candidate, null);
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    return (SourceResult.Success) result;
  }

  @Test
  @DisplayName("发现 session index 布局并解析 rollout/tool/subagent/token 语义")
  void parsesCodexRolloutSemanticsWithoutMutatingSourceRoot() throws IOException {
    String sessionId = "thread-main";

    // 写入 session_index.jsonl
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Main Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    // 创建 rollout 文件
    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(rollout, codexRollout(), StandardCharsets.UTF_8);
    FileState before = FileState.capture(rollout);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult result = adapter.parse(candidate, null);

    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    SourceResult.Success success = (SourceResult.Success) result;
    assertThat(success.records()).allSatisfy(r -> assertThat(r).isInstanceOf(SourceRecord.class));
    assertThat(eventTypes(success))
        .containsExactly(
            "turn_context",
            "session_meta",
            "assistant",
            "tool_use",
            "tool_result",
            "response_item",
            "unknown");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("SUBAGENT_SESSION", "UNKNOWN_BLOCK_TYPE");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .doesNotContain("TOKEN_NO_CUMULATIVE", "TOOL_ORPHAN");
    SourceRecord tokenRecord = success.records().get(2);
    assertThat(tokenRecord.model()).contains("gpt-test");
    assertThat(tokenRecord.usage().inputTokens()).isEqualTo(60);
    assertThat(tokenRecord.usage().cacheReadInputTokens()).isEqualTo(40);
    assertThat(tokenRecord.usage().outputTokens()).isEqualTo(20);
    assertThat(tokenRecord.usage().total()).isEqualTo(120);
    assertThat(success.records().get(0).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[0]");
    assertThat(candidate.sessionKey()).isEqualTo("codex:" + sessionId);
    // 无 threads.db 时 projectKey 为空
    assertThat(candidate.projectKey()).isEmpty();
    assertThat(FileState.capture(rollout)).isEqualTo(before);
    assertThat(adapter.fingerprint(rollout))
        .usingRecursiveComparison()
        .isEqualTo(candidate.fingerprint());
  }

  @Test
  @DisplayName("孤立 tool result 产生诊断但不丢弃 rollout")
  void orphanToolResultProducesDiagnosticButKeepsSession() throws IOException {
    String sessionId = "thread-orphan";

    // 写入 session_index.jsonl
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Orphan Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    // 创建 rollout 文件
    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(
        rollout,
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"missing\"}}\n",
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);

    assertThat(success.records()).hasSize(1);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOOL_ORPHAN_RESULT");
  }

  @Test
  @DisplayName("时间戳从顶层 event.timestamp 传递到所有 SourceRecord")
  void timestampPropagatedToAllSourceRecords() throws IOException {
    String sessionId = "thread-ts";

    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"TS Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(
        rollout,
        String.join(
            "\n",
            "{\"type\":\"turn_context\",\"timestamp\":\"2026-06-23T10:00:00Z\","
                + "\"payload\":{\"model\":\"gpt-test\"}}",
            "{\"type\":\"event_msg\",\"timestamp\":\"2026-06-23T10:00:01Z\","
                + "\"payload\":{\"type\":\"user_message\",\"content\":\"hello\"}}",
            "{\"type\":\"response_item\",\"timestamp\":\"2026-06-23T10:00:02Z\","
                + "\"payload\":{\"type\":\"function_call\",\"call_id\":\"c1\",\"name\":\"shell\"}}",
            ""),
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);

    assertThat(success.records()).hasSize(3);
    // 所有记录都应包含时间戳
    assertThat(success.records().get(0).timestamp()).hasValue("2026-06-23T10:00:00Z");
    assertThat(success.records().get(1).timestamp()).hasValue("2026-06-23T10:00:01Z");
    assertThat(success.records().get(2).timestamp()).hasValue("2026-06-23T10:00:02Z");
  }

  @Test
  @DisplayName("event_msg 和 response_item 的 payload.type 编码到 turnId")
  void payloadSubtypeEncodedInTurnId() throws IOException {
    String sessionId = "thread-turnid";

    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"TurnId Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(
        rollout,
        String.join(
            "\n",
            // 用户消息，轮次标识为消息子类型
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"content\":\"hi\"}}",
            // 助手消息，轮次标识为消息子类型
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_message\",\"content\":\"ok\"}}",
            // 函数调用，轮次标识为工具子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\","
                + "\"call_id\":\"c1\",\"name\":\"shell\"}}",
            // 自定义工具调用，轮次标识为工具子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\","
                + "\"call_id\":\"c2\",\"name\":\"custom\"}}",
            // 助手文本消息，轮次标识为消息子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\","
                + "\"role\":\"assistant\",\"content\":\"done\"}}",
            // 推理内容，轮次标识为推理子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"reasoning\","
                + "\"content\":\"thinking\"}}",
            ""),
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);

    assertThat(success.records()).hasSize(6);
    // 验证消息事件的轮次子类型
    assertThat(success.records().get(0).turnId()).hasValue("user_message");
    assertThat(success.records().get(0).eventType()).isEqualTo("event_msg");
    assertThat(success.records().get(1).turnId()).hasValue("agent_message");
    assertThat(success.records().get(1).eventType()).isEqualTo("event_msg");
    // 验证响应项的轮次子类型
    assertThat(success.records().get(2).turnId()).hasValue("function_call");
    assertThat(success.records().get(2).eventType()).isEqualTo("tool_use");
    assertThat(success.records().get(3).turnId()).hasValue("custom_tool_call");
    assertThat(success.records().get(3).eventType()).isEqualTo("tool_use");
    assertThat(success.records().get(4).turnId()).hasValue("message");
    assertThat(success.records().get(5).turnId()).hasValue("reasoning");
  }

  @Test
  @DisplayName("session_index.jsonl 中的 model 字段作为回退传递到记录")
  void modelFallbackFromIndexEntry() throws IOException {
    String sessionId = "thread-model";

    // session_index.jsonl 包含 model 字段
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Model Thread\",\"updated_at\":\"2026-06-23\","
            + "\"model\":\"gpt-4-fallback\"}\n",
        StandardCharsets.UTF_8);

    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    // 第一个事件没有 model，应使用 indexEntry 回退值
    Files.writeString(
        rollout,
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"content\":\"hi\"}}\n",
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    // 验证 candidate metadata 包含 model
    assertThat(candidate.metadata()).containsEntry("model", "gpt-4-fallback");

    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);
    // 记录应使用回退模型
    assertThat(success.records().get(0).model()).hasValue("gpt-4-fallback");
  }

  private static List<String> eventTypes(SourceResult.Success success) {
    return success.records().stream().map(SourceRecord::eventType).toList();
  }

  private static String codexRollout() {
    return String.join(
        "\n",
        "{\"type\":\"turn_context\",\"payload\":{\"model\":\"gpt-test\"}}",
        "{\"type\":\"session_meta\",\"payload\":{\"id\":\"thread-main\",\"thread_source\":\"subagent\",\"parent_thread_id\":\"thread-parent\"}}",
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":100,\"cached_input_tokens\":40,\"output_tokens\":20}}}}",
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"call_1\",\"name\":\"shell\"}}",
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_1\",\"output\":\"ok\"}}",
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"done\"}]}}",
        "{\"payload\":{\"schema\":\"drift\"}}",
        "");
  }

  private record FileState(long size, FileTime lastModified, String hash) {
    static FileState capture(Path file) throws IOException {
      SourceFingerprint fp = new CodexSourceAdapter().fingerprint(file);
      return new FileState(
          Files.size(file), Files.getLastModifiedTime(file), fp.contentHash().orElseThrow());
    }
  }
}
