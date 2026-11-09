package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.ParseSeverity;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

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

  @ParameterizedTest
  @ValueSource(ints = {SourceResult.MAX_DIAGNOSTICS, SourceResult.MAX_DIAGNOSTICS + 100})
  void longRolloutWithAmbiguousCountersKeepsAllRecordsWithinDiagnosticBudget(int ambiguousCount)
      throws Exception {
    Path file = directory.resolve("synthetic-long-rollout.jsonl");
    Files.writeString(
        file,
        legacy(100, 40, 20)
            + legacy(20, 5, 4).repeat(ambiguousCount)
            + message("user", "synthetic prompt after counter reset"));

    try (var result = parse(file);
        var cursor = result.recordSequence().openCursor()) {
      assertThat(result.candidateCount()).isEqualTo(ambiguousCount + 2);
      assertThat(result.diagnostics())
          .extracting(SourceDiagnostic::code)
          .containsExactly(
              "TOKEN_USAGE_AMBIGUOUS", "TOKEN_COUNTER_RESET", "CODEX_DIAGNOSTICS_TRUNCATED");
      assertThat(result.diagnostics().getLast().message())
          .isEqualTo("Additional Codex diagnostics omitted: " + (ambiguousCount - 1));
      assertThat(cursor.next().usage().total()).isEqualTo(120);
      for (int i = 0; i < ambiguousCount; i++) {
        assertThat(cursor.next().usage().total()).isZero();
      }
      assertThat(cursor.next().content()).isEqualTo("synthetic prompt after counter reset");
      assertThat(cursor.hasNext()).isFalse();
    }
    assertThat(new CodexSourceAdapter().singleFileMetadata(file))
        .containsEntry("tokenContainsUnknown", "true");
  }

  @Test
  void diagnosticOverflowCannotHideALateParseError() throws Exception {
    Path file = directory.resolve("synthetic-malformed-rollout.jsonl");
    Files.writeString(file, "null\n".repeat(SourceResult.MAX_DIAGNOSTICS) + "{broken}\n");

    try (var result = parse(file)) {
      assertThat(result.diagnostics())
          .extracting(SourceDiagnostic::code)
          .containsExactly("BAD_JSON", "NON_OBJECT_SKIPPED", "CODEX_DIAGNOSTICS_TRUNCATED");
      assertThat(result.diagnostics().stream().filter(d -> d.severity() == ParseSeverity.ERROR))
          .singleElement()
          .satisfies(
              error -> {
                assertThat(error.code()).isEqualTo("BAD_JSON");
                assertThat(error.lineNo()).isEqualTo(SourceResult.MAX_DIAGNOSTICS + 1);
              });
    }
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
