package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceToolCall;
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

@DisplayName("Codex source-specific contract")
class CodexSourceSpecificContractTest {

  @TempDir Path tempDir;

  private final CodexSourceAdapter adapter = new CodexSourceAdapter();

  @Test
  void onlyCorroboratedInnerCommandBindsToTheExactResult() throws Exception {
    String declaration =
        """
        {"type":"response_item","payload":{"type":"custom_tool_call","name":"exec","call_id":"tool","input":"run synthetic-cmd-example"}}
        """;
    String command =
        """
        {"type":"event_msg","payload":{"type":"item_completed","item":{"type":"CommandExecution","source":"unified_exec_startup","command":["shell","-c","synthetic-cmd-example"],"aggregated_output":"unique synthetic stdout","status":"completed","exit_code":0,"duration":{"secs":0,"nanos":6458}}}}
        """;
    String result =
        """
        {"type":"response_item","payload":{"type":"custom_tool_call_output","call_id":"tool","output":[{"type":"input_text","text":"unique synthetic stdout"}]}}
        """;
    try (var parsed = parseContentFixture(declaration + command + result)) {
      var value = parsed.records().getLast().toolObservation().orElseThrow();
      assertThat(value.toolCallId()).isEqualTo("tool");
      assertThat(value.kind()).isEqualTo("inner_command");
      assertThat(value.source()).isEqualTo("codex:item_completed#event[1]");
      assertThat(value.durationNanos()).isEqualTo(6458);
      assertThat(value.exitCode()).isZero();
      assertThat(value.status()).isEqualTo("completed");
    }
    for (String input :
        List.of(
            declaration + command + command + result,
            declaration + command + result.replace("stdout", "different"),
            declaration + command + result.replace("\"tool\"", "\"other\""),
            declaration
                + command.replace("synthetic-cmd-example", "another-synthetic-command")
                + result,
            declaration + command + declaration.replace("\"tool\"", "\"other\"") + result)) {
      try (var parsed = parseContentFixture(input)) {
        assertThat(parsed.records()).allMatch(record -> record.toolObservation().isEmpty());
      }
    }
  }

  @Test
  void qualifiedInputPreservesMessageItemsAndQueueReceiptsWithoutLifecycle() throws Exception {
    String target = "11111111-1111-4111-8111-111111111111";
    String message =
        inputEvent(
            "message",
            "multi_agent_v1",
            "function_call",
            "{\"target\":\"" + target + "\",\"message\":\"synthetic followup\"}");
    String items =
        inputEvent(
            "items",
            "multi_agent_v1",
            "function_call",
            "{\"target\":\""
                + target
                + "\",\"interrupt\":true,\"items\":[{\"type\":\"mention\",\"name\":\"drive\",\"path\":\"app://google_drive\"},{\"type\":\"text\",\"text\":\"synthetic"
                + " items\"}]}");
    try (var parsed =
        parseContentFixture(
            message + items + inputResult("message", "one") + inputResult("items", "two"))) {
      var facts =
          parsed.records().stream().flatMap(record -> record.collaboration().stream()).toList();
      assertThat(facts)
          .hasSize(4)
          .allSatisfy(
              fact -> {
                assertThat(fact.kind()).isEqualTo("input");
                assertThat(fact.targetId()).contains(target);
                assertThat(fact.sourceLocator()).contains("#event[");
              });
      assertThat(facts)
          .filteredOn(fact -> fact.phase().equals("result_report"))
          .allSatisfy(fact -> assertThat(fact.reportedStatus()).contains("queued"));
      assertThat(facts.toString()).doesNotContain("synthetic followup", "synthetic items");
    }
  }

  @Test
  void inputQualificationAndConflictingReceiptsRemainConservative() throws Exception {
    String args = "{\"target\":\"11111111-1111-4111-8111-111111111111\",\"message\":\"synthetic\"}";
    String source =
        inputEvent("bare", "", "function_call", args)
            + inputEvent("wrong", "other", "function_call", args)
            + inputEvent("custom", "multi_agent_v1", "custom_tool_call", args)
            + inputEvent("conflict", "multi_agent_v1", "function_call", args)
            + inputResult("conflict", "one")
            + inputResult("conflict", "two")
            + inputEvent("duplicate", "multi_agent_v1", "function_call", args)
            + inputEvent("duplicate", "other", "function_call", args)
            + inputEvent(
                "bad",
                "multi_agent_v1",
                "function_call",
                "{\"target\":\"not-a-thread\",\"message\":\"synthetic\"}")
            + inputEvent("missing", "multi_agent_v1", "function_call", args)
            + inputEvent("namespace", "multi_agent_v1", "function_call", args)
            + "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"namespace\":\"other\",\"call_id\":\"namespace\",\"output\":{\"submission_id\":\"one\"}}}\n"
            + inputEvent("error", "multi_agent_v1", "function_call", args)
            + "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"error\",\"is_error\":true,\"output\":{\"submission_id\":\"one\"}}}\n";
    try (var parsed = parseContentFixture(source)) {
      var facts =
          parsed.records().stream().flatMap(record -> record.collaboration().stream()).toList();
      assertThat(facts)
          .noneMatch(
              fact -> java.util.Set.of("bare", "wrong", "custom").contains(fact.toolCallId()));
      assertThat(facts)
          .filteredOn(
              fact -> fact.toolCallId().equals("conflict") && fact.phase().equals("result_report"))
          .hasSize(2)
          .allSatisfy(
              fact -> {
                assertThat(fact.reason()).isEqualTo("conflicting_report");
                assertThat(fact.reportedStatus()).isEmpty();
              });
      assertThat(facts)
          .filteredOn(fact -> fact.toolCallId().equals("duplicate"))
          .hasSize(2)
          .allSatisfy(fact -> assertThat(fact.reason()).isEqualTo("conflicting_tool_identity"));
      assertThat(facts)
          .filteredOn(fact -> fact.toolCallId().equals("bad"))
          .singleElement()
          .satisfies(
              fact -> {
                assertThat(fact.reason()).isEqualTo("invalid_target");
                assertThat(fact.targetId()).isEmpty();
              });
      assertThat(facts)
          .filteredOn(fact -> fact.toolCallId().equals("missing"))
          .singleElement()
          .satisfies(fact -> assertThat(fact.phase()).isEqualTo("declaration"));
      assertThat(facts)
          .filteredOn(
              fact -> fact.toolCallId().equals("namespace") && fact.phase().equals("result_report"))
          .singleElement()
          .satisfies(fact -> assertThat(fact.reason()).isEqualTo("conflicting_report"));
      assertThat(facts)
          .filteredOn(
              fact -> fact.toolCallId().equals("error") && fact.phase().equals("result_report"))
          .singleElement()
          .satisfies(
              fact -> {
                assertThat(fact.reason()).isEqualTo("explicit_error");
                assertThat(fact.reportedStatus()).isEmpty();
              });
    }
  }

  @Test
  void nonTextInputItemsKeepFactsAndTextErrorsDoNotInventAnErrorReport() throws Exception {
    String args =
        """
        {"target":"11111111-1111-4111-8111-111111111111","items":[
          {"type":"image","image_url":"synthetic://image"},
          {"type":"audio","audio_url":"synthetic://audio"},
          {"type":"local_image","path":"synthetic/image.png"},
          {"type":"local_audio","path":"synthetic/audio.wav"},
          {"type":"skill","name":"synthetic","path":"synthetic/SKILL.md"},
          {"type":"mention","name":"synthetic","path":"app://synthetic"}]}
        """;
    String result =
        """
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"non-text","output":"Error: synthetic unstructured text, not a structured error receipt"}}
        """;
    try (var parsed =
        parseContentFixture(
            inputEvent("non-text", "multi_agent_v1", "function_call", args) + result)) {
      assertThat(parsed.records())
          .flatExtracting(record -> record.collaboration())
          .hasSize(2)
          .allSatisfy(
              fact -> assertThat(fact.targetId()).contains("11111111-1111-4111-8111-111111111111"))
          .filteredOn(fact -> fact.phase().equals("result_report"))
          .singleElement()
          .satisfies(
              fact -> {
                assertThat(fact.reason()).isEqualTo("report_status_unknown");
                assertThat(fact.reportedStatus()).isEmpty();
              });
    }
  }

