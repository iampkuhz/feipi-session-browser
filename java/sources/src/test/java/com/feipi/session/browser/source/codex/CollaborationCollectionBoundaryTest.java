package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 明确 child 采集的资源、循环、冲突及磁盘重放边界。 */
class CollaborationCollectionBoundaryTest {
  @TempDir Path directory;

  @Test
  void inputTargetNeverDiscoversAnAdjacentChild() throws Exception {
    String target = "11111111-1111-4111-8111-111111111111";
    Path parent = file(0);
    Path neighbor = directory.resolve("rollout-" + target + ".jsonl");
    Files.writeString(
        parent,
        meta(0, -1)
            + """
        {"type":"response_item","payload":{"type":"function_call","namespace":"multi_agent_v1","name":"send_input","call_id":"input","arguments":{"target":"11111111-1111-4111-8111-111111111111","message":"synthetic"}}}
        """);
    Files.writeString(
        neighbor,
        """
        {"type":"session_meta","payload":{"id":"11111111-1111-4111-8111-111111111111","source":{"subagent":{"thread_spawn":{"parent_thread_id":"worker-0"}}}}}
        {"type":"event_msg","payload":{"type":"user_message","message":"synthetic neighbor must not load"}}
        """);
    try (var parsed = parse(parent)) {
      assertThat(parsed.records())
          .noneMatch(record -> record.locator().startsWith(neighbor.toString()));
      assertThat(parsed.records())
          .flatExtracting(record -> record.collaboration())
          .singleElement()
          .satisfies(
              fact -> {
                assertThat(fact.kind()).isEqualTo("input");
                assertThat(fact.targetId()).contains(target);
              });
      assertThat(parsed.records())
          .allSatisfy(
              record -> {
                assertThat(record.relation().parentToolCallId()).isEmpty();
                assertThat(record.content()).doesNotContain("neighbor must not load");
              });
    }
  }

  @Test
  void depthIsBoundedAndDelegationAtBoundaryRemainsRecorded() throws Exception {
    for (int i = 0; i <= 10; i++) Files.writeString(file(i), meta(i, i - 1) + spawn(i, i + 1));
    try (var parsed = parse(file(0))) {
      assertThat(parsed.diagnostics())
          .extracting(diagnostic -> diagnostic.code())
          .contains("SUBAGENT_COLLECTION_TRUNCATED");
      assertThat(parsed.records())
          .flatExtracting(record -> record.collaboration())
          .anySatisfy(fact -> assertThat(fact.targetId()).contains("worker-9"));
      assertThat(parsed.records())
          .noneMatch(record -> record.locator().startsWith(file(9).toString()));
    }
  }

  @Test
  void nodeCountIsBoundedAndNoDeclaredTargetDisappears() throws Exception {
    StringBuilder root = new StringBuilder(meta(0, -1));
    for (int i = 1; i <= 130; i++) {
      root.append(spawn(i, i));
      Files.writeString(file(i), meta(i, 0));
    }
    Files.writeString(file(0), root);
    try (var parsed = parse(file(0))) {
      assertThat(parsed.diagnostics())
          .extracting(diagnostic -> diagnostic.code())
          .contains("SUBAGENT_COLLECTION_TRUNCATED");
      assertThat(parsed.records())
          .flatExtracting(record -> record.collaboration())
          .filteredOn(fact -> fact.phase().equals("declaration"))
          .hasSize(130);
      assertThat(parsed.candidateCount()).isEqualTo(261 + 128);
    }
  }

  @Test
  void cycleIsDiagnosedInsteadOfReplayingTheRoot() throws Exception {
    Files.writeString(file(0), meta(0, 1) + spawn(0, 1));
    Files.writeString(file(1), meta(1, 0) + spawn(1, 0));
    try (var parsed = parse(file(0))) {
      assertThat(parsed.diagnostics())
          .extracting(diagnostic -> diagnostic.code())
          .contains("SUBAGENT_CYCLE");
      assertThat(parsed.records()).hasSize(6);
    }
  }

  @Test
  void conflictingOutputsAndDuplicateChildIdsNeverSelectFirstOrLast() throws Exception {
    Files.writeString(
        file(0),
        meta(0, -1)
            + spawn(0, 1)
            + "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"spawn-0\",\"output\":{\"agent_id\":\"worker-2\"}}}\n");
    Files.writeString(file(1), meta(1, 0));
    Files.writeString(file(2), meta(2, 0));
    try (var parsed = parse(file(0))) {
      assertThat(parsed.diagnostics())
          .extracting(diagnostic -> diagnostic.code())
          .contains("SUBAGENT_SPAWN_AMBIGUOUS");
      assertThat(parsed.records())
          .flatExtracting(record -> record.collaboration())
          .allSatisfy(
              fact -> {
                assertThat(fact.reason()).isEqualTo("conflicting_tool_identity");
                assertThat(fact.targetId()).isEmpty();
              });
    }
    Files.writeString(directory.resolve("rollout-duplicate.jsonl"), meta(1, 0));
    Files.writeString(file(0), meta(0, -1) + spawn(0, 1));
    try (var parsed = parse(file(0))) {
      assertThat(parsed.diagnostics())
          .extracting(diagnostic -> diagnostic.code())
          .contains("SUBAGENT_IDENTITY_CONFLICT");
      assertThat(parsed.records())
          .allSatisfy(record -> assertThat(record.locator()).startsWith(file(0).toString()));
    }
  }

