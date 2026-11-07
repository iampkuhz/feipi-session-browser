package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.junit.jupiter.api.io.TempDir;

/** fork 的原生 ordinal 标识继承范围；重写的顶层时间不使父正文成为 child 新活动。 */
class CodexInheritedHistoryTest {
  @TempDir Path directory;

  @Test
  void inheritedContextDoesNotBecomeChildActivityBeforeReportedZero() throws Exception {
    assertNewActivity(true);
  }

  @Test
  void inheritedContextDoesNotBecomeChildUnknownCalls() throws Exception {
    assertNewActivity(false);
  }

  @Test
  void inheritedOnlyForkDoesNotManufactureChildExecution() throws Exception {
    var child = inherited();
    var records = parse(child);
    assertThat(records.stream().filter(r -> r.eventType().equals("assistant"))).isEmpty();
    assertThat(records.stream().filter(r -> !r.metaContext() && r.messageRole().isPresent()))
        .isEmpty();
    assertThat(records.stream().filter(r -> r.eventType().equals("tool_use"))).isEmpty();
    assertThat(records.stream().filter(r -> r.eventType().equals("tool_result"))).isEmpty();
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isZero();
    assertThat(records.stream().filter(r -> !r.usage().provenance().isEmpty())).isEmpty();
  }

  @Test
  void inheritedModelRemainsContextWithoutInheritedExecution() throws Exception {
    var child = inherited();
    child.set(8, "{\"type\":\"turn_context\",\"payload\":{\"model\":\"inherited-context-model\"}}");
    appendOwn(child, false);
    var records = parse(child);
    assertOwn(records, 11, 12, 13, 14, 15, false);
    assertThat(records.stream().filter(r -> r.eventType().equals("assistant")))
        .singleElement()
        .satisfies(call -> assertThat(call.model()).contains("inherited-context-model"));
  }

  @TestFactory
  Stream<DynamicTest> invalidAndUnsupportedHistoryCannotSilentlyBecomeActivity() {
    var events = inherited();
    appendOwn(events, true);
    String valid = jsonl(events, true);
    var continuations = inherited();
    continuations.set(8, legacy(10));
    appendOwn(continuations, true);
    String reset = jsonl(continuations, true);
    continuations.set(15, legacy(12));
    String continued = jsonl(continuations, true);
    return Stream.of(
        invalid("missing-native-ordinal", valid.replace("\"ordinal\":3,", ""), "ordinal"),
        invalid(
            "duplicate-native-ordinal",
            valid.replace("\"ordinal\":4,", "\"ordinal\":3,"),
            "ordinal"),
        invalid(
            "out-of-range-cut",
            valid.replace("history_start_ordinal\":9", "history_start_ordinal\":999"),
            "boundary"),
        invalid(
            "conflicting-fork-parent",
            valid.replace("forked_from_id\":\"parent\"", "forked_from_id\":\"other\""),
            "parent"),
        invalid(
            "conflicting-copied-parent-meta",
            valid.replace("\"id\":\"parent\"", "\"id\":\"other\""),
            "parent"),
        invalid("conflicting-direct-and-nested-parent", conflictingParent(valid), "parent"),
        invalid(
            "bad-physical-record-with-otherwise-continuous-ordinals",
            valid.replace("{\"ordinal\":4,", "{broken}\n{\"ordinal\":4,"),
            "history"),
        invalid("inherited-legacy-continuation-is-unsupported", continued, "usage"),
        invalid("inherited-legacy-reset-is-unsupported", reset, "usage"));
  }

  @Test
  void conflictingParentEvidenceCannotProduceSingleFileUsageMetadata() throws Exception {
    Path file = conflictingParentFile();
    assertThatThrownBy(() -> new CodexSourceAdapter().singleFileMetadata(file))
        .isInstanceOf(IOException.class)
        .satisfies(error -> assertThat(error.getMessage()).containsIgnoringCase("parent"));
  }

  @Test
  void optimizedMetadataProjectionRetainsConflictingParentEvidence() throws Exception {
    var result =
        CodexMetadataProjection.read(
            new com.feipi.session.browser.source.common.JsonlReader(), conflictingParentFile());
    assertThatThrownBy(() -> CodexActivityRange.create(result.events(), result.diagnostics()))
        .isInstanceOf(IOException.class)
        .satisfies(error -> assertThat(error.getMessage()).containsIgnoringCase("parent"));
  }

  private Path conflictingParentFile() throws Exception {
    var child = inherited();
    appendOwn(child, true);
    return Files.writeString(
        directory.resolve("conflicting-parent.jsonl"), conflictingParent(jsonl(child, true)));
  }

