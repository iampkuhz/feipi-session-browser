package com.feipi.session.browser.contracttest.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 真正消息身份不由 usage、日期或轮次数推断。 */
class MessageCountEvidenceContractTest {
  @TempDir Path directory;

  @Test
  void messageCountHasSameMeaningAcrossDates() throws Exception {
    for (String date : List.of("2025-01-01", "2026-11-05")) {
      var artifact =
          normalize(
              event("user_message", "prompt")
                  + event("agent_message", "answer")
                  + usage(10)
                  + usage(20)
                  + "{\"type\":\"turn_context\",\"timestamp\":\""
                  + date
                  + "T10:00:00Z\"}\n");
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
    }
  }

  @Test
  void usageOnlyCannotEstablishMessagesOrMeasuredZero() throws Exception {
    var artifact = normalize(usage(10) + usage(20));
    assertThat(artifact.session())
        .containsEntry("assistantMessageCount", 0L)
        .containsEntry("assistantMessageCountMeasured", false)
        .containsEntry("userMessageCountMeasured", false);
    assertThat(artifact.session().get("totalTokens")).isEqualTo(20L);
  }

  @Test
  void reasoningOnlyCannotEstablishAssistantMessage() throws Exception {
    var artifact =
        normalize(
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"reasoning\",\"summary\":[]}}\n");
    assertThat(artifact.session())
        .containsEntry("assistantMessageCount", 0L)
        .containsEntry("assistantMessageCountMeasured", false);
  }

  @Test
  void responseMessagesCountRegardlessOfUsageAndAllowEmptyText() throws Exception {
    for (String usage : List.of("", usage(10))) {
      var artifact = normalize(response("user", "prompt") + response("assistant", "") + usage);
      assertThat(artifact.session())
          .containsEntry("assistantMessageCount", 1L)
          .containsEntry("userMessageCount", 1L)
          .containsEntry("assistantMessageCountMeasured", true);
    }
  }

  @Test
  void exactCompleteMirrorIsOneMessagePerRole() throws Exception {
    String timestamp = "\"timestamp\":\"2026-11-05T10:00:00Z\",";
    String input =
        event("user_message", "prompt")
            + event("agent_message", "answer")
            + response("user", "prompt")
            + response("assistant", "answer");
    var artifact = normalize(input.replace("{\"type\":", "{" + timestamp + "\"type\":"));
    assertThat(artifact.session())
        .containsEntry("assistantMessageCount", 1L)
        .containsEntry("userMessageCount", 1L);
  }

  @Test
  void interleavedExplicitMirrorCountsOneMessagePerRole() throws Exception {
    String timestamp = "\"timestamp\":\"2026-11-05T10:00:00Z\",";
    String input =
        event("user_message", "prompt")
            + response("user", "prompt")
            + response("assistant", "answer")
            + event("agent_message", "answer");
    var artifact = normalize(input.replace("{\"type\":", "{" + timestamp + "\"type\":"));
    assertThat(artifact.session())
        .containsEntry("userMessageCount", 1L)
        .containsEntry("assistantMessageCount", 1L);
  }

  @Test
  void mixedSegmentsAndRepeatedTextRemainIndependentMessages() throws Exception {
    var artifact =
        normalize(
            event("user_message", "same")
                + event("agent_message", "same")
                + response("user", "same")
                + response("assistant", "same"));
    assertThat(artifact.session())
        .containsEntry("assistantMessageCount", 2L)
        .containsEntry("userMessageCount", 2L);
  }

  @Test
  void twoExplicitMessagesInOneTurnAreNotOneMessage() throws Exception {
    var artifact =
        normalize(
            response("user", "prompt")
                + response("assistant", "first")
                + response("assistant", "second")
                + usage(10));
    assertThat(artifact.session()).containsEntry("assistantMessageCount", 2L);
  }

  @Test
  void userEvidenceDoesNotImplyMeasuredAssistantZero() throws Exception {
    var artifact = normalize(response("user", "prompt"));
    assertThat(artifact.session())
        .containsEntry("userMessageCount", 1L)
        .containsEntry("userMessageCountMeasured", true)
        .containsEntry("assistantMessageCount", 0L)
        .containsEntry("assistantMessageCountMeasured", false);
  }

  private NormalizedSessionArtifact normalize(String content) throws Exception {
    Files.writeString(directory.resolve("session_index.jsonl"), "{\"id\":\"synthetic\"}\n");
    Path sessions = directory.resolve("sessions/synthetic");
    Files.createDirectories(sessions);
    Files.writeString(sessions.resolve("rollout-synthetic.jsonl"), content);
    var adapter = new CodexSourceAdapter();
    var parsed =
        (SourceResult.Success)
            adapter.parse(adapter.discover(directory).orderedItems().getFirst(), null);
    return new NormalizationEngine()
        .normalize(NormalizedAgent.CODEX, parsed.records(), parsed.diagnostics(), List.of());
  }

  private static String event(String role, String content) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\""
        + role
        + "\",\"message\":\""
        + content
        + "\"}}\n";
  }

  private static String response(String role, String content) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\""
        + role
        + "\",\"content\":\""
        + content
        + "\"}}\n";
  }

  private static String usage(int tokens) {
    return "{\"type\":\"event_msg\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":"
        + tokens
        + ",\"output_tokens\":0}}}}\n";
  }
}
