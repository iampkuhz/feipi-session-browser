package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.feipi.session.browser.application.imports.ImportedSessionUseCase;
import com.feipi.session.browser.application.sessiondetail.PayloadCallContentExtractor;
import com.feipi.session.browser.application.sessiondetail.PayloadLookup;
import com.feipi.session.browser.application.sessiondetail.ToolInputContents;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.scan.artifact.CanonicalJsonWriter;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 使用真实三来源解析器证明导入保留计量、正文、工具及完整 payload。所有数据均为合成。 */
class ImportedSessionAnalysisIntegrationTest {

  @ParameterizedTest
  @ValueSource(strings = {"mode", "permission-mode", "attachment", "all"})
  void knownClaudeAuxiliaryRecordsDoNotIncreasePromptsCallsOrReportedUsage(String type)
      throws Exception {
    String base =
        messageTranscript()
            .replace("\"input_tokens\":12", "\"input_tokens\":11")
            .replace("\"cache_read_input_tokens\":4", "\"cache_read_input_tokens\":3")
            .replace("\"cache_creation_input_tokens\":3", "\"cache_creation_input_tokens\":2")
            .replace("\"output_tokens\":5", "\"output_tokens\":7");
    List<String> types =
        "all".equals(type) ? List.of("mode", "permission-mode", "attachment") : List.of(type);
    String auxiliaries =
        String.join(
            "\n",
            types.stream()
                .map(
                    value ->
                        "{\"type\":\""
                            + value
                            + "\",\"sessionId\":\"shared-session\",\"content\":\"synthetic"
                            + " auxiliary context\"}")
                .toList());
    String transcript = auxiliaries + "\n" + base;
    try (var service = service()) {
      var analysis =
          service.create(
              input(transcript), "synthetic-known-aux.jsonl", NormalizedAgent.CLAUDE_CODE);
      var row = analysis.sessionRow();
      assertThat(row.userMessageCount()).isEqualTo(1);
      assertThat(row.assistantMessageCount()).isEqualTo(1);
      assertThat(analysis.artifact().calls()).hasSize(1);
      assertThat(row.toolCallCount()).isEqualTo(1);
      assertThat(row.freshInputTokens()).isEqualTo(11);
      assertThat(row.cacheReadTokens()).isEqualTo(3);
      assertThat(row.cacheWriteTokens()).isEqualTo(2);
      assertThat(row.outputTokens()).isEqualTo(7);
      assertThat(row.totalTokens()).isEqualTo(23);
      assertThat(row.tokenProvenance())
          .isEqualTo(
              new TokenProvenance(
                  "provider_reported",
                  "provider_reported",
                  "provider_reported",
                  "provider_reported",
                  "",
                  0,
                  0,
                  0));
      assertThat(
              analysis.artifact().sourceUnitCatalog().values().stream()
                  .filter(unit -> "import_raw_event".equals(unit.unitType()))
                  .map(unit -> unit.payload())
                  .toList())
          .containsExactlyInAnyOrderElementsOf(transcript.lines().toList());
    }
  }

  @ParameterizedTest
  @ValueSource(strings = {"mode", "permission-mode", "attachment"})
  void auxiliaryAllowlistDoesNotAcceptCodexOrUnknownTypes(String type) throws Exception {
    try (var service = service()) {
      String auxiliary = "{\"type\":\"" + type + "\",\"content\":\"synthetic auxiliary\"}";
      assertThatThrownBy(
              () ->
                  service.create(
                      input(codexTranscript() + "\n" + auxiliary),
                      "synthetic-codex-aux.jsonl",
                      NormalizedAgent.CODEX))
          .isInstanceOf(SessionImportException.class)
          .extracting("code")
          .isEqualTo("unsupported_format");
      String unknown = "{\"type\":\"" + type + "-synthetic-unknown\"}";
      for (NormalizedAgent source : NormalizedAgent.values()) {
        assertThatThrownBy(
                () -> service.create(input(unknown), "synthetic-unknown-aux.jsonl", source))
            .isInstanceOf(SessionImportException.class)
            .extracting("code")
            .isEqualTo("unsupported_format");
      }
    }
  }

