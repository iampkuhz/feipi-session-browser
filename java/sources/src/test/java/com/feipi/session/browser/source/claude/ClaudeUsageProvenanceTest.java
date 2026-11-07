package com.feipi.session.browser.source.claude;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ClaudeUsageProvenanceTest {
  @TempDir Path tempDir;

  @Test
  void selectedMessageFieldsKeepProvenanceWithoutBorrowingAnotherCall() throws Exception {
    Files.writeString(
        tempDir.resolve(ClaudeConstants.HISTORY_FILE),
        "{\"sessionId\":\"synthetic-usage\",\"project\":\"synthetic-project\",\"timestamp\":1000}\n");
    Path project = tempDir.resolve(ClaudeConstants.PROJECTS_DIR).resolve("synthetic-project");
    Files.createDirectories(project);
    Files.writeString(
        project.resolve("synthetic-usage.jsonl"),
        """
        {"type":"assistant","message":{"id":"a","content":"partial","usage":{"input_tokens":9,"output_tokens":1}}}
        {"type":"assistant","message":{"id":"a","stop_reason":"end_turn","content":[{"type":"text","text":"final"},{"type":"text","text":"fragment"}],"usage":{"input_tokens":0,"cache_read_input_tokens":0,"output_tokens":2}}}
        {"type":"assistant","message":{"id":"b","content":"other","usage":{"cache_creation_input_tokens":7,"output_tokens":0}}}
        {"type":"assistant","message":{"id":"c","content":"no usage"}}
        {"type":"assistant","message":{"id":"d","content":"start","usage":{"input_tokens":8,"cache_creation_input_tokens":3}}}
        {"type":"assistant","message":{"id":"d","stop_reason":"end_turn","content":"end","usage":{"output_tokens":1}}}
        """);
    ClaudeSourceAdapter adapter = new ClaudeSourceAdapter();
    SourceResult.Success result =
        (SourceResult.Success)
            adapter.parse(adapter.discover(tempDir).orderedItems().getFirst(), null);
    List<SourceRecord> selected =
        result.records().stream()
            .filter(record -> record.responseMessageId().orElse("").equals("a"))
            .toList();
    assertThat(selected)
        .isNotEmpty()
        .allSatisfy(
            record -> {
              assertThat(record.usage().inputTokens()).isZero();
              assertThat(record.usage().outputTokens()).isEqualTo(2);
              assertThat(record.usage().provenance())
                  .containsEntry("freshInputTokenPrecision", "provider_reported")
                  .containsEntry("cacheReadTokenPrecision", "provider_reported")
                  .containsEntry("cacheWriteTokenPrecision", "unavailable");
            });
    assertThat(
            result.records().stream()
                .filter(record -> record.responseMessageId().orElse("").equals("d")))
        .hasSize(2)
        .allSatisfy(
            record -> {
              assertThat(record.usage().inputTokens()).isEqualTo(8);
              assertThat(record.usage().cacheCreationInputTokens()).isEqualTo(3);
              assertThat(record.usage().provenance())
                  .containsEntry("freshInputTokenPrecision", "provider_reported")
                  .containsEntry("cacheWriteTokenPrecision", "provider_reported")
                  .containsEntry("cacheReadTokenPrecision", "unavailable");
            });
    assertThat(
            result.records().stream()
                .filter(record -> record.responseMessageId().orElse("").equals("c")))
        .allSatisfy(record -> assertThat(record.usage().provenance()).isEmpty());
  }
}
