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

/** 仅用合成记录验证提供方工具标识属于局部作用域，不能充当全局执行标识。 */
class ToolIdentityCollisionTest {
  @TestFactory
  Stream<DynamicTest> toolIdentityContractsForListAndManaged() {
    return Stream.of(false, true)
        .flatMap(
            managed ->
                Stream.of(
                    test(managed, "independent-tail-results", () -> tailResults(managed)),
                    test(managed, "main-and-two-children", () -> acrossScopes(managed)),
                    test(managed, "same-scope-distinct-origins", () -> acrossOrigins(managed)),
                    test(
                        managed,
                        "same-origin-repeated-occurrences",
                        () -> repeatedOccurrences(managed)),
                    test(managed, "root-spawn-evidence", () -> parentSpawn(managed)),
                    test(
                        managed,
                        "inherited-spawn-is-not-root-execution",
                        () -> inheritedSpawn(managed)),
                    test(
                        managed,
                        "ambiguous-parent-is-not-last-wins",
                        () -> ambiguousParent(managed)),
                    test(managed, "missing-root-parent-is-not-self", () -> missingParent(managed)),
                    test(
                        managed,
                        "explicit-child-evidence-precedes-root-fallback",
                        () -> nestedParent(managed)),
                    test(
                        managed,
                        "repeated-parent-diagnostics-are-bounded",
                        () -> boundedDiagnostics(managed)),
                    test(
                        managed,
                        "parent-cache-keeps-incoming-origin",
                        () -> originAwareParentCache(managed)),
                    test(managed, "standalone-declarations", () -> standalone(managed)),
                    test(managed, "unchanged-provider-id", () -> unchanged(managed)),
                    test(
                        managed,
                        "provider-id-reserves-generated-namespace",
                        () -> generatedCollision(managed))));
  }

  private static DynamicTest test(boolean managed, String name, Checked action) {
    return DynamicTest.dynamicTest((managed ? "managed/" : "list/") + name, action::run);
  }

  private static void tailResults(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    round(records, "root", "first", "shared", SourceRecordRelation.empty());
    for (String origin : List.of("root", "other", "child-a", "child-b")) {
      var relation =
          origin.startsWith("child") ? child(origin, "spawn") : SourceRecordRelation.empty();
      records.add(assistant(origin, 10, origin + "-tail", "shared", relation));
      records.add(result(origin, 11, "shared", origin + "-error", relation));
    }
    var artifact = normalize(managed, records, List.of());
    assertThat(artifact.toolExecutions()).hasSize(5);
    assertThat(artifact.sourceUnitCatalog()).hasSize(5);
    for (String origin : List.of("root", "other", "child-a", "child-b")) {
      var tool = edge(artifact, origin + "-tail");
      assertThat(tool.resultConsumedByCallId()).isEmpty();
      assertThat(call(artifact, origin + "-tail").request().toolResultIds()).isEmpty();
      assertThat(artifact.sourceUnitCatalog().values())
          .filteredOn(entry -> entry.label().filter(tool.toolCallId()::equals).isPresent())
          .singleElement()
          .satisfies(entry -> assertThat(entry.text()).contains(origin + "-result"));
    }
    assertEdge(artifact, "first-declare", "first-consume", "first-error");
  }

  private static void acrossScopes(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    for (String origin : List.of("root", "child-a", "child-b")) {
      var relation = origin.equals("root") ? SourceRecordRelation.empty() : child(origin, "spawn");
      records.add(assistant(origin, 0, origin + "-declare", "shared", relation));
    }
    for (String origin : List.of("root", "child-a", "child-b")) {
      var relation = origin.equals("root") ? SourceRecordRelation.empty() : child(origin, "spawn");
      records.add(result(origin, 1, "shared", origin + "-error", relation));
      records.add(assistant(origin, 2, origin + "-consume", null, relation));
    }
    var artifact = normalize(managed, records, List.of());
    assertThat(artifact.toolExecutions()).hasSize(3);
    for (String origin : List.of("root", "child-a", "child-b")) {
      assertEdge(artifact, origin + "-declare", origin + "-consume", origin + "-error");
    }
    assertThat(edge(artifact, "root-declare").scope()).isEqualTo(CallScope.MAIN);
    assertThat(edge(artifact, "child-a-declare").scope()).isEqualTo(CallScope.SUBAGENT);
  }