  @Test
  void completeUsageImportsKeepReportedProvenanceAndExactBrowserTotals() throws Exception {
    try (var service = service()) {
      for (NormalizedAgent source : NormalizedAgent.values()) {
        String transcript =
            source == NormalizedAgent.CODEX
                ? codexTranscript()
                : messageTranscript()
                    .replace("\"input_tokens\":12", "\"input_tokens\":11")
                    .replace("\"cache_read_input_tokens\":4", "\"cache_read_input_tokens\":3")
                    .replace(
                        "\"cache_creation_input_tokens\":3", "\"cache_creation_input_tokens\":2")
                    .replace("\"output_tokens\":5", "\"output_tokens\":7");
        var analysis = service.create(input(transcript), "synthetic-reported.jsonl", source);
        assertThat(analysis.sessionRow().totalTokens())
            .isEqualTo(source == NormalizedAgent.CODEX ? 123 : 23);
        assertThat(analysis.sessionRow().tokenProvenance())
            .isEqualTo(
                new TokenProvenance(
                    "provider_reported",
                    "provider_reported",
                    "provider_reported",
                    "provider_reported",
                    "",
                    0,
                    0,
                    0));
        assertThat(TokenProvenance.fromMetadata(analysis.artifact().session()))
            .isEqualTo(analysis.sessionRow().tokenProvenance());
      }
    }
  }

  @Test
  void reportedZeroIsDistinctFromUnreportedCacheWriteForEverySource() throws Exception {
    try (var service = service()) {
      for (NormalizedAgent source : NormalizedAgent.values()) {
        String zero =
            (source == NormalizedAgent.CODEX ? codexTranscript() : messageTranscript())
                .replaceAll(
                    "(\"(?:input_tokens|cached_input_tokens|cache_read_input_tokens|cache_creation_input_tokens|output_tokens|total_tokens)\":)\\d+",
                    "$10");
        var reported = service.create(input(zero), "synthetic-zero.jsonl", source);
        assertThat(reported.sessionRow().totalTokens()).isZero();
        assertThat(reported.sessionRow().tokenProvenance())
            .isEqualTo(
                new TokenProvenance(
                    "provider_reported",
                    "provider_reported",
                    "provider_reported",
                    "provider_reported",
                    "",
                    0,
                    0,
                    0));
        var missing =
            service.create(
                input(zero.replace(",\"cache_creation_input_tokens\":0", "")),
                "synthetic-missing.jsonl",
                source);
        assertThat(missing.sessionRow().totalTokens()).isZero();
        assertThat(missing.sessionRow().tokenProvenance())
            .isEqualTo(
                new TokenProvenance(
                    "provider_reported",
                    "provider_reported",
                    "unavailable",
                    "provider_reported",
                    "",
                    0,
                    1,
                    0));
        for (var analysis : List.of(reported, missing)) {
          assertThat(analysis.artifact().calls()).hasSize(1);
          var call = analysis.artifact().calls().getFirst();
          var fullPayload = PayloadLookup.fromArtifact(analysis.artifact(), PayloadVisibility.FULL);
          assertThat(fullPayload.lookup("main:resp:" + call.callId()).orElseThrow().content())
              .contains("import answer");
          assertThat(fullPayload.lookup("main:req:" + call.callId()).orElseThrow().content())
              .contains("import question");
          assertThat(fullPayload.lookup("tool:input:tool-1").orElseThrow().content())
              .contains("echo synthetic");
          assertThat(fullPayload.lookup("tool:result:tool-1").orElseThrow().content())
              .isEqualTo("synthetic output");
          assertThat(analysis.artifact().toolExecutions())
              .singleElement()
              .satisfies(tool -> assertThat(tool.declaredByCallId()).isEqualTo(call.callId()));
        }
      }
    }
  }