  @Test
  void inputInvalidBodiesAndResourceLimitsNeverBecomeQueueSuccess() throws Exception {
    String target = "11111111-1111-4111-8111-111111111111";
    var bodies =
        List.of(
            "{}",
            "{\"target\":\"" + target + "\"}",
            "{\"target\":\"" + target + "\",\"message\":\" \"}",
            "{\"target\":\"" + target + "\",\"items\":[]}",
            "{\"target\":\"" + target + "\",\"items\":[{\"type\":\"unknown\"}]}",
            "{\"target\":\"" + target + "\",\"items\":[{\"type\":\"text\",\"text\":1}]}",
            "{\"target\":\""
                + target
                + "\",\"message\":\"x\",\"items\":[{\"type\":\"text\",\"text\":\"x\"}]}",
            "{\"target\":\"" + target + "\",\"message\":\"x\",\"interrupt\":\"yes\"}",
            "{\"target\":\"" + target + "\",\"message\":\"" + "x".repeat(1024 * 1024 + 1) + "\"}");
    for (int i = 0; i < bodies.size(); i++) {
      try (var parsed =
          parseContentFixture(
              inputEvent("invalid", "multi_agent_v1", "function_call", bodies.get(i))
                  + inputResult("invalid", "receipt"))) {
        var records = new java.util.ArrayList<SourceRecord>();
        try (var cursor = parsed.recordSequence().openCursor()) {
          while (cursor.hasNext()) records.add(cursor.next());
        }
        assertThat(records)
            .flatExtracting(record -> record.collaboration())
            .hasSize(2)
            .allSatisfy(
                fact -> {
                  assertThat(fact.reason())
                      .isIn("invalid_target", "invalid_input", "protocol_payload_resource_limit");
                  assertThat(fact.reportedStatus()).isEmpty();
                });
      }
    }
  }

  @Test
  void inputResultShapeAndIdentityLimitsKeepUnknownRatherThanAcceptingText() throws Exception {
    var json = new com.fasterxml.jackson.databind.ObjectMapper();
    String args = "{\"target\":\"11111111-1111-4111-8111-111111111111\",\"message\":\"synthetic\"}";
    var outputs =
        List.of(
            "{}",
            "{\"submission_id\":1}",
            "{\"submission_id\":\" \"}",
            "{\"submission_id\":\"" + "x".repeat(4097) + "\"}",
            json.writeValueAsString("x".repeat(1024 * 1024 + 1)));
    for (String output : outputs) {
      String result =
          "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"shape\",\"output\":"
              + output
              + "}}\n";
      try (var parsed =
              parseContentFixture(
                  inputEvent("shape", "multi_agent_v1", "function_call", args) + result);
          var cursor = parsed.recordSequence().openCursor()) {
        var facts =
            new java.util.ArrayList<
                com.feipi.session.browser.domain.source.SourceCollaborationEvidence>();
        while (cursor.hasNext()) facts.addAll(cursor.next().collaboration());
        assertThat(facts)
            .filteredOn(fact -> fact.phase().equals("result_report"))
            .singleElement()
            .satisfies(
                fact -> {
                  assertThat(fact.reportedStatus()).isEmpty();
                  assertThat(fact.reason())
                      .isIn(
                          "report_status_unknown",
                          "identity_resource_limit",
                          "protocol_payload_resource_limit");
                });
      }
    }
    try (var parsed =
        parseContentFixture(
            inputEvent("x".repeat(4097), "multi_agent_v1", "function_call", args))) {
      assertThat(parsed.records())
          .flatExtracting(record -> record.collaboration())
          .singleElement()
          .satisfies(fact -> assertThat(fact.reason()).isEqualTo("identity_resource_limit"));
    }
  }

  private static String inputEvent(String id, String namespace, String type, String arguments)
      throws Exception {
    var json = new com.fasterxml.jackson.databind.ObjectMapper();
    return json.writeValueAsString(
            java.util.Map.of(
                "type",
                "response_item",
                "payload",
                java.util.Map.of(
                    "type",
                    type,
                    "call_id",
                    id,
                    "name",
                    "send_input",
                    "namespace",
                    namespace,
                    "arguments",
                    json.writeValueAsString(json.readTree(arguments)))))
        + "\n";
  }

