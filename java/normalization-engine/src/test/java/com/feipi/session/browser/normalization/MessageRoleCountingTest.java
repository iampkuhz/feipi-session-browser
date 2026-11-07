package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 显式角色计数排除上下文、工具和子会话，不把同轮消息合并。 */
class MessageRoleCountingTest {
  @Test
  void humanPromptExcludesMetaToolResultAndBothChildScopeForms() {
    var human =
        SourceRecord.of("synthetic#event[0]", 0, "user").withMessageRole(Optional.of("user"));
    var childRelation =
        new SourceRecordRelation(
            Optional.of("child"),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty());
    var meta =
        copy(human, "synthetic#event[1]", 1, SourceRecordRelation.empty(), true, Optional.empty());
    var tool =
        copy(
            human,
            "synthetic#event[2]",
            2,
            SourceRecordRelation.empty(),
            false,
            Optional.of("tool"));
    var child = copy(human, "synthetic#event[3]", 3, childRelation, false, Optional.empty());
    var sidecar =
        copy(
            human,
            "synthetic/subagents/child#event[0]",
            0,
            SourceRecordRelation.empty(),
            false,
            Optional.empty());
    for (var agent : NormalizedAgent.values()) {
      var artifact =
          new NormalizationEngine()
              .normalize(agent, List.of(human, meta, tool, child, sidecar), List.of(), List.of());
      assertThat(artifact.session())
          .containsEntry("userMessageCount", 1L)
          .containsEntry("userMessageCountMeasured", true)
          .containsEntry("assistantMessageCountMeasured", false);
    }
  }

  @Test
  void unmarkedAssistantRecordsAreNotGuessedAndSameTurnMessagesRemainDistinct() {
    var unknown = SourceRecord.of("synthetic#event[0]", 0, "assistant");
    var first =
        copy(
            unknown.withMessageRole(Optional.of("assistant")),
            "synthetic#event[1]",
            1,
            SourceRecordRelation.empty(),
            false,
            Optional.empty());
    var second =
        copy(first, "synthetic#event[2]", 2, SourceRecordRelation.empty(), false, Optional.empty());
    var artifact =
        new NormalizationEngine()
            .normalize(
                NormalizedAgent.CLAUDE_CODE, List.of(unknown, first, second), List.of(), List.of());
    assertThat(artifact.calls()).hasSize(3);
    assertThat(artifact.session()).containsEntry("assistantMessageCount", 2L);
  }

  @Test
  void providerMessageFragmentsPreserveRoleAndCountOneExplicitMessage() {
    var fragments =
        java.util.stream.IntStream.range(0, 2)
            .mapToObj(
                index ->
                    new SourceRecord(
                            "synthetic#event[" + index + "]",
                            index,
                            "assistant",
                            Optional.of("fragment-" + index),
                            Optional.empty(),
                            Optional.empty(),
                            Optional.empty(),
                            com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
                            List.of(),
                            Optional.empty(),
                            Optional.empty(),
                            Optional.empty(),
                            SourceRecordRelation.empty(),
                            "fragment " + index,
                            Optional.of("explicit-message"),
                            Optional.empty())
                        .withMessageRole(Optional.of("assistant")))
            .toList();
    assertThat(ClaudeResponseRecords.merge(fragments))
        .singleElement()
        .satisfies(record -> assertThat(record.messageRole()).contains("assistant"));
    assertThat(QoderResponseRecords.merge(fragments))
        .singleElement()
        .satisfies(record -> assertThat(record.messageRole()).contains("assistant"));
    for (var agent : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.QODER)) {
      var artifact = new NormalizationEngine().normalize(agent, fragments, List.of(), List.of());
      assertThat(artifact.session()).containsEntry("assistantMessageCount", 1L);
    }
  }

  private static SourceRecord copy(
      SourceRecord record,
      String locator,
      int index,
      SourceRecordRelation relation,
      boolean meta,
      Optional<String> toolUseId) {
    return new SourceRecord(
        locator,
        index,
        record.eventType(),
        record.callId(),
        record.model(),
        record.timestamp(),
        Optional.of("same-turn"),
        record.usage(),
        record.toolCalls(),
        toolUseId,
        record.toolName(),
        record.toolError(),
        relation,
        record.content(),
        record.responseMessageId(),
        record.responseStopReason(),
        record.timing(),
        meta,
        record.messageRole());
  }
}