  @Test
  void partialUsageAcrossResponsesRetainsMixedCoverageWithoutEstimatingMissingFields()
      throws Exception {
    try (var service = service()) {
      for (NormalizedAgent source : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.QODER)) {
        String second =
            messageTranscript()
                .lines()
                .toList()
                .get(1)
                .replace("msg-1", "synthetic-second-message")
                .replace("assistant-1", "synthetic-second-assistant")
                .replace(",\"cache_creation_input_tokens\":3", "");
        var analysis =
            service.create(
                input(messageTranscript() + "\n" + second), "synthetic-mixed.jsonl", source);
        assertThat(analysis.sessionRow().tokenProvenance())
            .isEqualTo(
                new TokenProvenance(
                    "provider_reported",
                    "provider_reported",
                    "mixed",
                    "provider_reported",
                    "",
                    0,
                    1,
                    0));
      }
      String codex =
          """
          {"type":"session_meta","payload":{"id":"synthetic-mixed-modern"}}
          {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"synthetic prompt"}]}}
          {"type":"token_usage_record","payload":{"response_id":"synthetic-first-response","usage":{"input_tokens":3,"cached_input_tokens":1,"cache_write_input_tokens":0,"output_tokens":2}}}
          {"type":"token_usage_record","payload":{"response_id":"synthetic-second-response","usage":{"input_tokens":4,"cached_input_tokens":2,"output_tokens":1}}}
          """;
      var codexAnalysis =
          service.create(input(codex), "synthetic-mixed-modern.jsonl", NormalizedAgent.CODEX);
      assertThat(codexAnalysis.sessionRow().tokenProvenance())
          .isEqualTo(
              new TokenProvenance(
                  "mixed", "provider_reported", "mixed", "provider_reported", "", 0, 1, 0));
    }
  }

  @Test
  void sourcesWithoutUsageDoNotInventReportedMeasurement() throws Exception {
    var mapper = new ObjectMapper();
    var lines = new ArrayList<String>();
    for (String line : messageTranscript().lines().toList()) {
      var event = (ObjectNode) mapper.readTree(line);
      ((ObjectNode) event.get("message")).remove("usage");
      lines.add(mapper.writeValueAsString(event));
    }
    try (var service = service()) {
      var claude =
          service.create(
              input(String.join("\n", lines)),
              "synthetic-unknown.jsonl",
              NormalizedAgent.CLAUDE_CODE);
      assertThat(claude.sessionRow().tokenProvenance()).isEqualTo(TokenProvenance.unknown());
      String codex =
          String.join(
              "\n",
              codexTranscript().lines().filter(line -> !line.contains("token_count")).toList());
      var codexAnalysis =
          service.create(input(codex), "synthetic-unknown-codex.jsonl", NormalizedAgent.CODEX);
      assertThat(codexAnalysis.sessionRow().tokenProvenance()).isEqualTo(TokenProvenance.unknown());
      assertThat(claude.sessionRow().totalTokens()).isZero();
      assertThat(codexAnalysis.sessionRow().totalTokens()).isZero();
    }
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "content",
        "parts",
        "message.content",
        "message.parts",
        "payload.content",
        "payload.parts"
      })
  void qoderNoUsageEstimatesMatchTheirMethodsForAllSupportedContainers(String container)
      throws Exception {
    try (var service = service()) {
      for (boolean cache : List.of(false, true)) {
        String transcript = estimateTranscript(container, cache);
        var analysis =
            service.create(input(transcript), "synthetic-estimate.jsonl", NormalizedAgent.QODER);
        long fresh = cache ? 2 : 6;
        assertThat(analysis.sessionRow().freshInputTokens()).isEqualTo(fresh);
        assertThat(analysis.sessionRow().outputTokens()).isEqualTo(4);
        assertThat(analysis.sessionRow().totalTokens()).isEqualTo(fresh + 4);
        assertThat(analysis.sessionRow().tokenProvenance())
            .isEqualTo(
                new TokenProvenance(
                    "estimated",
                    "unavailable",
                    "unavailable",
                    "estimated",
                    cache ? "cache_transcript_v1" : "visible_context_v1",
                    1,
                    1,
                    0));
        assertThat(analysis.artifact().session())
            .containsEntry("freshInputTokens", fresh)
            .containsEntry("outputTokens", 4L)
            .containsEntry("totalTokens", fresh + 4);
      }
    }
  }

  @Test
  void mixedQoderLayoutsWithoutUsageRemainUnknownWithoutInventedEstimates() throws Exception {
    String transcript =
        estimateTranscript("content", true).lines().toList().getFirst()
            + "\n"
            + estimateTranscript("message.content", false).lines().toList().get(1);
    try (var service = service()) {
      var analysis =
          service.create(
              input(transcript), "synthetic-layout-conflict.jsonl", NormalizedAgent.QODER);
      assertThat(analysis.sessionRow().tokenProvenance()).isEqualTo(TokenProvenance.unknown());
      assertThat(analysis.sessionRow().totalTokens()).isZero();
      assertThat(analysis.artifact().calls().getFirst().sourceUnits())
          .extracting(unit -> unit.get("text"))
          .containsExactly("abcdefg", "hijklmn");
    }
  }

  @Test
  void importedMetaContextRemainsUserContextWithoutAddingHumanPromptsOrLosingTiming()
      throws Exception {
    String transcript =
        """
        {"type":"user","sessionId":"synthetic-meta-import","message":{"role":"user","content":"human prompt"}}
        {"type":"user","sessionId":"synthetic-meta-import","isMeta":true,"message":{"role":"user","content":"  meta context\\n"}}
        {"type":"assistant","sessionId":"synthetic-meta-import","message":{"id":"synthetic-meta-answer","content":"answer","usage":{"input_tokens":1,"cache_read_input_tokens":0,"cache_creation_input_tokens":0,"output_tokens":1}}}
        {"type":"system","sessionId":"synthetic-meta-import","subtype":"turn_duration","durationMs":1700,"uuid":"synthetic-duration"}
        """;
    try (var service = service()) {
      var analysis =
          service.create(input(transcript), "synthetic-meta.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(analysis.sessionRow().userMessageCount()).isEqualTo(1);
      var units = analysis.artifact().calls().getFirst().sourceUnits();
      assertThat(units)
          .extracting(unit -> unit.get("text"))
          .containsExactly("human prompt", "  meta context\n", "answer");
      assertThat(units.get(1))
          .containsEntry("role", "user")
          .containsEntry("type", "user")
          .containsEntry("isMeta", true);
      assertThat(analysis.sessionRow().timing().agentTurnSeconds()).isEqualTo(1.7);
    }
  }

  private static String estimateTranscript(String container, boolean cache) throws Exception {
    var mapper = new ObjectMapper();
    var lines = new ArrayList<String>();
    String[] texts = {"abcdefg", "hijklmn", "opqrstu"};
    for (int i = 0; i < texts.length; i++) {
      ObjectNode event = mapper.createObjectNode();
      event.put(cache ? "role" : "type", i == 0 ? "user" : "assistant");
      event.put("sessionId", "synthetic-estimate-session");
      event.put("uuid", "synthetic-estimate-" + i);
      String[] fields = container.split("\\.");
      ObjectNode owner = fields.length == 1 ? event : event.putObject(fields[0]);
      owner
          .putArray(fields[fields.length - 1])
          .addObject()
          .put("type", "text")
          .put("text", texts[i]);
      lines.add(mapper.writeValueAsString(event));
    }
    return String.join("\n", lines);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "content",
        "parts",
        "message.content",
        "message.parts",
        "payload.content",
        "payload.parts"
      })
  void qoderRoleCachePreservesAllSupportedContentContainers(String container) throws Exception {
    String transcript = roleCacheTranscript(container);
    try (var service = service()) {
      var analysis = service.create(input(transcript), "role-cache.jsonl", NormalizedAgent.QODER);
      var artifact = analysis.artifact();
      assertThat(analysis.sessionRow().freshInputTokens()).isEqualTo(12);
      assertThat(analysis.sessionRow().cacheReadTokens()).isEqualTo(4);
      assertThat(analysis.sessionRow().cacheWriteTokens()).isEqualTo(3);
      assertThat(analysis.sessionRow().outputTokens()).isEqualTo(5);
      assertThat(analysis.sessionRow().totalTokens()).isEqualTo(24);
      assertThat(artifact.calls()).hasSize(1);
      assertThat(artifact.calls().getFirst().usage())
          .isEqualTo(new NormalizedCallUsage(12, 4, 3, 5, 24));
      assertThat(artifact.toolExecutions()).hasSize(1);
      assertThat(ToolInputContents.all(artifact)).containsOnlyKeys("tool-1");
      String expectedInput = "{\"command\":\"echo synthetic token=SYNTHETIC_ONLY\"}";
      String expectedResult = "synthetic output token=SYNTHETIC_ONLY";
      assertThat(ToolInputContents.all(artifact).get("tool-1").input()).isEqualTo(expectedInput);
      assertThat(PayloadCallContentExtractor.extractToolResultContents(artifact))
          .containsEntry("tool-1", expectedResult);
      var full = PayloadLookup.fromArtifact(artifact, PayloadVisibility.FULL);
      var standard = PayloadLookup.fromArtifact(artifact, PayloadVisibility.STANDARD);
      assertThat(full.lookup("tool:input:tool-1").orElseThrow().content()).isEqualTo(expectedInput);
      assertThat(full.lookup("tool:result:tool-1").orElseThrow().content())
          .isEqualTo(expectedResult);
      assertThat(standard.lookup("tool:input:tool-1").orElseThrow().content())
          .isEqualTo("{\"command\":\"echo synthetic token=[REDACTED]\"}");
      assertThat(standard.lookup("tool:result:tool-1").orElseThrow().content())
          .isEqualTo("synthetic output token=[REDACTED]");
      var call = artifact.calls().getFirst();
      assertThat(PayloadCallContentExtractor.extractUserMessageTexts(call, artifact))
          .containsExactly("import question");
      assertThat(PayloadCallContentExtractor.extractAssistantText(call, artifact))
          .isEqualTo("import answer");
      assertThat(
              artifact.sourceUnitCatalog().values().stream()
                  .filter(entry -> "import_raw_event".equals(entry.unitType()))
                  .map(entry -> entry.payload())
                  .toList())
          .containsExactlyInAnyOrderElementsOf(transcript.lines().toList());
      assertThat(
              artifact.sourceUnitCatalog().values().stream()
                  .filter(entry -> "tool_use".equals(entry.unitType()))
                  .toList())
          .hasSize(1);
      assertThat(
              artifact.sourceUnitCatalog().values().stream()
                  .filter(entry -> "tool_result".equals(entry.unitType()))
                  .toList())
          .hasSize(1);
      assertThat(artifact.diagnostics())
          .anySatisfy(
              diagnostic -> assertThat(diagnostic.get("code")).isEqualTo("CACHE_FORMAT_ROLE"));
    }
  }

  @Test
  void threeRealParsersPreserveExactUsageAndDetail() throws Exception {
    try (var service = service();
        var useCase = new ImportedSessionUseCase(service)) {
      for (NormalizedAgent source : NormalizedAgent.values()) {
        boolean codex = source == NormalizedAgent.CODEX;
        String text = codex ? codexTranscript() : messageTranscript();
        var metadata = useCase.create(input(text), "../../shared.jsonl", source);
        var analysis = service.find(metadata.importId()).orElseThrow();
        var row = analysis.sessionRow();
        assertThat(metadata.filename()).isEqualTo("shared.jsonl");
        assertThat(metadata.originalSessionId()).isEqualTo("shared-session");
        assertThat(row.sessionKey()).isEqualTo("import:" + metadata.importId());
        assertThat(row.freshInputTokens()).isEqualTo(codex ? 60 : 12);
        assertThat(row.cacheReadTokens()).isEqualTo(4 + (codex ? 36 : 0));
        assertThat(row.cacheWriteTokens()).isEqualTo(3);
        assertThat(row.outputTokens()).isEqualTo(codex ? 20 : 5);
        assertThat(row.totalTokens()).isEqualTo(codex ? 123 : 24);
        assertThat(row.userMessageCount()).isPositive();
        assertThat(row.toolCallCount()).isEqualTo(1);
        assertThat(analysis.artifact().calls())
            .hasSize(1)
            .extracting(call -> call.usage())
            .contains(
                codex
                    ? new NormalizedCallUsage(60, 40, 3, 20, 123)
                    : new NormalizedCallUsage(12, 4, 3, 5, 24));
        assertThat(analysis.artifact().calls().getFirst().response().toolCallIds())
            .containsExactly("tool-1");
        assertThat(analysis.artifact().toolExecutions()).hasSize(1);
        assertThat(
                analysis.artifact().sourceUnitCatalog().values().stream()
                    .filter(entry -> "import_raw_event".equals(entry.unitType()))
                    .map(entry -> entry.payload())
                    .toList())
            .containsExactlyInAnyOrderElementsOf(text.lines().toList());
        assertThat(PayloadCallContentExtractor.extractToolResultContents(analysis.artifact()))
            .containsEntry("tool-1", "synthetic output");
        assertThat(ToolInputContents.all(analysis.artifact()))
            .as(
                "%s tool declarations: calls=%s, tools=%s",
                source,
                analysis.artifact().calls().stream()
                    .map(call -> call.callId() + call.response())
                    .toList(),
                analysis.artifact().toolExecutions())
            .containsKey("tool-1");
        assertThat(ToolInputContents.all(analysis.artifact()).get("tool-1").input())
            .isEqualTo("{\"command\":\"echo synthetic\"}");
        var fullPayload = PayloadLookup.fromArtifact(analysis.artifact(), PayloadVisibility.FULL);
        assertThat(fullPayload.lookup("tool:input:tool-1").orElseThrow().content())
            .isEqualTo("{\"command\":\"echo synthetic\"}");
        assertThat(fullPayload.lookup("tool:result:tool-1").orElseThrow().content())
            .isEqualTo("synthetic output");
        String json =
            new String(
                new CanonicalJsonWriter().serialize(analysis.artifact()), StandardCharsets.UTF_8);
        assertThat(json)
            .contains(
                "import question",
                "import answer",
                "synthetic output",
                "echo synthetic",
                "SINGLE_FILE_ONLY")
            .doesNotContain("feipi-import-", "upload-");
        var context =
            useCase
                .getDetailContextWithAnomalies(metadata.importId(), PayloadVisibility.FULL)
                .orElseThrow();
        assertThat(context.detail().rounds()).isNotEmpty();
        assertThat(context.detail().payloadSources()).isNotEmpty();
        assertThat(context.artifact()).isSameAs(analysis.artifact());
        assertThat(context.detail().sessionRow()).isSameAs(row);
      }
    }
  }

  @Test
  void completeToolInputAndResultUseExistingStandardMaskingAndFullVisibilityForThreeSources()
      throws Exception {
    try (var service = service()) {
      for (NormalizedAgent source : NormalizedAgent.values()) {
        String transcript =
            source == NormalizedAgent.CODEX ? codexTranscript() : messageTranscript();
        var analysis =
            service.create(
                input(
                    transcript
                        .replace("synthetic output", "token=SYNTHETIC_ONLY")
                        .replace("echo synthetic", "echo synthetic token=SYNTHETIC_ONLY")),
                "synthetic.jsonl",
                source);
        var standard = PayloadLookup.fromArtifact(analysis.artifact(), PayloadVisibility.STANDARD);
        var full = PayloadLookup.fromArtifact(analysis.artifact(), PayloadVisibility.FULL);
        assertThat(ToolInputContents.all(analysis.artifact()).get("tool-1").input())
            .isEqualTo("{\"command\":\"echo synthetic token=SYNTHETIC_ONLY\"}");
        assertThat(standard.lookup("tool:input:tool-1").orElseThrow().content())
            .contains("echo synthetic", "[REDACTED]")
            .doesNotContain("SYNTHETIC_ONLY");
        assertThat(full.lookup("tool:input:tool-1").orElseThrow().content())
            .isEqualTo("{\"command\":\"echo synthetic token=SYNTHETIC_ONLY\"}");
        assertThat(standard.lookup("tool:result:tool-1").orElseThrow().content())
            .contains("[REDACTED]")
            .doesNotContain("SYNTHETIC_ONLY");
        assertThat(full.lookup("tool:result:tool-1").orElseThrow().content())
            .isEqualTo("token=SYNTHETIC_ONLY");
      }
    }
  }

  @Test
  void selectedSourceRejectsStrongMismatchAndMixedSessionsWithoutChangingPreviousImport()
      throws Exception {
    try (var service = service()) {
      var first =
          service.create(input(messageTranscript()), "same.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThatThrownBy(
              () -> service.create(input(codexTranscript()), "same.jsonl", NormalizedAgent.QODER))
          .isInstanceOf(SessionImportException.class)
          .extracting("code")
          .isEqualTo("source_mismatch");
      String modern =
          """
          {"type":"token_usage_record","payload":{"response_id":"synthetic-source-guard","usage":{"input_tokens":3,"cached_input_tokens":1,"cache_write_input_tokens":0,"output_tokens":1}}}
          """;
      for (NormalizedAgent source : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.QODER)) {
        assertThatThrownBy(() -> service.create(input(modern), "synthetic-mismatch.jsonl", source))
            .isInstanceOf(SessionImportException.class)
            .extracting("code")
            .isEqualTo("source_mismatch");
      }
      for (NormalizedAgent source : NormalizedAgent.values()) {
        assertThatThrownBy(
                () ->
                    service.create(
                        input("{\"type\":\"synthetic_unknown_type\"}"),
                        "synthetic-unknown-type.jsonl",
                        source))
            .isInstanceOf(SessionImportException.class)
            .extracting("code")
            .isEqualTo("unsupported_format");
      }
      assertThatThrownBy(
              () ->
                  service.create(
                      input(
                          messageTranscript()
                              + "\n"
                              + "{\"type\":\"user\",\"sessionId\":\"other\",\"message\":{\"content\":\"other\"}}"),
                      "same.jsonl",
                      NormalizedAgent.CLAUDE_CODE))
          .isInstanceOf(SessionImportException.class)
          .extracting("code")
          .isEqualTo("multiple_sessions");
      assertThat(service.find(first.metadata().importId())).contains(first);
      var duplicate =
          service.create(input(messageTranscript()), "same.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(duplicate.metadata().importId()).isNotEqualTo(first.metadata().importId());
      assertThat(duplicate.sessionRow().sessionKey()).isNotEqualTo(first.sessionRow().sessionKey());
      assertThat(duplicate.artifact().sourceFiles()).isNotEqualTo(first.artifact().sourceFiles());
    }
  }

  private static IsolatedSessionImportService service() throws Exception {
    return new IsolatedSessionImportService(
        source -> SourceAdapterRegistry.forSourceId(source.getValue()));
  }

  private static ByteArrayInputStream input(String text) {
    return new ByteArrayInputStream(text.getBytes(StandardCharsets.UTF_8));
  }

  private static String roleCacheTranscript(String container) throws Exception {
    var mapper = new ObjectMapper();
    List<String> lines = new ArrayList<>();
    String original =
        messageTranscript()
            .replace("echo synthetic", "echo synthetic token=SYNTHETIC_ONLY")
            .replace("synthetic output", "synthetic output token=SYNTHETIC_ONLY");
    for (String line : original.lines().toList()) {
      var event = (ObjectNode) mapper.readTree(line);
      var message = (ObjectNode) event.remove("message");
      event.remove("type");
      event.setAll(message);
      var content = event.remove("content");
      String[] fields = container.split("\\.");
      ObjectNode owner = fields.length == 1 ? event : event.putObject(fields[0]);
      owner.set(fields[fields.length - 1], content);
      lines.add(mapper.writeValueAsString(event));
    }
    return String.join("\n", lines);
  }

  static String messageTranscript() {
    return String.join(
        "\n",
        List.of(
            "{\"type\":\"user\",\"sessionId\":\"shared-session\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"message\":{\"role\":\"user\",\"content\":\"import"
                + " question\"}}",
            "{\"type\":\"assistant\",\"sessionId\":\"shared-session\",\"uuid\":\"assistant-1\",\"timestamp\":\"2026-01-01T00:00:01Z\",\"message\":{\"id\":\"msg-1\",\"role\":\"assistant\",\"model\":\"synthetic-model\",\"content\":[{\"type\":\"text\",\"text\":\"import"
                + " answer\"},{\"type\":\"tool_use\",\"id\":\"tool-1\",\"name\":\"Bash\",\"input\":{\"command\":\"echo"
                + " synthetic\"}}],\"usage\":{\"input_tokens\":12,\"cache_read_input_tokens\":4,\"cache_creation_input_tokens\":3,\"output_tokens\":5}}}",
            "{\"type\":\"user\",\"sessionId\":\"shared-session\",\"timestamp\":\"2026-01-01T00:00:02Z\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"tool-1\",\"content\":\"synthetic"
                + " output\"}]}}"));
  }

  static String codexTranscript() {
    return String.join(
        "\n",
        List.of(
            "{\"type\":\"session_meta\",\"timestamp\":\"2026-01-01T00:00:00Z\",\"payload\":{\"id\":\"shared-session\",\"cwd\":\"/synthetic/not-readable\"}}",
            "{\"type\":\"turn_context\",\"payload\":{\"model\":\"synthetic-model\"}}",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"import"
                + " question\"}]}}",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"id\":\"provider-item-1\",\"call_id\":\"tool-1\",\"name\":\"shell\",\"arguments\":\"{\\\"command\\\":\\\"echo"
                + " synthetic\\\"}\"}}",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"tool-1\",\"output\":\"synthetic"
                + " output\"}}",
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"import"
                + " answer\"}]}}",
            "{\"type\":\"event_msg\",\"timestamp\":\"2026-01-01T00:00:03Z\",\"payload\":{\"type\":\"token_count\",\"info\":{\"total_token_usage\":{\"input_tokens\":100,\"cached_input_tokens\":40,\"cache_creation_input_tokens\":3,\"output_tokens\":20,\"total_tokens\":123}}}}"));
  }
}
