package com.feipi.session.browser.domain.normalized;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Collections;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class NormalizedSessionContentTest {
  @Test
  void legacyViewRetainsIdentityAndReplacementHeaderWithoutOpeningCursor() {
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of("session_key", "synthetic"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var content = NormalizedSessionContent.fromArtifact(artifact);
    assertThat(content.legacyArtifact()).containsSame(artifact);
    var replacement =
        new NormalizedContentHeader(
            content.header().schemaVersion(),
            content.header().agent(),
            NormalizedSessionMetadata.fromMap(Map.of("session_key", "replacement")),
            content.header().totals());
    NormalizedSessionContent trap =
        new NormalizedSessionContent() {
          @Override
          public NormalizedContentHeader header() {
            return content.header();
          }

          @Override
          public ContentCursor openCursor() {
            throw new AssertionError("must not read cursor");
          }

          @Override
          public java.util.Optional<NormalizedSessionArtifact> legacyArtifact() {
            return java.util.Optional.of(artifact);
          }
        };
    var changed = trap.withHeader(replacement);
    assertThat(changed.header()).isSameAs(replacement);
    var view = changed.legacyArtifact().orElseThrow();
    assertThat(view.session()).isEqualTo(replacement.session());
    assertThat(view.calls()).isSameAs(artifact.calls());
    assertThat(view.toolExecutions()).isSameAs(artifact.toolExecutions());
    assertThat(view.sourceFiles()).isSameAs(artifact.sourceFiles());
    assertThat(changed.withHeader(content.header()).legacyArtifact().orElseThrow().session())
        .isEqualTo(artifact.session());
  }

  @Test
  void smallTotalsAndFromListsDoNotClaimExistingLegacyArtifact() {
    var header =
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            NormalizedSessionMetadata.fromMap(Map.of("session_key", "synthetic")),
            ListSessionContent.totals(
                List.of(), List.of(), List.of(), List.of(), Map.of(), Map.of()));
    var lists =
        NormalizedSessionContent.fromLists(
            header, List.of(), List.of(), List.of(), List.of(), Map.of(), Map.of());
    assertThat(lists.legacyArtifact()).isEmpty();
    assertThat(lists.withHeader(header).legacyArtifact()).isEmpty();
    NormalizedSessionContent stream =
        new NormalizedSessionContent() {
          @Override
          public NormalizedContentHeader header() {
            return header;
          }

          @Override
          public ContentCursor openCursor() {
            throw new AssertionError("must not read cursor");
          }
        };
    assertThat(stream.legacyArtifact()).isEmpty();
    assertThat(stream.withHeader(header).legacyArtifact()).isEmpty();
  }

  @Test
  void emptyLegacyWrapperIsReplayableAndHeaderCanBeReplaced() throws Exception {
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of("session_key", "synthetic"),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    var content = NormalizedSessionContent.fromArtifact(artifact);
    assertThat(content.header().totals())
        .containsEntry("calls", 0L)
        .containsEntry("sourceUnitSequenceEntries", 0L)
        .hasSize(6);
    for (int replay = 0; replay < 2; replay++) {
      try (var cursor = content.openCursor()) {
        assertThat(cursor.hasNext()).isTrue();
        assertThat(cursor.next().unitIndex()).isZero();
        assertThat(cursor.hasNext()).isFalse();
        assertThatThrownBy(cursor::next).isInstanceOf(java.util.NoSuchElementException.class);
      }
    }
    assertThat(content.withHeader(content.header()).header()).isEqualTo(content.header());
    assertThat(content.toArtifact()).isEqualTo(artifact);
  }

  @Test
  void sequenceAndDiagnosticsPartitionWithoutDuplicationOrOffsetReset() throws Exception {
    var diagnostics =
        java.util.stream.IntStream.range(0, 10_234)
            .mapToObj(i -> NormalizedDiagnostic.fromMap(Map.of("message", "diagnostic-" + i)))
            .toList();
    var keys = java.util.stream.IntStream.range(0, 10_234).mapToObj(i -> "key-" + i).toList();
    var header =
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            NormalizedSessionMetadata.fromMap(Map.of("session_key", "synthetic")),
            Map.of(
                "calls",
                0L,
                "toolExecutions",
                0L,
                "diagnostics",
                10_234L,
                "sourceFiles",
                0L,
                "sourceUnitCatalog",
                0L,
                "sourceUnitSequenceEntries",
                10_234L));
    var content =
        NormalizedSessionContent.fromLists(
            header, List.of(), List.of(), List.of(), diagnostics, Map.of(), Map.of("events", keys));
    for (int replay = 0; replay < 2; replay++) {
      long offset = 0;
      long diagnosticCount = 0;
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          var unit = cursor.next();
          diagnosticCount += unit.diagnostics().size();
          assertThat(unit.diagnostics().size()).isLessThanOrEqualTo(10_000);
          for (var chunk : unit.sourceUnitSequences()) {
            assertThat(chunk.offset()).isEqualTo(offset);
            for (var key : chunk.keys()) {
              assertThat(key).isEqualTo("key-" + offset++);
            }
          }
        }
      }
      assertThat(offset).isEqualTo(10_234);
      assertThat(diagnosticCount).isEqualTo(10_234);
    }
  }

  @Test
  void unitAndSequenceRetainExistingCollectionLimit() {
    assertThatThrownBy(
            () -> new NormalizedSequenceChunk("events", 0, Collections.nCopies(10_001, "key")))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () ->
                new NormalizedContentUnit(
                    0,
                    List.of(),
                    List.of(),
                    List.of(),
                    List.of(),
                    Map.of(),
                    Collections.nCopies(
                        10_001, new NormalizedSequenceChunk("events", 0, List.of()))))
        .isInstanceOf(IllegalArgumentException.class);
    assertThat(
            new NormalizedSequenceChunk("events", 10_000, Collections.nCopies(10_000, "key"))
                .offset())
        .isEqualTo(10_000);
  }
}