  private static void acrossOrigins(boolean managed) throws Exception {
    var records =
        List.of(
            assistant("one", 0, "one-declare", "shared", SourceRecordRelation.empty()),
            assistant("two", 0, "two-declare", "shared", SourceRecordRelation.empty()),
            result("one", 1, "shared", "one-error", SourceRecordRelation.empty()),
            result("two", 1, "shared", "two-error", SourceRecordRelation.empty()),
            assistant("two", 2, "two-consume", null, SourceRecordRelation.empty()),
            assistant("one", 2, "one-consume", null, SourceRecordRelation.empty()));
    assertThat(records)
        .allSatisfy(record -> assertThat(CallBuilder.callScope(record)).isEqualTo(CallScope.MAIN));
    var artifact = normalize(managed, records, List.of());
    assertThat(artifact.calls())
        .extracting(NormalizedCall::callId)
        .containsExactly("one-declare", "two-declare", "two-consume", "one-consume");
    assertEdge(artifact, "one-declare", "one-consume", "one-error");
    assertEdge(artifact, "two-declare", "two-consume", "two-error");
    assertThat(call(artifact, "two-consume").sourceUnits())
        .noneMatch(unit -> "one-result".equals(unit.get("text")));
    assertThat(call(artifact, "one-consume").sourceUnits())
        .noneMatch(unit -> "two-result".equals(unit.get("text")));
  }

  private static void repeatedOccurrences(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    round(records, "root", "first", "shared", SourceRecordRelation.empty());
    round(records, "root", "second", "shared", SourceRecordRelation.empty());
    var artifact = normalize(managed, records, List.of());
    assertThat(artifact.toolExecutions()).hasSize(2);
    assertEdge(artifact, "first-declare", "first-consume", "first-error");
    assertEdge(artifact, "second-declare", "second-consume", "second-error");
  }

  private static void parentSpawn(boolean managed) throws Exception {
    var records =
        List.of(
            assistant("root", 0, "parent", "spawn", SourceRecordRelation.empty(), "spawn_agent"),
            assistant(
                "other", 0, "unrelated", "spawn", SourceRecordRelation.empty(), "spawn_agent"),
            assistant("child", 0, "child-call", null, child("child", "spawn")));
    var artifact = normalize(managed, records, rootFiles());
    assertThat(call(artifact, "child-call").parentCallId())
        .contains(call(artifact, "parent").callId());
    assertThat(call(artifact, "child-call").parentToolCallId())
        .contains(edge(artifact, "parent").toolCallId());
    assertThat(edge(artifact, "parent").scope()).isEqualTo(CallScope.MAIN);
    assertThat(artifact.sourceFiles())
        .filteredOn(file -> file.subagentId().isPresent())
        .singleElement()
        .satisfies(
            file ->
                assertThat(file.parentToolUseId()).contains(edge(artifact, "parent").toolCallId()));
  }

  private static void inheritedSpawn(boolean managed) throws Exception {
    var relation = child("child", "spawn");
    var records =
        List.of(
            assistant("root", 0, "parent", null, SourceRecordRelation.empty()),
            record(
                "root",
                1,
                "tool_use",
                "spawn",
                null,
                "spawn_agent",
                null,
                List.of(new SourceToolCall("spawn", "spawn_agent", "root-input")),
                relation),
            record(
                "child",
                0,
                "tool_use",
                "spawn",
                null,
                "spawn_agent",
                null,
                List.of(new SourceToolCall("spawn", "spawn_agent", "child-input")),
                relation),
            result("child", 1, "spawn", "child-error", relation),
            assistant("child", 2, "child-call", null, relation));
    var artifact = normalize(managed, records, rootFiles());
    var root = edge(artifact, "parent");
    var inherited = edge(artifact, "child-call");
    assertThat(root.scope()).isEqualTo(CallScope.MAIN);
    assertThat(inherited.scope()).isEqualTo(CallScope.SUBAGENT);
    assertThat(inherited.resultConsumedByCallId()).contains(call(artifact, "child-call").callId());
    assertThat(inherited.status()).contains("child-error");
    assertThat(call(artifact, "child-call").parentCallId())
        .contains(call(artifact, "parent").callId());
    assertThat(call(artifact, "child-call").parentToolCallId()).contains(root.toolCallId());
    assertThat(call(artifact, "child-call").request().toolResultIds())
        .contains(inherited.toolCallId());
  }

