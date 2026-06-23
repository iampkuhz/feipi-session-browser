package com.feipi.session.browser.source.claude;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParsedRecord;
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
    Path projectDir = tempDir.resolve("projects").resolve("home%2Fwork%2Fdemo");
    Files.createDirectories(projectDir);
    Path transcript = projectDir.resolve("claude-session.jsonl");
    Files.writeString(transcript, claudeTranscript(), StandardCharsets.UTF_8);
    FileState before = FileState.capture(transcript);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult result = adapter.parse(candidate, null);

    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    SourceResult.Success success = (SourceResult.Success) result;
    assertThat(success.records()).allSatisfy(r -> assertThat(r).isInstanceOf(ParsedRecord.class));
    assertThat(eventTypes(success))
        .containsExactly(
            "summary", "user", "assistant", "assistant", "user", "assistant", "unknown");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("UNKNOWN_BLOCK_TYPE");
    assertThat(success.records().get(0).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[0]");
    assertThat(success.records().get(5).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[5]");
    assertThat(success.records())
        .extracting(ParsedRecord::locator)
        .noneMatch(locator -> locator.matches(".*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}.*"));
    assertThat(candidate.sessionKey()).isEqualTo("home%2Fwork%2Fdemo/claude-session");
    assertThat(candidate.projectKey()).isEqualTo("home%2Fwork%2Fdemo");
    assertThat(FileState.capture(transcript)).isEqualTo(before);
    assertThat(adapter.fingerprint(transcript))
        .usingRecursiveComparison()
        .isEqualTo(candidate.fingerprint());
  }

  private static List<String> eventTypes(SourceResult.Success success) {
    return success.records().stream()
        .map(record -> ((ClaudeParsedRecord) record).eventType())
        .toList();
  }

  private static String claudeTranscript() {
    return String.join(
        "\n",
        "{\"type\":\"summary\",\"summary\":\"history snapshot\"}",
        "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"open project transcript\"}]}}",
        "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"fragment one\"},{\"type\":\"text\",\"text\":\"fragment two\"}]},\"usage\":{\"input_tokens\":12,\"cache_creation_input_tokens\":3,\"cache_read_input_tokens\":4,\"output_tokens\":5}}",
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
