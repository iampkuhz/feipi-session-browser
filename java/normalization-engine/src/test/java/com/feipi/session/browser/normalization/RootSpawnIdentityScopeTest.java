package com.feipi.session.browser.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordRelation;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.domain.source.SourceRecordUsage;
import com.feipi.session.browser.domain.source.SourceTiming;
import com.feipi.session.browser.domain.source.SourceToolCall;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

/** 仅用合成记录验证根来源派发工具的执行作用域不受子代理父关联歧义影响。 */
class RootSpawnIdentityScopeTest {
  @TestFactory
  Stream<DynamicTest> rootResultSurvivesAmbiguousParent() {
    return Stream.of(false, true)
        .map(
            managed ->
                DynamicTest.dynamicTest(
                    managed ? "managed/root-result" : "list/root-result",
                    () -> verifyRootResult(managed)));
  }

  private static void verifyRootResult(boolean managed) throws Exception {
    var relation =
        new SourceRecordRelation(
            Optional.of("child"),
            Optional.empty(),
            Optional.of("spawn"),
            Optional.empty(),
            Optional.of("spawn_agent"));
    var result =
        new SourceRecord(
            "synthetic/root.jsonl#event[2]",
            2,
            "tool_result",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            SourceRecordUsage.empty(),
            List.of(),
            Optional.of("spawn"),
            Optional.empty(),
            Optional.empty(),
            relation,
            "root-result-one",
            Optional.empty(),
            Optional.empty(),
            SourceTiming.empty(),
            false,
            Optional.empty());
    var records =
        List.of(
            record("root", 0, "assistant", "A", SourceRecordRelation.empty(), "body-A"),
            record("root", 1, "tool_use", "spawn", relation, "input-root-one"),
            result,
            record("root", 3, "assistant", "B", SourceRecordRelation.empty(), "body-B"),
            record("root", 4, "tool_use", "spawn", relation, "input-root-two"),
            record("child", 0, "tool_use", "spawn", relation, "input-child"),
            record("child", 1, "assistant", "C", relation, "body-C"));
    var files =
        List.of(
            new NormalizedSourceFile(
                SourceFileRole.TRANSCRIPT,
                Path.of("synthetic/root.jsonl"),
                Optional.empty(),
                Optional.empty()),
            new NormalizedSourceFile(
                SourceFileRole.COMPANION,
                Path.of("synthetic/child.jsonl"),
                Optional.of("child"),
                Optional.of("spawn")));
    var engine = new NormalizationEngine();
    NormalizedSessionArtifact artifact;
    if (managed) {
      try (var sequence = SourceRecordSequence.fromList(records)) {
        artifact =
            engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), files).toArtifact();
      }
    } else {
      artifact = engine.normalize(NormalizedAgent.CODEX, records, List.of(), files);
    }
    assertThat(artifact.calls()).hasSize(3);
    assertThat(artifact.toolExecutions()).hasSize(3);
    var a = call(artifact, "body-A");
    var b = call(artifact, "body-B");
    var c = call(artifact, "body-C");
    assertTool(artifact, a, "input-root-one", CallScope.MAIN);
    assertTool(artifact, b, "input-root-two", CallScope.MAIN);
    assertTool(artifact, c, "input-child", CallScope.SUBAGENT);
    var tools = artifact.toolExecutions();
    assertThat(tools).extracting(NormalizedToolExecution::toolCallId).doesNotHaveDuplicates();
    var first =
        tools.stream()
            .filter(t -> t.declaredByCallId().equals(a.callId()))
            .findFirst()
            .orElseThrow();
    var identities = new ToolIdentityPlan(files);
    for (int i = 0; i < records.size(); i++) identities.accept(i, records.get(i));
    identities.finish();
    assertThat(first.toolCallId()).isEqualTo(identities.id(1, -1, "spawn"));
    assertThat(first.resultConsumedByCallId()).contains(b.callId());
    assertThat(b.request().toolResultIds()).containsExactly(first.toolCallId());
    assertThat(b.sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry("type", "tool_result")
                    .containsEntry("text", "root-result-one")
                    .containsEntry("tool_call_id", first.toolCallId()));
    assertThat(c.request().toolResultIds()).doesNotContain(first.toolCallId());
    assertThat(c.sourceUnits()).noneMatch(unit -> "root-result-one".equals(unit.get("text")));
    assertThat(c.parentCallId()).isEmpty();
    assertThat(c.parentToolCallId()).isEmpty();
    var callIds = artifact.calls().stream().map(NormalizedCall::callId).toList();
    var toolIds = tools.stream().map(NormalizedToolExecution::toolCallId).toList();
    for (var tool : tools) {
      assertThat(callIds).contains(tool.declaredByCallId());
      tool.resultConsumedByCallId().ifPresent(id -> assertThat(callIds).contains(id));
    }
    for (var call : artifact.calls()) {
      call.parentCallId().ifPresent(id -> assertThat(callIds).contains(id));
      call.parentToolCallId().ifPresent(id -> assertThat(toolIds).contains(id));
      assertThat(toolIds).containsAll(call.request().toolResultIds());
      assertThat(toolIds).containsAll(call.response().toolCallIds());
    }
    var baseline =
        engine.normalize(
            NormalizedAgent.CODEX,
            records.stream().filter(r -> "assistant".equals(r.eventType())).toList(),
            List.of(),
            files);
    assertThat(artifact.calls().stream().map(NormalizedCall::usage).toList())
        .isEqualTo(baseline.calls().stream().map(NormalizedCall::usage).toList());
    assertThat(artifact.session().get("totalTokens"))
        .isEqualTo(baseline.session().get("totalTokens"));
    assertThat(artifact.session().get("assistantMessageCount"))
        .isEqualTo(baseline.session().get("assistantMessageCount"));
    if (managed)
      assertThat(artifact)
          .isEqualTo(engine.normalize(NormalizedAgent.CODEX, records, List.of(), files));
  }

  @TestFactory
  Stream<DynamicTest> rootSelfAnchorSurvivesAmbiguousParent() {
    return Stream.of(false, true)
        .flatMap(
            managed ->
                Stream.of(false, true)
                    .map(
                        beforeFirst ->
                            DynamicTest.dynamicTest(
                                (managed ? "managed/" : "list/")
                                    + (beforeFirst ? "before-first-assistant" : "after-assistant"),
                                () -> verify(managed, beforeFirst))));
  }

  private static void verify(boolean managed, boolean beforeFirst) throws Exception {
    var relation =
        new SourceRecordRelation(
            Optional.of("child"),
            Optional.empty(),
            Optional.of("spawn"),
            Optional.empty(),
            Optional.of("spawn_agent"));
    var records = new ArrayList<SourceRecord>();
    var first = record("root", 0, "assistant", "A", SourceRecordRelation.empty(), "body-A");
    var spawn = record("root", 1, "tool_use", "spawn", relation, "input-root-one");
    records.add(beforeFirst ? spawn : first);
    records.add(beforeFirst ? first : spawn);
    records.add(record("root", 2, "assistant", "B", SourceRecordRelation.empty(), "body-B"));
    records.add(record("root", 3, "tool_use", "spawn", relation, "input-root-two"));
    records.add(record("child", 0, "tool_use", "spawn", relation, "input-child"));
    records.add(record("child", 1, "assistant", "C", relation, "body-C"));
    var files =
        List.of(
            new NormalizedSourceFile(
                SourceFileRole.TRANSCRIPT,
                Path.of("synthetic/root.jsonl"),
                Optional.empty(),
                Optional.empty()),
            new NormalizedSourceFile(
                SourceFileRole.COMPANION,
                Path.of("synthetic/child.jsonl"),
                Optional.of("child"),
                Optional.of("spawn")));
    var identities = new ToolIdentityPlan(files);
    for (int ordinal = 0; ordinal < records.size(); ordinal++) {
      identities.accept(ordinal, records.get(ordinal));
    }
    identities.finish();
    for (int ordinal : List.of(beforeFirst ? 0 : 1, 3)) {
      assertThat(identities.relation(ordinal, relation).parentToolCallId())
          .contains(identities.id(ordinal, -1, "spawn"));
    }
    assertThat(identities.relation(5, relation).parentToolCallId()).isEmpty();
    var engine = new NormalizationEngine();
    NormalizedSessionArtifact artifact;
    if (managed) {
      try (var sequence = SourceRecordSequence.fromList(records)) {
        var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), files);
        artifact = content.toArtifact();
        assertThat(content.toArtifact()).isEqualTo(artifact);
      }
    } else {
      artifact = engine.normalize(NormalizedAgent.CODEX, records, List.of(), files);
    }
    assertThat(artifact.calls()).hasSize(3);
    assertThat(artifact.toolExecutions()).hasSize(3);
    assertThat(artifact.toolExecutions())
        .extracting(NormalizedToolExecution::toolCallId)
        .doesNotHaveDuplicates();
    var a = call(artifact, "body-A");
    var b = call(artifact, "body-B");
    var c = call(artifact, "body-C");
    assertTool(artifact, a, "input-root-one", CallScope.MAIN);
    assertTool(artifact, b, "input-root-two", CallScope.MAIN);
    assertTool(artifact, c, "input-child", CallScope.SUBAGENT);
    assertThat(c.parentCallId()).isEmpty();
    assertThat(c.parentToolCallId()).isEmpty();
    assertThat(artifact.diagnostics()).isNotEmpty();
    var callIds = artifact.calls().stream().map(NormalizedCall::callId).toList();
    var toolIds =
        artifact.toolExecutions().stream().map(NormalizedToolExecution::toolCallId).toList();
    for (var tool : artifact.toolExecutions()) {
      assertThat(callIds).contains(tool.declaredByCallId());
      tool.resultConsumedByCallId().ifPresent(id -> assertThat(callIds).contains(id));
    }
    for (var call : artifact.calls()) {
      call.parentCallId().ifPresent(id -> assertThat(callIds).contains(id));
      call.parentToolCallId().ifPresent(id -> assertThat(toolIds).contains(id));
      assertThat(toolIds).containsAll(call.request().toolResultIds());
      assertThat(toolIds).containsAll(call.response().toolCallIds());
    }
    var assistants = records.stream().filter(r -> "assistant".equals(r.eventType())).toList();
    var baseline = engine.normalize(NormalizedAgent.CODEX, assistants, List.of(), files);
    assertThat(artifact.calls().stream().map(NormalizedCall::usage).toList())
        .isEqualTo(baseline.calls().stream().map(NormalizedCall::usage).toList());
    assertThat(artifact.session().get("assistantMessageCount"))
        .isEqualTo(baseline.session().get("assistantMessageCount"));
    assertThat(artifact.session().get("totalTokens"))
        .isEqualTo(baseline.session().get("totalTokens"));
    if (managed) {
      assertThat(artifact)
          .isEqualTo(engine.normalize(NormalizedAgent.CODEX, records, List.of(), files));
    }
  }

  private static NormalizedCall call(NormalizedSessionArtifact artifact, String body) {
    var calls =
        artifact.calls().stream()
            .filter(c -> c.sourceUnits().stream().anyMatch(u -> body.equals(u.get("text"))))
            .toList();
    assertThat(calls).hasSize(1);
    return calls.getFirst();
  }

  private static void assertTool(
      NormalizedSessionArtifact artifact, NormalizedCall owner, String input, CallScope scope) {
    var tools =
        artifact.toolExecutions().stream()
            .filter(t -> t.declaredByCallId().equals(owner.callId()))
            .toList();
    assertThat(tools).hasSize(1);
    var tool = tools.getFirst();
    assertThat(tool.scope()).isEqualTo(scope);
    assertThat(owner.sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry("type", "tool_use")
                    .containsEntry("id", tool.toolCallId())
                    .containsEntry("input", input));
  }

  private static SourceRecord record(
      String origin,
      int index,
      String type,
      String id,
      SourceRecordRelation relation,
      String body) {
    boolean assistant = "assistant".equals(type);
    return new SourceRecord(
        "synthetic/" + origin + ".jsonl#event[" + index + "]",
        index,
        type,
        Optional.of(id),
        Optional.of("synthetic-model"),
        Optional.empty(),
        Optional.empty(),
        assistant ? new SourceRecordUsage(3, 2, 1, 0) : SourceRecordUsage.empty(),
        assistant ? List.of() : List.of(new SourceToolCall(id, "spawn_agent", body)),
        Optional.empty(),
        assistant ? Optional.empty() : Optional.of("spawn_agent"),
        Optional.empty(),
        relation,
        assistant ? body : "",
        Optional.empty(),
        Optional.empty(),
        SourceTiming.empty(),
        false,
        assistant ? Optional.of("assistant") : Optional.empty());
  }
}