  private static void ambiguousParent(boolean managed) throws Exception {
    var records =
        List.of(
            assistant(
                "root", 0, "candidate-one", "spawn", SourceRecordRelation.empty(), "spawn_agent"),
            assistant(
                "root", 1, "candidate-two", "spawn", SourceRecordRelation.empty(), "spawn_agent"),
            assistant("child", 0, "child-call", null, child("child", "spawn")));
    var artifact = normalize(managed, records, rootFiles());
    assertThat(call(artifact, "child-call").parentCallId()).isEmpty();
    assertThat(call(artifact, "child-call").parentToolCallId()).isEmpty();
    assertThat(artifact.diagnostics()).isNotEmpty();
  }

  private static void missingParent(boolean managed) throws Exception {
    var relation = child("child", "spawn");
    var records =
        List.of(
            assistant("root", 0, "root-call", null, SourceRecordRelation.empty()),
            record(
                "child",
                0,
                "tool_use",
                "spawn",
                null,
                "spawn_agent",
                null,
                List.of(new SourceToolCall("spawn", "spawn_agent", "inherited-input")),
                relation),
            assistant("child", 1, "child-call", null, relation));
    var artifact = normalize(managed, records, rootFiles());
    assertThat(call(artifact, "child-call").parentCallId()).isEmpty();
    assertThat(call(artifact, "child-call").parentToolCallId()).isEmpty();
    assertThat(artifact.sourceFiles())
        .filteredOn(file -> file.subagentId().isPresent())
        .allSatisfy(file -> assertThat(file.parentToolUseId()).isEmpty());
    assertThat(artifact.diagnostics()).isNotEmpty();
  }

  private static void nestedParent(boolean managed) throws Exception {
    var target = child("nested", "spawn");
    var records =
        List.of(
            assistant("root", 0, "root-call", null, SourceRecordRelation.empty()),
            record(
                "root",
                1,
                "tool_use",
                "spawn",
                null,
                "spawn_agent",
                null,
                List.of(new SourceToolCall("spawn", "spawn_agent", "unrelated-input")),
                child("other-child", "spawn")),
            assistant("companion", 0, "actual-parent", null, SourceRecordRelation.empty()),
            record(
                "companion",
                1,
                "tool_use",
                "spawn",
                null,
                "spawn_agent",
                null,
                List.of(new SourceToolCall("spawn", "spawn_agent", "actual-parent-input")),
                target),
            assistant("nested", 0, "nested-call", null, target));
    var files =
        List.of(
            new NormalizedSourceFile(
                SourceFileRole.TRANSCRIPT,
                Path.of("synthetic/root.jsonl"),
                Optional.empty(),
                Optional.empty()),
            new NormalizedSourceFile(
                SourceFileRole.COMPANION,
                Path.of("synthetic/companion.jsonl"),
                Optional.empty(),
                Optional.empty()),
            new NormalizedSourceFile(
                SourceFileRole.COMPANION,
                Path.of("synthetic/nested.jsonl"),
                Optional.of("nested"),
                Optional.of("spawn")));
    var artifact = normalize(managed, records, files);
    assertThat(call(artifact, "nested-call").parentCallId())
        .contains(call(artifact, "actual-parent").callId());
    assertThat(call(artifact, "nested-call").parentToolCallId())
        .contains(edge(artifact, "actual-parent").toolCallId());
    assertThat(artifact.sourceFiles())
        .filteredOn(file -> file.subagentId().filter("nested"::equals).isPresent())
        .singleElement()
        .satisfies(
            file ->
                assertThat(file.parentToolUseId())
                    .contains(edge(artifact, "actual-parent").toolCallId()));
  }

  private static void boundedDiagnostics(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    records.add(
        assistant(
            "root", 0, "candidate-one", "spawn", SourceRecordRelation.empty(), "spawn_agent"));
    records.add(
        assistant(
            "root", 1, "candidate-two", "spawn", SourceRecordRelation.empty(), "spawn_agent"));
    for (int index = 0; index < 128; index++) {
      records.add(assistant("child", index, "child-call-" + index, null, child("child", "spawn")));
    }
    var artifact = normalize(managed, records, rootFiles());
    for (int index = 0; index < 128; index++) {
      assertThat(call(artifact, "child-call-" + index).parentCallId()).isEmpty();
      assertThat(call(artifact, "child-call-" + index).parentToolCallId()).isEmpty();
    }
    // 同一未解析关联只汇总一项诊断，不随携带正文的源记录重复生成。
    assertThat(artifact.diagnostics()).hasSize(1);
    assertThat(artifact.diagnostics().getFirst()).containsEntry("occurrenceCount", 128L);
  }

