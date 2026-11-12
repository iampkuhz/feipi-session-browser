package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.Random;
import org.junit.jupiter.api.Test;

/** 对照旧列表路径的完整对象，保留文本 occurrence、关系和 header 的精确语义。 */
class ManagedNormalizationParityTest {
  @Test
  void recordedTailResultsRemainIndependentOfMissingConsumersIncludingEmptyBodies()
      throws Exception {
    for (String body : List.of("synthetic tail result", "")) {
      for (boolean managed : List.of(false, true)) {
        var records =
            List.of(
                record(0, "main", "assistant", "declaring response", "declare"),
                record(1, "main", "tool_result", body, "result"));
        try (var sequence = SourceRecordSequence.fromList(records)) {
          var engine = new NormalizationEngine();
          var content =
              managed
                  ? engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of())
                  : engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
          var artifact = content.toArtifact();
          assertThat(artifact.calls()).hasSize(1);
          assertThat(artifact.toolExecutions()).hasSize(1);
          var tool = artifact.toolExecutions().getFirst();
          assertThat(tool.resultConsumedByCallId()).isEmpty();
          assertThat(artifact.calls().getFirst().request().toolResultIds()).isEmpty();
          assertThat(artifact.calls().getFirst().sourceUnits())
              .noneMatch(unit -> "tool_result".equals(unit.get("type")));
          assertThat(artifact.session().get("consumedResults")).isEqualTo(0);
          assertThat(content.header().totals().get("sourceUnitCatalog")).isEqualTo(1L);
          assertThat(artifact.sourceUnitCatalog().values())
              .singleElement()
              .satisfies(
                  entry -> {
                    assertThat(entry.unitType()).isEqualTo("tool_result");
                    assertThat(entry.label()).contains(tool.toolCallId());
                    assertThat(entry.text()).contains(body);
                  });
          assertThat(content.toArtifact()).isEqualTo(artifact);
        }
      }
    }
  }

  @Test
  void onlyAnActualFollowingFrameConsumesTheRecordedResult() throws Exception {
    var records =
        List.of(
            record(0, "main", "assistant", "declaring response", "declare"),
            record(1, "main", "tool_result", "synthetic result", "result"),
            SourceRecord.of("synthetic/main#event[2]", 2, "assistant"));
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var engine = new NormalizationEngine();
      for (var content :
          List.of(
              engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()),
              engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of()))) {
        var artifact = content.toArtifact();
        var tool = artifact.toolExecutions().getFirst();
        assertThat(tool.resultConsumedByCallId()).contains(artifact.calls().getLast().callId());
        assertThat(artifact.calls().getFirst().request().toolResultIds()).isEmpty();
        assertThat(artifact.calls().getLast().request().toolResultIds())
            .containsExactly(tool.toolCallId());
        assertThat(artifact.sourceUnitCatalog().values())
            .singleElement()
            .satisfies(entry -> assertThat(entry.text()).contains("synthetic result"));
      }
    }
  }

  @Test
  void globalRelationsBodiesErrorsUnknownTimingAndRepeatedIdsMatchLegacyTwice() throws Exception {
    var records = new ArrayList<SourceRecord>();
    records.add(record(0, "main", "user", "question", "u"));
    records.add(record(1, "child", "assistant", "child answer", "child-call"));
    records.add(record(2, "main", "tool_use", "", "shared-tool"));
    records.add(record(3, "main", "assistant", "same body", "token_count:close"));
    records.add(record(4, "main", "response_item", "late response", "late"));
    records.add(record(5, "main", "tool_result", "result one", "result"));
    records.add(record(6, "main", "tool_result", "result two", "result"));
    records.add(record(7, "main", "assistant", "same body", "same-call-7"));
    records.add(record(8, "main", "assistant", "", "same-call-8"));
    records.add(record(9, "main", "tool_use", "", "shared-tool"));
    records.add(record(10, "main", "response_item", "EOF response", "late"));
    records.add(record(11, "main", "unknown-type", "not retained", "unknown"));
    records.add(record(12, "main", "unknown-type", "not retained twice", "unknown"));
    records.add(record(13, "main", "task", "", "task"));
    records.add(record(14, "main", "task", "", "task"));
    compare(records);
  }

  @Test
  void deterministicInterleavingMatchesLegacyWithoutBodyDeduplication() throws Exception {
    for (int seed = 0; seed < 24; seed++) {
      Random random = new Random(seed);
      var records = new ArrayList<SourceRecord>();
      String[] types = {"assistant", "user", "response_item", "tool_use", "tool_result", "neutral"};
      for (int index = 0; index < 45; index++) {
        String type = types[random.nextInt(types.length)];
        String scope = random.nextBoolean() ? "main" : "child";
        // 保留全部随机记录，但先显式闭合旧段；未完成工具段另有严格失败回归。
        if ("user".equals(type)) {
          records.add(
              record(records.size(), scope, "assistant", "segment completion", "close-" + index));
        }
        records.add(
            record(
                records.size(),
                scope,
                type,
                index % 3 == 0 ? "" : "repeated text",
                index % 5 == 0 ? "token_count:closing-" + index : "call-" + index));
      }
      for (String scope : List.of("main", "child")) {
        records.add(
            record(records.size(), scope, "assistant", "segment completion", "end-" + scope));
      }
      compare(records);
    }
  }

  @Test
  void duplicateCallIdsPreserveContentButBothArtifactPathsRejectThem() throws Exception {
    var records =
        List.of(
            record(0, "main", "assistant", "first occurrence", "duplicate"),
            record(1, "main", "tool_result", "result occurrence", "result"),
            record(2, "main", "assistant", "second occurrence", "duplicate"));
    var engine = new NormalizationEngine();
    var legacy = engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of());
    try (var sequence = SourceRecordSequence.fromList(records)) {
      var managed = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertThat(managed.header()).isEqualTo(legacy.header());
      for (int pass = 0; pass < 2; pass++) {
        var expectedCalls =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedCall>();
        var actualCalls =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedCall>();
        var expectedTools =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedToolExecution>();
        var actualTools =
            new ArrayList<com.feipi.session.browser.domain.normalized.NormalizedToolExecution>();
        try (var cursor = legacy.openCursor()) {
          while (cursor.hasNext()) {
            var unit = cursor.next();
            expectedCalls.addAll(unit.calls());
            expectedTools.addAll(unit.toolExecutions());
          }
        }
        try (var cursor = managed.openCursor()) {
          while (cursor.hasNext()) {
            var unit = cursor.next();
            actualCalls.addAll(unit.calls());
            actualTools.addAll(unit.toolExecutions());
          }
        }
        assertThat(actualCalls).isEqualTo(expectedCalls);
        assertThat(actualTools).isEqualTo(expectedTools);
      }
      assertThatThrownBy(legacy::toArtifact).isInstanceOf(IllegalArgumentException.class);
      assertThatThrownBy(managed::toArtifact).isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void locatedReadsAreLinearAndFailuresAreNotEmptySuccess() throws Exception {
    var records = new ArrayList<SourceRecord>();
    for (int i = 0; i < 80; i++)
      records.add(record(i, "main", "assistant", "body-" + i, "call-" + i));
    var engine = new NormalizationEngine();
    var sequence = new TrackingSequence(records);
    try {
      var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      assertThat(sequence.reads).isEqualTo(records.size());
      assertThat(content.toArtifact())
          .isEqualTo(engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of()));
      assertThat(sequence.reads).isEqualTo(records.size() * 2);
      assertThat(sequence.starts.stream().filter(value -> value > 0).count()).isEqualTo(79);
      sequence.broken = true;
      assertThatThrownBy(content::toArtifact)
          .isInstanceOf(IOException.class)
          .hasMessageContaining("corrupt");
      sequence.broken = false;
      var cursor = content.openCursor();
      try {
        cursor.close();
        assertThatThrownBy(cursor::hasNext).isInstanceOf(IOException.class);
      } finally {
        cursor.close();
      }
      sequence.close();
      assertThatThrownBy(content::toArtifact)
          .isInstanceOf(IOException.class)
          .hasMessageContaining("closed");
    } finally {
      sequence.close();
    }
  }

  @Test
  void unsupportedManagedProviderIsExplicitlyRejected() throws Exception {
    try (var sequence = SourceRecordSequence.fromList(List.of())) {
      assertThatThrownBy(
              () ->
                  new NormalizationEngine()
                      .normalizeContent(NormalizedAgent.QODER, sequence, List.of(), List.of()))
          .isInstanceOf(IllegalArgumentException.class)
          .hasMessageContaining("CODEX");
    }
  }

  private static void compare(List<SourceRecord> records) throws Exception {
    var engine = new NormalizationEngine();
    var expected = engine.normalize(NormalizedAgent.CODEX, records, List.of(), List.of());
    try (var sequence = new TrackingSequence(records)) {
      var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), List.of());
      var expectedHeader =
          engine.normalizeContent(NormalizedAgent.CODEX, records, List.of(), List.of()).header();
      assertThat(content.header()).isEqualTo(expectedHeader);
      for (int pass = 0; pass < 2; pass++) assertThat(content.toArtifact()).isEqualTo(expected);
      assertThat(sequence.closed).isFalse();
    }
  }

  private static SourceRecord record(
      int index, String scope, String type, String text, String callId) {
    var relation =
        "child".equals(scope)
            ? new SourceRecordRelation(
                Optional.of("child"),
                Optional.empty(),
                Optional.of("shared-tool"),
                Optional.empty(),
                Optional.of("spawn_agent"))
            : SourceRecordRelation.empty();
    SourceTiming timing =
        "task".equals(type)
            ? new SourceTiming(
                index % 2 == 1 ? "task_started" : "task_complete",
                "task-turn",
                Optional.of("2026-01-01T00:00:00Z"),
                Optional.of("2026-01-01T00:00:02Z"),
                OptionalLong.of(2000),
                OptionalLong.of(1000),
                OptionalLong.of(500),
                "event-" + index)
            : SourceTiming.empty();
    return new SourceRecord(
        "synthetic/" + scope + "#event[" + index + "]",
        index,
        type,
        Optional.of(callId),
        Optional.of("synthetic-model"),
        Optional.of("2026-01-01T00:00:01Z"),
        Optional.of("turn-" + index % 2),
        new SourceRecordUsage(index % 4, 2, 1, index % 3),
        List.of("assistant", "tool_use").contains(type)
            ? List.of(
                new SourceToolCall("shared-tool", "synthetic-tool", "{\"index\":" + index + "}"))
            : List.of(),
        "tool_result".equals(type) ? Optional.of("shared-tool") : Optional.empty(),
        "tool_use".equals(type) ? Optional.of("synthetic-tool") : Optional.empty(),
        "tool_result".equals(type) || "tool_use".equals(type)
            ? Optional.of("error-" + index)
            : Optional.empty(),
        relation,
        text,
        Optional.empty(),
        Optional.empty(),
        timing,
        false,
        List.of("assistant", "user").contains(type) ? Optional.of(type) : Optional.empty());
  }

  private static final class TrackingSequence implements SourceRecordSequence {
    private final List<SourceRecord> records;
    private final List<Long> starts = new ArrayList<>();
    private int reads;
    private boolean closed;
    private boolean broken;

    private TrackingSequence(List<SourceRecord> records) {
      this.records = List.copyOf(records);
    }

    @Override
    public long recordCount() {
      return records.size();
    }

    @Override
    public RecordCursor openCursor(long ordinal) throws IOException {
      if (closed) throw new IOException("closed sequence");
      if (ordinal < 0 || ordinal > records.size()) throw new IllegalArgumentException("ordinal");
      starts.add(ordinal);
      return new RecordCursor() {
        private int position = (int) ordinal;
        private boolean cursorClosed;

        @Override
        public boolean hasNext() throws IOException {
          if (closed || cursorClosed) throw new IOException("closed cursor");
          if (broken) throw new IOException("corrupt sequence");
          return position < records.size();
        }

        @Override
        public SourceRecord next() throws IOException {
          if (!hasNext()) throw new NoSuchElementException();
          reads++;
          return records.get(position++);
        }

        @Override
        public void close() {
          cursorClosed = true;
        }
      };
    }

    @Override
    public void close() {
      closed = true;
    }
  }
}
