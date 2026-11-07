package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexLegacyUsageTruthTest {
  @TempDir Path directory;

  @Test
  void legacyDecreaseAndFollowingSegmentRemainUnknownWithoutEpochIdentity() throws Exception {
    Path file = directory.resolve("legacy.jsonl");
    Files.writeString(
        file,
        legacy(100, 40, 20)
            + legacy(20, 5, 4)
            + "{\"type\":\"turn_context\",\"payload\":{\"turn_id\":\"not-an-epoch\"}}\n"
            + legacy(30, 8, 6));
    var result = parse(file);
    assertThat(result.diagnostics()).anyMatch(d -> d.code().equals("TOKEN_COUNTER_RESET"));
    assertThat(result.diagnostics()).anyMatch(d -> d.code().equals("TOKEN_USAGE_AMBIGUOUS"));
    assertThat(
            result.diagnostics().stream()
                .filter(d -> d.code().equals("TOKEN_COUNTER_RESET"))
                .map(d -> d.message()))
        .allSatisfy(
            message ->
                assertThat(message).doesNotContain("Modern", "establishes").contains("unknown"));
    assertThat(result.records().stream().filter(r -> r.eventType().equals("assistant")).count())
        .isEqualTo(1);
    assertThat(result.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(120);
    var metadata = new CodexSourceAdapter().singleFileMetadata(file);
    assertThat(metadata.get("tokenContainsUnknown")).isEqualTo("true");
    assertThat(metadata.get("freshInputTokenPrecision")).isEqualTo("mixed");
    assertThat(result.records()).hasSize(4);
  }

  @Test
  void missingInclusiveDependencyIsNotMeasuredFreshButExplicitZerosAre() throws Exception {
    Path partial = directory.resolve("partial.jsonl");
    Files.writeString(
        partial,
        modern(
            "partial", "\"input_tokens\":100,\"cache_write_input_tokens\":0,\"output_tokens\":20"));
    var metadata = new CodexSourceAdapter().singleFileMetadata(partial);
    assertThat(metadata.get("freshInputTokenPrecision")).isNotEqualTo("provider_reported");
    assertThat(
            parse(partial)
                .records()
                .getFirst()
                .usage()
                .provenance()
                .get("freshInputTokenPrecision"))
        .isNotEqualTo("provider_reported");
    Path zeros = directory.resolve("zeros.jsonl");
    Files.writeString(
        zeros,
        modern(
            "zeros",
            "\"input_tokens\":0,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":0"));
    assertThat(
            parse(zeros).records().getFirst().usage().provenance().get("freshInputTokenPrecision"))
        .isEqualTo("provider_reported");
  }

  @Test
  void ambiguityKeepsBothObservedQuestionsAndAnswers() throws Exception {
    Path file = directory.resolve("bodies.jsonl");
    String firstQuestion = message("user", "first question");
    String firstAnswer = message("assistant", "first answer");
    String secondQuestion = message("user", "second question");
    String secondAnswer = message("assistant", "second answer");
    Files.writeString(
        file,
        firstQuestion
            + firstAnswer
            + legacy(100, 40, 20)
            + secondQuestion
            + legacy(20, 5, 4)
            + secondAnswer
            + legacy(30, 8, 6));
    var records = parse(file).records();
    assertThat(records.stream().filter(r -> r.messageRole().orElse("").equals("user")).count())
        .isEqualTo(2);
    assertThat(records.stream().filter(r -> r.messageRole().orElse("").equals("assistant")).count())
        .isEqualTo(2);
    for (String body :
        java.util.List.of("first question", "first answer", "second question", "second answer")) {
      assertThat(records.stream().filter(r -> r.content().equals(body)).count())
          .as(body)
          .isEqualTo(1);
    }
    assertThat(
            records.stream().filter(r -> r.callId().orElse("").startsWith("token_count:")).count())
        .isEqualTo(1);
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(120);
  }

  @Test
  void explicitZeroCounterSnapshotKeepsPrecisionWithoutInventingACall() throws Exception {
    Path file = directory.resolve("zero-counter.jsonl");
    Files.writeString(file, legacy(0, 0, 0) + legacy(20, 5, 4));
    var records = parse(file).records();
    assertThat(records.stream().filter(r -> r.eventType().equals("assistant")).count())
        .isEqualTo(1);
    assertThat(records.getFirst().usage().provenance())
        .containsEntry("freshInputTokenPrecision", "provider_reported");
    assertThat(records.getFirst().callId()).isEmpty();
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(24);
  }

  @Test
  void selectedMixedLegacyUsesTheSameInclusiveDependenciesAsItsArithmetic() throws Exception {
    Path file = directory.resolve("mixed-missing-write.jsonl");
    Files.writeString(
        file,
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":100,\"cached_input_tokens\":40,\"output_tokens\":20}}}}\n"
            + "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"modern\",\"usage\":{\"input_tokens\":20,\"cached_input_tokens\":5,\"cache_write_input_tokens\":0,\"output_tokens\":3},\"thread_token_usage\":{\"input_tokens\":120,\"cached_input_tokens\":45,\"cache_write_input_tokens\":0,\"output_tokens\":23}}}\n");
    var records = parse(file).records();
    assertThat(records.getFirst().usage().provenance())
        .containsEntry("freshInputTokenPrecision", "unavailable");
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(143);
    assertThat(new CodexSourceAdapter().singleFileMetadata(file))
        .containsEntry("freshInputTokenPrecision", "mixed");
  }

  private static String message(String role, String body) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\""
        + role
        + "\",\"content\":\""
        + body
        + "\"}}\n";
  }

  private SourceResult.Success parse(Path file) {
    var adapter = new CodexSourceAdapter();
    return (SourceResult.Success)
        adapter.parse(new Candidate(adapter.fingerprint(file), "codex:truth", "", Map.of()), null);
  }

  private static String legacy(int input, int read, int output) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":"
        + input
        + ",\"cached_input_tokens\":"
        + read
        + ",\"cache_write_input_tokens\":0,\"output_tokens\":"
        + output
        + "}}}}\n";
  }

  private static String modern(String id, String usage) {
    return "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\""
        + id
        + "\",\"usage\":{"
        + usage
        + "}}}\n";
  }
}