  private static void originAwareParentCache(boolean managed) throws Exception {
    var relation = child("child", "spawn");
    var records =
        List.of(
            assistant("one", 0, "candidate", "spawn", relation, "spawn_agent"),
            assistant("two", 0, "descendant", null, relation));
    var artifact = normalize(managed, records, List.of());
    assertThat(call(artifact, "candidate").parentCallId()).isEmpty();
    assertThat(call(artifact, "candidate").parentToolCallId()).isEmpty();
    assertThat(call(artifact, "descendant").parentCallId())
        .contains(call(artifact, "candidate").callId());
    assertThat(call(artifact, "descendant").parentToolCallId())
        .contains(edge(artifact, "candidate").toolCallId());
  }

  private static void standalone(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    for (String origin : List.of("one", "two")) {
      records.add(assistant(origin, 0, origin + "-declare", null, SourceRecordRelation.empty()));
      records.add(
          record(
              origin,
              1,
              "tool_use",
              "shared",
              null,
              "Read",
              null,
              List.of(new SourceToolCall("shared", "Read", "synthetic-input")),
              SourceRecordRelation.empty()));
      records.add(result(origin, 2, "shared", origin + "-error", SourceRecordRelation.empty()));
      records.add(assistant(origin, 3, origin + "-consume", null, SourceRecordRelation.empty()));
    }
    var artifact = normalize(managed, records, List.of());
    assertThat(artifact.toolExecutions()).hasSize(2);
    assertEdge(artifact, "one-declare", "one-consume", "one-error", false);
    assertEdge(artifact, "two-declare", "two-consume", "two-error", false);
  }

  private static void unchanged(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    round(records, "root", "only", "provider-original", SourceRecordRelation.empty());
    var artifact = normalize(managed, records, List.of());
    assertEdge(artifact, "only-declare", "only-consume", "only-error");
    assertThat(edge(artifact, "only-declare").toolCallId()).isEqualTo("provider-original");
  }

  private static void generatedCollision(boolean managed) throws Exception {
    var records = new ArrayList<SourceRecord>();
    round(records, "one", "first", "shared", SourceRecordRelation.empty());
    round(records, "two", "second", "shared", SourceRecordRelation.empty());
    var initial = normalize(managed, records, List.of());
    String generated =
        initial.toolExecutions().stream()
            .map(NormalizedToolExecution::toolCallId)
            .filter(id -> !id.equals("shared"))
            .findFirst()
            .orElseThrow();
    round(records, "three", "reserved", generated, SourceRecordRelation.empty());
    var artifact = normalize(managed, records, List.of());
    assertThat(artifact.toolExecutions()).hasSize(3);
    assertThat(edge(artifact, "reserved-declare").toolCallId()).isEqualTo(generated);
    assertEdge(artifact, "first-declare", "first-consume", "first-error");
    assertEdge(artifact, "second-declare", "second-consume", "second-error");
    assertEdge(artifact, "reserved-declare", "reserved-consume", "reserved-error");
  }

  private static NormalizedSessionArtifact normalize(
      boolean managed, List<SourceRecord> records, List<NormalizedSourceFile> files)
      throws Exception {
    var engine = new NormalizationEngine();
    NormalizedSessionArtifact artifact;
    if (managed) {
      try (var sequence = SourceRecordSequence.fromList(records)) {
        var content = engine.normalizeContent(NormalizedAgent.CODEX, sequence, List.of(), files);
        artifact = content.toArtifact();
        assertThat(content.toArtifact()).isEqualTo(artifact);
      }
      assertThat(artifact)
          .isEqualTo(engine.normalize(NormalizedAgent.CODEX, records, List.of(), files));
    } else {
      artifact = engine.normalize(NormalizedAgent.CODEX, records, List.of(), files);
    }
    assertThat(artifact.toolExecutions())
        .extracting(NormalizedToolExecution::toolCallId)
        .doesNotHaveDuplicates();
    return artifact;
  }

  private static void assertEdge(
      NormalizedSessionArtifact artifact, String owner, String consumer, String error) {
    assertEdge(artifact, owner, consumer, error, true);
  }

