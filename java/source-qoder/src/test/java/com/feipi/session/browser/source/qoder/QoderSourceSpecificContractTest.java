package com.feipi.session.browser.source.qoder;

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

@DisplayName("Qoder source-specific contract")
class QoderSourceSpecificContractTest {

  @TempDir Path tempDir;

  private final QoderSourceAdapter adapter = new QoderSourceAdapter();

  @Test
  @DisplayName("多目录布局、parts、schema variants 和 unknown part 不退化为计数器")
  void parsesQoderProviderSemanticsWithoutMutatingSourceRoot() throws IOException {
    Path project = tempDir.resolve("projects").resolve("home%2Fqoder%2Fdemo");
    Path cacheProject = tempDir.resolve("cache").resolve("projects").resolve("cached");
    Files.createDirectories(project);
    Files.createDirectories(cacheProject);
    Path session = project.resolve("session-main.jsonl");
    Path cacheSession = cacheProject.resolve("session-cache.jsonl");
    Files.writeString(session, qoderSession(), StandardCharsets.UTF_8);
    Files.writeString(
        cacheSession, "{\"role\":\"assistant\",\"content\":\"cached\"}\n", StandardCharsets.UTF_8);
    FileState before = FileState.capture(session);

    List<Candidate> candidates = adapter.discover(tempDir).orderedItems();
    Candidate candidate =
        candidates.stream()
            .filter(item -> item.fingerprint().locator().endsWith("session-main.jsonl"))
            .findFirst()
            .orElseThrow();
    SourceResult result = adapter.parse(candidate, null);

    assertThat(candidates).hasSize(2);
    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    SourceResult.Success success = (SourceResult.Success) result;
    assertThat(success.records()).allSatisfy(r -> assertThat(r).isInstanceOf(ParsedRecord.class));
    assertThat(eventTypes(success))
        .containsExactly("message", "tool", "usage", "assistant", "unknown", "message");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("CACHE_FORMAT_ROLE", "UNKNOWN_BLOCK_TYPE", "UNKNOWN_PART_TYPE");
    assertThat(success.records().get(0).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[0]");
    assertThat(success.records())
        .extracting(ParsedRecord::locator)
        .noneMatch(locator -> locator.matches(".*[0-9a-fA-F]{8}-[0-9a-fA-F]{4}.*"));
    assertThat(candidate.sessionKey()).isEqualTo("home%2Fqoder%2Fdemo/session-main");
    assertThat(candidate.projectKey()).isEqualTo("home/qoder/demo");
    assertThat(FileState.capture(session)).isEqualTo(before);
    assertThat(adapter.fingerprint(session))
        .usingRecursiveComparison()
        .isEqualTo(candidate.fingerprint());
  }

  private static List<String> eventTypes(SourceResult.Success success) {
    return success.records().stream()
        .map(record -> ((QoderParsedRecord) record).eventType())
        .toList();
  }

  private static String qoderSession() {
    return String.join(
        "\n",
        "{\"type\":\"message\",\"role\":\"user\",\"parts\":[{\"type\":\"text\",\"text\":\"hello\"},{\"type\":\"tool_use\",\"id\":\"tool_1\",\"name\":\"read\"}]}",
        "{\"type\":\"tool\",\"parts\":[{\"type\":\"tool_result\",\"tool_use_id\":\"tool_1\",\"content\":\"ok\"}]}",
        "{\"type\":\"usage\",\"usage\":{\"input_tokens\":7,\"cache_read_input_tokens\":2,\"output_tokens\":3}}",
        "{\"role\":\"assistant\",\"parts\":[{\"type\":\"text\",\"text\":\"cache role schema\"}]}",
        "{\"parts\":[{\"type\":\"mystery_part\",\"payload\":true}]}",
        "{\"type\":\"message\",\"parts\":[{\"text\":\"missing part type\"}]}",
        "");
  }

  private record FileState(long size, FileTime lastModified, String hash) {
    static FileState capture(Path file) throws IOException {
      SourceFingerprint fp = new QoderSourceAdapter().fingerprint(file);
      return new FileState(
          Files.size(file), Files.getLastModifiedTime(file), fp.contentHash().orElseThrow());
    }
  }
}
