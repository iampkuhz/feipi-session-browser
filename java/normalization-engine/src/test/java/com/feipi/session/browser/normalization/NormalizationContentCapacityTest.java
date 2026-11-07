package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class NormalizationContentCapacityTest {
  @Test
  void sourcesAndCatalogCrossLimitWithoutBeingCopiedIntoEveryUnit() throws Exception {
    var files =
        IntStream.range(0, 10_234)
            .mapToObj(
                i ->
                    new com.feipi.session.browser.domain.normalized.NormalizedSourceFile(
                        com.feipi.session.browser.domain.normalized.SourceFileRole.TRANSCRIPT,
                        java.nio.file.Path.of("synthetic/source-" + i + ".jsonl"),
                        null,
                        null))
            .toList();
    var content =
        new NormalizationEngine()
            .normalizeContent(NormalizedAgent.CODEX, List.of(), List.of(), files);
    assertThat(content.header().totals())
        .containsEntry("sourceFiles", 10_234L)
        .containsEntry("sourceUnitCatalog", 10_234L);
    long sourceCount = 0;
    long catalogCount = 0;
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) {
        var unit = cursor.next();
        sourceCount += unit.sourceFiles().size();
        catalogCount += unit.sourceUnitCatalog().size();
      }
    }
    assertThat(sourceCount).isEqualTo(10_234);
    assertThat(catalogCount).isEqualTo(10_234);
    assertThatThrownBy(content::toArtifact).isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void independentCallsCrossLegacyLimitWithoutResetOrMergeAndReplayExactly() throws Exception {
    for (int size : new int[] {10_000, 10_001, 10_234}) {
      List<SourceRecord> records =
          IntStream.range(0, size)
              .mapToObj(
                  i ->
                      new SourceRecord(
                              "synthetic/events#event[" + i + "]",
                              i,
                              "assistant",
                              java.util.Optional.of("call-" + i),
                              java.util.Optional.of("synthetic-model"),
                              java.util.Optional.empty(),
                              java.util.Optional.of("shared-turn"),
                              com.feipi.session.browser.domain.source.SourceRecordUsage.empty(),
                              List.of(
                                  new com.feipi.session.browser.domain.source.SourceToolCall(
                                      "tool-" + i, "synthetic-tool", "{}")),
                              java.util.Optional.empty(),
                              java.util.Optional.empty(),
                              java.util.Optional.empty(),
                              com.feipi.session.browser.domain.source.SourceRecordRelation.empty(),
                              "answer-" + i)
                          .withMessageRole(java.util.Optional.of("assistant")))
              .toList();
      var engine = new NormalizationEngine();
      if (size > 10_000) {
        assertThatThrownBy(
                () -> engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of()))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("calls size");
      }
      var content = engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
      assertThat(content.header().totals())
          .containsEntry("calls", (long) size)
          .containsEntry("toolExecutions", (long) size);
      for (int replay = 0; replay < 2; replay++) {
        long count = 0;
        long unitIndex = 0;
        long tools = 0;
        try (var cursor = content.openCursor()) {
          while (cursor.hasNext()) {
            var unit = cursor.next();
            assertThat(unit.unitIndex()).isEqualTo(unitIndex++);
            tools += unit.toolExecutions().size();
            assertThat(unit.calls().size()).isLessThanOrEqualTo(10_000);
            for (var call : unit.calls()) {
              assertThat(call.callIndex()).isEqualTo(++count);
              assertThat(call.callId()).isEqualTo("call-" + (count - 1));
              assertThat(call.turnId()).contains("shared-turn");
              assertThat(call.response().toolCallIds()).containsExactly("tool-" + (count - 1));
            }
          }
        }
        assertThat(count).isEqualTo(size);
        assertThat(tools).isEqualTo(size);
      }
    }
  }
}