  private static void assertEdge(
      NormalizedSessionArtifact artifact,
      String owner,
      String consumer,
      String error,
      boolean assistantDeclaration) {
    var execution = edge(artifact, owner);
    assertThat(execution.resultConsumedByCallId()).contains(call(artifact, consumer).callId());
    assertThat(execution.status()).contains(error);
    if (assistantDeclaration) {
      assertThat(call(artifact, owner).response().toolCallIds()).contains(execution.toolCallId());
    } else {
      // 独立工具声明不要求额外合成助手响应引用。
      assertThat(call(artifact, owner).response().toolCallIds())
          .allSatisfy(
              id ->
                  assertThat(artifact.toolExecutions())
                      .anyMatch(tool -> tool.toolCallId().equals(id)));
    }
    assertThat(call(artifact, owner).sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry("type", "tool_use")
                    .containsEntry("id", execution.toolCallId()));
    assertThat(call(artifact, consumer).request().toolResultIds()).contains(execution.toolCallId());
    assertThat(call(artifact, consumer).sourceUnits())
        .anySatisfy(unit -> assertThat(unit).containsEntry("tool_call_id", execution.toolCallId()));
  }

  private static NormalizedToolExecution edge(NormalizedSessionArtifact artifact, String owner) {
    var matching =
        artifact.toolExecutions().stream()
            .filter(tool -> tool.declaredByCallId().equals(call(artifact, owner).callId()))
            .toList();
    assertThat(matching).hasSize(1);
    return matching.getFirst();
  }

  private static NormalizedCall call(NormalizedSessionArtifact artifact, String id) {
    var matching =
        artifact.calls().stream()
            .filter(
                call ->
                    call.sourceUnits().stream()
                        .anyMatch(
                            unit ->
                                "assistant".equals(unit.get("type"))
                                    && ("synthetic-assistant:" + id).equals(unit.get("text"))))
            .toList();
    assertThat(matching).hasSize(1);
    return matching.getFirst();
  }

  private static List<NormalizedSourceFile> rootFiles() {
    return List.of(
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
  }

  private static SourceRecordRelation child(String id, String parentTool) {
    return new SourceRecordRelation(
        Optional.of(id),
        Optional.empty(),
        Optional.of(parentTool),
        Optional.empty(),
        Optional.of("spawn_agent"));
  }

  private static void round(
      List<SourceRecord> records,
      String origin,
      String name,
      String tool,
      SourceRecordRelation relation) {
    int index = records.size();
    records.add(assistant(origin, index, name + "-declare", tool, relation));
    records.add(result(origin, index + 1, tool, name + "-error", relation));
    records.add(assistant(origin, index + 2, name + "-consume", null, relation));
  }

  private static SourceRecord assistant(
      String origin, int index, String call, String tool, SourceRecordRelation relation) {
    return assistant(origin, index, call, tool, relation, "Read");
  }

  private static SourceRecord assistant(
      String origin,
      int index,
      String call,
      String tool,
      SourceRecordRelation relation,
      String name) {
    return record(
        origin,
        index,
        "assistant",
        call,
        null,
        null,
        null,
        tool == null ? List.of() : List.of(new SourceToolCall(tool, name, "{\"synthetic\":true}")),
        relation);
  }

  private static SourceRecord result(
      String origin, int index, String tool, String error, SourceRecordRelation relation) {
    return record(origin, index, "tool_result", null, tool, null, error, List.of(), relation);
  }

  private static SourceRecord record(
      String origin,
      int index,
      String type,
      String call,
      String tool,
      String name,
      String error,
      List<SourceToolCall> declarations,
      SourceRecordRelation relation) {
    return new SourceRecord(
        "synthetic/" + origin + ".jsonl#event[" + index + "]",
        index,
        type,
        Optional.ofNullable(call),
        Optional.of("synthetic-model"),
        Optional.empty(),
        Optional.empty(),
        new SourceRecordUsage(3, 2, 1, 0),
        declarations,
        Optional.ofNullable(tool),
        Optional.ofNullable(name),
        Optional.ofNullable(error),
        relation,
        type.equals("assistant")
            ? "synthetic-assistant:" + call
            : origin + (type.equals("tool_result") ? "-result" : "-" + call),
        Optional.empty(),
        Optional.empty(),
        SourceTiming.empty(),
        false,
        type.equals("assistant") ? Optional.of("assistant") : Optional.empty());
  }

  @FunctionalInterface
  private interface Checked {
    void run() throws Exception;
  }
}
