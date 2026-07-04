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
        "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"open project transcript\"}]}}",
        "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"model\":\"claude-test-model\",\"content\":[{\"type\":\"text\",\"text\":\"fragment one\"},{\"type\":\"text\",\"text\":\"fragment two\"}],\"usage\":{\"input_tokens\":12,\"cache_creation_input_tokens\":3,\"cache_read_input_tokens\":4,\"output_tokens\":5}}}",
        "{\"type\":\"assistant\",\"message\":{\"content\":[{\"type\":\"tool_use\",\"id\":\"toolu_parent\",\"name\":\"Task\",\"input\":{\"subagent_type\":\"implementer\"}}]}}",
        "{\"type\":\"user\",\"message\":{\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"toolu_parent\",\"content\":\"subagent done\"}]}}",
        "{\"type\":\"assistant\",\"parent_tool_use_id\":\"toolu_parent\",\"isSidechain\":true,\"message\":{\"content\":[{\"type\":\"text\",\"text\":\"subagent sidechain\"}]}}",
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
