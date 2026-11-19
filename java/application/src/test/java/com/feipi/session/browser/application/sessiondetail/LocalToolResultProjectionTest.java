package com.feipi.session.browser.application.sessiondetail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** synthetic：消费 v200/v201 已验证的普通/managed 同源键载体，不重新运行 normalization。 */
class LocalToolResultProjectionTest {
  @TempDir Path directory;

  @Test
  void preservesPositionsMirrorsAndEveryConfirmedCallWithoutScalarConsumer() throws Exception {
    String key = key(1);
    var artifact =
        artifact(
            List.of(
                owner(),
                call(2, List.of(key, key), List.of(inline(key, "SAME"))),
                call(3, List.of(key(2)), List.of()),
                call(4, List.of(key), List.of())),
            List.of(tool("c1")),
            List.of(entry(2, "SAME"), entry(1, "SAME")),
            Map.of());
    var reader = new SessionContentReader(NormalizedSessionContent.fromArtifact(artifact), 0);
    var results = reader.localResults("tool:result:t", PayloadVisibility.FULL);
    assertThat(results.occurrences()).hasSize(2);
    assertThat(results.occurrences())
        .extracting(item -> item.content().text())
        .containsExactly("SAME", "SAME");
    var first = results.occurrences().getFirst();
    var second = results.occurrences().getLast();
    assertThat(first.occurrenceId())
        .isNotEqualTo(second.occurrenceId())
        .doesNotContain("synthetic");
    var relations = reader.localResultRelations(first.occurrenceId(), 0, 20, null);
    assertThat(relations.coverage()).isEqualTo("complete");
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::callId)
        .containsExactly("c2", "c2", "c4");
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::recordIndex)
        .containsExactly(2, 2, 4);
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::scope)
        .containsOnly("main");
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::referenceId)
        .doesNotHaveDuplicates();
    var input = reader.localResults("main:req:c2", PayloadVisibility.FULL);
    assertThat(input.references()).hasSize(2);
    assertThat(input.references()).allMatch(ref -> ref.occurrenceId().equals(first.occurrenceId()));
    assertThat(reader.localResultRelations(second.occurrenceId(), 0, 20, null).targets())
        .extracting(PayloadLookup.ResultTarget::callId)
        .containsExactly("c3");
    assertThat(reader.localResultRelations(second.occurrenceId(), 0, 20, null).targets())
        .extracting(PayloadLookup.ResultTarget::recordIndex)
        .containsExactly(3);
  }

  @Test
  void anchoredInlineOnlyAndUnanchoredInlineAreNotGuessedFromTextOrBareId() throws Exception {
    var artifact =
        artifact(
            List.of(
                owner(), call(2, List.of(), List.of(inline(key(1), "SAME"), inline("", "SAME")))),
            List.of(tool("c1")),
            List.of(),
            Map.of());
    var reader = new SessionContentReader(NormalizedSessionContent.fromArtifact(artifact), 0);
    var results = reader.localResults("tool:result:t", PayloadVisibility.FULL);
    assertThat(results.occurrences())
        .extracting(PayloadLookup.LocalResultOccurrence::identity)
        .containsExactly("confirmed", "unconfirmed");
    assertThat(
            reader
                .localResultRelations(results.occurrences().getFirst().occurrenceId(), 0, 20, null)
                .targets())
        .hasSize(1);
    var unconfirmed =
        reader.localResultRelations(results.occurrences().getLast().occurrenceId(), 0, 20, null);
    assertThat(unconfirmed.coverage()).isEqualTo("unknown");
    assertThat(unconfirmed.targets()).isEmpty();
    assertThat(
            reader
                .localResults("main:req:c2", PayloadVisibility.FULL)
                .references()
                .getLast()
                .occurrenceId())
        .isEmpty();
  }

  @Test
  void eofExplicitEmptyAndMissingRemainDifferentWithoutInventingTargets() throws Exception {
    var missing = entry(3, null);
    var artifact =
        artifact(
            List.of(owner()),
            List.of(tool("unknown")),
            List.of(entry(1, "EOF"), entry(2, ""), missing),
            Map.of());
    var reader = new SessionContentReader(NormalizedSessionContent.fromArtifact(artifact), 0);
    var results = reader.localResults("tool:result:t", PayloadVisibility.FULL);
    assertThat(results.occurrences())
        .extracting(item -> item.content().state())
        .containsExactly("available", "available", "missing");
    assertThat(results.occurrences().get(1).content().text()).isEmpty();
    for (var item : results.occurrences()) {
      var relations = reader.localResultRelations(item.occurrenceId(), 0, 20, null);
      assertThat(relations.coverage()).isEqualTo("complete");
      assertThat(relations.targets()).isEmpty();
    }
  }

  @Test
  void conflictsDuplicatesAndCrossContextCannotSelectFirstOrLastIdentity() throws Exception {
    var cross = call(2, List.of(key(1)), List.of());
    var subagent =
        new NormalizedCall(
            cross.callId(),
            cross.callIndex(),
            cross.callKey(),
            CallScope.SUBAGENT,
            Optional.of("c1"),
            Optional.of("parent"),
            Optional.empty(),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            cross.sourceUnitRefRanges(),
            List.of(),
            Map.of(),
            Map.of(),
            Optional.of("child"),
            Optional.empty());
    for (String mutation : List.of("text", "tool", "call", "context", "catalog")) {
      var calls =
          new ArrayList<>(
              List.of(
                  owner(),
                  call(
                      2,
                      List.of(key(1)),
                      mutation.equals("text") ? List.of(inline(key(1), "CONFLICT")) : List.of())));
      if (mutation.equals("call")) calls.add(calls.getLast());
      if (mutation.equals("context")) calls.set(1, subagent);
      var tools =
          mutation.equals("tool") ? List.of(tool("c1"), tool("unknown")) : List.of(tool("c1"));
      var base =
          artifact(List.of(owner()), List.of(tool("c1")), List.of(entry(1, "VALUE")), Map.of());
      NormalizedSessionContent content =
          replay(
              NormalizedSessionContent.fromArtifact(base),
              List.of(unit(0, calls, tools, Map.of(key(1), entry(1, "VALUE")))));
      if (mutation.equals("catalog")) {
        content =
            replay(
                content,
                List.of(
                    unit(0, calls, tools, Map.of(key(1), entry(1, "VALUE"))),
                    unit(1, List.of(), List.of(), Map.of(key(1), entry(1, "OTHER")))));
      }
      var reader = LocalToolResultProjection.build(content);
      var occurrence =
          reader
              .read("tool:result:t", 0, 20, null, PayloadVisibility.FULL)
              .occurrences()
              .getFirst();
      assertThat(occurrence.identity()).as(mutation).isEqualTo("ambiguous");
      var relations = reader.relations(occurrence.occurrenceId(), 0, 20, null);
      assertThat(relations.targets()).as(mutation).isEmpty();
      assertThat(relations.coverage()).as(mutation).isEqualTo("unknown");
    }
  }

  @Test
  void sequenceAndExactLateReferenceWindowDoNotWalkPrefixes() throws Exception {
    var keys = java.util.Collections.nCopies(45, key(1));
    var sequenceCall = call(2, List.of(), List.of());
    sequenceCall =
        new NormalizedCall(
            sequenceCall.callId(),
            2,
            "C2",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            List.of(
                new SourceUnitRefRange(
                    Optional.of("sequence"), 0, 45, List.of(), Optional.of("user"))),
            List.of(),
            Map.of(),
            Map.of());
    var content =
        NormalizedSessionContent.fromArtifact(
            artifact(
                List.of(owner(), sequenceCall),
                List.of(tool("c1")),
                List.of(entry(1, "VALUE")),
                Map.of("sequence", keys)));
    var opens = new AtomicInteger();
    var reader = new SessionContentReader(counted(content, opens), 0);
    int before = opens.get();
    var occurrence =
        reader.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    assertThat(opens.get() - before).isEqualTo(3); // 两轮 metadata，一次所选正文重放
    var relations = reader.localResultRelations(occurrence.occurrenceId(), 40, 20, null);
    assertThat(relations.targets()).hasSize(5);
    var allTargets = reader.localResultRelations(occurrence.occurrenceId(), 0, 100, null).targets();
    assertThat(allTargets).hasSize(45);
    assertThat(allTargets).extracting(PayloadLookup.ResultTarget::recordIndex).containsOnly(2);
    assertThat(allTargets).extracting(PayloadLookup.ResultTarget::scope).containsOnly("main");
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::recordIndex)
        .containsOnly(2);
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::scope)
        .containsOnly("main");
    var target = relations.targets().getLast().target();
    var precise = reader.localResults("main:req:c2", 0, 20, target, PayloadVisibility.FULL);
    assertThat(precise.offset()).isEqualTo(40);
    assertThat(precise.references()).hasSize(5);
    assertThat(precise.references().getLast().position()).isEqualTo(44);
    assertThat(precise.references().getLast().referenceId()).isEqualTo(target);
    assertThat(opens.get() - before).isEqualTo(4); // 后续只读正文，不重建 metadata
    assertThat(reader.localResultRelations(occurrence.occurrenceId(), 0, 20, target).offset())
        .isEqualTo(40);
    assertThatThrownBy(
            () -> reader.localResults("main:req:c2", 0, 101, null, PayloadVisibility.FULL))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> reader.localResults("main:req:c1", 0, 20, target, PayloadVisibility.FULL))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void defaultReadAddsNoProjectionAndSingleBulkMaterializedShareSafety() throws Exception {
    String text = "{\"api_key\":\"synthetic-secret\",\"output\":\"VALUE\"}";
    var artifact =
        artifact(
            List.of(owner(), call(2, List.of(key(1)), List.of(inline(key(1), text)))),
            List.of(tool("c1")),
            List.of(entry(1, text)),
            Map.of());
    var opens = new AtomicInteger();
    var content = counted(NormalizedSessionContent.fromArtifact(artifact), opens);
    var reader = new SessionContentReader(content, 0);
    reader.payload("tool:result:t", PayloadVisibility.FULL);
    int ordinary = opens.get();
    var another = new SessionContentReader(content, 0);
    assertThat(opens.get() - ordinary).isEqualTo(1); // 原生 round index，无新投影
    for (var visibility : PayloadVisibility.values()) {
      var page = another.localResults("tool:result:t", visibility);
      var item = page.occurrences().getFirst();
      var single = item.content();
      int beforeMembership = opens.get();
      assertThat(another.localResultBelongsToPayload("tool:result:t", item.occurrenceId()))
          .isTrue();
      assertThat(another.localResultBelongsToPayload("tool:result:other", item.occurrenceId()))
          .isFalse();
      assertThat(another.localResultBelongsToPayload("main:req:c2", item.occurrenceId())).isTrue();
      assertThat(another.localResultBelongsToPayload("main:req:c1", item.occurrenceId())).isFalse();
      assertThat(another.localResultBelongsToPayload("main:resp:c2", item.occurrenceId()))
          .isFalse();
      assertThat(another.localResultBelongsToPayload("tool:result:t", "missing")).isFalse();
      assertThat(opens.get()).isEqualTo(beforeMembership); // 已建元数据复用，不重读正文
      var materialized =
          PayloadLookup.localResultReader(artifact)
              .localResults("tool:result:t", 0, 20, null, visibility)
              .occurrences()
              .getFirst()
              .content();
      assertThat(materialized).isEqualTo(single);
      try (var bulk = ExportPayloadLookup.build(content, directory)) {
        int before = opens.get();
        var projection = LocalToolResultProjection.build(content);
        assertThat(opens.get() - before).isEqualTo(2);
        var projected = projection.read("tool:result:t", 0, 20, null, visibility, bulk);
        assertThat(projected.occurrences().getFirst().content()).isEqualTo(single);
        assertThat(opens.get() - before).isEqualTo(2); // 正文随机读私有 offset，不新增 cursor
      }
      try (var files = Files.list(directory)) {
        assertThat(files.toList()).isEmpty();
      }
      assertThat(single.truncated()).isFalse();
      assertThat(single.text().contains("synthetic-secret"))
          .isEqualTo(visibility == PayloadVisibility.FULL);
    }
  }

  @Test
  void defaultTwentyAndExplicitHundredPreserveLaterOccurrences() throws Exception {
    var entries =
        java.util.stream.IntStream.rangeClosed(1, 125).mapToObj(i -> entry(i, "R" + i)).toList();
    var reader =
        new SessionContentReader(
            NormalizedSessionContent.fromArtifact(
                artifact(List.of(owner()), List.of(tool("c1")), entries, Map.of())),
            0);
    assertThat(reader.localResults("tool:result:t", PayloadVisibility.FULL).occurrences())
        .hasSize(20);
    var last = reader.localResults("tool:result:t", 100, 100, null, PayloadVisibility.FULL);
    assertThat(last.occurrences()).hasSize(25);
    var target = last.occurrences().getLast().occurrenceId();
    var precise = reader.localResults("tool:result:t", 0, 20, target, PayloadVisibility.FULL);
    assertThat(precise.offset()).isEqualTo(120);
    assertThat(precise.occurrences().getLast().content().text()).isEqualTo("R125");
    assertThat(reader.payload("tool:result:t", PayloadVisibility.FULL).orElseThrow().content())
        .endsWith("R125");
  }

  @Test
  void missingExplicitReferencesAndSequencesCannotClaimNoRecordedInclusion() throws Exception {
    for (boolean sequence : List.of(false, true)) {
      var call = call(2, List.of("absent"), List.of());
      if (sequence)
        call =
            new NormalizedCall(
                call.callId(),
                2,
                "C2",
                CallScope.MAIN,
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                "synthetic",
                Optional.empty(),
                NormalizedCallUsage.empty(),
                NormalizedCallRequest.empty(),
                NormalizedCallResponse.empty(),
                List.of(
                    new SourceUnitRefRange(
                        Optional.of("absent"), 0, 1, List.of(), Optional.empty())),
                List.of(),
                Map.of(),
                Map.of());
      var reader =
          new SessionContentReader(
              NormalizedSessionContent.fromArtifact(
                  artifact(
                      List.of(owner(), call),
                      List.of(tool("c1")),
                      List.of(entry(1, "EOF")),
                      Map.of())),
              0);
      var results = reader.localResults("tool:result:t", PayloadVisibility.FULL);
      assertThat(results.coverage()).isEqualTo("unknown");
      assertThat(
              reader
                  .localResultRelations(
                      results.occurrences().getFirst().occurrenceId(), 0, 20, null)
                  .coverage())
          .isEqualTo("unknown");
    }
  }

  @Test
  void metadataItemStringAndTotalBudgetsRefuseCompletenessWithoutCountingBody() throws Exception {
    var base =
        NormalizedSessionContent.fromArtifact(
            artifact(
                List.of(owner()),
                List.of(tool("c1")),
                List.of(entry(1, "X".repeat(4_194_305))),
                Map.of()));
    var normal =
        LocalToolResultProjection.build(base)
            .read("tool:result:t", 0, 20, null, PayloadVisibility.FULL);
    assertThat(normal.coverage()).isEqualTo("complete");
    assertThat(normal.occurrences().getFirst().content().text()).hasSize(4_194_305);
    for (String budget : List.of("call", "tool", "catalog", "string", "total")) {
      var units = new ArrayList<NormalizedContentUnit>();
      units.add(unit(0, List.of(owner()), List.of(tool("c1")), Map.of(key(1), entry(1, "VALUE"))));
      int count = budget.equals("string") ? 1 : budget.equals("total") ? 5000 : 16_384;
      for (int i = 0; i < count; i++) {
        String id = "extra" + i;
        var extra =
            new NormalizedToolExecution(
                id,
                budget.equals("string")
                    ? "x".repeat(1025)
                    : budget.equals("total") ? "x".repeat(900) : "synthetic",
                CallScope.MAIN,
                "unknown",
                Optional.empty(),
                Optional.empty(),
                Optional.empty(),
                0,
                List.of(),
                Optional.empty());
        units.add(
            unit(
                i + 1,
                budget.equals("call") ? List.of(owner()) : List.of(),
                budget.equals("tool") || budget.equals("string") || budget.equals("total")
                    ? List.of(extra)
                    : List.of(),
                budget.equals("catalog") ? Map.of(id, entry(i + 2, "VALUE")) : Map.of()));
      }
      var opens = new AtomicInteger();
      var projection = LocalToolResultProjection.build(counted(replay(base, units), opens));
      assertThat(opens.get()).as(budget).isEqualTo(1);
      var results = projection.read("tool:result:t", 0, 20, null, PayloadVisibility.FULL);
      assertThat(results.coverage()).as(budget).isEqualTo("unknown");
      assertThat(results.reason())
          .as(budget)
          .contains(
              budget.equals("total") || budget.equals("string")
                  ? "metadata_string_budget"
                  : budget + "_budget");
    }
  }

  @Test
  void exactTargetsRebuildAcrossIndependentMaterializedStreamingAndBulkReaders() throws Exception {
    var artifact =
        artifact(
            List.of(
                owner(),
                call(
                    2,
                    java.util.Collections.nCopies(45, key(1)),
                    List.of(inline(key(1), "VALUE")))),
            List.of(tool("c1")),
            List.of(entry(1, "VALUE")),
            Map.of());
    var content = NormalizedSessionContent.fromArtifact(artifact);
    var first = new SessionContentReader(content, 0);
    var occurrence =
        first.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    var target =
        first.localResultRelations(occurrence.occurrenceId(), 40, 20, null).targets().getLast();
    var second = new SessionContentReader(content, 0);
    assertThat(
            second
                .localResults("tool:result:t", PayloadVisibility.STANDARD)
                .occurrences()
                .getFirst()
                .occurrenceId())
        .isEqualTo(occurrence.occurrenceId());
    assertThat(
            second.localResultRelations(occurrence.occurrenceId(), 0, 20, target.target()).offset())
        .isEqualTo(40);
    assertThat(
            second
                .localResults(
                    target.requestPayloadId(), 0, 20, target.target(), PayloadVisibility.FULL)
                .references()
                .getLast()
                .referenceId())
        .isEqualTo(target.referenceId());
    var materialized = PayloadLookup.localResultReader(artifact);
    assertThat(
            materialized
                .localResults("tool:result:t", PayloadVisibility.FULL)
                .occurrences()
                .getFirst()
                .occurrenceId())
        .isEqualTo(occurrence.occurrenceId());
    var projection = LocalToolResultProjection.build(content);
    try (var bulk = ExportPayloadLookup.build(content, directory)) {
      assertThat(
              projection
                  .read(
                      target.requestPayloadId(),
                      0,
                      20,
                      target.target(),
                      PayloadVisibility.FULL,
                      bulk)
                  .references()
                  .getLast()
                  .referenceId())
          .isEqualTo(target.referenceId());
    }
    try (var exported = new SessionContentReader(content, 0).exportPayloads()) {
      assertThat(
              exported
                  .localResultRelations(occurrence.occurrenceId(), 0, 20, target.target())
                  .offset())
          .isEqualTo(40);
      assertThat(
              exported
                  .localResults(
                      target.requestPayloadId(), 0, 20, target.target(), PayloadVisibility.FULL)
                  .references()
                  .getLast()
                  .referenceId())
          .isEqualTo(target.referenceId());
    }
    var streamed =
        replay(
            content,
            List.of(
                unit(0, artifact.calls(), artifact.toolExecutions(), Map.of()),
                unit(1, List.of(), List.of(), artifact.sourceUnitCatalog())));
    var streaming = new SessionContentReader(streamed, 0);
    assertThat(
            streaming
                .localResultRelations(occurrence.occurrenceId(), 0, 20, target.target())
                .offset())
        .isEqualTo(40);
    assertThat(
            streaming
                .localResults(
                    target.requestPayloadId(), 0, 20, target.target(), PayloadVisibility.FULL)
                .references()
                .getLast()
                .referenceId())
        .isEqualTo(target.referenceId());
  }

  @Test
  void completeScopeRebuildsWithoutSessionKeyAndSeparatesImportSourcesAndSessions()
      throws Exception {
    var base =
        artifact(
            List.of(owner(), call(2, List.of(key(1)), List.of())),
            List.of(tool("c1")),
            List.of(entry(1, "VALUE")),
            Map.of());
    var normal =
        withScope(base, "codex:synthetic-a", List.of("synthetic/a.jsonl", "synthetic/b.jsonl"));
    var first = PayloadLookup.localResultReader(normal);
    var occurrence =
        first.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    var target =
        first.localResultRelations(occurrence.occurrenceId(), 0, 20, null).targets().getFirst();
    var reordered =
        PayloadLookup.localResultReader(
            withScope(
                base, "codex:synthetic-a", List.of("synthetic/b.jsonl", "synthetic/a.jsonl")));
    assertThat(
            reordered
                .localResults("tool:result:t", PayloadVisibility.FULL)
                .occurrences()
                .getFirst()
                .occurrenceId())
        .isEqualTo(occurrence.occurrenceId());
    for (var changed :
        List.of(
            withScope(base, "codex:synthetic-b", List.of("synthetic/a.jsonl", "synthetic/b.jsonl")),
            withScope(base, "codex:synthetic-a", List.of("synthetic/other.jsonl")))) {
      var reader = PayloadLookup.localResultReader(changed);
      assertThat(
              reader
                  .localResults("tool:result:t", PayloadVisibility.FULL)
                  .occurrences()
                  .getFirst()
                  .occurrenceId())
          .isNotEqualTo(occurrence.occurrenceId());
      assertThatThrownBy(() -> reader.localResultRelations(occurrence.occurrenceId(), 0, 20, null))
          .isInstanceOf(IllegalArgumentException.class);
      assertThatThrownBy(
              () ->
                  reader.localResults(
                      "main:req:c2", 0, 20, target.target(), PayloadVisibility.FULL))
          .isInstanceOf(IllegalArgumentException.class);
    }
    var imported = withScope(base, "", List.of("imports/synthetic-a/upload.jsonl"));
    var importReader = PayloadLookup.localResultReader(imported);
    var importOccurrence =
        importReader.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    assertThat(importOccurrence.identity()).isEqualTo("confirmed");
    var importTarget =
        importReader
            .localResultRelations(importOccurrence.occurrenceId(), 0, 20, null)
            .targets()
            .getFirst();
    assertThat(
            PayloadLookup.localResultReader(imported)
                .localResults("main:req:c2", 0, 20, importTarget.target(), PayloadVisibility.FULL)
                .references()
                .getFirst()
                .referenceId())
        .isEqualTo(importTarget.referenceId());
    var otherImport =
        PayloadLookup.localResultReader(
            withScope(base, "", List.of("imports/synthetic-b/upload.jsonl")));
    assertThat(
            otherImport
                .localResults("tool:result:t", PayloadVisibility.FULL)
                .occurrences()
                .getFirst()
                .occurrenceId())
        .isNotEqualTo(importOccurrence.occurrenceId());
    assertThatThrownBy(
            () ->
                otherImport.localResults(
                    "main:req:c2", 0, 20, importTarget.target(), PayloadVisibility.FULL))
        .isInstanceOf(IllegalArgumentException.class);
    var unknown =
        PayloadLookup.localResultReader(withScope(base, "", List.of()))
            .localResults("tool:result:t", PayloadVisibility.FULL);
    assertThat(unknown.occurrences().getFirst().content().text()).isEqualTo("VALUE");
    assertThat(unknown.occurrences().getFirst().identity()).isEqualTo("unconfirmed");
    assertThat(unknown.reason()).isEqualTo("missing_content_scope");
  }

  @Test
  void handlesBindActualOwnerContextAndSourceNotBodyOrCollaborationChild() throws Exception {
    var base =
        artifact(
            List.of(owner(), call(2, List.of(key(1)), List.of())),
            List.of(tool("c1")),
            List.of(entry(1, "VALUE")),
            Map.of());
    var first = PayloadLookup.localResultReader(base);
    var occurrence =
        first.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    var target =
        first.localResultRelations(occurrence.occurrenceId(), 0, 20, null).targets().getFirst();
    var changedBody =
        artifact(
            base.calls(), base.toolExecutions(), List.of(entry(1, "DIFFERENT BODY")), Map.of());
    assertThat(
            PayloadLookup.localResultReader(changedBody)
                .localResults("tool:result:t", PayloadVisibility.FULL)
                .occurrences()
                .getFirst()
                .occurrenceId())
        .isEqualTo(occurrence.occurrenceId());
    var ownerUnknown =
        artifact(base.calls(), List.of(tool("unknown")), List.of(entry(1, "VALUE")), Map.of());
    assertThat(
            PayloadLookup.localResultReader(ownerUnknown)
                .localResults("tool:result:t", PayloadVisibility.FULL)
                .occurrences()
                .getFirst()
                .occurrenceId())
        .isNotEqualTo(occurrence.occurrenceId());
    var execution =
        new NormalizedToolExecution(
            "t",
            "synthetic-tool",
            CallScope.SUBAGENT,
            "c1",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            0,
            List.of(),
            Optional.of("unrelated-child"));
    var content = NormalizedSessionContent.fromArtifact(base);
    var subagent =
        replay(
            content,
            List.of(
                unit(
                    0,
                    List.of(subagent(owner()), subagent(base.calls().getLast())),
                    List.of(execution),
                    base.sourceUnitCatalog())));
    var scoped = new SessionContentReader(subagent, 0);
    var scopedOccurrence =
        scoped.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    assertThat(scopedOccurrence.identity()).isEqualTo("confirmed");
    var scopedTargets =
        scoped.localResultRelations(scopedOccurrence.occurrenceId(), 0, 20, null).targets();
    assertThat(scopedTargets)
        .extracting(PayloadLookup.ResultTarget::recordIndex)
        .containsExactly(2);
    assertThat(scopedTargets)
        .extracting(PayloadLookup.ResultTarget::scope)
        .containsExactly("subagent");
    assertThat(scopedOccurrence.occurrenceId()).isNotEqualTo(occurrence.occurrenceId());
    assertThatThrownBy(() -> scoped.localResultRelations(occurrence.occurrenceId(), 0, 20, null))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> scoped.localResults("sa:req:c2", 0, 20, target.target(), PayloadVisibility.FULL))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void declaredMetadataTotalsCannotGrantPrefixQualificationWhenCursorIsIncomplete()
      throws Exception {
    var base =
        NormalizedSessionContent.fromArtifact(
            artifact(
                List.of(owner(), call(2, List.of(key(1)), List.of())),
                List.of(tool("c1")),
                List.of(entry(1, "VALUE")),
                Map.of()));
    for (String field :
        List.of("calls", "toolExecutions", "sourceUnitCatalog", "sourceUnitSequenceEntries")) {
      var totals = new LinkedHashMap<>(base.header().totals());
      totals.put(field, totals.get(field) + 1);
      var incomplete =
          base.withHeader(
              new com.feipi.session.browser.domain.normalized.NormalizedContentHeader(
                  base.header().schemaVersion(),
                  base.header().agent(),
                  base.header().session(),
                  totals));
      var reader = new SessionContentReader(incomplete, 0);
      var page = reader.localResults("tool:result:t", PayloadVisibility.FULL);
      assertThat(page.coverage()).as(field).isEqualTo("unknown");
      assertThat(page.reason()).as(field).isEqualTo("incomplete_metadata:" + field);
      var occurrence = page.occurrences().getFirst();
      assertThat(occurrence.content().text()).as(field).isEqualTo("VALUE");
      assertThat(occurrence.identity()).as(field).isEqualTo("unconfirmed");
      var relations = reader.localResultRelations(occurrence.occurrenceId(), 0, 20, null);
      assertThat(relations.coverage()).as(field).isEqualTo("unknown");
      assertThat(relations.targets()).as(field).isEmpty();
      assertThat(
              reader
                  .localResults("main:req:c2", PayloadVisibility.FULL)
                  .references()
                  .getFirst()
                  .occurrenceId())
          .as(field)
          .isEmpty();
    }
    var missing = new LinkedHashMap<>(base.header().totals());
    missing.remove("calls");
    assertThatThrownBy(
            () ->
                new com.feipi.session.browser.domain.normalized.NormalizedContentHeader(
                    base.header().schemaVersion(),
                    base.header().agent(),
                    base.header().session(),
                    missing))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void inventedInlinePositionCannotAliasAnExplicitCatalogSourceKey() throws Exception {
    var catalog =
        new SourceUnitCatalogEntry(
            "inline:1:0",
            "synthetic.jsonl",
            "synthetic#event[1]",
            "tool_result",
            "",
            SourceUnitDirection.REQUEST,
            1,
            0,
            ByteRange.empty(),
            "",
            Optional.empty(),
            Optional.of("t"),
            50,
            Optional.empty(),
            Optional.of("VALUE"),
            Map.of("type", "tool_result", "tool_call_id", "t"),
            Optional.empty(),
            Optional.empty(),
            List.of());
    var reader =
        PayloadLookup.localResultReader(
            artifact(
                List.of(owner(), call(2, List.of(), List.of(inline("", "VALUE")))),
                List.of(tool("c1")),
                List.of(catalog),
                Map.of()));
    var results = reader.localResults("tool:result:t", PayloadVisibility.FULL);
    assertThat(results.occurrences()).hasSize(2);
    assertThat(results.occurrences())
        .extracting(PayloadLookup.LocalResultOccurrence::occurrenceId)
        .doesNotHaveDuplicates();
    assertThat(results.occurrences())
        .extracting(PayloadLookup.LocalResultOccurrence::identity)
        .containsExactlyInAnyOrder("confirmed", "unconfirmed");
    var input = reader.localResults("main:req:c2", PayloadVisibility.FULL).references().getFirst();
    assertThat(input.occurrenceId()).isEmpty();
    for (var occurrence : results.occurrences()) {
      assertThat(reader.localResultRelations(occurrence.occurrenceId(), 0, 20, null).targets())
          .isEmpty();
    }
  }

  @Test
  void incompleteOrOverBudgetSourceScopeKeepsBodyWithoutNavigationQualification() throws Exception {
    var base =
        withScope(
            artifact(
                List.of(owner(), call(2, List.of(key(1)), List.of())),
                List.of(tool("c1")),
                List.of(entry(1, "VALUE")),
                Map.of()),
            "",
            List.of("imports/synthetic/upload.jsonl"));
    var content = NormalizedSessionContent.fromArtifact(base);
    var incomplete =
        replay(
            content,
            List.of(unit(0, base.calls(), base.toolExecutions(), base.sourceUnitCatalog())));
    var missing =
        LocalToolResultProjection.build(incomplete)
            .read("tool:result:t", 0, 20, null, PayloadVisibility.FULL);
    assertThat(missing.reason()).isEqualTo("incomplete_source_scope");
    assertThat(missing.occurrences().getFirst().content().text()).isEqualTo("VALUE");
    assertThat(missing.occurrences().getFirst().identity()).isEqualTo("unconfirmed");
    var units = new ArrayList<NormalizedContentUnit>();
    units.add(unit(0, base.calls(), base.toolExecutions(), base.sourceUnitCatalog()));
    for (int i = 1; i <= 16_385; i++) {
      var source =
          new com.feipi.session.browser.domain.normalized.NormalizedSourceFile(
              com.feipi.session.browser.domain.normalized.SourceFileRole.TRANSCRIPT,
              Path.of("imports/synthetic/part-" + i + ".jsonl"),
              Optional.empty(),
              Optional.empty());
      units.add(
          new NormalizedContentUnit(
              i, List.of(source), List.of(), List.of(), List.of(), Map.of(), List.of()));
    }
    var capped = LocalToolResultProjection.build(replay(content, units));
    var page = capped.read("tool:result:t", 0, 20, null, PayloadVisibility.FULL);
    assertThat(page.reason()).isEqualTo("source_scope_budget");
    assertThat(page.occurrences().getFirst().content().text()).isEqualTo("VALUE");
    assertThat(page.occurrences().getFirst().identity()).isEqualTo("unconfirmed");
    assertThat(
            capped.relations(page.occurrences().getFirst().occurrenceId(), 0, 20, null).targets())
        .isEmpty();
  }

  private static NormalizedCall subagent(NormalizedCall call) {
    return new NormalizedCall(
        call.callId(),
        call.callIndex(),
        call.callKey(),
        CallScope.SUBAGENT,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        call.usage(),
        call.request(),
        call.response(),
        call.sourceUnitRefRanges(),
        call.sourceUnits(),
        Map.of(),
        Map.of(),
        Optional.of("synthetic-executor"),
        Optional.empty());
  }

  private static NormalizedSessionArtifact withScope(
      NormalizedSessionArtifact base, String key, List<String> paths) {
    var files =
        paths.stream()
            .map(
                path ->
                    new com.feipi.session.browser.domain.normalized.NormalizedSourceFile(
                        com.feipi.session.browser.domain.normalized.SourceFileRole.TRANSCRIPT,
                        Path.of(path),
                        Optional.empty(),
                        Optional.empty()))
            .toList();
    return new NormalizedSessionArtifact(
        base.schemaVersion(),
        base.agent(),
        files,
        key.isEmpty() ? Map.of() : Map.of("session_key", key),
        base.calls(),
        base.toolExecutions(),
        base.diagnostics(),
        base.sourceUnitCatalog(),
        base.sourceUnitSequences());
  }

  @Test
  void missingReferenceRetainsKnownTargetsButCannotClaimCompleteCoverage() throws Exception {
    var reader =
        new SessionContentReader(
            NormalizedSessionContent.fromArtifact(
                artifact(
                    List.of(
                        owner(),
                        call(2, List.of("missing"), List.of()),
                        call(3, List.of(key(1)), List.of())),
                    List.of(tool("c1")),
                    List.of(entry(1, "VALUE")),
                    Map.of())),
            0);
    var missing =
        reader.localResults("main:req:c2", PayloadVisibility.FULL).references().getFirst();
    assertThat(missing.content().state()).isEqualTo("missing");
    assertThat(missing.occurrenceId()).isEmpty();
    var occurrence =
        reader.localResults("tool:result:t", PayloadVisibility.FULL).occurrences().getFirst();
    var relations = reader.localResultRelations(occurrence.occurrenceId(), 0, 20, null);
    assertThat(relations.coverage()).isEqualTo("partial");
    assertThat(relations.targets())
        .extracting(PayloadLookup.ResultTarget::callId)
        .containsExactly("c3");
  }

  @Test
  void expandedReferenceBudgetDoesNotGrantPrefixCompleteness() throws Exception {
    var source =
        new SourceUnitCatalogEntry(
            "r",
            "synthetic.jsonl",
            "synthetic#event[1]",
            "tool_result",
            "",
            SourceUnitDirection.REQUEST,
            1,
            0,
            ByteRange.empty(),
            "",
            Optional.empty(),
            Optional.of("t"),
            50,
            Optional.empty(),
            Optional.of("VALUE"),
            Map.of("type", "tool_result", "tool_call_id", "t"),
            Optional.empty(),
            Optional.empty(),
            List.of());
    var range =
        new SourceUnitRefRange(
            Optional.empty(),
            0,
            16_384,
            java.util.Collections.nCopies(10_000, "r"),
            Optional.of("user"));
    var call =
        new NormalizedCall(
            "c2",
            2,
            "C2",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            "synthetic",
            Optional.empty(),
            NormalizedCallUsage.empty(),
            NormalizedCallRequest.empty(),
            NormalizedCallResponse.empty(),
            java.util.Collections.nCopies(7, range),
            List.of(),
            Map.of(),
            Map.of());
    var opens = new AtomicInteger();
    var projection =
        LocalToolResultProjection.build(
            counted(
                NormalizedSessionContent.fromArtifact(
                    artifact(
                        List.of(owner(), call), List.of(tool("c1")), List.of(source), Map.of())),
                opens));
    assertThat(opens.get()).isEqualTo(2);
    var results = projection.read("tool:result:t", 0, 20, null, PayloadVisibility.FULL);
    assertThat(results.reason()).isEqualTo("reference_budget");
    var relations =
        projection.relations(results.occurrences().getFirst().occurrenceId(), 0, 20, null);
    assertThat(relations.coverage()).isEqualTo("unknown");
    assertThat(relations.targets()).isEmpty();
  }

  @Test
  void failedMetadataReadClosesBothCursorsAndDoesNotCachePartialProjection() throws Exception {
    var base =
        NormalizedSessionContent.fromArtifact(
            artifact(List.of(owner()), List.of(tool("c1")), List.of(entry(1, "VALUE")), Map.of()));
    var opens = new AtomicInteger();
    var closes = new AtomicInteger();
    var broken =
        new NormalizedSessionContent() {
          @Override
          public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
            return base.header();
          }

          @Override
          public ContentCursor openCursor() throws IOException {
            var delegate = base.openCursor();
            int pass = opens.incrementAndGet();
            return new ContentCursor() {
              @Override
              public boolean hasNext() throws IOException {
                if (pass == 2) throw new IOException("synthetic metadata read failure");
                return delegate.hasNext();
              }

              @Override
              public NormalizedContentUnit next() throws IOException {
                return delegate.next();
              }

              @Override
              public void close() throws IOException {
                closes.incrementAndGet();
                delegate.close();
              }
            };
          }
        };
    assertThatThrownBy(() -> LocalToolResultProjection.build(broken))
        .isInstanceOf(IOException.class);
    assertThat(opens.get()).isEqualTo(2);
    assertThat(closes.get()).isEqualTo(2);
    assertThat(
            LocalToolResultProjection.build(broken)
                .read("tool:result:t", 0, 20, null, PayloadVisibility.FULL)
                .occurrences()
                .getFirst()
                .content()
                .text())
        .isEqualTo("VALUE");
  }

  private static String key(int index) {
    return "tool-result:" + index + ":synthetic#event[" + index + "]";
  }

  private static Map<String, Object> inline(String key, String text) {
    var source = new LinkedHashMap<String, Object>();
    source.put("type", "tool_result");
    source.put("role", "user");
    source.put("text", text);
    source.put("tool_call_id", "t");
    if (!key.isEmpty()) source.put("result_source_unit_key", key);
    return source;
  }

  private static SourceUnitCatalogEntry entry(int index, String text) {
    return new SourceUnitCatalogEntry(
        key(index),
        "synthetic.jsonl",
        "synthetic#event[" + index + "]",
        "tool_result",
        "",
        SourceUnitDirection.REQUEST,
        index,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.of("t"),
        50,
        Optional.empty(),
        Optional.ofNullable(text),
        Map.of("type", "tool_result", "tool_call_id", "t"),
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  private static NormalizedToolExecution tool(String owner) {
    return new NormalizedToolExecution(
        "t",
        "synthetic-tool",
        CallScope.MAIN,
        owner,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        0,
        List.of(),
        Optional.empty());
  }

  private static NormalizedCall owner() {
    return call(1, List.of(), List.of());
  }

  private static NormalizedCall call(
      int index, List<String> refs, List<Map<String, Object>> sources) {
    return new NormalizedCall(
        "c" + index,
        index,
        "C" + index,
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        NormalizedCallUsage.empty(),
        NormalizedCallRequest.empty(),
        NormalizedCallResponse.empty(),
        refs.isEmpty()
            ? List.of()
            : List.of(
                new SourceUnitRefRange(
                    Optional.empty(), 0, refs.size(), refs, Optional.of("user"))),
        sources,
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionArtifact artifact(
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      List<SourceUnitCatalogEntry> entries,
      Map<String, List<String>> sequences) {
    var catalog = new LinkedHashMap<String, SourceUnitCatalogEntry>();
    entries.forEach(entry -> catalog.put(entry.unitKey(), entry));
    return new NormalizedSessionArtifact(
        NormalizedConstants.SCHEMA_VERSION,
        NormalizedAgent.CODEX,
        List.of(),
        Map.of("session_key", "codex:synthetic-local-results"),
        calls,
        tools,
        List.of(),
        catalog,
        sequences);
  }

  private static NormalizedContentUnit unit(
      long index,
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog) {
    return new NormalizedContentUnit(index, List.of(), calls, tools, List.of(), catalog, List.of());
  }

  private static NormalizedSessionContent replay(
      NormalizedSessionContent base, List<NormalizedContentUnit> units) {
    return new NormalizedSessionContent() {
      @Override
      public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
        return base.header();
      }

      @Override
      public ContentCursor openCursor() {
        return new ContentCursor() {
          private int index;

          @Override
          public boolean hasNext() {
            return index < units.size();
          }

          @Override
          public NormalizedContentUnit next() {
            return units.get(index++);
          }

          @Override
          public void close() {}
        };
      }
    };
  }

  private static NormalizedSessionContent counted(
      NormalizedSessionContent content, AtomicInteger opens) {
    return new NormalizedSessionContent() {
      @Override
      public com.feipi.session.browser.domain.normalized.NormalizedContentHeader header() {
        return content.header();
      }

      @Override
      public ContentCursor openCursor() throws IOException {
        opens.incrementAndGet();
        return content.openCursor();
      }
    };
  }
}