  @Test
  void childByteBudgetRejectsSparseOversizeBeforeReadingItsBody() throws Exception {
    Files.writeString(file(0), meta(0, -1) + spawn(0, 1));
    Files.writeString(file(1), meta(1, 0));
    try (var channel = FileChannel.open(file(1), StandardOpenOption.WRITE)) {
      channel.position(128L * 1024 * 1024);
      channel.write(ByteBuffer.wrap(new byte[] {'\n'}));
    }
    try (var parsed = parse(file(0))) {
      assertThat(parsed.diagnostics())
          .extracting(diagnostic -> diagnostic.code())
          .contains("SUBAGENT_COLLECTION_TRUNCATED");
      assertThat(parsed.records()).hasSize(3);
    }
  }

  @Test
  void managedSourceSpoolKeepsMultipleTargetsWithoutCopyingResultBodiesIntoFacts()
      throws Exception {
    StringBuilder source = new StringBuilder(meta(0, -1));
    for (int i = 0; i < 1100; i++)
      source.append("{\"type\":\"event_msg\",\"payload\":{\"type\":\"synthetic\"}}\n");
    source.append(
        """
        {"type":"response_item","payload":{"type":"function_call","call_id":"wait","name":"wait_agent","arguments":{"targets":["worker-shared-001","worker-shared-002"]}}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"wait","output":{"status":{"worker-shared-001":{"completed":"synthetic large body"},"worker-shared-002":{"completed":"synthetic large body"}}}}}
        """);
    Files.writeString(file(0), source);
    try (var parsed = parse(file(0))) {
      assertThat(parsed.recordSequence().recordCount()).isGreaterThan(1024);
      for (int pass = 0; pass < 2; pass++) {
        int facts = 0;
        try (var cursor = parsed.recordSequence().openCursor()) {
          while (cursor.hasNext()) {
            var record = cursor.next();
            facts += record.collaboration().size();
            assertThat(record.collaboration().toString()).doesNotContain("synthetic large body");
            assertThat(record.collaboration())
                .allSatisfy(fact -> assertThat(fact.sourceLocator()).isEqualTo(record.locator()));
          }
        }
        assertThat(facts).isEqualTo(4);
      }
    }
  }

  @Test
  void oversizedProtocolAndToolIdentityKeepOneExplicitLimitFactAndOriginalPayload()
      throws Exception {
    var json = new com.fasterxml.jackson.databind.ObjectMapper();
    String large = " ".repeat(1024 * 1024) + "{\"status\":{}}";
    String longId = "w".repeat(5000);
    String source = meta(0, -1);
    for (String id : java.util.List.of("wait-bounded", longId)) {
      source +=
          json.writeValueAsString(
                  Map.of(
                      "type",
                      "response_item",
                      "payload",
                      Map.of(
                          "type",
                          "function_call",
                          "call_id",
                          id,
                          "name",
                          "wait_agent",
                          "arguments",
                          Map.of("targets", java.util.List.of("one", "two")))))
              + "\n";
      source +=
          json.writeValueAsString(
                  Map.of(
                      "type",
                      "response_item",
                      "payload",
                      Map.of(
                          "type",
                          "function_call_output",
                          "call_id",
                          id,
                          "output",
                          id.equals(longId) ? "{}" : large)))
              + "\n";
    }
    source +=
        "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"empty-spawn\",\"name\":\"spawn_agent\"}}\n"
            + "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"empty-spawn\",\"output\":\"\"}}\n";
    Files.writeString(file(0), source);
    try (var parsed = parse(file(0))) {
      var records = new java.util.ArrayList<com.feipi.session.browser.domain.source.SourceRecord>();
      try (var cursor = parsed.recordSequence().openCursor()) {
        while (cursor.hasNext()) records.add(cursor.next());
      }
      assertThat(records)
          .flatExtracting(record -> record.collaboration())
          .extracting(fact -> fact.reason())
          .contains("identity_resource_limit", "protocol_payload_resource_limit");
      assertThat(records)
          .filteredOn(record -> record.callId().filter(longId::equals).isPresent())
          .allSatisfy(
              record -> {
                assertThat(record.collaboration()).hasSize(1);
                assertThat(record.collaboration().getFirst().toolCallId()).isEqualTo(longId);
              });
      assertThat(records).anySatisfy(record -> assertThat(record.content()).isEqualTo(large));
    }
  }

  private Path file(int index) {
    return directory.resolve("rollout-" + index + ".jsonl");
  }

  private SourceResult.Success parse(Path file) {
    var adapter = new CodexSourceAdapter();
    var result =
        adapter.parse(
            new Candidate(adapter.fingerprint(file), "codex:synthetic", "", Map.of()), null);
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    return (SourceResult.Success) result;
  }

  private static String meta(int id, int parent) {
    return "{\"type\":\"session_meta\",\"payload\":{\"id\":\"worker-"
        + id
        + "\",\"parent_thread_id\":\"worker-"
        + parent
        + "\"}}\n";
  }

  private static String spawn(int id, int child) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"spawn-"
        + id
        + "\",\"name\":\"spawn_agent\"}}\n"
        + "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"spawn-"
        + id
        + "\",\"output\":{\"agent_id\":\"worker-"
        + child
        + "\"}}}\n";
  }
}
