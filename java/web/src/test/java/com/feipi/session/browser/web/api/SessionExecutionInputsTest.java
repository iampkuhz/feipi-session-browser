package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedSequenceChunk;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.domain.source.SourceToolObservation;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/** 合成完整参数记录的累计投影，不执行参数中的任何命令。 */
class SessionExecutionInputsTest {
  @Test
  void qualifiedIndependentInputIsReadableButNeverGrantsSameInputEligibility() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    var catalog = new java.util.LinkedHashMap<String, SourceUnitCatalogEntry>();
    for (int i = 0; i < 3; i++) {
      var original = tool("orphan-" + i, 500_000_000L);
      tools.add(
          new NormalizedToolExecution(
              original.toolCallId(),
              original.name(),
              original.scope(),
              "unknown",
              original.resultConsumedByCallId(),
              original.status(),
              original.exitCode(),
              original.durationMs(),
              original.filesTouched(),
              original.subagentId(),
              original.observation()));
      String locator = "synthetic/orphan#event[" + i + "]";
      String key = "tool-input:" + i + ":0:" + locator;
      catalog.put(
          key,
          new SourceUnitCatalogEntry(
              key,
              "synthetic/orphan",
              locator,
              "tool_use",
              "independent_tool_input.v1",
              SourceUnitDirection.RESPONSE,
              i,
              0,
              ByteRange.empty(),
              "",
              Optional.empty(),
              Optional.of(original.toolCallId()),
              50,
              Optional.empty(),
              Optional.empty(),
              Map.of(
                  "type", "tool_use",
                  "id", original.toolCallId(),
                  "name", original.name(),
                  "input",
                      i < 2 ? "{\"cmd\":\"synthetic-repeated\"}" : "{\"cmd\":\"synthetic-other\"}",
                  "independent",
                      Map.of(
                          "ordinal",
                          Integer.toString(i),
                          "slot",
                          "0",
                          "scope",
                          "main",
                          "subagent",
                          "")),
              Optional.empty(),
              Optional.empty(),
              List.of()));
    }
    var artifact =
        new com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(),
            Map.of(),
            List.of(),
            tools,
            List.of(),
            catalog,
            Map.of());
    var inputs =
        com.feipi.session.browser.application.sessiondetail.ToolInputContents.all(artifact);
    assertThat(inputs).hasSize(3);
    assertThat(inputs.get("orphan-0").input()).isEqualTo("{\"cmd\":\"synthetic-repeated\"}");
    assertThat(inputs.get("orphan-1").input()).isEqualTo(inputs.get("orphan-0").input());
    assertThat(inputs.get("orphan-2").input()).isEqualTo("{\"cmd\":\"synthetic-other\"}");
    assertThat(maximum(baseline()).isNull()).isFalse();
    assertThat(artifact.calls()).isEmpty();
    var content = NormalizedSessionContent.fromArtifact(artifact);
    var previews = SessionContentPreviews.read(content);
    assertThat(previews.independentToolInputs()).hasSize(3);
    var units = new ArrayList<NormalizedContentUnit>();
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) units.add(cursor.next());
    }
    assertThat(collect(content, units, tools)).isNull();
    var diagnostics = SessionExecutionProjection.diagnostics(content);
    assertThat(diagnostics.totalTools()).isEqualTo(3);
    assertThat(diagnostics.measuredTools()).isEqualTo(3);
    // 未确认模型归属不创造候选组，也不能输出同参累计热点。
    assertThat(diagnostics.workloadSignals().candidates()).isEmpty();
    assertThat(diagnostics.workloads())
        .allSatisfy(parent -> assertThat(parent.sameInputMaximum()).isNull());
    assertThat(tools).allSatisfy(tool -> assertThat(tool.declaredByCallId()).isEqualTo("unknown"));
  }

  @Test
  void twoHundredCallsExposeBetaNinetySecondsWithoutReplacingAlpha() throws Exception {
    var tools = new ArrayList<NormalizedToolExecution>();
    var sources = new ArrayList<Map<String, Object>>();
    for (int i = 0; i < 200; i++) {
      String id = String.format(java.util.Locale.ROOT, "tool-%03d", i);
      tools.add(tool(id, 500_000_000L));
      sources.add(
          declaration(
              id, i < 20 ? "{\"cmd\":\"synthetic-alpha\"}" : "{\"cmd\":\"synthetic-beta\"}"));
    }
    var result = SessionExecutionProjection.diagnostics(content(tools, sources));
    var json = new ObjectMapper().valueToTree(result);
    var parent = json.path("workloadSignals").path("candidates").get(0);
    assertThat(parent.path("measuredWorkNanos").asText()).isEqualTo("100000000000");
    assertThat(parent.path("totalTools").asLong()).isEqualTo(200);
    assertThat(parent.path("longest").path("tool").path("inputPreview").asText())
        .isEqualTo("synthetic-alpha");
    var maximum = parent.path("sameInputMaximum");
    assertThat(maximum.path("measuredWorkNanos").asText()).isEqualTo("90000000000");
    assertThat(maximum.path("measuredTools").asLong()).isEqualTo(180);
    assertThat(maximum.path("totalTools").asLong()).isEqualTo(180);
    assertThat(maximum.path("distinctInputs").asLong()).isEqualTo(2);
    assertThat(maximum.path("identifiedInputs").asLong()).isEqualTo(200);
    assertThat(maximum.path("totalInputs").asLong()).isEqualTo(200);
    assertThat(maximum.path("tool").path("inputPreview").asText()).isEqualTo("synthetic-beta");
    assertThat(json.path("workloads").get(0).path("sameInputMaximum")).isEqualTo(maximum);
    assertThat(result.workloads().getFirst().sameInputMaximum())
        .isSameAs(result.workloadSignals().candidates().getFirst().sameInputMaximum());
  }

  @Test
  void hotspotBelongsToChildAgentNotSpawnAndKeepsThirtyFiveSecondSingle() throws Exception {
    var calls = new ArrayList<NormalizedCall>();
    var tools = new ArrayList<NormalizedToolExecution>();
    var sources = new ArrayList<Map<String, Object>>();
    for (int i = 0; i < 200; i++) {
      var t = tool(String.format(java.util.Locale.ROOT, "child-tool-%03d", i), 500_000_000L);
      tools.add(
          new NormalizedToolExecution(
              t.toolCallId(),
              t.name(),
              CallScope.SUBAGENT,
              "child-call",
              t.resultConsumedByCallId(),
              t.status(),
              t.exitCode(),
              t.durationMs(),
              t.filesTouched(),
              Optional.of("child08"),
              t.observation()));
      sources.add(declaration(t.toolCallId(), i < 20 ? "synthetic-alpha" : "synthetic-beta"));
    }
    var child = firstCall(content(tools, sources));
    calls.add(
        new NormalizedCall(
            "child-call",
            2,
            "C2",
            CallScope.SUBAGENT,
            Optional.empty(),
            Optional.of("spawn"),
            child.turnId(),
            child.model(),
            child.timestamp(),
            child.usage(),
            child.request(),
            child.response(),
            List.of(),
            sources,
            Map.of(),
            Map.of(),
            Optional.of("child08"),
            Optional.of("spawn_agent")));
    var single = tool("single", 35_000_000_000L);
    tools.add(single);
    tools.add(
        new NormalizedToolExecution(
            "spawn",
            "spawn_agent",
            CallScope.MAIN,
            "call-1",
            Optional.empty(),
            Optional.empty(),
            Optional.empty(),
            null,
            List.of(),
            Optional.empty(),
            Optional.empty()));
    var root =
        firstCall(
            content(
                List.of(single, tools.getLast()),
                List.of(declaration("single", "synthetic-long-single"))));
    calls.add(root);
    var base = content(tools, List.of());
    var header = base.header();
    var complete =
        NormalizedSessionContent.fromLists(
            new NormalizedContentHeader(
                header.schemaVersion(),
                header.agent(),
                header.session(),
                Map.of(
                    "calls",
                    2L,
                    "toolExecutions",
                    202L,
                    "sourceFiles",
                    0L,
                    "diagnostics",
                    0L,
                    "sourceUnitCatalog",
                    0L,
                    "sourceUnitSequenceEntries",
                    0L)),
            List.of(),
            calls,
            tools,
            List.of(),
            Map.of(),
            Map.of());
    var result = SessionExecutionProjection.diagnostics(complete);
    var parent = result.workloadSignals().candidates().getFirst();
    assertThat(parent.scope()).isEqualTo("subagent");
    assertThat(parent.subagentId()).isEqualTo("child08");
    assertThat(parent.measuredWorkNanos()).isEqualTo("100000000000");
    assertThat(parent.sameInputMaximum().measuredWorkNanos()).isEqualTo("90000000000");
    assertThat(parent.sameInputMaximum().tool().declaredByCallId()).isEqualTo("child-call");
    assertThat(parent.sameInputMaximum().tool().subagentId()).isEqualTo("child08");
    assertThat(parent.longest().tool().inputPreview()).isEqualTo("synthetic-alpha");
    assertThat(result.longOperations().candidates().getFirst().durationNanos())
        .isEqualTo("35000000000");
    var selected = SessionExecutionProjection.diagnostics(complete, "subagent:child08");
    assertThat(selected.workloadSignals().candidates().getFirst().sameInputMaximum())
        .isEqualTo(parent.sameInputMaximum());
  }

  @Test
  void completeRecordIdentityNeverMergesMatchingPreviewsOrUnicodeForms() throws Exception {
    for (var pair :
        List.of(
            List.of(
                "{\"cmd\":\"synthetic\",\"argument\":1}", "{\"cmd\":\"synthetic\",\"argument\":2}"),
            List.of("{\"cmd\":\"synthetic\",\"a\":1}", "{ \"cmd\":\"synthetic\",\"a\":1}"),
            List.of("synthetic-" + "a".repeat(200) + "x", "synthetic-" + "a".repeat(200) + "y"),
            List.of("synthetic-é", "synthetic-e\u0301"),
            List.of("synthetic-\uD800", "synthetic-\uD801"),
            List.of(
                "{\"cmd\":\"synthetic\",\"api_key\":\"synthetic-secret-one\"}",
                "{\"cmd\":\"synthetic\",\"api_key\":\"synthetic-secret-two\"}"))) {
      var tools = List.of(tool("a", 2L), tool("b", 2L), tool("c", 1L), tool("d", 1L));
      var maximum =
          maximum(
              content(
                  tools,
                  List.of(
                      declaration("a", pair.get(0)),
                      declaration("b", pair.get(0)),
                      declaration("c", pair.get(1)),
                      declaration("d", pair.get(1)))));
      assertThat(maximum.path("distinctInputs").asLong()).as(pair.toString()).isEqualTo(2);
      assertThat(maximum.path("totalTools").asLong()).isEqualTo(2);
      assertThat(maximum.path("measuredWorkNanos").asText()).isEqualTo("4");
      String serialized = maximum.toString();
      assertThat(serialized)
          .doesNotContain("fingerprint", "synthetic-secret-one", "synthetic-secret-two");
    }
  }

  @Test
  void malformedMissingAmbiguousOrUnboundedInputPoisonsEntireParent() throws Exception {
    var tools = List.of(tool("a", 2L), tool("b", 2L), tool("c", 1L));
    var missing = Map.<String, Object>of("type", "tool_use", "id", "c", "name", "exec_command");
    var ambiguous = new java.util.HashMap<>(declaration("c", "synthetic-other"));
    ambiguous.put("arguments", "synthetic-other");
    var truncated = new java.util.HashMap<>(declaration("c", "synthetic-other"));
    truncated.put("truncated", true);
    var variants = new ArrayList<Map<String, Object>>(List.of(missing, ambiguous, truncated));
    for (Object bad :
        List.of(
            Map.of("cmd", "synthetic"), List.of("synthetic"), 1, "", " \n ", "x".repeat(65_537)))
      variants.add(declaration("c", bad));
    for (var bad : variants)
      assertThat(
              maximum(
                      content(
                          tools,
                          List.of(
                              declaration("a", "synthetic"), declaration("b", "synthetic"), bad)))
                  .isNull())
          .isTrue();
    assertThat(
            maximum(
                    content(
                        tools,
                        List.of(declaration("a", "synthetic"), declaration("b", "synthetic"))))
                .isNull())
        .isTrue();
  }

  @Test
  void exactPartialCoverageKeepsUnknownOtherZeroAndHugeSumsIndependent() throws Exception {
    var tools =
        List.of(
            tool("a", Long.MAX_VALUE),
            tool("b", Long.MAX_VALUE),
            tool("c", null),
            other(tool("d", 10L)),
            tool("e", 0L));
    var sources =
        tools.stream()
            .map(
                t ->
                    declaration(
                        t.toolCallId(),
                        "e".equals(t.toolCallId()) ? "synthetic-other" : "synthetic-main"))
            .toList();
    var result = SessionExecutionProjection.diagnostics(content(tools, sources));
    var maximum = result.workloadSignals().candidates().getFirst().sameInputMaximum();
    assertThat(maximum.measuredWorkNanos()).isEqualTo("18446744073709551614");
    assertThat(maximum.totalTools()).isEqualTo(4);
    assertThat(maximum.measuredTools()).isEqualTo(2);
    assertThat(maximum.unknownTools()).isEqualTo(1);
    assertThat(maximum.otherKindTools()).isEqualTo(1);
    assertThat(result.workloads().getFirst().sameInputMaximum()).isNull();
    var tiny = List.of(tool("a", 0L), tool("b", 0L), tool("c", null));
    assertThat(
            maximum(
                    content(
                        tiny,
                        List.of(
                            declaration("a", "synthetic-main"),
                            declaration("b", "synthetic-main"),
                            declaration("c", "synthetic-other"))))
                .path("measuredWorkNanos")
                .asText())
        .isEqualTo("0");
  }

  @Test
  void uniqueHighestNeverFallsBackAndSingleMultilineInputIsOneCall() throws Exception {
    var tools = List.of(tool("a", 1L), tool("b", 1L), tool("c", 3L));
    assertThat(
            maximum(
                    content(
                        tools,
                        List.of(
                            declaration("a", "synthetic-main"),
                            declaration("b", "synthetic-main"),
                            declaration("c", "synthetic-other\nsynthetic-line"))))
                .isNull())
        .isTrue();
    assertThat(
            maximum(
                    content(
                        tools,
                        tools.stream()
                            .map(t -> declaration(t.toolCallId(), "synthetic-one\nsynthetic-two"))
                            .toList()))
                .isNull())
        .isTrue();
  }

  @Test
  void allDistinctInputsDoNotCreateARepeatedHotspot() throws Exception {
    var tools = List.of(tool("a", 10L), tool("b", 20L), tool("c", 30L));
    var declarations =
        tools.stream()
            .map(t -> declaration(t.toolCallId(), "synthetic-unique-" + t.toolCallId()))
            .toList();
    assertThat(maximum(content(tools, declarations)).isNull()).isTrue();
  }

  @Test
  void stableRepresentativesAndTiesUseCompleteIdentityNotReadOrder() throws Exception {
    var tools = List.of(tool("d", 1L), tool("c", 1L), tool("b", 1L), tool("a", 1L));
    var sources =
        tools.stream()
            .map(
                t ->
                    declaration(
                        t.toolCallId(),
                        t.toolCallId().compareTo("c") < 0 ? "synthetic-alpha" : "synthetic-beta"))
            .toList();
    assertThat(maximum(content(tools, sources)).path("tool").path("toolCallId").asText())
        .isEqualTo("a");
    var reversed = new ArrayList<>(tools);
    java.util.Collections.reverse(reversed);
    assertThat(maximum(content(reversed, sources))).isEqualTo(maximum(content(tools, sources)));
  }

  @Test
  void catalogInlineMirrorsAndSequenceOwnershipAreOrderIndependent() throws Exception {
    var base = baseline();
    var call = firstCall(base);
    var sources = call.sourceUnits();
    var entries = new java.util.LinkedHashMap<String, SourceUnitCatalogEntry>();
    for (int i = 0; i < sources.size(); i++)
      entries.put("source-" + i, entry("source-" + i, sources.get(i)));
    var range =
        new SourceUnitRefRange(
            Optional.of("synthetic-sequence"), 0, 3, List.of(), Optional.of("assistant"));
    var owner = replace(call, sources, List.of(range));
    var callUnit = unit(List.of(owner), List.of(), Map.of(), List.of());
    var catalogUnit =
        unit(
            List.of(),
            List.of(),
            entries,
            List.of(
                new NormalizedSequenceChunk(
                    "synthetic-sequence", 0, List.copyOf(entries.keySet()))));
    var tools = firstTools(base);
    var toolUnit = unit(List.of(), tools, Map.of(), List.of());
    var first = collect(base, List.of(toolUnit, catalogUnit, callUnit), tools);
    var second = collect(base, List.of(callUnit, catalogUnit, toolUnit), tools);
    assertThat(first).isNotNull().isEqualTo(second);
    assertThat(first.tool().inputPreview()).isEqualTo("synthetic-alpha");
    var catalogOnly =
        unit(List.of(replace(call, List.of(), List.of(range))), List.of(), Map.of(), List.of());
    assertThat(collect(base, List.of(catalogOnly, toolUnit, catalogUnit), tools)).isEqualTo(first);
    var incomplete =
        unit(
            List.of(
                replace(
                    call,
                    sources,
                    List.of(
                        new SourceUnitRefRange(
                            Optional.of("missing"), 0, 3, List.of(), Optional.empty())))),
            tools,
            entries,
            List.of());
    assertThat(collect(base, List.of(incomplete), tools)).isNull();
    var unowned = unit(List.of(call), tools, entries, List.of());
    assertThat(collect(base, List.of(unowned), tools)).isNull();
    var duplicateEntries = new java.util.LinkedHashMap<>(entries);
    duplicateEntries.put("independent", entry("independent", sources.getFirst()));
    var duplicateRange =
        new SourceUnitRefRange(
            Optional.empty(),
            0,
            0,
            List.copyOf(duplicateEntries.keySet()),
            Optional.of("assistant"));
    assertThat(
            collect(
                base,
                List.of(
                    unit(
                        List.of(replace(call, sources, List.of(duplicateRange))),
                        tools,
                        duplicateEntries,
                        List.of())),
                tools))
        .isNull();
    var repeatedRef =
        new SourceUnitRefRange(
            Optional.empty(),
            0,
            0,
            List.of("source-0", "source-0", "source-1", "source-2"),
            Optional.of("assistant"));
    assertThat(
            collect(
                base,
                List.of(
                    unit(
                        List.of(replace(call, sources, List.of(repeatedRef))),
                        tools,
                        entries,
                        List.of())),
                tools))
        .isNull();
    var resultOnly =
        unit(
            List.of(),
            List.of(),
            Map.of(
                "result",
                entry(
                    "result",
                    Map.of(
                        "type", "tool_result", "tool_call_id", "a", "output", "synthetic-output"))),
            List.of());
    assertThat(
            collect(
                base, List.of(unit(List.of(call), tools, Map.of(), List.of()), resultOnly), tools))
        .isNotNull();
  }

  @Test
  void duplicateAndLateConflictingDeclarationsInvalidateWithoutChangingOldCounts()
      throws Exception {
    var base = baseline();
    var call = firstCall(base);
    var tools = firstTools(base);
    var initial = unit(List.of(call), tools, Map.of(), List.of());
    var duplicateTool = unit(List.of(), List.of(tools.getFirst()), Map.of(), List.of());
    assertThat(collect(base, List.of(initial, duplicateTool), tools)).isNull();
    assertThat(
            collect(
                base, List.of(initial, unit(List.of(call), List.of(), Map.of(), List.of())), tools))
        .isNull();
    var duplicated = new ArrayList<>(call.sourceUnits());
    duplicated.add(call.sourceUnits().getFirst());
    assertThat(
            collect(
                base,
                List.of(
                    unit(
                        List.of(replace(call, duplicated, List.of())), tools, Map.of(), List.of())),
                tools))
        .isNull();
    var conflict =
        unit(
            List.of(),
            List.of(),
            Map.of("late", entry("late", declaration("a", "synthetic-conflict"))),
            List.of());
    assertThat(collect(base, List.of(initial, conflict), tools)).isNull();
    var duplicateTools = new ArrayList<>(tools);
    duplicateTools.add(tools.getFirst());
    var duplicatedContent = content(duplicateTools, call.sourceUnits());
    var result = SessionExecutionProjection.diagnostics(duplicatedContent);
    assertThat(result.totalTools()).isEqualTo(3);
    assertThat(result.workloadSignals().candidates().getFirst().sameInputMaximum()).isNull();
  }

  @Test
  void nonCodexOrUnconfirmedContextNeverAcquiresInputFact() throws Exception {
    var base = baseline();
    var header = base.header();
    var other =
        base.withHeader(
            new NormalizedContentHeader(
                header.schemaVersion(),
                NormalizedAgent.CLAUDE_CODE,
                header.session(),
                header.totals()));
    assertThat(maximum(other).isNull()).isTrue();
    var collector = new SessionExecutionInputs(base);
    collector.observe(unit(List.of(firstCall(base)), firstTools(base), Map.of(), List.of()));
    collector.resolve();
    for (var tool : firstTools(base))
      collector.add(SessionApiHandler.toolSummary(tool, "synthetic", false), false);
    assertThat(collector.maximum(List.of("main", "", "exec_command"), 3, 3, 0, 0, "5")).isNull();
  }

  @Test
  void globalBudgetOverflowRetractsEarlierFactsWithNoExtraCursor() throws Exception {
    var base = baseline();
    var tools = firstTools(base);
    var original = unit(List.of(firstCall(base)), tools, Map.of(), List.of());
    var empty = unit(List.of(), List.of(), Map.of(), List.of());
    var within = new ArrayList<NormalizedContentUnit>();
    within.add(original);
    for (int i = 1; i < 16_384; i++) within.add(empty);
    assertThat(collect(base, within, tools)).isNotNull();
    within.add(empty);
    assertThat(collect(base, within, tools)).isNull();
    var late =
        unit(
            List.of(
                replace(firstCall(base), List.of(Map.of("metadata", "x".repeat(1025))), List.of())),
            List.of(),
            Map.of(),
            List.of());
    assertThat(collect(base, List.of(original, late), tools)).isNull();
    var mirrors = new ArrayList<NormalizedContentUnit>();
    mirrors.add(original);
    for (int i = 0; i < 65; i++)
      mirrors.add(
          unit(
              List.of(),
              List.of(),
              Map.of(
                  "large-" + i,
                  entry("large-" + i, declaration("unrelated-" + i, "x".repeat(65_536)))),
              List.of()));
    assertThat(collect(base, mirrors, tools)).isNull();
    var opens = new int[] {0};
    NormalizedSessionContent counted =
        new NormalizedSessionContent() {
          /** 返回合成冻结元数据。 */
          @Override
          public NormalizedContentHeader header() {
            return base.header();
          }

          /** 记录打开次数，不修改内容遍历。 */
          @Override
          public ContentCursor openCursor() throws java.io.IOException {
            opens[0]++;
            return base.openCursor();
          }
        };
    SessionExecutionProjection.diagnostics(counted);
    // 原诊断已有 owner/tool、preview 与 inputPreview 四个游标，本功能新增零个。
    assertThat(opens[0]).isEqualTo(4);
  }

  @Test
  void parameterCharacterBudgetCountsMirrorsAndStopsBeforeEncodingOverflow() throws Exception {
    var base = baseline();
    var tools = firstTools(base);
    var initial = unit(List.of(firstCall(base)), tools, Map.of(), List.of());
    var units = new ArrayList<NormalizedContentUnit>();
    units.add(initial);
    int initialCharacters = "synthetic-alpha".length() * 2 + "synthetic-beta".length();
    for (int i = 0; i < 63; i++)
      units.add(
          unit(
              List.of(),
              List.of(),
              Map.of(
                  "large-" + i,
                  entry("large-" + i, declaration("unrelated-" + i, "x".repeat(65_536)))),
              List.of()));
    units.add(
        unit(
            List.of(),
            List.of(),
            Map.of(
                "last",
                entry(
                    "last", declaration("unrelated-last", "x".repeat(65_536 - initialCharacters)))),
            List.of()));
    assertThat(collect(base, units, tools)).isNotNull();
    units.add(
        unit(
            List.of(),
            List.of(),
            Map.of("over", entry("over", declaration("unrelated-over", "x"))),
            List.of()));
    assertThat(collect(base, units, tools)).isNull();
    var maxSingle =
        firstCall(
            content(
                List.of(tool("a", 2L), tool("b", 2L), tool("c", 1L)),
                List.of(
                    declaration("a", "x".repeat(65_536)),
                    declaration("b", "x".repeat(65_536)),
                    declaration("c", "y"))));
    assertThat(collect(base, List.of(unit(List.of(maxSingle), tools, Map.of(), List.of())), tools))
        .isNotNull();
  }

  @Test
  void eachCollectionLimitAcceptsBoundaryAndRejectsNextItem() throws Exception {
    var base = baseline();
    var tools = firstTools(base);
    var owner = firstCall(base);
    var calls = new ArrayList<NormalizedCall>();
    calls.add(owner);
    for (int i = 1; i < 16_384; i++) calls.add(emptyCall("extra-call-" + i));
    assertThat(
            collect(
                base,
                List.of(
                    unit(calls.subList(0, 9000), tools, Map.of(), List.of()),
                    unit(calls.subList(9000, calls.size()), List.of(), Map.of(), List.of())),
                tools))
        .isNotNull();
    calls.add(emptyCall("over-call"));
    assertThat(
            collect(
                base,
                List.of(
                    unit(calls.subList(0, 9000), tools, Map.of(), List.of()),
                    unit(calls.subList(9000, calls.size()), List.of(), Map.of(), List.of())),
                tools))
        .isNull();
    var catalog = new java.util.HashMap<String, SourceUnitCatalogEntry>();
    for (int i = 0; i < 16_384; i++) catalog.put("empty-" + i, entry("empty-" + i, Map.of()));
    assertThat(collect(base, catalogUnits(owner, tools, catalog), tools)).isNotNull();
    catalog.put("over", entry("over", Map.of()));
    assertThat(collect(base, catalogUnits(owner, tools, catalog), tools)).isNull();
    var allTools = new ArrayList<>(tools);
    for (int i = 3; i < 16_384; i++) {
      var t = tool("extra-tool-" + i, null);
      allTools.add(
          new NormalizedToolExecution(
              t.toolCallId(),
              "synthetic-noop",
              t.scope(),
              "unrelated-call",
              t.resultConsumedByCallId(),
              t.status(),
              t.exitCode(),
              t.durationMs(),
              t.filesTouched(),
              t.subagentId(),
              t.observation()));
    }
    assertThat(
            collect(
                base,
                List.of(
                    unit(List.of(owner), allTools.subList(0, 9000), Map.of(), List.of()),
                    unit(List.of(), allTools.subList(9000, allTools.size()), Map.of(), List.of())),
                tools))
        .isNotNull();
    allTools.add(tool("over-tool", null));
    assertThat(
            collect(
                base,
                List.of(
                    unit(List.of(owner), allTools.subList(0, 9000), Map.of(), List.of()),
                    unit(List.of(), allTools.subList(9000, allTools.size()), Map.of(), List.of())),
                tools))
        .isNull();
  }

  @Test
  void metadataRefsDepthAndNodeBudgetsFailClosedWithoutPoisoningOldDiagnostics() throws Exception {
    var base = baseline();
    var tools = firstTools(base);
    var owner = firstCall(base);
    var initial = unit(List.of(owner), tools, Map.of(), List.of());
    var extra = emptyCall("extra");
    assertThat(
            collect(
                base,
                List.of(
                    initial,
                    unit(
                        List.of(
                            replace(
                                extra, List.of(Map.of("metadata", "x".repeat(1024))), List.of())),
                        List.of(),
                        Map.of(),
                        List.of())),
                tools))
        .isNotNull();
    assertThat(
            collect(
                base,
                List.of(
                    initial,
                    unit(
                        List.of(
                            replace(
                                extra, List.of(Map.of("metadata", "x".repeat(1025))), List.of())),
                        List.of(),
                        Map.of(),
                        List.of())),
                tools))
        .isNull();
    Object nested = "synthetic";
    for (int i = 0; i < 8; i++) nested = List.of(nested);
    assertThat(
            collect(
                base,
                List.of(
                    initial,
                    unit(List.of(), List.of(), Map.of("depth", entry("depth", nested)), List.of())),
                tools))
        .isNotNull();
    assertThat(
            collect(
                base,
                List.of(
                    initial,
                    unit(
                        List.of(),
                        List.of(),
                        Map.of("depth", entry("depth", List.of(nested))),
                        List.of())),
                tools))
        .isNull();
    var nodeBoundary = java.util.Collections.nCopies(1023, "synthetic");
    assertThat(
            collect(
                base,
                List.of(
                    initial,
                    unit(
                        List.of(),
                        List.of(),
                        Map.of("nodes", entry("nodes", nodeBoundary)),
                        List.of())),
                tools))
        .isNotNull();
    assertThat(
            collect(
                base,
                List.of(
                    initial,
                    unit(
                        List.of(),
                        List.of(),
                        Map.of(
                            "nodes",
                            entry("nodes", java.util.Collections.nCopies(1024, "synthetic"))),
                        List.of())),
                tools))
        .isNull();
    var keys = new ArrayList<String>();
    for (int i = 0; i < 65_533; i++) keys.add("key-" + i);
    var chunks = chunks(keys);
    assertThat(collect(base, List.of(initial, unit(List.of(), List.of(), Map.of(), chunks)), tools))
        .isNotNull();
    keys.add("over-key");
    assertThat(
            collect(
                base, List.of(initial, unit(List.of(), List.of(), Map.of(), chunks(keys))), tools))
        .isNull();
    var manyNodes = new ArrayList<NormalizedContentUnit>();
    manyNodes.add(initial);
    for (int i = 0; i < 255; i++)
      manyNodes.add(
          unit(
              List.of(),
              List.of(),
              Map.of("nodes-" + i, entry("nodes-" + i, nodeBoundary)),
              List.of()));
    manyNodes.add(
        unit(
            List.of(),
            List.of(),
            Map.of(
                "final-nodes",
                entry("final-nodes", java.util.Collections.nCopies(1008, "synthetic"))),
            List.of()));
    assertThat(collect(base, manyNodes, tools)).isNotNull();
    manyNodes.add(
        unit(
            List.of(), List.of(), Map.of("over-node", entry("over-node", "synthetic")), List.of()));
    assertThat(collect(base, manyNodes, tools)).isNull();
    var manyMetadata = new ArrayList<NormalizedContentUnit>();
    manyMetadata.add(initial);
    for (int i = 0; i < 4097; i++)
      manyMetadata.add(
          unit(
              List.of(),
              List.of(),
              Map.of(
                  "metadata-" + i,
                  entry(
                      "metadata-" + i,
                      Map.of(
                          "metadata",
                          String.format(java.util.Locale.ROOT, "%04d", i) + "x".repeat(1020)))),
              List.of()));
    assertThat(collect(base, manyMetadata, tools)).isNull();
  }

  @Test
  void repeatedMetadataCharactersExceedBudgetRegardlessOfStringObjectSharing() throws Exception {
    var base = baseline();
    var tools = firstTools(base);
    String shared = "synthetic-metadata-" + "x".repeat(1005);
    assertThat(shared.length()).isEqualTo(1024);
    var maxima = new ArrayList<SessionExecutionInputs.SameInputMaximum>();
    for (boolean copy : List.of(false, true)) {
      var sources = new ArrayList<>(firstCall(base).sourceUnits());
      for (int i = 0; i < 4097; i++)
        sources.add(Map.of("metadata", copy ? new String(shared) : shared));
      var result = SessionExecutionProjection.diagnostics(content(tools, sources));
      var parent = result.workloadSignals().candidates().getFirst();
      maxima.add(parent.sameInputMaximum());
      assertThat(result.totalTools()).isEqualTo(3);
      assertThat(result.measuredTools()).isEqualTo(3);
      assertThat(parent.measuredWorkNanos()).isEqualTo("5");
      assertThat(parent.longest().tool().toolCallId()).isEqualTo("a");
    }
    assertThat(maxima).containsOnlyNulls();
  }

  private static List<NormalizedSequenceChunk> chunks(List<String> keys) {
    var result = new ArrayList<NormalizedSequenceChunk>();
    for (int i = 0; i < keys.size(); i += 9000)
      result.add(
          new NormalizedSequenceChunk(
              "unrelated", i, keys.subList(i, Math.min(keys.size(), i + 9000))));
    return result;
  }

  private static List<NormalizedContentUnit> catalogUnits(
      NormalizedCall owner,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog) {
    var keys = new ArrayList<>(catalog.keySet());
    var result = new ArrayList<NormalizedContentUnit>();
    result.add(unit(List.of(owner), tools, Map.of(), List.of()));
    for (int i = 0; i < keys.size(); i += 9000) {
      var part = new java.util.HashMap<String, SourceUnitCatalogEntry>();
      for (int j = i; j < Math.min(keys.size(), i + 9000); j++)
        part.put(keys.get(j), catalog.get(keys.get(j)));
      result.add(unit(List.of(), List.of(), part, List.of()));
    }
    return result;
  }

  private static NormalizedCall emptyCall(String id) {
    return new NormalizedCall(
        id,
        1,
        "C1",
        CallScope.MAIN,
        Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        "synthetic",
        Optional.empty(),
        new NormalizedCallUsage(0, 0, 0, 0, 0),
        new NormalizedCallRequest(List.of()),
        new NormalizedCallResponse(List.of()),
        List.of(),
        List.of(),
        Map.of(),
        Map.of());
  }

  private static NormalizedSessionContent baseline() {
    return content(
        List.of(tool("a", 2L), tool("b", 2L), tool("c", 1L)),
        List.of(
            declaration("a", "synthetic-alpha"),
            declaration("b", "synthetic-alpha"),
            declaration("c", "synthetic-beta")));
  }

  private static com.fasterxml.jackson.databind.JsonNode maximum(NormalizedSessionContent content)
      throws Exception {
    var json = new ObjectMapper().valueToTree(SessionExecutionProjection.diagnostics(content));
    return json.path("workloadSignals").path("candidates").get(0).path("sameInputMaximum");
  }

  private static NormalizedCall firstCall(NormalizedSessionContent content) throws Exception {
    try (var cursor = content.openCursor()) {
      return cursor.next().calls().getFirst();
    }
  }

  private static List<NormalizedToolExecution> firstTools(NormalizedSessionContent content)
      throws Exception {
    var result = new ArrayList<NormalizedToolExecution>();
    try (var cursor = content.openCursor()) {
      while (cursor.hasNext()) result.addAll(cursor.next().toolExecutions());
    }
    return result;
  }

  private static SessionExecutionInputs.SameInputMaximum collect(
      NormalizedSessionContent base,
      List<NormalizedContentUnit> units,
      List<NormalizedToolExecution> tools) {
    var collector = new SessionExecutionInputs(base);
    units.forEach(collector::observe);
    collector.resolve();
    for (var tool : tools)
      collector.add(SessionApiHandler.toolSummary(tool, "wrong-bare-id-preview", false), true);
    return collector.maximum(
        List.of("main", "", "exec_command"), tools.size(), tools.size(), 0, 0, "5");
  }

  private static NormalizedContentUnit unit(
      List<NormalizedCall> calls,
      List<NormalizedToolExecution> tools,
      Map<String, SourceUnitCatalogEntry> catalog,
      List<NormalizedSequenceChunk> sequences) {
    return new NormalizedContentUnit(0, List.of(), calls, tools, List.of(), catalog, sequences);
  }

  private static NormalizedCall replace(
      NormalizedCall call, List<Map<String, Object>> sources, List<SourceUnitRefRange> ranges) {
    return new NormalizedCall(
        call.callId(),
        call.callIndex(),
        call.callKey(),
        call.scope(),
        call.parentCallId(),
        call.parentToolCallId(),
        call.turnId(),
        call.model(),
        call.timestamp(),
        call.usage(),
        call.request(),
        call.response(),
        ranges,
        sources,
        call.attributionCandidates(),
        call.usageSource());
  }

  private static SourceUnitCatalogEntry entry(String key, Object payload) {
    return new SourceUnitCatalogEntry(
        key,
        "synthetic",
        "synthetic#event[1]",
        "text",
        "",
        SourceUnitDirection.RESPONSE,
        1,
        0,
        ByteRange.empty(),
        "",
        Optional.empty(),
        Optional.empty(),
        50,
        Optional.empty(),
        Optional.empty(),
        payload,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  private static NormalizedToolExecution other(NormalizedToolExecution tool) {
    return new NormalizedToolExecution(
        tool.toolCallId(),
        tool.name(),
        tool.scope(),
        tool.declaredByCallId(),
        tool.resultConsumedByCallId(),
        tool.status(),
        tool.exitCode(),
        tool.durationMs(),
        tool.filesTouched(),
        tool.subagentId(),
        Optional.of(
            new SourceToolObservation(
                tool.toolCallId(), 10L, 0, null, null, "other", "synthetic:event", null)));
  }

  private static Map<String, Object> declaration(String id, Object input) {
    return Map.of("type", "tool_use", "id", id, "name", "exec_command", "input", input);
  }

  private static NormalizedToolExecution tool(String id, Long nanos) {
    return new NormalizedToolExecution(
        id,
        "exec_command",
        CallScope.MAIN,
        "call-1",
        Optional.empty(),
        Optional.empty(),
        Optional.of(0),
        nanos == null ? null : nanos / 1_000_000,
        List.of(),
        Optional.empty(),
        nanos == null
            ? Optional.empty()
            : Optional.of(
                new SourceToolObservation(
                    id,
                    nanos,
                    0,
                    null,
                    null,
                    "executor_reported",
                    "codex:exec_command_end#event[1]",
                    null)));
  }

  private static NormalizedSessionContent content(
      List<NormalizedToolExecution> tools, List<Map<String, Object>> sources) {
    var call =
        new NormalizedCall(
            "call-1",
            1,
            "C1",
            CallScope.MAIN,
            Optional.empty(),
            Optional.empty(),
            Optional.of("synthetic-turn"),
            "synthetic",
            Optional.empty(),
            new NormalizedCallUsage(0, 0, 0, 0, 0),
            new NormalizedCallRequest(List.of()),
            new NormalizedCallResponse(
                tools.stream().map(NormalizedToolExecution::toolCallId).toList()),
            List.of(),
            sources,
            Map.of(),
            Map.of());
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                1L,
                "toolExecutions",
                (long) tools.size(),
                "diagnostics",
                0L,
                "sourceFiles",
                0L,
                "sourceUnitCatalog",
                0L,
                "sourceUnitSequenceEntries",
                0L)),
        List.of(),
        List.of(call),
        tools,
        List.of(),
        Map.of(),
        Map.of());
  }
}
