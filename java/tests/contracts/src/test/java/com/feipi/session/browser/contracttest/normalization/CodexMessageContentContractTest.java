package com.feipi.session.browser.contracttest.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** Codex 显式事件文本须进入调用，且不重复计量或覆盖权威响应项。 */
class CodexMessageContentContractTest {
  @TempDir Path directory;

  @Test
  void responseItemOnlySessionCountsObservedMainRoundWithoutUsage() throws IOException {
    for (String timestamp : List.of("2025-11-05T08:00:00Z", "2026-11-05T08:00:00Z")) {
      var artifact =
          normalize(
              parse(
                  """
          {"type":"response_item","timestamp":"%s","payload":{"type":"message","role":"user","content":"Response-only prompt"}}
          {"type":"response_item","timestamp":"%s","payload":{"type":"message","role":"assistant","content":"Response-only answer"}}
          """
                      .formatted(timestamp, timestamp)));
      assertContent(artifact, "Response-only prompt", "Response-only answer");
      assertThat(artifact.session())
          .containsEntry("userMessageCount", 1L)
          .containsEntry("assistantMessageCount", 1L)
          .containsEntry("totalTokens", 0L);
    }
  }

  @Test
  void eventOnlyMessageAndContentFieldsProduceOneUnmeteredRound() throws IOException {
    for (String field : List.of("message", "content")) {
      var parsed = parse(events(field));
      var artifact = normalize(parsed);
      assertContent(artifact, "Synthetic user", "Synthetic answer");
      assertThat(artifact.session())
          .containsEntry("userMessageCount", 1L)
          .containsEntry("assistantMessageCount", 1L)
          .containsEntry("totalTokens", 0L)
          .containsEntry("eventCount", 4);
      assertThat(parsed.candidateCount()).isEqualTo(2);
      assertThat(parsed.records())
          .allSatisfy(
              record -> {
                assertThat(record.locator()).contains("#event[");
                assertThat(record.eventIndex()).isBetween(0, 1);
              });
      assertThat(parsed.records().stream().filter(record -> "event_msg".equals(record.eventType())))
          .hasSize(2);
    }
  }

  @Test
  void usageFramesKeepCallCountAndUsageWhileReceivingEventText() throws IOException {
    List<String> usages =
        List.of(
            """
        {"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":3}}}}
        """,
            """
        {"type":"token_usage_record","payload":{"response_id":"synthetic-response","usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":3}}}
        """);
    for (String usage : usages) {
      var artifact = normalize(parse(events("message") + usage));
      assertContent(artifact, "Synthetic user", "Synthetic answer");
      assertThat(artifact.session()).containsEntry("totalTokens", 13L);
    }
    var lastOnly =
        normalize(
            parse(
                events("content")
                    + """
        {"type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":10,"output_tokens":3}}}}
        """));
    assertContent(lastOnly, "Synthetic user", "Synthetic answer");
    assertThat(lastOnly.session()).containsEntry("totalTokens", 0L);
  }

