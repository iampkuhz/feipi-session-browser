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
  @DisplayName("发现 session index 布局并解析 rollout/tool/subagent/token 语义")
  void parsesCodexRolloutSemanticsWithoutMutatingSourceRoot() throws IOException {
    String sessionId = "thread-main";

    // 写入 session_index.jsonl
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\"" + sessionId
            + "\",\"thread_name\":\"Main Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    // 创建 rollout 文件
    Path dayDir =
        tempDir
            .resolve(CodexConstants.SESSIONS_DIR)
            .resolve("2026")
            .resolve("06")
            .resolve("23");
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
        "{\"id\":\"" + sessionId
            + "\",\"thread_name\":\"Orphan Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    // 创建 rollout 文件
    Path dayDir =
        tempDir
            .resolve(CodexConstants.SESSIONS_DIR)
            .resolve("2026")
            .resolve("06")
            .resolve("23");
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
