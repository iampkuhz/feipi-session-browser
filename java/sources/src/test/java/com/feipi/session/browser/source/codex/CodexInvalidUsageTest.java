package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.ValueSource;

class CodexInvalidUsageTest {
  @TempDir Path directory;

  static Stream<Arguments> invalidComponents() {
    return Stream.of(
            "input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens")
        .flatMap(
            field ->
                Stream.of("-1", "0.5", "9223372036854775808")
                    .map(value -> Arguments.of(field, value)));
  }

  @ParameterizedTest
  @MethodSource("invalidComponents")
  void invalidNumericComponentIsUnavailableWithoutErasingIndependentUsageOrBodies(
      String field, String value) throws Exception {
    String usage =
        "\"input_tokens\":10,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":7";
    String validValue =
        field.equals("input_tokens") ? "10" : field.equals("output_tokens") ? "7" : "0";
    usage = usage.replace("\"" + field + "\":" + validValue, "\"" + field + "\":" + value);
    var result = parse(message() + modern("invalid", usage) + modern("later", validUsage()));
    SourceRecord invalid = response(result, "invalid");
    String precision =
        switch (field) {
          case "input_tokens" -> "freshInputTokenPrecision";
          case "cached_input_tokens" -> "cacheReadTokenPrecision";
          case "cache_write_input_tokens" -> "cacheWriteTokenPrecision";
          default -> "outputTokenPrecision";
        };
    assertThat(invalid.usage().provenance()).containsEntry(precision, "unavailable");
    if (!field.equals("output_tokens")) {
      assertThat(invalid.usage().outputTokens()).isEqualTo(7);
      assertThat(invalid.usage().provenance())
          .containsEntry("outputTokenPrecision", "provider_reported");
      assertThat(invalid.usage().provenance())
          .containsEntry("freshInputTokenPrecision", "unavailable");
    } else {
      assertThat(invalid.usage().outputTokens()).isZero();
      assertThat(invalid.usage().inputTokens()).isEqualTo(10);
      assertThat(invalid.usage().provenance())
          .containsEntry("freshInputTokenPrecision", "provider_reported");
    }
    assertThat(result.records()).anyMatch(record -> record.content().equals("visible body"));
    SourceRecord later = response(result, "later");
    assertThat(later.usage().inputTokens()).isEqualTo(10);
    assertThat(later.usage().outputTokens()).isEqualTo(7);
    assertThat(later.usage().provenance())
        .containsEntry("freshInputTokenPrecision", "provider_reported")
        .containsEntry("outputTokenPrecision", "provider_reported");
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "\"input_tokens\":1,\"cached_input_tokens\":2,\"cache_write_input_tokens\":0",
        "\"input_tokens\":0,\"cached_input_tokens\":9223372036854775807,\"cache_write_input_tokens\":9223372036854775807"
      })
  void impossibleInclusiveDependenciesDoNotProduceMeasuredFreshZeroOrOverflow(String usage)
      throws Exception {
    var record = response(parse(modern("invalid", usage + ",\"output_tokens\":7")), "invalid");
    assertThat(record.usage().inputTokens()).isZero();
    assertThat(record.usage().provenance())
        .containsEntry("freshInputTokenPrecision", "unavailable");
    assertThat(record.usage().outputTokens()).isEqualTo(7);
    assertThat(record.usage().provenance())
        .containsEntry("outputTokenPrecision", "provider_reported");
  }

  @Test
  void validLaterAliasCannotGiveInvalidSelectedAliasProviderCredit() throws Exception {
    var record =
        response(
            parse(
                modern(
                    "alias",
                    validUsage()
                        .replace(
                            "\"output_tokens\":7", "\"output_tokens\":-1,\"outputTokens\":7"))),
            "alias");
    assertThat(record.usage().outputTokens()).isZero();
    assertThat(record.usage().provenance()).containsEntry("outputTokenPrecision", "unavailable");
  }

  @Test
  void missingOutputIsUnavailableWhileInputAndBodyRemainVisible() throws Exception {
    var result =
        parse(
            message()
                + modern(
                    "missing",
                    "\"input_tokens\":10,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0"));
    var record = response(result, "missing");
    assertThat(record.usage().outputTokens()).isZero();
    assertThat(record.usage().provenance()).containsEntry("outputTokenPrecision", "unavailable");
    assertThat(record.usage().inputTokens()).isEqualTo(10);
    assertThat(record.usage().provenance())
        .containsEntry("freshInputTokenPrecision", "provider_reported");
    assertThat(result.records()).anyMatch(event -> event.content().equals("visible body"));
  }

  @Test
  void explicitLegalZerosRemainProviderReported() throws Exception {
    var record =
        response(
            parse(modern("zero", validUsage().replace(":10", ":0").replace(":7", ":0"))), "zero");
    assertThat(record.usage().total()).isZero();
    for (String key :
        new String[] {
          "freshInputTokenPrecision",
          "cacheReadTokenPrecision",
          "cacheWriteTokenPrecision",
          "outputTokenPrecision"
        }) {
      assertThat(record.usage().provenance()).containsEntry(key, "provider_reported");
    }
  }

  private SourceResult.Success parse(String contents) throws Exception {
    Path file = directory.resolve("synthetic.jsonl");
    Files.writeString(file, contents);
    var adapter = new CodexSourceAdapter();
    var result =
        adapter.parse(
            new Candidate(adapter.fingerprint(file), "codex:invalid", "", Map.of()), null);
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    return (SourceResult.Success) result;
  }

  private static SourceRecord response(SourceResult.Success result, String id) {
    return result.records().stream()
        .filter(record -> record.callId().orElse("").equals("token_usage_record:" + id))
        .findFirst()
        .orElseThrow();
  }

  private static String validUsage() {
    return "\"input_tokens\":10,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":7";
  }

  private static String modern(String id, String usage) {
    return "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\""
        + id
        + "\",\"usage\":{"
        + usage
        + "}}}\n";
  }

  private static String message() {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":\"visible"
        + " body\"}}\n";
  }
}