  @Test
  void separateUserBoundariesKeepUnmeteredAndMeteredRoundsComplete() throws IOException {
    for (int variant = 0; variant < 4; variant++) {
      boolean firstMetered = variant == 1 || variant == 3;
      boolean secondMetered = variant == 2 || variant == 3;
      String first =
          events("message")
              .replace("Synthetic user", "First prompt")
              .replace("Synthetic answer", "First answer");
      String second =
          events("content")
              .replace("Synthetic user", "Second prompt")
              .replace("Synthetic answer", "Second answer");
      String firstUsage = firstMetered ? cumulativeUsage(10, 3) : "";
      String secondUsage =
          secondMetered ? cumulativeUsage(firstMetered ? 20 : 10, firstMetered ? 6 : 3) : "";
      String content =
          (first + firstUsage + second + secondUsage)
              .replace(
                  "{\"type\":\"event_msg\",",
                  "{\"timestamp\":\"2026-11-05T08:00:01Z\",\"type\":\"event_msg\",");
      var artifact = normalize(parse(content));

      assertThat(artifact.calls()).as("usage variant %s", variant).hasSize(2);
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 2L);
      assertThat(SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()))
          .hasSize(2);
      assertThat(artifact.calls().get(0).sourceUnits())
          .extracting(unit -> unit.get("text"))
          .contains("First prompt", "First answer")
          .doesNotContain("Second prompt", "Second answer");
      assertThat(artifact.calls().get(1).sourceUnits())
          .extracting(unit -> unit.get("text"))
          .contains("Second prompt", "Second answer")
          .doesNotContain("First prompt", "First answer");
      long expectedTokens = (firstMetered ? 13L : 0L) + (secondMetered ? 13L : 0L);
      assertThat(artifact.session()).containsEntry("totalTokens", expectedTokens);
      assertThat(artifact.calls().get(0).usage().total()).isEqualTo(firstMetered ? 13L : 0L);
      assertThat(artifact.calls().get(1).usage().total()).isEqualTo(secondMetered ? 13L : 0L);
    }
  }

  @Test
  void explicitTaskBoundariesKeepUnmeteredTailWithoutAnotherUserMessage() throws IOException {
    for (String boundary :
        List.of(
            "{\"type\":\"turn_context\",\"payload\":{\"turn_id\":\"second-task\"}}\n",
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\",\"turn_id\":\"second-task\"}}\n")) {
      var artifact =
          normalize(
              parse(
                  events("message")
                      + cumulativeUsage(10, 3)
                      + boundary
                      + """
          {"type":"event_msg","payload":{"type":"agent_message","message":"Second task answer"}}
          """));
      assertThat(artifact.calls()).hasSize(2);
      assertThat(SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()))
          .hasSize(2);
      assertThat(artifact.calls().get(0).sourceUnits())
          .extracting(unit -> unit.get("text"))
          .contains("Synthetic user", "Synthetic answer")
          .doesNotContain("Second task answer");
      assertThat(artifact.calls().get(1).sourceUnits())
          .extracting(unit -> unit.get("text"))
          .contains("Second task answer")
          .doesNotContain("Synthetic user", "Synthetic answer");
      assertThat(artifact.calls().get(0).usage().total()).isEqualTo(13L);
      assertThat(artifact.calls().get(1).usage().total()).isZero();
      assertThat(artifact.session()).containsEntry("totalTokens", 13L);
    }
  }

  private static String cumulativeUsage(int input, int output) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":"
        + input
        + ",\"cached_input_tokens\":0,\"output_tokens\":"
        + output
        + "}}}}\n";
  }

  @Test
  void responseItemRemainsAuthoritativeAndDoesNotDuplicateTextOrCalls() throws IOException {
    var artifact =
        normalize(
            parse(
                events("message")
                    + """
        {"type":"response_item","payload":{"type":"message","role":"user","content":"Authoritative user"}}
        {"type":"response_item","payload":{"type":"message","role":"assistant","content":"Authoritative answer"}}
        """));
    assertContent(artifact, "Authoritative user", "Authoritative answer");
    assertThat(artifact.calls().getFirst().sourceUnits())
        .extracting(unit -> unit.get("text"))
        .doesNotContain("Synthetic user", "Synthetic answer");
    assertThat(artifact.session()).containsEntry("totalTokens", 0L);
  }

  @Test
  void parentAndChildRolloutsChooseFallbackIndependently() throws IOException {
    Path day = directory.resolve("sessions/synthetic");
    Files.createDirectories(day);
    Files.writeString(
        day.resolve("rollout-child.jsonl"),
        """
        {"type":"session_meta","payload":{"id":"child","parent_thread_id":"parent","agent_path":"/root/task"}}
        """
            + events("message"));
    var parsed =
        parse(
            """
        {"type":"session_meta","payload":{"id":"parent"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"spawn","name":"spawn_agent"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn","output":{"task_name":"/root/task"}}}
        {"type":"response_item","payload":{"type":"message","role":"assistant","content":"Parent authoritative answer"}}
        """);
    var artifact = normalize(parsed);
    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.calls().stream().flatMap(call -> call.sourceUnits().stream()))
        .extracting(unit -> unit.get("text"))
        .contains("Parent authoritative answer", "Synthetic user", "Synthetic answer");
  }

  @Test
  void authoritativeChildDoesNotSuppressEventOnlyParent() throws IOException {
    Path day = directory.resolve("sessions/synthetic");
    Files.createDirectories(day);
    Files.writeString(
        day.resolve("rollout-child.jsonl"),
        """
        {"type":"session_meta","payload":{"id":"child","parent_thread_id":"parent","agent_path":"/root/task"}}
        {"type":"response_item","payload":{"type":"message","role":"assistant","content":"Child authoritative answer"}}
        """);
    var parsed =
        parse(
            """
        {"type":"session_meta","payload":{"id":"parent"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"spawn","name":"spawn_agent"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"spawn","output":{"task_name":"/root/task"}}}
        """
                + events("content"));
    var artifact = normalize(parsed);
    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.calls().stream().flatMap(call -> call.sourceUnits().stream()))
        .extracting(unit -> unit.get("text"))
        .contains("Child authoritative answer", "Synthetic user", "Synthetic answer");
    assertThat(artifact.session()).containsEntry("totalTokens", 0L);
  }

  private SourceResult.Success parse(String content) throws IOException {
    Files.writeString(
        directory.resolve("session_index.jsonl"),
        "{\"id\":\"parent\",\"thread_name\":\"Synthetic\"}\n");
    Path day = directory.resolve("sessions/synthetic");
    Files.createDirectories(day);
    Files.writeString(day.resolve("rollout-parent.jsonl"), content);
    var adapter = new CodexSourceAdapter();
    return (SourceResult.Success)
        adapter.parse(adapter.discover(directory).orderedItems().getFirst(), null);
  }

  private static String events(String field) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\""
        + field
        + "\":\"Synthetic user\"}}\n"
        + "{\"type\":\"event_msg\",\"payload\":{\"type\":\"agent_message\",\""
        + field
        + "\":\"Synthetic answer\"}}\n";
  }

  private static NormalizedSessionArtifact normalize(SourceResult.Success parsed) {
    return new NormalizationEngine()
        .normalize(NormalizedAgent.CODEX, parsed.records(), parsed.diagnostics(), List.of());
  }

  private static void assertContent(
      NormalizedSessionArtifact artifact, String user, String answer) {
    assertThat(artifact.calls()).hasSize(1);
    assertThat(SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()))
        .hasSize(1);
    assertThat(artifact.calls().getFirst().sourceUnits())
        .extracting(unit -> unit.get("text"))
        .contains(user, answer);
  }
}
