package com.feipi.session.browser.source.qoder;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class QoderUsageProvenanceTest {
  @TempDir Path tempDir;

  private static final String STREAM =
      """
      {"type":"assistant","message":{"id":"a","content":"stream fragment"}}
      {"type":"assistant","message":{"id":"a","stop_reason":"end_turn","content":"final","usage":{"input_tokens":12,"cache_read_input_tokens":0,"cache_creation_input_tokens":0,"output_tokens":3}}}
      """;

  @Test
  void sameResponseFragmentsUseReportedUsageIncludingZeroWithoutLosingRecords() throws IOException {
    Path file = write(STREAM);
    QoderSourceAdapter adapter = new QoderSourceAdapter();
    Map<String, String> metadata = adapter.singleFileMetadata(file);
    assertPrecision(metadata, "provider_reported");
    assertThat(metadata)
        .doesNotContainKey("tokenContainsUnavailable")
        .doesNotContainKey("tokenEstimationMethod");
    var candidate = adapter.discover(tempDir).orderedItems().getFirst();
    assertPrecision(candidate.metadata(), "provider_reported");
    SourceResult.Success parsed = (SourceResult.Success) adapter.parse(candidate, null);
    assertThat(parsed.records()).hasSize(2);
    assertThat(parsed.records().getLast().usage().inputTokens()).isEqualTo(12);
    assertThat(parsed.records().getLast().usage().outputTokens()).isEqualTo(3);
    assertThat(parsed.records().getFirst().content()).isEqualTo("stream fragment");
  }

  @Test
  void anotherResponseWithoutUsageStillMakesEveryComponentMixed() throws IOException {
    Map<String, String> metadata =
        new QoderSourceAdapter()
            .singleFileMetadata(
                write(
                    STREAM
                        + """
        {"type":"assistant","message":{"id":"b","content":"separate response"}}
        """));
    assertPrecision(metadata, "mixed");
    assertThat(metadata).containsEntry("tokenContainsUnavailable", "true");
  }

  @Test
  void missingIdentityDoesNotBorrowUsageFromAdjacentResponse() throws IOException {
    Map<String, String> metadata =
        new QoderSourceAdapter()
            .singleFileMetadata(
                write(
                    STREAM
                        + """
        {"type":"assistant","parentUuid":"a","message":{"content":"stream fragment"}}
        """));
    assertPrecision(metadata, "mixed");
  }

  @Test
  void terminalOrInputBoundaryPreventsReusingAnEarlierResponseIdentity() throws IOException {
    for (String boundary :
        new String[] {"", "{\"type\":\"user\",\"message\":{\"content\":\"next\"}}\n"}) {
      Map<String, String> metadata =
          new QoderSourceAdapter()
              .singleFileMetadata(
                  write(
                      STREAM
                          + boundary
                          + """
          {"type":"assistant","message":{"id":"a","content":"new response without usage"}}
          """));
      assertPrecision(metadata, "mixed");
    }
  }

  @Test
  void conflictingReportedUsageRetainsExistingMaximumNumbersAndReportedSource() throws IOException {
    Path file =
        write(
            """
        {"type":"assistant","message":{"id":"a","content":"earlier","usage":{"input_tokens":20,"cache_read_input_tokens":0,"cache_creation_input_tokens":0,"output_tokens":1}}}
        """
                + STREAM);
    QoderSourceAdapter adapter = new QoderSourceAdapter();
    assertPrecision(adapter.singleFileMetadata(file), "provider_reported");
    var result =
        (SourceResult.Success)
            adapter.parse(adapter.discover(tempDir).orderedItems().getFirst(), null);
    assertThat(result.records().getFirst().usage().inputTokens()).isEqualTo(20);
    assertThat(result.records().getLast().usage().inputTokens()).isEqualTo(12);
  }

  @Test
  void partialUsageAtTheWinningZeroRetainsUnavailableEvidence() throws IOException {
    Map<String, String> metadata =
        new QoderSourceAdapter()
            .singleFileMetadata(
                write(
                    """
        {"type":"assistant","message":{"id":"a","content":"partial","usage":{"output_tokens":0}}}
        """
                        + STREAM));
    assertThat(metadata)
        .containsEntry("freshInputTokenPrecision", "provider_reported")
        .containsEntry("outputTokenPrecision", "provider_reported")
        .containsEntry("cacheReadTokenPrecision", "mixed")
        .containsEntry("cacheWriteTokenPrecision", "mixed")
        .containsEntry("tokenContainsUnavailable", "true");
  }

  @Test
  void metaContextBoundaryCannotBorrowUsageEvenWithTheSameId() throws IOException {
    Map<String, String> metadata =
        new QoderSourceAdapter()
            .singleFileMetadata(
                write(
                    """
        {"type":"assistant","isMeta":true,"message":{"id":"a","content":"separate meta fragment"}}
        """
                        + STREAM));
    assertPrecision(metadata, "mixed");
  }

  @Test
  void noUsageStillUsesExistingSessionEstimate() throws IOException {
    Map<String, String> metadata =
        new QoderSourceAdapter()
            .singleFileMetadata(
                write(
                    """
        {"type":"user","message":{"content":"synthetic context"}}
        {"type":"assistant","message":{"id":"a","content":"synthetic answer"}}
        """));
    assertThat(metadata)
        .containsEntry("freshInputTokenPrecision", "estimated")
        .containsEntry("outputTokenPrecision", "estimated")
        .containsEntry("cacheReadTokenPrecision", "unavailable")
        .containsEntry("tokenEstimationMethod", "visible_context_v1");
  }

  private Path write(String events) throws IOException {
    Path project = Files.createDirectories(tempDir.resolve("projects/synthetic"));
    Path file = project.resolve("synthetic-response.jsonl");
    Files.writeString(file, events);
    return file;
  }

  private static void assertPrecision(Map<String, String> metadata, String precision) {
    assertThat(metadata)
        .containsEntry("freshInputTokenPrecision", precision)
        .containsEntry("cacheReadTokenPrecision", precision)
        .containsEntry("cacheWriteTokenPrecision", precision)
        .containsEntry("outputTokenPrecision", precision);
  }
}
