package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceNormalizationInputs;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

/** 同一合成文件通过来源解析/归一化与严格导入后，身份无关的内容事实一致。 */
class JsonlContentConsistencyTest {
  @TempDir Path directory;

  @Test
  void emptyQoderTypeUsesExplicitRoleRatherThanSilentlyLosingMessages() throws Exception {
    String jsonl =
        """
        {"type":"","role":"user","content":"synthetic question"}
        {"type":"","role":"assistant","id":"a","content":"synthetic answer"}
        """;
    var scanned = parse(NormalizedAgent.QODER, jsonl);
    assertThat(scanned.calls()).hasSize(1);
    assertThat(scanned.session()).containsEntry("userMessageCount", 1L);
    try (var imports = service()) {
      var imported = imports.create(input(jsonl), "synthetic.jsonl", NormalizedAgent.QODER);
      assertThat(imported.sessionRow().userMessageCount()).isEqualTo(1);
      assertThat(imported.artifact().calls()).hasSize(1);
    }
  }

  @ParameterizedTest
  @EnumSource(
      value = NormalizedAgent.class,
      names = {"CLAUDE_CODE", "QODER"})
  void ignoredMetadataCannotInjectToolDeclarationsIntoScannedFacts(NormalizedAgent source)
      throws Exception {
    String jsonl =
        """
        {"type":"workspace-directories","usage":{"input_tokens":999},"parts":[{"type":"tool_use","id":"not-a-tool","name":"Ignored"}]}
        """
            + ImportedSessionAnalysisIntegrationTest.messageTranscript();
    var scanned = parse(source, jsonl);
    try (var imports = service()) {
      var imported = imports.create(input(jsonl), "synthetic.jsonl", source);
      assertThat(scanned.toolExecutions()).hasSize(1);
      assertThat(scanned.toolExecutions().stream().map(tool -> tool.name()).toList())
          .containsExactlyElementsOf(
              imported.artifact().toolExecutions().stream().map(tool -> tool.name()).toList());
      assertThat(scanned.calls().stream().map(call -> call.usage()).toList())
          .containsExactlyElementsOf(
              imported.artifact().calls().stream().map(call -> call.usage()).toList());
    }
  }

  @ParameterizedTest
  @EnumSource(NormalizedAgent.class)
  void inputWithoutModelCallHasReadableObservedRequest(NormalizedAgent source) throws Exception {
    String jsonl =
        source == NormalizedAgent.CODEX
            ? """
              {"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"synthetic pending input"}]}}
              """
            : """
              {"type":"user","message":{"role":"user","content":"synthetic pending input"}}
              """;
    var scanned = parse(source, jsonl);
    assertObservedRequest(scanned);
    try (var imports = service()) {
      var imported = imports.create(input(jsonl), "pending.jsonl", source);
      assertThat(imported.sessionRow().userMessageCount()).isEqualTo(1);
      assertObservedRequest(imported.artifact());
    }
  }

  @Test
  void splitInputKeepsBlockIdentityAndExcludesToolResultsFromObservedText() throws Exception {
    String jsonl =
        """
        {"type":"user","message":{"role":"user","content":[{"type":"text","text":"synthetic first token=SYNTHETIC_ONLY"},{"type":"tool_result","tool_use_id":"missing-declaration","content":"synthetic result is not user input"},{"type":"text","text":"synthetic second"}]}}
        """;
    try (var imports = service()) {
      var imported = imports.create(input(jsonl), "split.jsonl", NormalizedAgent.CLAUDE_CODE);
      assertThat(imported.sessionRow().userMessageCount()).isEqualTo(1);
      for (var artifact :
          java.util.List.of(parse(NormalizedAgent.CLAUDE_CODE, jsonl), imported.artifact())) {
        var reader =
            new SessionContentReader(
                com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
                    artifact),
                1);
        var full = reader.payload("round:req:1", PayloadVisibility.FULL).orElseThrow();
        assertThat(full.content())
            .contains("synthetic first", "synthetic second")
            .doesNotContain("result is not user input");
        assertThat(
                reader.payload("round:req:1", PayloadVisibility.STANDARD).orElseThrow().content())
            .doesNotContain("SYNTHETIC_ONLY");
        assertThat(reader.observedInputPreview()).doesNotContain("SYNTHETIC_ONLY");
      }
    }
  }

  @Test
  void highRecordCountRetainsTheLastInputInManagedScanAndStandaloneImport() throws Exception {
    var lines = new StringBuilder();
    int count = 12_065;
    for (int i = 0; i < count; i++) {
      lines
          .append(
              "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"synthetic input ")
          .append(i)
          .append("\"}]}}\n");
    }
    var scanned = parse(NormalizedAgent.CODEX, lines.toString());
    try (var imports = service()) {
      var imported =
          imports.create(input(lines.toString()), "many-records.jsonl", NormalizedAgent.CODEX);
      assertThat(imported.sessionRow().userMessageCount()).isEqualTo(count);
      for (var artifact : java.util.List.of(scanned, imported.artifact())) {
        assertThat(artifact.calls()).isEmpty();
        var reader =
            new SessionContentReader(
                com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
                    artifact),
                count);
        assertThat(reader.payload("round:req:1", PayloadVisibility.FULL).orElseThrow().content())
            .startsWith("synthetic input 0\n")
            .endsWith("synthetic input 12064");
      }
    }
  }

  private static void assertObservedRequest(NormalizedSessionArtifact artifact) throws Exception {
    assertThat(artifact.calls()).isEmpty();
    assertThat(artifact.toolExecutions()).isEmpty();
    var reader =
        new SessionContentReader(
            com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
                artifact),
            1);
    assertThat(reader.payload("round:req:1", PayloadVisibility.STANDARD))
        .hasValueSatisfying(
            value -> assertThat(value.content()).contains("synthetic pending input"));
  }

  private NormalizedSessionArtifact parse(NormalizedAgent source, String jsonl) throws Exception {
    var adapter = adapter(source);
    Path file = directory.resolve(source.getValue() + ".jsonl");
    Files.writeString(file, jsonl);
    var candidate =
        new Candidate(adapter.fingerprint(file), "synthetic", "", adapter.singleFileMetadata(file));
    try (var result = (SourceResult.Success) adapter.parse(candidate, null)) {
      if (source == NormalizedAgent.CODEX) {
        return new NormalizationEngine()
            .normalizeContent(
                source,
                result.recordSequence(),
                result.diagnostics(),
                SourceNormalizationInputs.transcriptFiles(candidate))
            .toArtifact();
      }
      return new NormalizationEngine()
          .normalizeContent(
              source,
              result.records(),
              result.diagnostics(),
              SourceNormalizationInputs.transcriptFiles(candidate))
          .toArtifact();
    }
  }

  private static IsolatedSessionImportService service() throws Exception {
    return new IsolatedSessionImportService(JsonlContentConsistencyTest::adapter);
  }

  private static SourceAdapter adapter(NormalizedAgent source) {
    return switch (source) {
      case CLAUDE_CODE -> new ClaudeSourceAdapter();
      case CODEX -> new CodexSourceAdapter();
      case QODER -> new QoderSourceAdapter();
    };
  }

  private static ByteArrayInputStream input(String jsonl) {
    return new ByteArrayInputStream(jsonl.getBytes(StandardCharsets.UTF_8));
  }
}
