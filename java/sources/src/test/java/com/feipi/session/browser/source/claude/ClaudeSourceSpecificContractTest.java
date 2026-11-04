package com.feipi.session.browser.source.claude;

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

@DisplayName("Claude source-specific contract")
class ClaudeSourceSpecificContractTest {

  @TempDir Path tempDir;

  private final ClaudeSourceAdapter adapter = new ClaudeSourceAdapter();

  @Test
  @DisplayName("meta 上下文不占标题但主与 sidecar 仍保留原角色、文本和显式证据")
  void metaContextIsNotTitleAndSurvivesMainAndSidecarParsing() throws IOException {
    Files.writeString(
        tempDir.resolve(ClaudeConstants.HISTORY_FILE),
        "{\"sessionId\":\"synthetic-meta-session\",\"project\":\"synthetic-meta-project\",\"timestamp\":1000}\n");
    Path project = tempDir.resolve(ClaudeConstants.PROJECTS_DIR).resolve("synthetic-meta-project");
    Files.createDirectories(project);
    Path transcript = project.resolve("synthetic-meta-session.jsonl");
    Files.writeString(
        transcript,
        """
        {"type":"user","isMeta":true,"message":{"role":"user","content":"  synthetic main context\\n"}}
        {"type":"user","message":{"role":"user","content":"synthetic human prompt"}}
        {"type":"assistant","isMeta":true,"message":{"id":"synthetic-main-message","content":"synthetic main answer","usage":{"input_tokens":5,"output_tokens":2}}}
        """);
    Path sidecar = project.resolve("synthetic-meta-session/subagents/agent-synthetic-meta.jsonl");
    Files.createDirectories(sidecar.getParent());
    Files.writeString(
        sidecar,
        """
        {"type":"user","isMeta":true,"message":{"role":"user","content":"synthetic child context"}}
        {"type":"user","message":{"role":"user","content":"synthetic child task"}}
        {"type":"assistant","isMeta":true,"message":{"id":"synthetic-child-message","content":"synthetic child answer","usage":{"input_tokens":3,"output_tokens":1}}}
        """);
    FileState mainBefore = FileState.capture(transcript);
    FileState sideBefore = FileState.capture(sidecar);
    Candidate candidate = adapter.discover(tempDir).orderedItems().getFirst();
    assertThat(candidate.metadata()).containsEntry("title", "synthetic human prompt");
    SourceResult.Success result = (SourceResult.Success) adapter.parse(candidate, null);
    assertThat(result.records())
        .extracting(SourceRecord::eventType)
        .containsExactly("user", "user", "assistant", "user", "user", "assistant");
    assertThat(result.records())
        .extracting(SourceRecord::metaContext)
        .containsExactly(true, false, true, true, false, true);
    assertThat(result.records())
        .extracting(SourceRecord::content)
        .containsExactly(
            "  synthetic main context\n",
            "synthetic human prompt",
            "synthetic main answer",
            "synthetic child context",
            "synthetic child task",
            "synthetic child answer");
    assertThat(result.records().subList(0, 3))
        .allSatisfy(
            record -> assertThat(record.locator()).startsWith(transcript.toString() + "#event["));
    assertThat(result.records().subList(3, 6))
        .allSatisfy(
            record -> assertThat(record.locator()).startsWith(sidecar.toString() + "#event["));
    assertThat(result.records().get(2).usage().inputTokens()).isEqualTo(5);
    assertThat(result.records().get(5).usage().inputTokens()).isEqualTo(3);
    assertThat(FileState.capture(transcript)).isEqualTo(mainBefore);
    assertThat(FileState.capture(sidecar)).isEqualTo(sideBefore);
  }

  @Test
  @DisplayName("解析 history/project transcript/active/tool/subagent 语义且保持源只读")
  void parsesClaudeProviderSemanticsWithoutMutatingSourceRoot() throws IOException {
    // 写入 history.jsonl
    String sessionId = "claude-session-id";
    String project = "home%2Fwork%2Fdemo";
    Files.writeString(
        tempDir.resolve(ClaudeConstants.HISTORY_FILE),
        "{\"sessionId\":\""
            + sessionId
            + "\",\"project\":\""
            + project
            + "\",\"display\":\"Test\",\"timestamp\":1000}\n",
        StandardCharsets.UTF_8);

    // 创建 transcript 文件
    Path projectDir = tempDir.resolve(ClaudeConstants.PROJECTS_DIR).resolve(project);
    Files.createDirectories(projectDir);
    Path transcript = projectDir.resolve(sessionId + ".jsonl");
    Files.writeString(transcript, claudeTranscript(), StandardCharsets.UTF_8);
    FileState before = FileState.capture(transcript);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult result = adapter.parse(candidate, null);

    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    SourceResult.Success success = (SourceResult.Success) result;
    assertThat(success.records()).allSatisfy(r -> assertThat(r).isInstanceOf(SourceRecord.class));
    assertThat(eventTypes(success))
        .containsExactly(
            "summary", "user", "assistant", "assistant", "tool_result", "assistant", "unknown");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("UNKNOWN_BLOCK_TYPE");
    assertThat(success.records().get(2).model()).contains("claude-test-model");
    assertThat(success.records().get(2).usage().inputTokens()).isEqualTo(12);
    assertThat(success.records().get(2).usage().cacheCreationInputTokens()).isEqualTo(3);
    assertThat(success.records().get(2).usage().cacheReadInputTokens()).isEqualTo(4);
    assertThat(success.records().get(2).usage().outputTokens()).isEqualTo(5);
    assertThat(success.records().get(0).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[0]");
    assertThat(success.records().get(5).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[5]");
    assertThat(candidate.sessionKey()).isEqualTo("claude_code:" + sessionId);
    assertThat(candidate.projectKey()).isEqualTo(project);
    assertThat(FileState.capture(transcript)).isEqualTo(before);
    assertThat(adapter.fingerprint(transcript))
        .usingRecursiveComparison()
        .isEqualTo(candidate.fingerprint());
  }

  private static List<String> eventTypes(SourceResult.Success success) {
    return success.records().stream().map(SourceRecord::eventType).toList();
  }

  private static String claudeTranscript() {
    return String.join(
        "\n",
        "{\"type\":\"summary\",\"summary\":\"history snapshot\"}",
        "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"open"
            + " project transcript\"}]}}",
        "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"model\":\"claude-test-model\",\"content\":[{\"type\":\"text\",\"text\":\"fragment"
            + " one\"},{\"type\":\"text\",\"text\":\"fragment"
            + " two\"}],\"usage\":{\"input_tokens\":12,\"cache_creation_input_tokens\":3,\"cache_read_input_tokens\":4,\"output_tokens\":5}}}",
        "{\"type\":\"assistant\",\"message\":{\"content\":[{\"type\":\"tool_use\",\"id\":\"toolu_parent\",\"name\":\"Task\",\"input\":{\"subagent_type\":\"implementer\"}}]}}",
        "{\"type\":\"user\",\"message\":{\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"toolu_parent\",\"content\":\"subagent"
            + " done\"}]}}",
        "{\"type\":\"assistant\",\"parent_tool_use_id\":\"toolu_parent\",\"isSidechain\":true,\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"subagent"
            + " sidechain\"}]}}",
        "{\"source\":\"active-session\",\"active\":true}",
        "");
  }

  private record FileState(long size, FileTime lastModified, String hash) {
    static FileState capture(Path file) throws IOException {
      SourceFingerprint fp = new ClaudeSourceAdapter().fingerprint(file);
      return new FileState(
          Files.size(file), Files.getLastModifiedTime(file), fp.contentHash().orElseThrow());
    }
  }
}