  private static String conflictingParent(String valid) {
    return valid.replace(
        "\"forked_from_id\":\"parent\"",
        "\"forked_from_id\":\"parent\",\"source\":{\"subagent\":{\"thread_spawn\":{\"parent_thread_id\":\"other\"}}}");
  }

  private DynamicTest invalid(String name, String transcript, String reason) {
    return DynamicTest.dynamicTest(
        name,
        () -> {
          Path file = Files.writeString(directory.resolve("invalid-history.jsonl"), transcript);
          var adapter = new CodexSourceAdapter();
          var result =
              adapter.parse(
                  new Candidate(adapter.fingerprint(file), "codex:child", "", Map.of()), null);
          if (result instanceof SourceResult.Success success) success.close();
          assertThat(result).as(name).isInstanceOf(SourceResult.Fatal.class);
          assertThat(((SourceResult.Fatal) result).errorDetail()).containsIgnoringCase(reason);
          assertThatThrownBy(() -> adapter.singleFileMetadata(file))
              .as(name + " metadata must not turn invalid history into known usage")
              .isInstanceOf(IOException.class)
              .satisfies(error -> assertThat(error.getMessage()).containsIgnoringCase(reason));
        });
  }

  @Test
  void oldChildWithoutHistoryHeaderKeepsExistingSourceSemantics() throws Exception {
    var child = new ArrayList<String>();
    child.add(meta("child", "\"parent_thread_id\":\"parent\""));
    appendOwn(child, true);
    assertOwn(parse(child), 3, 4, 5, 6, 7, true);
  }

  private void assertNewActivity(boolean zero) throws Exception {
    var child = inherited();
    appendOwn(child, zero);
    assertOwn(parse(child), 11, 12, 13, 14, 15, zero);
    var metadata =
        new CodexSourceAdapter().singleFileMetadata(directory.resolve("rollout-child.jsonl"));
    for (String key :
        List.of(
            "freshInputTokenPrecision",
            "cacheReadTokenPrecision",
            "cacheWriteTokenPrecision",
            "outputTokenPrecision")) {
      assertThat(metadata).containsEntry(key, zero ? "provider_reported" : "unknown");
    }
  }

  private static void assertOwn(
      List<SourceRecord> records,
      int userIndex,
      int toolIndex,
      int resultIndex,
      int answerIndex,
      int usageIndex,
      boolean zero) {
    var calls = records.stream().filter(r -> r.eventType().equals("assistant")).toList();
    assertThat(calls).as("only new child output supplies a call").hasSize(1);
    var call = calls.getFirst();
    assertThat(call.relation().subagentId()).contains("child");
    assertThat(call.relation().parentToolCallId()).contains("spawn-root");
    assertThat(call.eventIndex()).isEqualTo(zero ? usageIndex : answerIndex);
    assertThat(call.usage().total()).isZero();
    for (String key :
        List.of(
            "freshInputTokenPrecision",
            "cacheReadTokenPrecision",
            "cacheWriteTokenPrecision",
            "outputTokenPrecision")) {
      assertThat(call.usage().provenance().getOrDefault(key, "unknown"))
          .as(key)
          .isEqualTo(zero ? "provider_reported" : "unknown");
    }
    assertThat(
            records.stream()
                .filter(r -> !r.metaContext() && r.messageRole().orElse("").equals("user")))
        .singleElement()
        .satisfies(r -> assertSource(r, userIndex, "own question"));
    assertThat(
            records.stream()
                .filter(r -> !r.metaContext() && r.messageRole().orElse("").equals("assistant")))
        .singleElement()
        .satisfies(r -> assertSource(r, answerIndex, "own answer"));
    assertThat(records.stream().filter(r -> r.eventType().equals("tool_use")))
        .singleElement()
        .satisfies(
            r -> {
              assertThat(r.eventIndex()).isEqualTo(toolIndex);
              assertThat(r.callId()).contains("own-tool");
              assertThat(r.toolCalls())
                  .singleElement()
                  .satisfies(
                      tool -> {
                        assertThat(tool.name()).isEqualTo("synthetic");
                        assertThat(tool.input()).isEqualTo("own input");
                      });
            });
    assertThat(records.stream().filter(r -> r.eventType().equals("tool_result")))
        .singleElement()
        .satisfies(
            r -> {
              assertSource(r, resultIndex, "own result");
              assertThat(r.toolUseId()).contains("own-tool");
            });
    assertThat(
            records.stream()
                .filter(r -> r.eventType().equals("tool_use") || r.eventType().equals("assistant"))
                .flatMap(r -> r.toolCalls().stream()))
        .noneMatch(tool -> tool.name().equals("spawn_agent"));
  }

