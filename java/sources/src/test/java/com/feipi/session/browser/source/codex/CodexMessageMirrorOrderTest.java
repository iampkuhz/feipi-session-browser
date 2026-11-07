package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexMessageMirrorOrderTest {
  private static final List<List<String>> ORDERS =
      List.of(
          List.of("EU", "EA", "RU", "RA"), List.of("EU", "RU", "EA", "RA"),
          List.of("EU", "RU", "RA", "EA"), List.of("RU", "RA", "EU", "EA"),
          List.of("RU", "EU", "RA", "EA"), List.of("RU", "EU", "EA", "RA"));
  @TempDir Path directory;

  @Test
  void completeMirrorsHaveOneMessagePerRoleAcrossAllOrderedInterleavings() throws Exception {
    for (var order : ORDERS) {
      for (boolean timestampIdentity : List.of(true, false)) {
        var parsed =
            parse(
                order,
                timestampIdentity,
                timestampIdentity ? "" : "same-turn",
                timestampIdentity ? "" : "same-turn");
        assertRoleCounts(parsed, 1);
        assertThat(parsed.candidateCount()).isEqualTo(4);
        assertThat(parsed.records()).hasSize(4);
        assertThat(
                parsed.records().stream()
                    .map(record -> record.content())
                    .filter(text -> !text.isBlank()))
            .containsExactly("prompt", "answer");
      }
    }
  }

  @Test
  void absentIdentityOrConflictingTurnsKeepBothSourceObservations() throws Exception {
    for (var order : ORDERS) {
      assertRoleCounts(parse(order, false, "", ""), 2);
      assertRoleCounts(parse(order, true, "event-turn", "response-turn"), 2);
    }
  }

  private static void assertRoleCounts(SourceResult.Success parsed, int expected) {
    for (String role : List.of("user", "assistant")) {
      assertThat(
              parsed.records().stream()
                  .filter(record -> record.messageRole().orElse("").equals(role)))
          .as(role)
          .hasSize(expected);
    }
  }

  private SourceResult.Success parse(
      List<String> order, boolean timestamps, String eventTurn, String responseTurn)
      throws Exception {
    Files.writeString(directory.resolve("session_index.jsonl"), "{\"id\":\"mirror\"}\n");
    Path file =
        Files.createDirectories(directory.resolve("sessions")).resolve("rollout-mirror.jsonl");
    var source = new StringBuilder();
    for (String kind : order) {
      boolean event = kind.startsWith("E");
      boolean user = kind.endsWith("U");
      String body = user ? "prompt" : "answer";
      String timestamp =
          timestamps ? "\"timestamp\":\"2026-11-05T10:00:0" + (user ? 1 : 2) + "Z\"," : "";
      String turn = event ? eventTurn : responseTurn;
      String turnField = turn.isEmpty() ? "" : ",\"turn_id\":\"" + turn + "\"";
      source
          .append("{\"type\":\"")
          .append(event ? "event_msg" : "response_item")
          .append("\",")
          .append(timestamp)
          .append("\"payload\":{");
      if (event) {
        source
            .append("\"type\":\"")
            .append(user ? "user_message" : "agent_message")
            .append("\",\"message\":\"")
            .append(body)
            .append("\"");
      } else {
        source
            .append("\"type\":\"message\",\"role\":\"")
            .append(user ? "user" : "assistant")
            .append("\",\"content\":\"")
            .append(body)
            .append("\"");
      }
      source.append(turnField).append("}}\n");
    }
    Files.writeString(file, source);
    var adapter = new CodexSourceAdapter();
    return (SourceResult.Success)
        adapter.parse(adapter.discover(directory).orderedItems().getFirst(), null);
  }
}
