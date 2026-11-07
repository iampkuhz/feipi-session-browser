package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import org.junit.jupiter.api.io.TempDir;

/** 零计量不能删除已有响应的调用帧；纯 counter 轮询也不能成为调用。 */
class CodexZeroUsageCallAnchorTest {
  @TempDir Path directory;

  @TestFactory
  Stream<DynamicTest> zeroUsageAnchors() {
    return Stream.of(false, true)
        .flatMap(
            managed ->
                Stream.of(
                    test(
                        managed,
                        "legacy-reported-zero",
                        () -> response(managed, false, false, false)),
                    test(
                        managed,
                        "legacy-missing-cache-write",
                        () -> response(managed, true, false, false)),
                    test(
                        managed,
                        "repeated-zero-poll-and-same-text-fallback",
                        () -> response(managed, false, true, false)),
                    test(managed, "complete-identity-mirror", () -> identityMirror(managed)),
                    test(
                        managed,
                        "modern-zero-repeated-identity",
                        () -> response(managed, false, true, true)),
                    test(managed, "counter-polls-without-response", () -> pollsOnly(managed)),
                    test(
                        managed,
                        "tool-declaration-with-zero-closing",
                        () -> toolEvidence(managed, true, true)),
                    test(
                        managed,
                        "isolated-result-with-zero-is-not-output",
                        () -> toolEvidence(managed, false, true)),
                    test(
                        managed,
                        "unfinished-tool-without-closing",
                        () -> toolEvidence(managed, true, false)),
                    test(
                        managed,
                        "zero-before-response-is-not-response-usage",
                        () -> earlierZero(managed, false)),
                    test(managed, "zero-in-earlier-user-segment", () -> earlierZero(managed, true)),
                    test(managed, "nonzero-followed-by-polls", () -> nonzeroPolls(managed)),
                    test(
                        managed,
                        "response-without-new-selected-usage",
                        () -> unmeteredResponse(managed, false)),
                    test(
                        managed,
                        "response-after-counter-reset",
                        () -> unmeteredResponse(managed, true)),
                    test(managed, "invalid-input-is-not-reported-zero", () -> invalidZero(managed)),
                    test(managed, "two-observed-zero-responses", () -> twoResponses(managed))));
  }

  private void response(boolean managed, boolean missingWrite, boolean repeat, boolean modern)
      throws Exception {
    String question = question(managed);
    String usage = modern ? modern() : legacy(missingWrite);
    String transcript = body(question) + usage;
    if (repeat) transcript += usage + usage;
    if (repeat && !modern) {
      transcript +=
          "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_message\",\"message\":\"visible"
              + " answer\"}}\n"
              + usage;
    }
    var records = parse(transcript, managed);
    var frames = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(frames).as("one observed response has one call frame").hasSize(1);
    assertThat(frames.getFirst().usage().total()).isZero();
    assertThat(frames.getFirst().usage().provenance())
        .containsEntry("freshInputTokenPrecision", "provider_reported")
        .containsEntry("cacheReadTokenPrecision", "provider_reported")
        .containsEntry(
            "cacheWriteTokenPrecision", missingWrite ? "unavailable" : "provider_reported")
        .containsEntry("outputTokenPrecision", "provider_reported");
    assertThat(records.stream().filter(r -> r.content().equals(question))).hasSize(1);
    assertThat(records.stream().filter(r -> r.content().equals("visible answer"))).hasSize(1);
    assertThat(records.stream().filter(r -> r.messageRole().orElse("").equals("assistant")))
        .hasSize(repeat && !modern ? 2 : 1);
    assertThat(records.stream().filter(r -> r.eventType().equals("tool_use")))
        .singleElement()
        .satisfies(
            r -> {
              assertThat(r.callId()).contains("synthetic-tool");
              assertThat(r.toolCalls())
                  .singleElement()
                  .satisfies(tool -> assertThat(tool.input()).isEqualTo("synthetic input"));
            });
    assertThat(records.stream().filter(r -> r.eventType().equals("tool_result")))
        .singleElement()
        .satisfies(
            r -> {
              assertThat(r.toolUseId()).contains("synthetic-tool");
              assertThat(r.content()).isEqualTo("visible result");
            });
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isZero();
  }

  private void pollsOnly(boolean managed) throws Exception {
    String transcript = (managed ? message("user", question(true)) : "") + legacy(false).repeat(4);
    var records = parse(transcript, managed);
    assertThat(records.stream().filter(r -> r.eventType().equals("assistant"))).isEmpty();
    assertThat(records.stream().filter(r -> r.callId().isPresent())).isEmpty();
    assertThat(
            records.stream()
                .filter(
                    r ->
                        r.usage()
                            .provenance()
                            .getOrDefault("outputTokenPrecision", "")
                            .equals("provider_reported")))
        .isNotEmpty();
  }

  private void identityMirror(boolean managed) throws Exception {
    String question = question(managed);
    String events =
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"turn_id\":\"synthetic-turn\",\"message\":\""
            + question
            + "\"}}\n"
            + "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_message\",\"turn_id\":\"synthetic-turn\",\"message\":\"visible"
            + " answer\"}}\n";
    String responses =
        (message("user", question) + message("assistant", "visible answer"))
            .replace(
                "\"type\":\"message\",", "\"type\":\"message\",\"turn_id\":\"synthetic-turn\",");
    var records = parse(events + responses + legacy(false).repeat(3), managed);
    assertThat(records.stream().filter(r -> r.eventType().equals("assistant"))).hasSize(1);
    assertThat(records.stream().filter(r -> r.messageRole().orElse("").equals("assistant")))
        .hasSize(1);
    assertThat(records.stream().filter(r -> r.messageRole().orElse("").equals("user"))).hasSize(1);
    assertThat(records.stream().filter(r -> r.content().equals("visible answer"))).hasSize(1);
    assertThat(records.stream().filter(r -> r.content().equals(question))).hasSize(1);
  }

