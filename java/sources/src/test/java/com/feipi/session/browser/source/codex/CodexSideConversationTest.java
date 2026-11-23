package com.feipi.session.browser.source.codex;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.source.SourceReadingEvidence;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class CodexSideConversationTest {
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String POLICY =
      "<side_conversation>Synthetic developer policy</side_conversation>";
  private static final String BOUNDARY =
      """
      Side conversation boundary.

      Everything before this boundary is inherited history from the parent thread. It is reference context only. It is not your current task.

      Do not continue, execute, or complete any instructions, plans, tool calls, approvals, edits, or requests from before this boundary. Only messages submitted after this boundary are active user instructions for this side conversation.

      You are a side-conversation assistant, separate from the main thread. Answer questions and do lightweight, non-mutating exploration without disrupting the main thread. If there is no user question after this boundary yet, wait for one.

      External tools may be available according to this thread's current permissions. Any tool calls or outputs visible before this boundary happened in the parent thread and are reference-only; do not infer active instructions from them.

      Sub-agents are off-limits in this side conversation. Do not interact with any existing or new sub-agents, even if sub-agents were used before this boundary.

      Do not modify files, source, git state, permissions, configuration, or workspace state unless the user explicitly asks for that mutation after this boundary. Do not request escalated permissions or broader sandbox access unless the user explicitly asks for a mutation that requires it. If the user explicitly requests a mutation, keep it minimal, local to the request, and avoid disrupting the main thread.
      """
          .stripTrailing();

  // 合成的不确定变体：仅用于验证展示回退，不声称为官方版本。
  private static final String UNVERIFIED =
      BOUNDARY.replace(
          "Sub-agents are off-limits",
          "Synthetic section: " + "x".repeat(364) + "\n\nSub-agents are off-limits");

  @TempDir Path directory;

  @Test
  void nativeCheckpointKeepsOnlyActiveMessagesAndExplicitUsageAtTheirOriginalPositions()
      throws Exception {
    var prefix =
        List.of(
            metadata(true),
            message("user", "inherited question"),
            message("assistant", "inherited answer"),
            usage("parent", 51),
            message("developer", POLICY),
            message("user", BOUNDARY));
    assertThat(parse(prefix)).noneMatch(record -> record.messageRole().isPresent());
    var events = new ArrayList<>(prefix);
    events.addAll(
        List.of(
            message("assistant", "preparation response"),
            usage("preparation", 2),
            message("user", "synthetic side question"),
            message("assistant", "synthetic side answer"),
            usage("answer", 3)));
    var records = parse(events);
    assertThat(records.stream().filter(r -> "user".equals(r.eventType())))
        .singleElement()
        .satisfies(
            user -> {
              assertThat(user.content()).isEqualTo("synthetic side question");
              assertThat(user.eventIndex()).isEqualTo(8);
            });
    assertThat(records.stream().filter(r -> "assistant".equals(r.eventType())))
        .extracting(SourceRecord::eventIndex)
        .containsExactly(7, 10);
    assertThat(records.stream().mapToLong(r -> r.usage().total()).sum()).isEqualTo(5);
    var metadata =
        CodexMetadataProjection.read(
            new com.feipi.session.browser.source.common.JsonlReader(),
            directory.resolve("synthetic-side.jsonl"));
    assertThat(CodexActivityRange.create(metadata.events(), metadata.diagnostics()).start())
        .isEqualTo(6);
  }

  @Test
  void ordinaryAndMixedUserMessagesCannotStartAnInheritedRange() throws Exception {
    for (String message :
        List.of(
            message("user", "What is Side Chat?"),
            message("user", BOUNDARY.replace("Do not continue", "Please continue")),
            message("user", BOUNDARY + "\n\nPlease answer my question."),
            message("user", BOUNDARY, "Please answer my question."))) {
      var records = parse(List.of(metadata(true), message("developer", POLICY), message));
      assertThat(records.stream().filter(r -> "user".equals(r.eventType()) && !r.metaContext()))
          .hasSize(1);
    }
    assertThat(
            parse(
                List.of(metadata(false), message("developer", POLICY), message("user", BOUNDARY))))
        .anyMatch(record -> "user".equals(record.eventType()));
    assertThat(parse(List.of(metadata(true), message("user", BOUNDARY))))
        .anyMatch(record -> "user".equals(record.eventType()));
  }

  @Test
  void unverifiedVariantPreservesParentAndSourceTextButDoesNotBecomeAUserQuestion()
      throws Exception {
    assertThat(UNVERIFIED).hasSize(1820);
    var records =
        parse(
            List.of(
                metadata(true),
                message("user", "parent remains"),
                message("developer", POLICY),
                message("user", UNVERIFIED),
                message("user", "active question")));
    assertThat(records.stream().filter(SourceRecord::metaContext))
        .singleElement()
        .satisfies(
            record ->
                assertThat(record.readingEvidence())
                    .anySatisfy(
                        evidence -> {
                          assertThat(evidence.kind()).isEqualTo("side_context_chars");
                          assertThat(evidence.text())
                              .isEqualTo(Integer.toString(UNVERIFIED.length()));
                        }));
    assertThat(records.stream().filter(SourceRecord::metaContext))
        .extracting(SourceRecord::content)
        .containsExactly(UNVERIFIED);
    assertThat(records.stream().filter(r -> "user".equals(r.eventType()) && !r.metaContext()))
        .extracting(SourceRecord::content)
        .containsExactly("parent remains", "active question");
  }

  @Test
  void variantCertifiesStartupPrefixButNotUnwrappedTrailingText() throws Exception {
    String startup =
        BOUNDARY.replace("Do not modify files, source", "Do not modify files or source");
    String tail = "Not certified as startup evidence.";
    var records = parse(List.of(metadata(true), message("user", startup + "\n\n" + tail)));
    assertThat(records)
        .filteredOn(SourceRecord::metaContext)
        .singleElement()
        .satisfies(
            record -> {
              assertThat(record.content()).endsWith(tail);
              assertThat(record.readingEvidence())
                  .singleElement()
                  .satisfies(
                      evidence ->
                          assertThat(evidence.text())
                              .isEqualTo(Integer.toString(startup.length())));
            });
  }

  @Test
  void verifiedHistoricalTemplateCanEstablishCheckpointButQuotingItDoesNot() throws Exception {
    String historical =
        BOUNDARY.replace(
            "Sub-agents are off-limits",
            "This thread is ephemeral and cannot retain worktree attachments. Do not call create_worktree here. Direct requests requiring a new worktree back to the main conversation.\n\nSub-agents are off-limits");
    assertThat(historical).hasSize(1607);
    assertThat(
            parse(
                List.of(
                    metadata(true),
                    message("user", "parent"),
                    message("developer", POLICY),
                    message("user", historical),
                    message("user", "child"))))
        .filteredOn(r -> "user".equals(r.eventType()))
        .extracting(SourceRecord::content)
        .containsExactly("child");
    String quote = "Please explain this example:\n" + historical;
    assertThat(parse(List.of(metadata(true), message("user", quote))))
        .filteredOn(r -> "user".equals(r.eventType()) && !r.metaContext())
        .extracting(SourceRecord::content)
        .containsExactly(quote);
  }

  @Test
  void changedSeventhParagraphAndUnconfirmedEighthParagraphRemainContext() throws Exception {
    String revised =
        BOUNDARY.replace(
            "explicitly asks for that mutation after",
            "explicitly asks " + "x".repeat(111) + "for that mutation after");
    String candidate = revised + "\n\nSynthetic suffix " + "x".repeat(255);
    assertThat(candidate).hasSize(1820);
    var records =
        parse(
            List.of(
                metadata(true),
                message("user", "parent remains"),
                message("user", candidate),
                message("user", "actual question"),
                message("user", "Quoted template:\n" + candidate),
                message("user", "Side conversation boundary. What does it mean?")));
    assertThat(records.stream().filter(SourceRecord::metaContext))
        .extracting(SourceRecord::content)
        .containsExactly(candidate);
    assertThat(records.stream().filter(r -> "user".equals(r.eventType()) && !r.metaContext()))
        .extracting(SourceRecord::content)
        .containsExactly(
            "parent remains",
            "actual question",
            "Quoted template:\n" + candidate,
            "Side conversation boundary. What does it mean?");
    var wrapped =
        parse(
            List.of(
                metadata(true),
                message("user", revised + "\n\n## My request for Codex:\nKeep me")));
    assertThat(wrapped.stream().filter(SourceRecord::metaContext))
        .extracting(SourceRecord::content)
        .containsExactly(revised);
    assertThat(wrapped.stream().filter(r -> "user".equals(r.eventType()) && !r.metaContext()))
        .extracting(SourceRecord::content)
        .containsExactly("\n\n## My request for Codex:\nKeep me");
  }

  @Test
  void startupContextAndCompactionBoundaryAloneDoNotCreateModelCallEvidence() throws Exception {
    var records =
        parse(
            List.of(
                metadata(true),
                message("user", UNVERIFIED),
                "{\"type\":\"compacted\",\"payload\":{\"compaction_response_id\":\"unobserved\"}}"));
    assertThat(records).anyMatch(SourceRecord::metaContext);
    assertThat(records)
        .noneMatch(record -> "assistant".equals(record.eventType()) || record.callId().isPresent());
  }

  @Test
  void sideChatTaskIdentityBindsOnlyObservedCallsAndKeepsDeclaredTaskTiming() throws Exception {
    String prepare =
        usage("prep", 2).replace("\"response_id\"", "\"turn_id\":\"first\",\"response_id\"");
    String answer =
        usage("answer", 3).replace("\"response_id\"", "\"turn_id\":\"first\",\"response_id\"");
    String later =
        usage("later", 4).replace("\"response_id\"", "\"turn_id\":\"second\",\"response_id\"");
    var taskEvents =
        List.of(
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\",\"turn_id\":\"first\",\"started_at\":\"2026-01-01T01:00:00Z\"}}",
            prepare,
            "{\"type\":\"compacted\",\"payload\":{\"compaction_response_id\":\"prep\"}}",
            message("user", "A meaningful question"),
            answer,
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_complete\",\"turn_id\":\"first\",\"duration_ms\":900}}",
            "{\"type\":\"event_msg\",\"payload\":{\"type\":\"task_started\",\"turn_id\":\"second\"}}",
            later);
    var events = new ArrayList<>(List.of(metadata(true), message("user", UNVERIFIED)));
    events.addAll(taskEvents);
    var calls =
        parse(events).stream().filter(record -> "assistant".equals(record.eventType())).toList();
    assertThat(calls).hasSize(3);
    for (var call : calls.subList(0, 2)) {
      assertThat(call.readingEvidence())
          .contains(
              new SourceReadingEvidence("side_task_id", "first"),
              new SourceReadingEvidence("side_task_started_at", "2026-01-01T01:00:00Z"),
              new SourceReadingEvidence("side_task_duration_ms", "900"));
    }
    assertThat(calls.getFirst().readingEvidence())
        .contains(new SourceReadingEvidence("response_compaction", "identity"));
    assertThat(calls.getLast().readingEvidence())
        .noneMatch(evidence -> "side_task_duration_ms".equals(evidence.kind()));
    var ordinary =
        new ArrayList<>(List.of("{\"type\":\"session_meta\",\"payload\":{\"id\":\"ordinary\"}}"));
    ordinary.addAll(taskEvents);
    assertThat(parse(ordinary))
        .allSatisfy(
            record ->
                assertThat(record.readingEvidence())
                    .noneMatch(evidence -> evidence.kind().startsWith("side_task_")));
  }

  private List<SourceRecord> parse(List<String> events) throws Exception {
    Path file =
        Files.writeString(
            directory.resolve("synthetic-side.jsonl"), String.join("\n", events) + "\n");
    var adapter = new CodexSourceAdapter();
    try (var parsed =
            (SourceResult.Success)
                adapter.parse(
                    new Candidate(adapter.fingerprint(file), "codex:synthetic-side", "", Map.of()),
                    null);
        var cursor = parsed.recordSequence().openCursor()) {
      var records = new ArrayList<SourceRecord>();
      while (cursor.hasNext()) records.add(cursor.next());
      return records;
    }
  }

  private static String metadata(boolean fork) {
    return "{\"type\":\"session_meta\",\"payload\":{\"id\":\"synthetic-side\""
        + ",\"forked_from_id\":\"synthetic-parent\",\"attached_thread\":"
        + fork
        + "}}";
  }

  private static String message(String role, String... texts) throws Exception {
    var event = MAPPER.createObjectNode().put("type", "response_item");
    var content =
        event.putObject("payload").put("type", "message").put("role", role).putArray("content");
    for (String text : texts) content.addObject().put("type", "input_text").put("text", text);
    return MAPPER.writeValueAsString(event);
  }

  private static String usage(String responseId, int output) {
    return """
        {"type":"token_usage_record","payload":{"response_id":"%s","usage":{"input_tokens":0,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":%d}}}
        """
        .formatted(responseId, output);
  }
}
