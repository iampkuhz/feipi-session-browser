package com.feipi.session.browser.index.api.query;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ContentRoundIndexTest {
  @Test
  void globalTurnsAndParentsMatchLegacyGrouping() throws Exception {
    var calls =
        List.of(
            call(1, "a", null),
            call(2, "b", null),
            call(3, "a", null),
            call(4, null, "c1"),
            call(5, null, "missing"));
    var artifact = artifact(calls);
    var index = ContentRoundIndex.build(NormalizedSessionContent.fromArtifact(artifact), 0);
    var rounds = RoundAssembler.buildRounds(artifact, 0);
    assertThat(index.roundCount()).isEqualTo(rounds.size());
    for (var round : rounds)
      for (var id : round.calls())
        assertThat(index.roundIndexForCall(id)).hasValue(round.roundIndex());
    assertThat(index.roundIndexForCall("missing")).isEmpty();
  }

  @Test
  void codexResponseBoundariesAreIndependentOfTaskAndParent() throws Exception {
    var calls =
        List.of(
            call(1, "token_usage_record:response-a", "same-task", null, ""),
            call(2, "token_usage_record:response-b", "same-task", null, ""),
            call(3, "child-SR1", "child-task", "token_usage_record:response-a", "response_usage"),
            call(4, "child-SR2", "child-task", "token_usage_record:response-a", "closing_counter"),
            call(5, "child-SR3", "child-task", "token_usage_record:response-a", ""),
            call(6, "token_usage_record:42", "unconfirmed-task", null, ""));
    var artifact = artifact(calls, NormalizedAgent.CODEX);
    var index = ContentRoundIndex.build(NormalizedSessionContent.fromArtifact(artifact), 0);
    assertThat(index.roundCount()).isEqualTo(6);
    var rounds = RoundAssembler.buildRounds(artifact, 0);
    assertThat(rounds).hasSize(6);
    for (var call : calls) {
      assertThat(index.roundIndexForCall(call.callId())).hasValue(call.callIndex());
      assertThat(rounds.get(call.callIndex() - 1).calls()).containsExactly(call.callId());
    }
    assertThat(rounds.get(2).parentCallId()).isEqualTo("token_usage_record:response-a");
    assertThat(rounds.get(4).parentCallId()).isEqualTo("token_usage_record:response-a");
    assertThat(
            calls.stream()
                .filter(
                    call -> !ContentRoundIndex.modelCallEvidence(artifact.agent(), call).isEmpty()))
        .containsExactlyElementsOf(calls.subList(0, 4));
  }

  @Test
  void retainsIndependentCallsPastLegacyBoundaryWithoutFlattening() throws Exception {
    for (int size : new int[] {10000, 10001, 10234}) {
      var calls = IntStream.rangeClosed(1, size).mapToObj(i -> call(i, "t" + i, null)).toList();
      var header =
          new NormalizedContentHeader(
              NormalizedConstants.SCHEMA_VERSION,
              NormalizedAgent.CLAUDE_CODE,
              NormalizedSessionMetadata.fromMap(Map.of()),
              Map.of(
                  "calls",
                  (long) size,
                  "toolExecutions",
                  0L,
                  "diagnostics",
                  0L,
                  "sourceFiles",
                  0L,
                  "sourceUnitCatalog",
                  0L,
                  "sourceUnitSequenceEntries",
                  0L));
      var content =
          NormalizedSessionContent.fromLists(
              header, List.of(), calls, List.of(), List.of(), Map.of(), Map.of());
      var index = ContentRoundIndex.build(content, 0);
      assertThat(index.roundCount()).isEqualTo(size);
      assertThat(index.roundIndexForCall("c" + size)).hasValue(size);
    }
  }

  @Test
  void measuredUserOnlyContentHasOneRound() throws Exception {
    assertThat(
            ContentRoundIndex.build(NormalizedSessionContent.fromArtifact(artifact(List.of())), 1)
                .roundCount())
        .isEqualTo(1);
  }

  private static NormalizedSessionArtifact artifact(List<NormalizedCall> calls) {
    return artifact(calls, NormalizedAgent.CLAUDE_CODE);
  }

  private static NormalizedSessionArtifact artifact(
      List<NormalizedCall> calls, NormalizedAgent agent) {
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        agent,
        List.of(),
        Map.of(),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(int index, String turn, String parent) {
    return call(index, "c" + index, turn, parent, "");
  }

  private static NormalizedCall call(
      int index, String id, String turn, String parent, String evidence) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        parent == null ? CallScope.MAIN : CallScope.SUBAGENT,
        Optional.ofNullable(parent),
        Optional.empty(),
        Optional.ofNullable(turn),
        "model",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        List.of(),
        List.of(),
        evidence.isEmpty() ? Map.of() : Map.of("modelCallEvidence", evidence),
        Map.of());
  }
}