  private void twoResponses(boolean managed) throws Exception {
    var records =
        parse(
            body(question(managed)) + legacy(false) + body("next question") + legacy(false),
            managed);
    var frames = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(frames).hasSize(2);
    assertThat(frames).extracting(r -> r.callId().orElse("")).doesNotHaveDuplicates();
    assertThat(frames.getFirst().usage().provenance())
        .containsEntry("outputTokenPrecision", "provider_reported");
    assertThat(frames.getLast().usage().provenance())
        .containsEntry("outputTokenPrecision", "unknown");
    assertThat(records.stream().filter(r -> r.content().equals("visible answer"))).hasSize(2);
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isZero();
  }

  private void toolEvidence(boolean managed, boolean declaration, boolean closing)
      throws Exception {
    String tool =
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"call_id\":\"tool-only\",\"name\":\"synthetic\",\"input\":\"only"
            + " input\"}}\n";
    String result =
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"tool-only\",\"output\":\"only"
            + " result\"}}\n";
    var records =
        parse(
            message("user", question(managed))
                + (declaration ? tool : result)
                + (closing ? legacy(false) : ""),
            managed);
    var frames = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(frames).hasSize(declaration && closing ? 1 : 0);
    if (!frames.isEmpty()) {
      assertThat(frames.getFirst().usage().provenance())
          .containsEntry("outputTokenPrecision", "provider_reported");
    }
    assertThat(
            records.stream()
                .filter(r -> r.eventType().equals(declaration ? "tool_use" : "tool_result")))
        .hasSize(1);
  }

  private void earlierZero(boolean managed, boolean differentUser) throws Exception {
    String prefix = message("user", question(managed)) + legacy(false);
    String response =
        (differentUser ? message("user", "later question") : "")
            + message("assistant", "later answer");
    var records = parse(prefix + response, managed);
    var frames = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(frames).hasSize(1);
    assertThat(frames.getFirst().content()).isEqualTo("later answer");
    assertThat(frames.getFirst().usage().provenance())
        .containsEntry("outputTokenPrecision", "unknown");
  }

  private void nonzeroPolls(boolean managed) throws Exception {
    String positive = legacy(false).replace("\"input_tokens\":0", "\"input_tokens\":10");
    var records = parse(body(question(managed)) + positive.repeat(4), managed);
    assertThat(records.stream().filter(r -> r.eventType().equals("assistant"))).hasSize(1);
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(10);
  }

  private void unmeteredResponse(boolean managed, boolean reset) throws Exception {
    String positive = legacy(false).replace("\"input_tokens\":0", "\"input_tokens\":10");
    var records =
        parse(
            body(question(managed))
                + positive
                + body("next question")
                + (reset ? legacy(false) : ""),
            managed);
    var frames = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(frames).hasSize(2);
    assertThat(frames.getLast().content()).isEqualTo("visible answer");
    assertThat(frames.getLast().usage().provenance())
        .containsEntry("outputTokenPrecision", "unknown");
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(10);
  }

  private void invalidZero(boolean managed) throws Exception {
    var records =
        parse(
            body(question(managed))
                + legacy(false).replace("\"input_tokens\":0", "\"input_tokens\":-1"),
            managed);
    var frames = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(frames).hasSize(1);
    assertThat(frames.getFirst().usage().provenance())
        .containsEntry("freshInputTokenPrecision", "unavailable");
  }

  private List<SourceRecord> parse(String transcript, boolean managed) throws Exception {
    Path file = Files.writeString(directory.resolve("zero-" + managed + ".jsonl"), transcript);
    var adapter = new CodexSourceAdapter();
    try (var success =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(file), "codex:synthetic-zero", "", Map.of()),
                null)) {
      assertThat(success.hasManagedRecords()).isEqualTo(managed);
      var records = new ArrayList<SourceRecord>();
      try (var cursor = success.recordSequence().openCursor()) {
        while (cursor.hasNext()) records.add(cursor.next());
      }
      if (!managed) assertThat(records).isEqualTo(success.records());
      return records;
    }
  }

  private static String question(boolean managed) {
    // 使用实际载荷预算选择 managed 表示，不修改阈值或全局配置。
    return managed ? "visible question " + "x".repeat(2_100_000) : "visible question";
  }

  private static String body(String question) {
    return message("user", question)
        + "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"call_id\":\"synthetic-tool\",\"name\":\"synthetic\",\"input\":\"synthetic"
        + " input\"}}\n"
        + "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"synthetic-tool\",\"output\":\"visible"
        + " result\"}}\n"
        + message("assistant", "visible answer");
  }

  private static String message(String role, String text) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\""
        + role
        + "\",\"content\":\""
        + text
        + "\"}}\n";
  }

  private static String legacy(boolean missingWrite) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":0,\"cached_input_tokens\":0,"
        + (missingWrite ? "" : "\"cache_creation_input_tokens\":0,")
        + "\"output_tokens\":0,\"total_tokens\":0}}}}\n";
  }

  private static String modern() {
    return "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"synthetic-response\",\"usage\":{\"input_tokens\":0,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":0}}}\n";
  }

  private static DynamicTest test(boolean managed, String name, Checked action) {
    return DynamicTest.dynamicTest((managed ? "managed/" : "list/") + name, action::run);
  }

  @FunctionalInterface
  private interface Checked {
    void run() throws Exception;
  }
}
