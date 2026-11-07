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
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CLAUDE_CODE,
        List.of(),
        Map.of(),
        calls,
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedCall call(int index, String turn, String parent) {
    return new NormalizedCall(
        "c" + index,
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
        Map.of(),
        Map.of());
  }
}