  private static String inputResult(String id, String receipt) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\""
        + id
        + "\",\"output\":{\"submission_id\":\""
        + receipt
        + "\"}}}\n";
  }

  @Test
  void structuredToolResultsKeepFullValuesWithoutChangingMessageExtraction() throws Exception {
    List<String> outputs =
        List.of(
            "{\"agent_id\":\"worker\"}",
            "{\"status\":{\"worker\":{\"completed\":\"tail report\"}}}",
            "[{\"type\":\"text\",\"text\":\"report\"},{\"opaque\":true}]",
            "{}",
            "[]",
            "42",
            "true",
            "\"already text\"",
            "\"\"",
            "null");
    StringBuilder source = new StringBuilder();
    for (int i = 0; i < outputs.size(); i++) {
      source
          .append(
              "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"")
          .append(i)
          .append("\",\"output\":")
          .append(outputs.get(i))
          .append("}}\n");
    }
    source.append(
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call_output\",\"call_id\":\"custom\",\"output\":{\"opaque\":true}}}\n");
    source.append(
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"missing\"}}\n");
    try (var parsed = parseContentFixture(source.toString())) {
      assertThat(parsed.records())
          .extracting(SourceRecord::content)
          .containsExactly(
              outputs.get(0),
              outputs.get(1),
              outputs.get(2),
              "{}",
              "[]",
              "42",
              "true",
              "already text",
              "",
              "",
              "{\"opaque\":true}",
              "");
    }
  }

  @Test
  void nestedSourceChangesInvalidateCandidateMetadataWithoutChangingParentFile() throws Exception {
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\"thread-main\",\"thread_name\":\"synthetic\"}\n");
    Path day = Files.createDirectories(tempDir.resolve("sessions/2026/11/13"));
    Path parent = day.resolve("rollout-100-thread-main.jsonl");
    Path child = day.resolve("rollout-101-thread-child.jsonl");
    Path grandchild = day.resolve("rollout-102-thread-grandchild.jsonl");
    Files.writeString(
        parent,
        """
        {"type":"session_meta","payload":{"id":"thread-main","source":"synthetic"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-parent","name":"spawn_agent"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-parent","output":{"agent_id":"thread-child"}}}
        """);
    Files.writeString(
        child,
        """
        {"type":"session_meta","payload":{"id":"thread-child","source":{"subagent":{"thread_spawn":{"parent_thread_id":"thread-main"}}}}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-child","name":"spawn_agent"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-child","output":{"agent_id":"thread-grandchild"}}}
        """);
    Files.writeString(
        grandchild,
        """
        {"type":"session_meta","payload":{"id":"thread-grandchild","source":{"subagent":{"thread_spawn":{"parent_thread_id":"thread-child"}}}}}
        """);
    Path deepest = day.resolve("rollout-103-thread-deepest.jsonl");
    Files.writeString(
        deepest,
        """
        {"type":"session_meta","payload":{"id":"thread-deepest","source":{"subagent":{"thread_spawn":{"parent_thread_id":"thread-grandchild"}}}}}
        """);
    for (int i = 0; i < 127; i++)
      Files.writeString(
          day.resolve("rollout-orphan-" + i + ".jsonl"),
          "{\"type\":\"session_meta\",\"payload\":{\"id\":\"orphan-"
              + i
              + "\",\"parent_thread_id\":\"thread-main\"}}\n");
    var before = adapter.discover(tempDir).orderedItems().getFirst();
    Files.writeString(
        deepest,
        Files.readString(deepest)
            + "{\"type\":\"event_msg\",\"payload\":{\"type\":\"synthetic\"}}\n");
    var after = adapter.discover(tempDir).orderedItems().getFirst();
    assertThat(after.fingerprint()).isEqualTo(before.fingerprint());
    assertThat(after.metadata().get("collaborationSourceFingerprint"))
        .isNotEqualTo(before.metadata().get("collaborationSourceFingerprint"));
    assertPrecision(after, "unknown", "unknown", "unknown", "unknown");
    Files.writeString(grandchild, Files.readString(grandchild) + reportedZeroUsage());
    var reported = adapter.discover(tempDir).orderedItems().getFirst();
    assertPrecision(reported, "mixed", "mixed", "mixed", "mixed");
  }

  @Test
  void explicitNestedDelegationIncludesGrandchildWithoutMergingSharedPrefixes() throws Exception {
    writeChildRollout("worker-shared-002", "worker-shared-001", "/root/a/b", true);
    writeChildRollout("worker-shared-001", "parent", "/root/a", true);
    Path child = tempDir.resolve("rollout-worker-shared-001.jsonl");
    Files.writeString(
        child,
        Files.readString(child)
            + """
            {"type":"response_item","payload":{"type":"function_call","call_id":"nested-spawn","name":"spawn_agent"}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"nested-spawn","output":{"agent_id":"worker-shared-002"}}}
            """);
    try (var parsed =
        parseContentFixture(
            """
            {"type":"session_meta","payload":{"id":"parent"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"root-spawn","name":"spawn_agent"}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"root-spawn","output":{"agent_id":"worker-shared-001"}}}
            """)) {
      assertThat(parsed.records().stream().filter(r -> "assistant".equals(r.eventType())))
          .anySatisfy(
              r -> {
                assertThat(r.relation().subagentId()).contains("worker-shared-002");
                assertThat(r.relation().parentThreadId()).contains("worker-shared-001");
                assertThat(r.relation().parentToolCallId()).contains("nested-spawn");
              });
    }
  }

  @Test
  void explicitExecutorObservationsPreserveZeroAndRejectCoercionAndOverflow() throws Exception {
    var durations =
        List.of(
            "{\"secs\":2,\"nanos\":1}",
            "{\"secs\":0,\"nanos\":0}",
            "null",
            "{\"secs\":-1,\"nanos\":0}",
            "{\"secs\":0,\"nanos\":1000000000}",
            "{\"secs\":1.5,\"nanos\":0}",
            "{\"secs\":9223372036854775807,\"nanos\":0}",
            "{\"secs\":\"2\",\"nanos\":0}",
            "{\"secs\":0}");
    for (int index = 0; index < durations.size(); index++) {
      try (var parsed =
          parseContentFixture(
              """
              {"timestamp":"2026-01-01T00:00:00Z","type":"event_msg","payload":{"type":"exec_command_end","call_id":"tool","duration":%s,"exit_code":0,"status":"completed","process_id":"123","stdout":"Wall time: 99 seconds"}}
              """
                  .formatted(durations.get(index)))) {
        var record = parsed.records().getFirst();
        var value = record.toolObservation().orElseThrow();
        assertThat(value.toolCallId()).isEqualTo("tool");
        assertThat(value.exitCode()).isZero();
        assertThat(value.status()).isEqualTo("completed");
        assertThat(value.processId()).isEqualTo("123");
        assertThat(value.source()).isEqualTo("codex:exec_command_end#event[0]");
        assertThat(record.toolCalls()).isEmpty();
        assertThat(record.toolUseId()).isEmpty();
        assertThat(record.content()).isEmpty();
        assertThat(record.timing().durationMs()).isEmpty();
        if (index < 2) {
          assertThat(value.durationNanos()).isEqualTo(index == 0 ? 2_000_000_001L : 0L);
          assertThat(value.issue()).isNull();
        } else {
          assertThat(value.durationNanos()).isNull();
          if (index > 2) assertThat(value.issue()).isNotBlank();
        }
      }
    }
  }

  @Test
  void completeAdjacentRepresentationMirrorsHaveOneSourceInputAndCall() throws IOException {
    String event =
        """
        {"type":"event_msg","timestamp":"2026-11-05T10:00:01Z","payload":{"type":"user_message","message":"p"}}
        {"type":"event_msg","timestamp":"2026-11-05T10:00:02Z","payload":{"type":"agent_message","message":"a"}}
        """;
    String response =
        """
        {"type":"response_item","timestamp":"2026-11-05T10:00:01Z","payload":{"type":"message","role":"user","content":"p"}}
        {"type":"response_item","timestamp":"2026-11-05T10:00:02Z","payload":{"type":"message","role":"assistant","content":"a"}}
        """;
    for (String content : List.of(event + response, response + event)) {
      SourceResult.Success success = parseContentFixture(content);
      assertBodyRecords(success, "p", "a");
      assertUsageFrames(success, 1, 0, 0, 0);
      assertThat(success.candidateCount()).isEqualTo(4);
      assertThat(success.records().stream().filter(record -> "user".equals(record.eventType())))
          .hasSize(1);
    }
    String withoutTimes =
        (event + response)
            .replace("\"timestamp\":\"2026-11-05T10:00:01Z\",", "")
            .replace("\"timestamp\":\"2026-11-05T10:00:02Z\",", "");
    SourceResult.Success unknownIdentity = parseContentFixture(withoutTimes);
    assertBodyRecords(unknownIdentity, "p", "a", "p", "a");
    assertUsageFrames(unknownIdentity, 2, 0, 0, 0);
    SourceResult.Success explicitIdentity =
        parseContentFixture(
            withoutTimes.replace("\"payload\":{", "\"payload\":{\"turn_id\":\"same-turn\","));
    assertBodyRecords(explicitIdentity, "p", "a");
    assertUsageFrames(explicitIdentity, 1, 0, 0, 0);
    SourceResult.Success separate =
        parseContentFixture(
            event.replace("\"payload\":{", "\"payload\":{\"turn_id\":\"first\",")
                + response.replace("\"payload\":{", "\"payload\":{\"turn_id\":\"second\","));
    assertBodyRecords(separate, "p", "a", "p", "a");
    assertUsageFrames(separate, 2, 0, 0, 0);
    SourceResult.Success taskBoundary =
        parseContentFixture(
            event
                + "{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\",\"turn_id\":\"second\"}}\n"
                + response);
    assertBodyRecords(taskBoundary, "p", "a", "p", "a");
    assertUsageFrames(taskBoundary, 2, 0, 0, 0);
  }

  @Test
  void trailingEmptyResponseDoesNotSuppressEarlierEventBody() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"event_msg","payload":{"type":"user_message","message":"p"}}
            {"type":"event_msg","payload":{"type":"agent_message","message":"valid answer"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":[]}}
            """);
    assertBodyRecords(success, "p", "valid answer");
    assertUsageFrames(success, 1, 0, 0, 0);
  }

  @Test
  void measuredResponseDoesNotConsumeNextUnmeteredInput() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":"p1"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"a1"}}
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"output_tokens":2}}}}
            {"type":"response_item","payload":{"type":"message","role":"user","content":"p2"}}
            {"type":"event_msg","payload":{"type":"agent_message","message":"a2"}}
            """);
    assertBodyRecords(success, "p1", "a1", "p2", "a2");
    assertUsageFrames(success, 2, 10, 0, 2);
  }

  @Test
  void responseUserStartsLocalFallbackSegment() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":"p1"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"a1"}}
            {"type":"response_item","payload":{"type":"message","role":"user","content":"p2"}}
            {"type":"event_msg","payload":{"type":"agent_message","message":"a2"}}
            """);
    assertBodyRecords(success, "p1", "a1", "p2", "a2");
    assertThat(success.records().stream().filter(record -> "assistant".equals(record.eventType())))
        .hasSize(2);
  }

  @Test
  void reverseUserRepresentationsShareOneInputSegment() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":"p1"}}
            {"type":"event_msg","payload":{"type":"user_message","message":"p1"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"a1"}}
            """);
    assertBodyRecords(success, "p1", "a1");
    assertThat(success.records().stream().filter(record -> "user".equals(record.eventType())))
        .hasSize(1);
  }

  @Test
  void emptyResponseAndCommentaryDoNotHideDifferentFinalBody() throws IOException {
    for (String response : List.of("[]", "\"commentary\"")) {
      SourceResult.Success success =
          parseContentFixture(
              """
              {"type":"event_msg","payload":{"type":"user_message","message":"p"}}
              {"type":"response_item","payload":{"type":"message","role":"assistant","content":%s}}
              {"type":"event_msg","payload":{"type":"agent_message","message":"final answer"}}
              """
                  .formatted(response));
      assertThat(
              success.records().stream()
                  .filter(record -> !"event_msg".equals(record.eventType()))
                  .map(SourceRecord::content))
          .contains("p", "final answer");
      assertThat(
              success.records().stream().filter(record -> "assistant".equals(record.eventType())))
          .hasSize(1);
    }
  }

  @Test
  void identicalBodiesAcrossResponseInputBoundariesRemainSeparate() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":"same prompt"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"same answer"}}
            {"type":"response_item","payload":{"type":"message","role":"user","content":"same prompt"}}
            {"type":"event_msg","payload":{"type":"agent_message","message":"same answer"}}
            """);
    assertBodyRecords(success, "same prompt", "same answer", "same prompt", "same answer");
  }

  private static void assertBodyRecords(SourceResult.Success success, String... expected) {
    assertThat(
            success.records().stream()
                .filter(record -> !"event_msg".equals(record.eventType()))
                .map(SourceRecord::content)
                .filter(text -> !text.isBlank()))
        .containsExactly(expected);
  }

  @Test
  void mixedRepresentationsPreserveLocallyMissingMessages() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"event_msg","payload":{"type":"user_message","message":"first prompt"}}
            {"type":"response_item","payload":{"type":"message","role":"user","content":"first prompt"}}
            {"type":"event_msg","payload":{"type":"agent_message","message":"first answer"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"first answer"}}
            {"type":"event_msg","payload":{"type":"user_message","message":"second prompt"}}
            {"type":"event_msg","payload":{"type":"agent_message","message":"second answer"}}
            """);
    assertThat(
            success.records().stream()
                .filter(record -> !"event_msg".equals(record.eventType()))
                .map(record -> record.content())
                .filter(text -> !text.isBlank()))
        .containsExactly("first prompt", "first answer", "second prompt", "second answer");
  }

  @Test
  void responseOnlyMessagesDoNotUseSubtypeAsTurnIdentity() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":"first"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"answer one"}}
            {"type":"response_item","payload":{"type":"message","role":"user","content":"second"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"answer two"}}
            """);
    assertThat(success.records()).allSatisfy(record -> assertThat(record.turnId()).isEmpty());
  }

  @Test
  @DisplayName("legacy counter 漏过一个已测现代响应后仍可逐响应镜像，不污染完整现代证据")
  void legacyCounterOffsetDoesNotMakeConservedModernUsageUnknown() throws IOException {
    assertConservedModernMirror(divergentLegacyCounterFixture(false));
  }

  @Test
  @DisplayName("重发的展示 turn_context 不能推翻完整 last usage 与 counter 增量镜像证据")
  void displayTurnContextCannotInvalidateProvenLegacyCounterMirrors() throws IOException {
    assertConservedModernMirror(divergentLegacyCounterFixture(true));
  }

  @Test
  @DisplayName("落后 counter 的增量与 last usage 不一致时仍保 unknown，不笼统忽略所有落后值")
  void legacyCounterOffsetNeedsMatchingIncrementAndCompleteLastUsage() throws IOException {
    String complete = divergentLegacyCounterFixture(false);
    String wrongIncrement = complete.replace("\"input_tokens\":147", "\"input_tokens\":148");
    String incompleteLast =
        complete.replace(
            "\"last_token_usage\":{\"input_tokens\":27,\"cached_input_tokens\":6,\"cache_write_input_tokens\":0,\"output_tokens\":3}",
            "\"last_token_usage\":{\"input_tokens\":27,\"cached_input_tokens\":6,\"output_tokens\":3}");

    for (String content : List.of(wrongIncrement, incompleteLast)) {
      SourceResult.Success success = parseContentFixture(content);
      assertUsageFrames(success, 4, 118, 136, 24);
      assertThat(success.diagnostics())
          .extracting(SourceDiagnostic::code)
          .contains("TOKEN_USAGE_AMBIGUOUS");
      assertThat(discoverContentFixture(content).metadata())
          .containsEntry("tokenContainsUnknown", "true");
    }
  }

  @Test
  @DisplayName("现代线程累计本身有未计历史缺口时不能用 counter offset 清除 unknown")
  void legacyCounterMirrorDoesNotHideUncoveredModernThreadHistory() throws IOException {
    String content =
        turnContext("synthetic-response-turn")
            + mixedModernUsage("coverage-first", "synthetic-response-turn", 120, 50, 9, 120, 50, 9)
            + mixedLegacySnapshot(120, 50, 9, 120, 50, 9)
            + mixedModernUsage("coverage-gap", "synthetic-response-turn", 64, 60, 7, 200, 110, 16)
            + mixedLegacySnapshot(120, 50, 9, 0, 0, 0)
            + mixedModernUsage("coverage-next", "synthetic-response-turn", 27, 6, 3, 227, 116, 19)
            + mixedLegacySnapshot(147, 56, 12, 27, 6, 3);
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 3, 95, 116, 19);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOKEN_USAGE_AMBIGUOUS");
    assertThat(discoverContentFixture(content).metadata())
        .containsEntry("tokenContainsUnknown", "true");
  }

  private void assertConservedModernMirror(String content) throws IOException {
    SourceResult.Success success = parseContentFixture(content);
    assertUsageFrames(success, 4, 118, 136, 24);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .doesNotContain("TOKEN_USAGE_AMBIGUOUS", "TOKEN_COUNTER_RESET");
    Candidate candidate = discoverContentFixture(content);
    assertPrecision(
        candidate,
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "provider_reported");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnknown", "false")
        .containsEntry("tokenContainsUnavailable", "false")
        .containsEntry("tokenContainsEstimated", "false");
  }

  private static String divergentLegacyCounterFixture(boolean conflictingContext) {
    String owner = "synthetic-response-turn";
    String context = conflictingContext ? "synthetic-display-context" : owner;
    return turnContext(owner)
        + mixedModernUsage("counter-first", owner, 120, 50, 9, 120, 50, 9)
        + mixedLegacySnapshot(120, 50, 9, 120, 50, 9)
        + mixedModernUsage("counter-omitted", owner, 64, 60, 7, 184, 110, 16)
        + turnContext(context)
        + mixedLegacySnapshot(120, 50, 9, 0, 0, 0)
        + mixedModernUsage("counter-next", owner, 27, 6, 3, 211, 116, 19)
        + mixedLegacySnapshot(147, 56, 12, 27, 6, 3)
        + mixedModernUsage("counter-last", owner, 43, 20, 5, 254, 136, 24)
        + mixedLegacySnapshot(190, 76, 17, 43, 20, 5);
  }

  private static String mixedLegacySnapshot(
      long input, long read, long output, long lastInput, long lastRead, long lastOutput) {
    return """
    {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":%d,"cached_input_tokens":%d,"cache_write_input_tokens":0,"output_tokens":%d},"last_token_usage":{"input_tokens":%d,"cached_input_tokens":%d,"cache_write_input_tokens":0,"output_tokens":%d}}}}
    """
        .formatted(input, read, output, lastInput, lastRead, lastOutput);
  }

  @Test
  @DisplayName("完整累计锚点保留 legacy 前缀，同轮提前和延后镜像及重复 response 不双计")
  void mixedHistoryPreservesLegacyPrefixWithoutCountingModernMirrorsTwice() throws IOException {
    String modern = mixedModernUsage("modern-one", "modern-turn", 150, 140, 30, 250, 180, 50);
    String content =
        turnContext("legacy-turn")
            + mixedLegacyUsage(100, 40, 20)
            + turnContext("modern-turn")
            + mixedLegacyUsage(250, 180, 50)
            + modern
            + mixedLegacyUsage(250, 180, 50)
            + modern;
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 2, 70, 180, 50);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .doesNotContain("TOKEN_USAGE_AMBIGUOUS");
    assertPrecision(
        discoverContentFixture(content),
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "provider_reported");
  }

  @Test
  @DisplayName("legacy 尾部从最后 modern 线程累计锚点差分，而非重新计入现代用量")
  void mixedHistoryPreservesLegacyTailAfterModernAnchor() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            turnContext("legacy-prefix")
                + mixedLegacyUsage(100, 40, 20)
                + turnContext("modern-turn")
                + mixedModernUsage("modern-one", "modern-turn", 150, 140, 30, 250, 180, 50)
                + turnContext("legacy-tail")
                + mixedLegacyUsage(330, 230, 70));

    assertUsageFrames(success, 3, 100, 230, 70);
    assertThat(success.records().stream().filter(r -> "assistant".equals(r.eventType())))
        .last()
        .satisfies(
            record -> {
              assertThat(record.usage().inputTokens()).isEqualTo(30);
              assertThat(record.usage().cacheReadInputTokens()).isEqualTo(50);
              assertThat(record.usage().outputTokens()).isEqualTo(20);
            });
  }

  @Test
  @DisplayName("完整 modern reset 锚点重新建立基准，同轮 legacy 尾部须与 last usage 精确对齐")
  void mixedHistoryUsesExplicitModernResetAnchorForFollowingLegacyDelta() throws IOException {
    String content =
        turnContext("first-turn")
            + mixedModernUsage("first", "first-turn", 100, 40, 20, 100, 40, 20)
            + turnContext("reset-turn")
            + mixedModernUsage("reset", "reset-turn", 20, 5, 4, 20, 5, 4)
            + """
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":30,"cached_input_tokens":8,"cache_write_input_tokens":0,"output_tokens":6},"last_token_usage":{"input_tokens":10,"cached_input_tokens":3,"cache_write_input_tokens":0,"output_tokens":2}}}}
            """;
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 3, 82, 48, 26);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOKEN_COUNTER_RESET")
        .doesNotContain("TOKEN_USAGE_AMBIGUOUS");
    assertThat(discoverContentFixture(content).metadata())
        .containsEntry("tokenContainsUnknown", "false");
  }

  @Test
  @DisplayName("无 modern reset 锚点的累计下降不夹成实测零，歧义显式保留 unknown")
  void mixedHistoryDoesNotGuessOwnershipAcrossUnanchoredCounterReset() throws IOException {
    String content =
        turnContext("modern-turn")
            + mixedModernUsage("modern-one", "modern-turn", 100, 40, 20, 100, 40, 20)
            + turnContext("unanchored-reset")
            + mixedLegacyUsage(20, 5, 4);
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 1, 60, 40, 20);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOKEN_USAGE_AMBIGUOUS");
    Candidate candidate = discoverContentFixture(content);
    assertPrecision(candidate, "mixed", "mixed", "mixed", "mixed");
    assertThat(candidate.metadata()).containsEntry("tokenContainsUnknown", "true");
  }

  @Test
  @DisplayName("没有 turn 或线程累计锚点时不能把前置快照猜为 legacy-only 历史")
  void mixedHistoryWithoutOwnershipEvidenceIsDiagnosedInsteadOfInventingCalls() throws IOException {
    String content =
        mixedLegacyUsage(100, 40, 20)
            + """
            {"type":"token_usage_record","payload":{"response_id":"unanchored","usage":{"input_tokens":150,"cached_input_tokens":140,"cache_write_input_tokens":0,"output_tokens":30}}}
            """;
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 1, 10, 140, 30);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOKEN_USAGE_AMBIGUOUS");
    assertThat(discoverContentFixture(content).metadata())
        .containsEntry("tokenContainsUnknown", "true");
  }

  @Test
  @DisplayName("modern 缺 turn_id 不能反推它一定不属于已有 legacy turn")
  void mixedHistoryDoesNotInventDisjointTurnOwnershipFromMissingModernTurnId() throws IOException {
    String content =
        turnContext("legacy-turn")
            + mixedLegacyUsage(100, 40, 20)
            + """
            {"type":"token_usage_record","payload":{"response_id":"missing-turn","usage":{"input_tokens":150,"cached_input_tokens":140,"cache_write_input_tokens":0,"output_tokens":30}}}
            """;
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 1, 10, 140, 30);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOKEN_USAGE_AMBIGUOUS");
  }

  @Test
  @DisplayName("legacy 独立缓存字段保持 fresh 语义，非零 write 与现代累计锚点四段守恒")
  void mixedHistoryRetainsLegacyIndependentCacheFieldSemantics() throws IOException {
    String content =
        turnContext("legacy-turn")
            + """
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":60,"cache_read_input_tokens":40,"cache_creation_input_tokens":10,"output_tokens":20}}}}
            """
            + turnContext("modern-turn")
            + """
            {"type":"token_usage_record","payload":{"response_id":"modern-write","turn_id":"modern-turn","usage":{"input_tokens":80,"cached_input_tokens":50,"cache_write_input_tokens":5,"output_tokens":10},"thread_token_usage":{"input_tokens":190,"cached_input_tokens":90,"cache_write_input_tokens":15,"output_tokens":30}}}
            """;
    SourceResult.Success success = parseContentFixture(content);
    List<SourceRecord> calls =
        success.records().stream()
            .filter(record -> "assistant".equals(record.eventType()))
            .toList();

    assertThat(calls).hasSize(2);
    assertThat(calls).extracting(record -> record.usage().inputTokens()).containsExactly(60L, 25L);
    assertThat(calls)
        .extracting(record -> record.usage().cacheReadInputTokens())
        .containsExactly(40L, 50L);
    assertThat(calls)
        .extracting(record -> record.usage().cacheCreationInputTokens())
        .containsExactly(10L, 5L);
    assertThat(calls.stream().mapToLong(record -> record.usage().total()).sum()).isEqualTo(220);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .doesNotContain("TOKEN_USAGE_AMBIGUOUS");
  }

  @Test
  @DisplayName("snapshot 与 modern 区间部分重叠或归属轮次冲突时不猜 residual call")
  void mixedHistoryRejectsPartialOverlapAndCrossTurnMirrorGuessing() throws IOException {
    String content =
        turnContext("legacy-turn")
            + mixedLegacyUsage(200, 150, 40)
            + mixedLegacyUsage(250, 180, 50)
            + turnContext("modern-turn")
            + mixedModernUsage("modern-one", "modern-turn", 150, 140, 30, 250, 180, 50);
    SourceResult.Success success = parseContentFixture(content);

    assertUsageFrames(success, 1, 10, 140, 30);
    assertThat(success.diagnostics().stream().filter(d -> "TOKEN_USAGE_AMBIGUOUS".equals(d.code())))
        .hasSize(2);
  }

  @Test
  @DisplayName("混合历史已选择 legacy 前缀的缺失分段参与 precision，而不是被现代覆盖")
  void mixedHistoryProvenanceIncludesSelectedLegacyPrefix() throws IOException {
    String content =
        turnContext("legacy-turn")
            + """
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}}
            """
            + turnContext("modern-turn")
            + mixedModernUsage("modern-one", "modern-turn", 150, 140, 30, 250, 180, 50);

    assertUsageFrames(parseContentFixture(content), 2, 70, 180, 50);
    Candidate candidate = discoverContentFixture(content);
    assertPrecision(candidate, "mixed", "provider_reported", "mixed", "provider_reported");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnavailable", "true")
        .containsEntry("tokenContainsUnknown", "false");
  }

  private static String turnContext(String turn) {
    return "{\"type\":\"turn_context\",\"payload\":{\"turn_id\":\"" + turn + "\"}}\n";
  }

  private static String mixedLegacyUsage(long input, long read, long output) {
    return """
    {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":%d,"cached_input_tokens":%d,"cache_write_input_tokens":0,"output_tokens":%d}}}}
    """
        .formatted(input, read, output);
  }

  private static String mixedModernUsage(
      String id,
      String turn,
      long input,
      long read,
      long output,
      long totalInput,
      long totalRead,
      long totalOutput) {
    return """
    {"type":"token_usage_record","payload":{"response_id":"%s","turn_id":"%s","usage":{"input_tokens":%d,"cached_input_tokens":%d,"cache_write_input_tokens":0,"output_tokens":%d},"thread_token_usage":{"input_tokens":%d,"cached_input_tokens":%d,"cache_write_input_tokens":0,"output_tokens":%d}}}
    """
        .formatted(id, turn, input, read, output, totalInput, totalRead, totalOutput);
  }

  private static void assertUsageFrames(
      SourceResult.Success success, int frames, long input, long read, long output) {
    List<SourceRecord> calls =
        success.records().stream()
            .filter(record -> "assistant".equals(record.eventType()))
            .toList();
    assertThat(calls).hasSize(frames);
    assertThat(calls.stream().mapToLong(record -> record.usage().inputTokens()).sum())
        .isEqualTo(input);
    assertThat(calls.stream().mapToLong(record -> record.usage().cacheReadInputTokens()).sum())
        .isEqualTo(read);
    assertThat(calls.stream().mapToLong(record -> record.usage().outputTokens()).sum())
        .isEqualTo(output);
    assertThat(calls.stream().mapToLong(record -> record.usage().total()).sum())
        .isEqualTo(input + read + output);
  }

  @Test
  @DisplayName("普通和自定义工具保留各自输入原文或 JSON 结构，缺失不猜配")
  void toolInputsPreserveProviderTextAndStructuresWithoutGuessing() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"function_call","call_id":"function-text","name":"exec","arguments":"  {\\"command\\":\\"echo synthetic\\"}  "}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"custom-text","name":"exec","input":"  echo synthetic\\nnext  "}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"function-object","name":"exec","arguments":{"command":"echo synthetic","flags":["-n"],"enabled":false}}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"custom-array","name":"exec","input":["first",{"line":2}]}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"function-empty","name":"exec","arguments":{}}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"custom-empty","name":"exec","input":{}}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"function-missing","name":"exec","input":"not arguments"}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"custom-missing","name":"exec","arguments":"not input"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"function-null","name":"exec","arguments":null}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"custom-null","name":"exec","input":null}}
            """);

    assertThat(success.records()).allSatisfy(r -> assertThat(r.eventType()).isEqualTo("tool_use"));
    assertThat(success.records().stream().flatMap(r -> r.toolCalls().stream()))
        .extracting(SourceToolCall::input)
        .containsExactly(
            "  {\"command\":\"echo synthetic\"}  ",
            "  echo synthetic\nnext  ",
            "{\"command\":\"echo synthetic\",\"flags\":[\"-n\"],\"enabled\":false}",
            "[\"first\",{\"line\":2}]",
            "{}",
            "{}",
            "",
            "",
            "",
            "");
  }

  @Test
  @DisplayName("主和 child 工具同名时输入仍按源声明及归属分离")
  void mainAndChildToolInputsStayWithTheirOwnDeclarations() throws IOException {
    Files.writeString(
        tempDir.resolve("rollout-child-input.jsonl"),
        """
        {"type":"session_meta","payload":{"id":"child-input","parent_thread_id":"parent-input"}}
        {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"child-tool","name":"exec","input":"child synthetic input"}}
        {"type":"token_usage_record","payload":{"response_id":"child-response","usage":{"input_tokens":10,"output_tokens":1}}}
        """);
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"session_meta","payload":{"id":"parent-input"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-input","name":"spawn_agent","arguments":{"task":"synthetic child"}}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-input","output":{"agent_id":"child-input"}}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"main-tool","name":"exec","arguments":"main synthetic input"}}
            {"type":"token_usage_record","payload":{"response_id":"main-response","usage":{"input_tokens":20,"output_tokens":2}}}
            """);

    List<SourceRecord> tools =
        success.records().stream().filter(record -> "tool_use".equals(record.eventType())).toList();
    assertThat(tools).hasSize(3);
    assertThat(tools.get(0).toolCalls())
        .singleElement()
        .satisfies(
            tool -> {
              assertThat(tool.toolCallId()).isEqualTo("spawn-input");
              assertThat(tool.input()).isEqualTo("{\"task\":\"synthetic child\"}");
            });
    assertThat(tools.get(1).relation().subagentId()).isEmpty();
    assertThat(tools.get(1).toolCalls())
        .singleElement()
        .satisfies(
            tool -> {
              assertThat(tool.toolCallId()).isEqualTo("main-tool");
              assertThat(tool.input()).isEqualTo("main synthetic input");
            });
    assertThat(tools.get(2).relation().subagentId()).contains("child-input");
    assertThat(tools.get(2).toolCalls())
        .singleElement()
        .satisfies(
            tool -> {
              assertThat(tool.toolCallId()).isEqualTo("child-tool");
              assertThat(tool.input()).isEqualTo("child synthetic input");
            });
  }

  @Test
  @DisplayName("现代 input 包含缓存读写，分段合计必须保持 provider total")
  void modernCacheWritesAreSeparatedFromInclusiveInput() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"token_usage_record","payload":{"response_id":"response-write","usage":{"input_tokens":100,"cached_input_tokens":40,"cache_write_input_tokens":10,"output_tokens":20,"reasoning_output_tokens":5,"total_tokens":120}}}
            """);

    assertThat(success.records())
        .singleElement()
        .satisfies(
            record -> {
              assertThat(record.usage().inputTokens()).isEqualTo(50);
              assertThat(record.usage().cacheReadInputTokens()).isEqualTo(40);
              assertThat(record.usage().cacheCreationInputTokens()).isEqualTo(10);
              assertThat(record.usage().outputTokens()).isEqualTo(20);
              assertThat(record.usage().total()).isEqualTo(120);
            });
  }

  @Test
  @DisplayName("真实零字段为 provider_reported，旧镜像缺字段不污染现代精度")
  void discoveredPrecisionPreservesReportedZeroAndIgnoresLegacyMirrors() throws IOException {
    Candidate candidate =
        discoverContentFixture(
            reportedZeroUsage()
                + """
                {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":0,"output_tokens":0}}}}
                {"type":"token_usage_record","payload":{"response_id":"zero","usage":{"input_tokens":0,"output_tokens":0}}}
                """);

    assertPrecision(
        candidate,
        "provider_reported",
        "provider_reported",
        "provider_reported",
        "provider_reported");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnknown", "false")
        .containsEntry("tokenContainsUnavailable", "false")
        .containsEntry("tokenContainsEstimated", "false");
  }

  @Test
  @DisplayName("usage 缺失分段为 unavailable 而非计量零")
  void discoveredPrecisionDistinguishesAbsentUsageComponents() throws IOException {
    Candidate candidate =
        discoverContentFixture(
            """
            {"type":"token_usage_record","payload":{"response_id":"partial","usage":{"input_tokens":0,"output_tokens":0}}}
            """);

    assertPrecision(candidate, "unavailable", "unavailable", "unavailable", "provider_reported");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnavailable", "true")
        .containsEntry("tokenContainsUnknown", "false");
  }

  @Test
  @DisplayName("多响应缺段精度为 mixed 并保留 unavailable 覆盖")
  void discoveredPrecisionAggregatesMissingComponentsAcrossResponses() throws IOException {
    Candidate candidate =
        discoverContentFixture(
            reportedZeroUsage()
                + """
                {"type":"token_usage_record","payload":{"response_id":"partial","usage":{"input_tokens":10,"output_tokens":5}}}
                """);

    assertPrecision(candidate, "mixed", "mixed", "mixed", "provider_reported");
    assertThat(candidate.metadata()).containsEntry("tokenContainsUnavailable", "true");
  }

  @Test
  @DisplayName("没有原始计量时四段精度均 unknown")
  void discoveredPrecisionWithoutMeasurementRemainsUnknown() throws IOException {
    Candidate candidate =
        discoverContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"synthetic"}}
            """);

    assertPrecision(candidate, "unknown", "unknown", "unknown", "unknown");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnknown", "true")
        .containsEntry("tokenContainsUnavailable", "false");
  }

  @Test
  @DisplayName("旧累计 usage 仍按原始字段存在性保留精度")
  void discoveredLegacyPrecisionPreservesMissingCacheWrite() throws IOException {
    Candidate candidate =
        discoverContentFixture(
            """
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}}
            """);

    assertPrecision(
        candidate, "provider_reported", "provider_reported", "unavailable", "provider_reported");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnavailable", "true")
        .containsEntry("tokenContainsUnknown", "false");
  }

  @Test
  @DisplayName("父 usage 与无计量 child 聚合为 mixed，并保留 unknown 覆盖")
  void discoveredPrecisionIncludesOnlyMatchedChildMeasurements() throws IOException {
    Path day = tempDir.resolve("sessions/2026/10/01");
    Files.createDirectories(day);
    Files.writeString(
        day.resolve("rollout-child-unknown.jsonl"),
        """
        {"type":"session_meta","payload":{"id":"child-unknown","parent_thread_id":"precision","agent_path":"/root/task"}}
        {"type":"response_item","payload":{"type":"message","role":"assistant","content":"synthetic"}}
        """);
    Candidate candidate =
        discoverContentFixture(
            """
            {"type":"session_meta","payload":{"id":"precision"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"spawn","name":"spawn_agent"}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn","output":{"task_name":"/root/task"}}}
            """
                + reportedZeroUsage());

    assertPrecision(candidate, "mixed", "mixed", "mixed", "mixed");
    assertThat(candidate.metadata())
        .containsEntry("tokenContainsUnknown", "true")
        .containsEntry("tokenContainsUnavailable", "false");
  }

  private Candidate discoverContentFixture(String content) throws IOException {
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\"precision\",\"thread_name\":\"Synthetic\"}\n");
    Path day = tempDir.resolve("sessions/2026/10/01");
    Files.createDirectories(day);
    Files.writeString(day.resolve("rollout-precision.jsonl"), content);
    return adapter.discover(tempDir).orderedItems().getFirst();
  }

  private static void assertPrecision(
      Candidate candidate, String input, String read, String write, String output) {
    assertThat(candidate.metadata())
        .containsEntry("freshInputTokenPrecision", input)
        .containsEntry("cacheReadTokenPrecision", read)
        .containsEntry("cacheWriteTokenPrecision", write)
        .containsEntry("outputTokenPrecision", output)
        .containsKey("tokenEstimationMethod");
  }

  private static String reportedZeroUsage() {
    return """
    {"type":"token_usage_record","payload":{"response_id":"zero","usage":{"input_tokens":0,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":0}}}
    """;
  }

  @Test
  @DisplayName("现代逐响应 usage 优先于落后的累计镜像并按 response_id 去重")
  void modernUsageRecordsReplaceLaggingCumulativeMirrors() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"turn_context","payload":{"model":"gpt-synthetic"}}
            {"type":"response_item","payload":{"type":"reasoning"}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"tool-a","name":"exec"}}
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}}
            {"type":"token_usage_record","timestamp":"2026-10-01T10:00:00Z","payload":{"response_id":"response-a","turn_id":"turn-a","usage":{"input_tokens":100,"cached_input_tokens":40,"cache_write_input_tokens":0,"output_tokens":20,"reasoning_output_tokens":5,"total_tokens":120}}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"tool-b","name":"exec"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"done"}]}}
            {"type":"token_usage_record","payload":{"response_id":"response-b","turn_id":"turn-a","usage":{"input_tokens":150,"cached_input_tokens":140,"output_tokens":30,"reasoning_output_tokens":7,"total_tokens":180}}}
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}}
            {"type":"token_usage_record","payload":{"response_id":"response-b","usage":{"input_tokens":150,"cached_input_tokens":140,"output_tokens":30,"total_tokens":180}}}
            """);

    List<SourceRecord> calls =
        success.records().stream().filter(r -> "assistant".equals(r.eventType())).toList();
    assertThat(calls).hasSize(2);
    assertThat(calls)
        .extracting(r -> r.callId().orElseThrow())
        .containsExactly("token_usage_record:response-a", "token_usage_record:response-b");
    assertThat(calls.getFirst().model()).contains("gpt-synthetic");
    assertThat(calls.getFirst().timestamp()).contains("2026-10-01T10:00:00Z");
    assertThat(calls.getFirst().turnId()).contains("turn-a");
    assertThat(calls).extracting(r -> r.usage().inputTokens()).containsExactly(60L, 10L);
    assertThat(calls).extracting(r -> r.usage().cacheReadInputTokens()).containsExactly(40L, 140L);
    assertThat(calls).extracting(r -> r.usage().outputTokens()).containsExactly(20L, 30L);
    assertThat(success.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(300);
    assertThat(success.records().get(6).content()).isEqualTo("done");
    assertThat(success.records().get(6).eventType()).isEqualTo("response_item");
  }

  @Test
  void explicitNumericResponseIdsDoNotCollideWithUnidentifiedUsageOrdinals() throws IOException {
    var records =
        parseContentFixture(
                """
                {"type":"token_usage_record","payload":{"response_id":"1","turn_id":"same","usage":{"input_tokens":11}}}
                {"type":"token_usage_record","payload":{"turn_id":"same","usage":{"input_tokens":13}}}
                {"type":"token_usage_record","payload":{"response_id":"42","turn_id":"same","usage":{"input_tokens":17}}}
                {"type":"token_usage_record","payload":{"response_id":"42","turn_id":"same","usage":{"input_tokens":99}}}
                """)
            .records();
    var calls = records.stream().filter(r -> "assistant".equals(r.eventType())).toList();
    assertThat(calls)
        .extracting(r -> r.callId().orElseThrow())
        .containsExactly("token_usage_record:1", "token_usage_ordinal:1", "token_usage_record:42");
    assertThat(calls.stream().map(SourceRecord::locator).distinct()).hasSize(3);
    assertThat(calls).extracting(r -> r.usage().inputTokens()).containsExactly(11L, 13L, 17L);
  }

  @Test
  @DisplayName("仅现代 usage 时不把 reasoning 或 assistant 文本重复建成调用")
  void modernOnlyUsageDefinesCallsInsteadOfResponseItems() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"reasoning"}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":"answer"}}
            {"type":"token_usage_record","payload":{"response_id":"response-only","usage":{"input_tokens":70,"cached_input_tokens":50,"output_tokens":10}}}
            """);

    assertThat(eventTypes(success)).containsExactly("response_item", "response_item", "assistant");
    assertThat(success.records().getLast().usage().total()).isEqualTo(80);
    assertThat(success.records().get(1).content()).isEqualTo("answer");
  }

  @Test
  @DisplayName("旧累计 usage 文件仍差分并忽略重复镜像")
  void legacyCumulativeUsageStillProducesIndependentDeltas() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}}
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}}
            {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":230,"cached_input_tokens":140,"output_tokens":50}}}}
            """);

    List<SourceRecord> calls =
        success.records().stream().filter(r -> "assistant".equals(r.eventType())).toList();
    assertThat(calls).hasSize(2);
    assertThat(calls).extracting(r -> r.usage().inputTokens()).containsExactly(60L, 30L);
    assertThat(calls).extracting(r -> r.usage().cacheReadInputTokens()).containsExactly(40L, 100L);
    assertThat(calls).extracting(r -> r.usage().outputTokens()).containsExactly(20L, 30L);
    assertThat(success.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(280);
  }

  @Test
  @DisplayName("task_name 精确匹配同父线程完整 agent_path，子 usage 和工具均保留")
  void taskPathSpawnResultsIncludeOnlyMatchingChildRollouts() throws IOException {
    writeChildRollout("child-a", "parent", "/root/task-a", false);
    writeChildRollout("child-b", "parent", "/root/task-b", true);
    writeChildRollout("unrelated", "other-parent", "/root/task-a", false);

    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"session_meta","payload":{"id":"parent"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-a","name":"spawn_agent"}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-a","output":"{\\"task_name\\":\\"/root/task-a\\"}"}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"spawn-b","name":"spawn_agent"}}
            {"type":"response_item","payload":{"type":"custom_tool_call_output","call_id":"spawn-b","output":{"task_name":"/root/task-b"}}}
            {"type":"token_usage_record","payload":{"response_id":"parent-response","usage":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":20}}}
            """);

    List<SourceRecord> calls =
        success.records().stream().filter(r -> "assistant".equals(r.eventType())).toList();
    assertThat(calls).hasSize(3);
    assertThat(calls.get(1).relation().subagentId()).contains("child-a");
    assertThat(calls.get(1).relation().parentToolCallId()).contains("spawn-a");
    assertThat(calls.get(2).relation().subagentId()).contains("child-b");
    assertThat(calls.get(2).relation().parentToolCallId()).contains("spawn-b");
    assertThat(calls.subList(1, 3))
        .allSatisfy(
            r -> {
              assertThat(r.relation().parentThreadId()).contains("parent");
              assertThat(r.model()).contains("gpt-child");
            });
    assertThat(success.records().stream().filter(r -> "tool_use".equals(r.eventType()))).hasSize(4);
    assertThat(success.records()).noneMatch(r -> r.locator().contains("unrelated"));
    assertThat(success.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(560);
  }

  @Test
  @DisplayName("同父线程存在重复 agent_path 时诊断歧义，不按顺序选子线程")
  void ambiguousChildPathsAreDiagnosedWithoutGuessing() throws IOException {
    writeChildRollout("child-a", "parent", "/root/task", false);
    writeChildRollout("child-b", "parent", "/root/task", false);
    SourceResult.Success success = parseContentFixture(taskPathParent());

    assertThat(success.records()).hasSize(3);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("SUBAGENT_SPAWN_AMBIGUOUS");
  }

  @Test
  @DisplayName("多个 spawn 输出复用同一路径时诊断歧义而不覆盖父工具归属")
  void ambiguousSpawnPathsAreDiagnosedWithoutGuessing() throws IOException {
    writeChildRollout("child-a", "parent", "/root/task", false);
    SourceResult.Success success =
        parseContentFixture(
            taskPathParent()
                + """
                {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-again","name":"spawn_agent"}}
                {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-again","output":{"task_name":"/root/task"}}}
                """);

    assertThat(success.records()).hasSize(5);
    assertThat(success.records()).allSatisfy(r -> assertThat(r.relation().subagentId()).isEmpty());
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("SUBAGENT_SPAWN_AMBIGUOUS");
  }

  @Test
  @DisplayName("旧 agent_id spawn 输出仍把 child rollout 归属到原始子线程 ID")
  void legacyAgentIdSpawnOutputRemainsSupported() throws IOException {
    writeChildRollout("child-legacy", "parent", "/root/legacy", false);
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"session_meta","payload":{"id":"parent"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-legacy","name":"spawn_agent"}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-legacy","output":{"agent_id":"child-legacy","nickname":"Synthetic"}}}
            """);

    assertThat(success.records().stream().filter(r -> "assistant".equals(r.eventType())))
        .singleElement()
        .satisfies(
            r -> {
              assertThat(r.relation().subagentId()).contains("child-legacy");
              assertThat(r.relation().parentToolCallId()).contains("spawn-legacy");
              assertThat(r.usage().total()).isEqualTo(220);
            });
  }

  private void writeChildRollout(String id, String parent, String agentPath, boolean nested)
      throws IOException {
    String metadata =
        nested
            ? "\"source\":{\"subagent\":{\"thread_spawn\":{\"parent_thread_id\":\"%s\",\"agent_path\":\"%s\"}}}"
                .formatted(parent, agentPath)
            : "\"parent_thread_id\":\"%s\",\"agent_path\":\"%s\"".formatted(parent, agentPath);
    Files.writeString(
        tempDir.resolve("rollout-" + id + ".jsonl"),
        "{\"type\":\"session_meta\",\"payload\":{\"id\":\""
            + id
            + "\","
            + metadata
            + "}}\n"
            + """
            {"type":"turn_context","payload":{"model":"gpt-child"}}
            {"type":"response_item","payload":{"type":"function_call","call_id":"exec-%s","name":"exec"}}
            {"type":"response_item","payload":{"type":"function_call_output","call_id":"exec-%s","output":"synthetic"}}
            {"type":"token_usage_record","payload":{"response_id":"response-%s","usage":{"input_tokens":200,"cached_input_tokens":150,"output_tokens":20}}}
            """
                .formatted(id, id, id));
  }

  private static String taskPathParent() {
    return """
    {"type":"session_meta","payload":{"id":"parent"}}
    {"type":"response_item","payload":{"type":"function_call","call_id":"spawn-task","name":"spawn_agent"}}
    {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn-task","output":{"task_name":"/root/task"}}}
    """;
  }

  @Test
  @DisplayName("有 token_count 时保留响应正文而不新增 assistant 帧或用量")
  void preservesResponseContentWithoutChangingTokenFrames() throws IOException {
    SourceResult.Success success = parseContentFixture(codexRollout());

    assertThat(success.records()).hasSize(7);
    assertThat(success.records().stream().filter(r -> "assistant".equals(r.eventType())))
        .hasSize(1);
    assertThat(success.records().get(4).content()).isEqualTo("ok");
    assertThat(success.records().get(5).eventType()).isEqualTo("response_item");
    assertThat(success.records().get(5).content()).isEqualTo("done");
    assertThat(success.records().get(5).usage().total()).isZero();
    assertThat(success.records().stream().mapToLong(r -> r.usage().inputTokens()).sum())
        .isEqualTo(60);
    assertThat(success.records().stream().mapToLong(r -> r.usage().cacheReadInputTokens()).sum())
        .isEqualTo(40);
    assertThat(success.records().stream().mapToLong(r -> r.usage().outputTokens()).sum())
        .isEqualTo(20);
    assertThat(success.records().stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(120);
  }

  @Test
  @DisplayName("消息与工具正文保持空白，元数据和工具调用不作为助手正文")
  void preservesTextBlocksAndExcludesNonMessagePayloads() throws IOException {
    SourceResult.Success success =
        parseContentFixture(
            """
            {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"  ask\\n"},{"type":"input_image","text":"excluded"},{"type":"text","text":"next  "}]}}
            {"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"  reply\\n"},{"text":"end  "}]}}
            {"type":"response_item","payload":{"type":"custom_tool_call","call_id":"tool-1","name":"shell","content":"excluded"}}
            {"type":"response_item","payload":{"type":"custom_tool_call_output","call_id":"tool-1","output":[{"type":"text","text":"  result\\n"},{"type":"output_text","text":"done  "}]}}
            {"type":"response_item","payload":{"type":"message","role":"developer","content":[{"text":"excluded"}]}}
            {"type":"response_item","payload":{"type":"reasoning","content":[{"text":"excluded"}]}}
            {"type":"session_meta","payload":{"content":"excluded"}}
            """);

    assertThat(eventTypes(success))
        .containsExactly(
            "user",
            "assistant",
            "tool_use",
            "tool_result",
            "response_item",
            "assistant",
            "session_meta");
    assertThat(success.records())
        .extracting(SourceRecord::content)
        .containsExactly("  ask\nnext  ", "  reply\nend  ", "", "  result\ndone  ", "", "", "");
    assertThat(success.records()).allSatisfy(r -> assertThat(r.usage().total()).isZero());
  }

  private SourceResult.Success parseContentFixture(String content) throws IOException {
    Path rollout = tempDir.resolve("content-fixture.jsonl");
    Files.writeString(rollout, content, StandardCharsets.UTF_8);
    Candidate candidate =
        new Candidate(
            adapter.fingerprint(rollout), "codex:content-fixture", "", java.util.Map.of());
    SourceResult result = adapter.parse(candidate, null);
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    return (SourceResult.Success) result;
  }

  @Test
  @DisplayName("发现 session index 布局并解析 rollout/tool/subagent/token 语义")
  void parsesCodexRolloutSemanticsWithoutMutatingSourceRoot() throws IOException {
    String sessionId = "thread-main";

    // 写入 session_index.jsonl
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Main Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    // 创建 rollout 文件
    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(rollout, codexRollout(), StandardCharsets.UTF_8);
    FileState before = FileState.capture(rollout);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult result = adapter.parse(candidate, null);

    assertThat(result.outcome()).isEqualTo(SourceOutcome.SUCCESS);
    SourceResult.Success success = (SourceResult.Success) result;
    assertThat(success.records()).allSatisfy(r -> assertThat(r).isInstanceOf(SourceRecord.class));
    assertThat(eventTypes(success))
        .containsExactly(
            "turn_context",
            "session_meta",
            "assistant",
            "tool_use",
            "tool_result",
            "response_item",
            "unknown");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("SUBAGENT_SESSION", "UNKNOWN_BLOCK_TYPE");
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .doesNotContain("TOKEN_NO_CUMULATIVE", "TOOL_ORPHAN");
    SourceRecord tokenRecord = success.records().get(2);
    assertThat(tokenRecord.model()).contains("gpt-test");
    assertThat(tokenRecord.usage().inputTokens()).isEqualTo(60);
    assertThat(tokenRecord.usage().cacheReadInputTokens()).isEqualTo(40);
    assertThat(tokenRecord.usage().outputTokens()).isEqualTo(20);
    assertThat(tokenRecord.usage().total()).isEqualTo(120);
    assertThat(success.records().get(0).locator())
        .isEqualTo(candidate.fingerprint().locator() + "#event[0]");
    assertThat(candidate.sessionKey()).isEqualTo("codex:" + sessionId);
    // 无 threads.db 时 projectKey 为空
    assertThat(candidate.projectKey()).isEmpty();
    assertThat(FileState.capture(rollout)).isEqualTo(before);
    assertThat(adapter.fingerprint(rollout))
        .usingRecursiveComparison()
        .isEqualTo(candidate.fingerprint());
  }

  @Test
  @DisplayName("孤立 tool result 产生诊断但不丢弃 rollout")
  void orphanToolResultProducesDiagnosticButKeepsSession() throws IOException {
    String sessionId = "thread-orphan";

    // 写入 session_index.jsonl
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Orphan Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    // 创建 rollout 文件
    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(
        rollout,
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"missing\"}}\n",
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);

    assertThat(success.records()).hasSize(1);
    assertThat(success.diagnostics())
        .extracting(SourceDiagnostic::code)
        .contains("TOOL_ORPHAN_RESULT");
  }

  @Test
  @DisplayName("时间戳从顶层 event.timestamp 传递到所有 SourceRecord")
  void timestampPropagatedToAllSourceRecords() throws IOException {
    String sessionId = "thread-ts";

    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"TS Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(
        rollout,
        String.join(
            "\n",
            "{\"type\":\"turn_context\",\"timestamp\":\"2026-06-23T10:00:00Z\","
                + "\"payload\":{\"model\":\"gpt-test\"}}",
            "{\"type\":\"event_msg\",\"timestamp\":\"2026-06-23T10:00:01Z\","
                + "\"payload\":{\"type\":\"user_message\",\"content\":\"hello\"}}",
            "{\"type\":\"response_item\",\"timestamp\":\"2026-06-23T10:00:02Z\","
                + "\"payload\":{\"type\":\"function_call\",\"call_id\":\"c1\",\"name\":\"shell\"}}",
            ""),
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);

    // 后备 user 是同一源事件的内容表示，不增加原始事件计数。
    assertThat(success.candidateCount()).isEqualTo(3);
    assertThat(success.records()).hasSize(4);
    assertThat(eventTypes(success))
        .containsExactly("turn_context", "event_msg", "user", "tool_use");
    assertThat(success.records().get(0).timestamp()).hasValue("2026-06-23T10:00:00Z");
    assertThat(success.records().get(1).timestamp()).hasValue("2026-06-23T10:00:01Z");
    assertThat(success.records().get(2).timestamp()).hasValue("2026-06-23T10:00:01Z");
    assertThat(success.records().get(3).timestamp()).hasValue("2026-06-23T10:00:02Z");
    assertThat(success.records().get(2).locator()).isEqualTo(success.records().get(1).locator());
    assertThat(success.records().get(2).eventIndex()).isEqualTo(1);
    assertThat(success.records().get(2).content()).isEqualTo("hello");
  }

  @Test
  @DisplayName("event_msg 和 response_item 的 payload.type 编码到 turnId")
  void payloadSubtypeEncodedInTurnId() throws IOException {
    String sessionId = "thread-turnid";

    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"TurnId Thread\",\"updated_at\":\"2026-06-23\"}\n",
        StandardCharsets.UTF_8);

    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    Files.writeString(
        rollout,
        String.join(
            "\n",
            // 用户消息，轮次标识为消息子类型
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"content\":\"hi\"}}",
            // 助手消息，轮次标识为消息子类型
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_message\",\"content\":\"ok\"}}",
            // 函数调用，轮次标识为工具子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\","
                + "\"call_id\":\"c1\",\"name\":\"shell\"}}",
            // 自定义工具调用，轮次标识为工具子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"custom_tool_call\","
                + "\"call_id\":\"c2\",\"name\":\"custom\"}}",
            // 助手文本消息，轮次标识为消息子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\","
                + "\"role\":\"assistant\",\"content\":\"done\"}}",
            // 推理内容，轮次标识为推理子类型
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"reasoning\","
                + "\"content\":\"thinking\"}}",
            ""),
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);

    List<SourceRecord> original =
        success.records().stream()
            .filter(record -> "event_msg".equals(record.eventType()) || record.eventIndex() >= 2)
            .toList();
    assertThat(original).hasSize(6);
    assertThat(original.get(0).turnId()).hasValue("user_message");
    assertThat(original.get(1).turnId()).hasValue("agent_message");
    assertThat(original.get(2).turnId()).hasValue("function_call");
    assertThat(original.get(3).turnId()).hasValue("custom_tool_call");
    assertThat(original.get(4).turnId()).isEmpty();
    assertThat(original.get(5).turnId()).isEmpty();
  }

  @Test
  @DisplayName("session_index.jsonl 中的 model 字段作为回退传递到记录")
  void modelFallbackFromIndexEntry() throws IOException {
    String sessionId = "thread-model";

    // session_index.jsonl 包含 model 字段
    Files.writeString(
        tempDir.resolve(CodexConstants.SESSION_INDEX_FILE),
        "{\"id\":\""
            + sessionId
            + "\",\"thread_name\":\"Model Thread\",\"updated_at\":\"2026-06-23\","
            + "\"model\":\"gpt-4-fallback\"}\n",
        StandardCharsets.UTF_8);

    Path dayDir =
        tempDir.resolve(CodexConstants.SESSIONS_DIR).resolve("2026").resolve("06").resolve("23");
    Files.createDirectories(dayDir);
    Path rollout = dayDir.resolve("rollout-100-" + sessionId + ".jsonl");
    // 第一个事件没有 model，应使用 indexEntry 回退值
    Files.writeString(
        rollout,
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"content\":\"hi\"}}\n",
        StandardCharsets.UTF_8);

    Candidate candidate = adapter.discover(tempDir).orderedItems().get(0);
    // 验证 candidate metadata 包含 model
    assertThat(candidate.metadata()).containsEntry("model", "gpt-4-fallback");

    SourceResult.Success success = (SourceResult.Success) adapter.parse(candidate, null);
    // 记录应使用回退模型
    assertThat(success.records().get(0).model()).hasValue("gpt-4-fallback");
  }

  private static List<String> eventTypes(SourceResult.Success success) {
    return success.records().stream().map(SourceRecord::eventType).toList();
  }

  private static String codexRollout() {
    return String.join(
        "\n",
        "{\"type\":\"turn_context\",\"payload\":{\"model\":\"gpt-test\"}}",
        "{\"type\":\"session_meta\",\"payload\":{\"id\":\"thread-main\",\"thread_source\":\"subagent\",\"parent_thread_id\":\"thread-parent\"}}",
        "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":100,\"cached_input_tokens\":40,\"output_tokens\":20}}}}",
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"call_1\",\"name\":\"shell\"}}",
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"call_1\",\"output\":\"ok\"}}",
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"done\"}]}}",
        "{\"payload\":{\"schema\":\"drift\"}}",
        "");
  }

  private record FileState(long size, FileTime lastModified, String hash) {
    static FileState capture(Path file) throws IOException {
      SourceFingerprint fp = new CodexSourceAdapter().fingerprint(file);
      return new FileState(
          Files.size(file), Files.getLastModifiedTime(file), fp.contentHash().orElseThrow());
    }
  }
}