  private static void assertSource(SourceRecord record, int index, String body) {
    assertThat(record.content()).isEqualTo(body);
    assertThat(record.eventIndex()).isEqualTo(index);
    assertThat(record.timestamp()).contains("2026-01-02T00:00:00Z");
    assertThat(record.locator()).endsWith("rollout-child.jsonl#event[" + index + "]");
  }

  private List<SourceRecord> parse(List<String> child) throws Exception {
    // 继承的是 payload；ordinal/timestamp 刻意不同，不假设整个对象前缀相等。
    var parent = new ArrayList<String>();
    parent.add(meta("parent", ""));
    parent.addAll(inheritedPayloads());
    parent.add(tool("spawn-root", "spawn_agent", "spawn child"));
    parent.add(output("spawn-root", "{\"agent_id\":\"child\"}", false));
    parent.add(modern());
    Path parentFile =
        Files.writeString(directory.resolve("rollout-parent.jsonl"), jsonl(parent, false));
    Files.writeString(directory.resolve("rollout-child.jsonl"), jsonl(child, true));
    var adapter = new CodexSourceAdapter();
    try (var success =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(parentFile), "codex:parent", "", Map.of()),
                null)) {
      var records = new ArrayList<SourceRecord>();
      try (var cursor = success.recordSequence().openCursor()) {
        while (cursor.hasNext()) {
          var record = cursor.next();
          if (record.locator().contains("rollout-child.jsonl#event[")) records.add(record);
        }
      }
      return records;
    }
  }

  private static ArrayList<String> inherited() {
    var events = new ArrayList<String>();
    events.add(
        meta(
            "child",
            "\"parent_thread_id\":\"parent\",\"forked_from_id\":\"parent\",\"subagent_history_start_ordinal\":9"));
    events.add(meta("parent", ""));
    events.addAll(inheritedPayloads());
    return events;
  }

  private static List<String> inheritedPayloads() {
    return List.of(
        message("user", "inherited question"),
        tool("inherited-spawn", "spawn_agent", "inherited spawn"),
        output("inherited-spawn", "{\"agent_id\":\"copied-other\"}", false),
        message("assistant", "inherited answer"),
        tool("inherited-tool", "synthetic", "inherited input"),
        output("inherited-tool", "inherited result", true),
        message("assistant", "inherited final answer"));
  }

  private static void appendOwn(List<String> events, boolean zero) {
    events.add("{\"type\":\"event_msg\",\"payload\":{\"type\":\"thread_settings_applied\"}}");
    events.add("{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\"}}");
    events.add(message("user", "own question"));
    events.add(tool("own-tool", "synthetic", "own input"));
    events.add(output("own-tool", "own result", true));
    events.add(message("assistant", "own answer"));
    if (zero)
      events.add(
          "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":0,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":0}}}}");
  }

  private static String jsonl(List<String> events, boolean child) {
    var lines = new ArrayList<String>();
    for (int ordinal = 0; ordinal < events.size(); ordinal++) {
      lines.add(
          "{\"ordinal\":"
              + ordinal
              + ",\"timestamp\":\"2026-01-0"
              + (child ? "2" : "1")
              + "T00:00:00Z\","
              + events.get(ordinal).substring(1));
    }
    return String.join("\n", lines) + "\n";
  }

  private static String meta(String id, String extra) {
    return "{\"type\":\"session_meta\",\"payload\":{\"id\":\""
        + id
        + "\""
        + (extra.isEmpty() ? "" : "," + extra)
        + "}}";
  }

  private static String message(String role, String body) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\""
        + role
        + "\",\"content\":\""
        + body
        + "\"}}";
  }

  private static String tool(String id, String name, String input) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\",\"call_id\":\""
        + id
        + "\",\"name\":\""
        + name
        + "\",\"input\":\""
        + input
        + "\"}}";
  }

  private static String output(String id, String output, boolean text) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\""
        + id
        + "\",\"output\":"
        + (text ? "\"" + output + "\"" : output)
        + "}}";
  }

  private static String modern() {
    return "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"parent-response\",\"usage\":{\"input_tokens\":1,\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":1}}}";
  }

  private static String legacy(int input) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":"
        + input
        + ",\"cached_input_tokens\":0,\"cache_write_input_tokens\":0,\"output_tokens\":0}}}}";
  }
}
