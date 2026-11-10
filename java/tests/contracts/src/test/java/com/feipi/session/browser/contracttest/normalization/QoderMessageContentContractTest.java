package com.feipi.session.browser.contracttest.normalization;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.api.imports.SessionImportException;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 合成 message/role/parts 内容须经真实 Qoder parser 保留到调用与轮次。 */
class QoderMessageContentContractTest {
  @TempDir Path directory;

  @Test
  void messagePartsReachCallsAndRoundsWithoutInventedUsage() throws IOException {
    Path project = directory.resolve("projects/synthetic");
    Files.createDirectories(project);
    Path file = project.resolve("message-parts.jsonl");
    Files.writeString(
        file,
        """
        {"type":"message","role":"user","parts":[{"type":"text","text":"Synthetic Qoder parts user"}],"timestamp":"2026-11-05T08:00:01Z"}
        {"type":"message","role":"assistant","parts":[{"type":"text","text":"Synthetic Qoder parts answer"}],"timestamp":"2026-11-05T08:00:02Z"}
        {"type":"message","message":{"role":"user","parts":[{"type":"text","text":"Synthetic envelope user"}]},"timestamp":"2026-11-05T08:00:03Z"}
        {"type":"message","message":{"role":"assistant","parts":[{"type":"text","text":"Synthetic envelope answer"}]} ,"timestamp":"2026-11-05T08:00:04Z"}
        """);
    var adapter = new QoderSourceAdapter();
    var candidate = adapter.discover(directory).orderedItems().getFirst();
    var parsed = (SourceResult.Success) adapter.parse(candidate, null);
    var artifact =
        new NormalizationEngine()
            .normalize(NormalizedAgent.QODER, parsed.records(), parsed.diagnostics(), List.of());

    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.session())
        .containsEntry("userMessageCount", 2L)
        .containsEntry("assistantMessageCount", 2L)
        .containsEntry("totalTokens", 0L);
    assertThat(artifact.calls().get(0).sourceUnits())
        .extracting(unit -> unit.get("text"))
        .contains("Synthetic Qoder parts user", "Synthetic Qoder parts answer");
    assertThat(artifact.calls().get(1).sourceUnits())
        .extracting(unit -> unit.get("text"))
        .contains("Synthetic envelope user", "Synthetic envelope answer");
    assertThat(SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()))
        .hasSize(2);

    try (var imports = new IsolatedSessionImportService(source -> new QoderSourceAdapter());
        var input = Files.newInputStream(file)) {
      var imported = imports.create(input, file.getFileName().toString(), NormalizedAgent.QODER);
      assertThat(imported.sessionRow().userMessageCount()).isEqualTo(2);
      assertThat(imported.sessionRow().assistantMessageCount()).isEqualTo(2);
      assertThat(imported.sessionRow().totalTokens()).isZero();
      assertThat(imported.artifact().calls())
          .extracting(call -> call.sourceUnits().stream().map(unit -> unit.get("text")).toList())
          .containsExactly(
              List.of("Synthetic Qoder parts user", "Synthetic Qoder parts answer"),
              List.of("Synthetic envelope user", "Synthetic envelope answer"));
    }
  }

  @Test
  void standaloneImportKeepsGoldenFixtureToolResultAndReportedUsage() throws IOException {
    try (var imports = new IsolatedSessionImportService(source -> new QoderSourceAdapter());
        var input =
            getClass().getResourceAsStream("/golden-fixtures/qoder/minimal-session.jsonl")) {
      assertThat(input).isNotNull();
      var imported = imports.create(input, "minimal-session.jsonl", NormalizedAgent.QODER);
      assertThat(imported.sessionRow().userMessageCount()).isEqualTo(1);
      assertThat(imported.sessionRow().toolCallCount()).isEqualTo(1);
      assertThat(imported.sessionRow().totalTokens()).isEqualTo(315);
      assertThat(imported.artifact().toolExecutions()).hasSize(1);
      String toolId = imported.artifact().toolExecutions().getFirst().toolCallId();
      assertThat(imported.artifact().sourceUnitCatalog().values())
          .filteredOn(unit -> "tool_result".equals(unit.unitType()))
          .singleElement()
          .satisfies(
              result -> {
                assertThat(result.label()).contains(toolId);
                assertThat(result.text()).contains("All 42 tests passed.");
              });
    }
  }

  @Test
  void standaloneImportStillRejectsInvalidMessagesUnknownTypesAndToolOnlyFiles()
      throws IOException {
    String message = "{\"type\":\"message\",\"role\":\"user\",\"content\":\"Synthetic question\"}";
    try (var imports = new IsolatedSessionImportService(source -> new QoderSourceAdapter())) {
      for (String unsupported :
          List.of(
              "{\"type\":\"tool_result\",\"tool_use_id\":\"synthetic-tool\",\"content\":\"result\"}",
              "{\"type\":\"message\",\"role\":\"system\"}",
              "{\"type\":\"message\"}",
              message + "\n{\"type\":\"synthetic-unknown\"}")) {
        assertThatThrownBy(
                () -> imports.create(utf8(unsupported), "invalid.jsonl", NormalizedAgent.QODER))
            .isInstanceOfSatisfying(
                SessionImportException.class,
                error -> assertThat(error.code()).isEqualTo("unsupported_format"));
      }
      for (var source : List.of(NormalizedAgent.CLAUDE_CODE, NormalizedAgent.CODEX)) {
        assertThatThrownBy(() -> imports.create(utf8(message), "invalid.jsonl", source))
            .isInstanceOfSatisfying(
                SessionImportException.class,
                error -> assertThat(error.code()).isEqualTo("unsupported_format"));
      }
    }
  }

  private static ByteArrayInputStream utf8(String value) {
    return new ByteArrayInputStream(value.getBytes(StandardCharsets.UTF_8));
  }
}
