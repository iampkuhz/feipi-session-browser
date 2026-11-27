package com.feipi.session.browser.scan.engine.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.index.api.imports.ImportLimits;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.common.JsonlReaderConfig;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 通过真实单文件入口核对事件坐标；核对完整读取与导入归属的条件边界。 */
class ImportOccurrenceReaderCheckpointTest {
  private static final ObjectMapper JSON = new ObjectMapper();
  private static final String LOGICAL = "imports/synthetic/upload.jsonl";
  @TempDir Path directory;

  @Test
  void topLevelFunctionAndCustomToolsKeepCompleteInputsAndOriginalCatalogKeys() throws Exception {
    Object argument = Map.of("cmd", "合成".repeat(2000), "nested", List.of(1, 2));
    String raw = tool("function_call", argument) + tool("custom_tool_call", argument) + usage();
    Path file = validated(raw, new CodexSourceAdapter());
    try (var parsed = parse(file, new CodexSourceAdapter())) {
      assertThat(objectCount(file)).isEqualTo(3);
      assertThat(parsed.candidateCount()).isEqualTo(3);
      var catalog = ImportPayloadCatalog.read(file, LOGICAL);
      for (int i = 0; i < 2; i++) {
        var record = parsed.records().get(i);
        assertThat(record.eventIndex()).isEqualTo(i);
        assertThat(record.locator()).isEqualTo(file + "#event[" + i + "]");
        assertThat(record.toolCalls())
            .singleElement()
            .satisfies(t -> assertThat(t.input()).isEqualTo(JSON.valueToTree(argument).toString()));
        assertThat(catalog)
            .containsKey(LOGICAL + "#raw[" + i + "]/tool")
            .doesNotContainKey(LOGICAL + "#raw[" + i + "]/tool/0");
      }
      var normal =
          new NormalizationEngine()
              .normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), List.of())
              .toArtifact();
      assertThat(normal.toolExecutions()).hasSize(2);
      var bound =
          new NormalizationEngine()
              .normalizeWithBindings(NormalizedAgent.CODEX, parsed.records(), List.of(), List.of());
      assertThat(bound.artifact()).isEqualTo(normal);
      assertThat(bound.bindings()).hasSize(2);
      assertThat(bound.bindings()).extracting(b -> b.recordOrdinal()).containsExactly(0, 1);
      assertThat(bound.bindings()).extracting(b -> b.eventIndex()).containsExactly(0, 1);
    }
    try (var service = new IsolatedSessionImportService(a -> new CodexSourceAdapter())) {
      var imported =
          service
              .create(
                  new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                  "synthetic.jsonl",
                  NormalizedAgent.CODEX)
              .artifact();
      assertThat(imported.toolExecutions()).hasSize(2);
      assertThat(imported.calls())
          .allSatisfy(c -> assertThat(c.sourceUnitRefRanges()).isNotEmpty());
    }
  }

  @Test
  void blankBomAndFallbackKeepEventIndexButNotRecordOrdinal() throws Exception {
    for (String prefix : List.of("", "\uFEFF\n \n")) {
      Path file =
          validated(
              prefix
                  + event("event_msg", Map.of("type", "user_message", "message", "合成"))
                  + "\n"
                  + tool("function_call", "full-input"),
              new CodexSourceAdapter());
      try (var parsed = parse(file, new CodexSourceAdapter())) {
        assertThat(objectCount(file)).isEqualTo(2);
        assertThat(parsed.candidateCount()).isEqualTo(2);
        assertThat(parsed.records()).hasSize(3);
        assertThat(parsed.records()).extracting(r -> r.eventIndex()).containsExactly(0, 0, 1);
        assertThat(parsed.records().get(1).toolCalls()).isEmpty();
        assertThat(parsed.records().get(2).toolCalls()).hasSize(1);
        assertThat(ImportPayloadCatalog.read(file, LOGICAL)).containsKey(LOGICAL + "#raw[1]/tool");
        assertImportedCoordinate(Files.readString(file) + usage(), 1);
      }
    }
  }

  @Test
  void codexRejectsIgnoredMetadataRatherThanProducingFilteredAnalysisFile() throws Exception {
    Path file = directory.resolve("metadata.jsonl");
    Files.writeString(file, event("runtime-config", Map.of()) + tool("function_call", "{}"));
    assertThatThrownBy(
            () ->
                ImportInputValidator.validate(
                    file, new CodexSourceAdapter(), ImportLimits.defaults()))
        .hasMessageContaining("unsupported_format");
  }

  @Test
  void historyPrefixRetainsOriginalEventCoordinatesWithBlankAndFallbackCombination()
      throws Exception {
    for (boolean combined : List.of(false, true)) {
      String header =
          JSON.writeValueAsString(
                  Map.of(
                      "type",
                      "session_meta",
                      "ordinal",
                      0,
                      "payload",
                      Map.of(
                          "id",
                          "child",
                          "history_mode",
                          "paginated",
                          "subagent_history_start_ordinal",
                          1)))
              + "\n";
      String message =
          JSON.writeValueAsString(
                  Map.of(
                      "type",
                      "event_msg",
                      "ordinal",
                      1,
                      "payload",
                      Map.of("type", "user_message", "message", "合成")))
              + "\n";
      var call = JSON.readTree(tool("function_call", "{}"));
      ((com.fasterxml.jackson.databind.node.ObjectNode) call).put("ordinal", 2);
      Path file =
          validated(
              (combined ? "\uFEFF\n\n" : "") + header + message + call + "\n",
              new CodexSourceAdapter());
      try (var parsed = parse(file, new CodexSourceAdapter())) {
        assertThat(objectCount(file)).isEqualTo(3);
        assertThat(parsed.candidateCount()).isEqualTo(3);
        assertThat(parsed.records()).extracting(r -> r.eventIndex()).containsExactly(1, 1, 2);
        assertThat(parsed.records().getLast().toolCalls()).hasSize(1);
        assertThat(ImportPayloadCatalog.read(file, LOGICAL)).containsKey(LOGICAL + "#raw[2]/tool");
        var closing = JSON.readTree(usage());
        ((com.fasterxml.jackson.databind.node.ObjectNode) closing).put("ordinal", 3);
        assertImportedCoordinate(Files.readString(file) + closing + "\n", 2);
      }
    }
  }

  @Test
  void recordLimitIsDetectedByCandidateCountNotProjectedRecordCount() throws Exception {
    Path file =
        validated(
            tool("function_call", "a") + tool("function_call", "b"), new CodexSourceAdapter());
    assertThat(objectCount(file)).isEqualTo(2);
    for (int limit : List.of(1, 2)) {
      try (var parsed = parse(file, limited(limit, 1000))) {
        assertThat(parsed.candidateCount()).isEqualTo(limit);
        assertThat(parsed.records()).hasSize(limit);
      }
    }
  }

  @Test
  void overlongObjectBeforeToolCannotReceiveAFalseOriginalCoordinate() throws Exception {
    String first = tool("function_call", "x".repeat(1500));
    Path file = validated(first + tool("function_call", "tail"), new CodexSourceAdapter());
    try (var complete = parse(file, limited(10, first.strip().length()));
        var bounded = parse(file, limited(10, 300))) {
      assertThat(objectCount(file)).isEqualTo(2);
      assertThat(complete.candidateCount()).isEqualTo(2);
      assertThat(complete.records().getFirst().toolCalls().getFirst().input()).hasSize(1500);
      assertThat(bounded.candidateCount()).isEqualTo(1);
      assertThat(bounded.records())
          .singleElement()
          .satisfies(
              r -> {
                assertThat(r.eventIndex()).isZero();
                assertThat(r.toolCalls())
                    .singleElement()
                    .satisfies(t -> assertThat(t.input()).isEqualTo("tail"));
              });
      assertThat(ImportPayloadCatalog.read(file, LOGICAL)).containsKey(LOGICAL + "#raw[1]/tool");
    }
  }

  @Test
  void sameCountChangedContentRequiresFingerprintAndMissingFileIsNotSuccess() throws Exception {
    var adapter = new CodexSourceAdapter();
    Path file = validated(tool("function_call", "alpha"), adapter);
    var modified = Files.getLastModifiedTime(file);
    long size = Files.size(file);
    byte[] before = MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file));
    try (var parsed = parse(file, adapter)) {
      Files.writeString(file, tool("function_call", "bravo"));
      Files.setLastModifiedTime(file, modified);
      assertThat(Files.size(file)).isEqualTo(size);
      assertThat(Files.getLastModifiedTime(file)).isEqualTo(modified);
      try (var changed = parse(file, adapter)) {
        assertThat(changed.candidateCount()).isEqualTo(parsed.candidateCount());
        assertThat(changed.records().getFirst().toolCalls().getFirst().input()).isEqualTo("bravo");
        assertThat(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)))
            .isNotEqualTo(before);
      }
      var candidate = new Candidate(adapter.fingerprint(file), "codex:synthetic", "", Map.of());
      Files.delete(file);
      assertThat(adapter.parse(candidate, null)).isNotInstanceOf(SourceResult.Success.class);
      assertThatThrownBy(() -> ImportPayloadCatalog.read(file, LOGICAL))
          .isInstanceOf(java.io.IOException.class);
    }
  }

  @Test
  void unreadableObjectPathProducesFatalRatherThanPartialSuccess() throws Exception {
    var adapter = new CodexSourceAdapter();
    Path file = validated(tool("function_call", "{}"), adapter);
    var candidate = new Candidate(adapter.fingerprint(file), "codex:synthetic", "", Map.of());
    Files.delete(file);
    Files.createDirectory(file);
    assertThat(adapter.parse(candidate, null)).isInstanceOf(SourceResult.Fatal.class);
    assertThatThrownBy(() -> ImportPayloadCatalog.read(file, LOGICAL))
        .isInstanceOf(java.io.IOException.class);
  }

  @Test
  void equalNestedBlocksRemainIndependentAndCannotBeZippedWithToolSlots() throws Exception {
    var block = Map.of("type", "tool_use", "id", "nested", "name", "exec_command", "input", "{}");
    var different =
        Map.of("type", "tool_use", "id", "other", "name", "exec_command", "input", "other");
    var payload =
        Map.of(
            "type",
            "function_call",
            "call_id",
            "top",
            "name",
            "exec_command",
            "arguments",
            "{}",
            "content",
            List.of(block, block, different));
    Path file = validated(event("response_item", payload), new CodexSourceAdapter());
    var catalog = ImportPayloadCatalog.read(file, LOGICAL);
    assertThat(catalog.keySet())
        .containsExactly(
            LOGICAL + "#raw[0]",
            LOGICAL + "#raw[0]/tool/payload/content/0",
            LOGICAL + "#raw[0]/tool/payload/content/1",
            LOGICAL + "#raw[0]/tool/payload/content/2",
            LOGICAL + "#raw[0]/tool");
    try (var parsed = parse(file, new CodexSourceAdapter())) {
      assertThat(parsed.records())
          .singleElement()
          .satisfies(
              r ->
                  assertThat(r.toolCalls())
                      .singleElement()
                      .satisfies(t -> assertThat(t.toolCallId()).isEqualTo("top")));
    }
  }

  @Test
  void unsupportedNestedOnlyDeclarationDoesNotInventAdapterTools() throws Exception {
    var block = Map.of("type", "tool_use", "id", "nested", "name", "exec_command", "input", "{}");
    Path file =
        validated(
            event(
                "response_item",
                Map.of("type", "message", "role", "assistant", "content", List.of(block, block))),
            new CodexSourceAdapter());
    try (var parsed = parse(file, new CodexSourceAdapter())) {
      assertThat(parsed.candidateCount()).isEqualTo(1);
      assertThat(parsed.records()).allSatisfy(r -> assertThat(r.toolCalls()).isEmpty());
      assertThat(ImportPayloadCatalog.read(file, LOGICAL).keySet())
          .containsExactly(
              LOGICAL + "#raw[0]",
              LOGICAL + "#raw[0]/tool/payload/content/0",
              LOGICAL + "#raw[0]/tool/payload/content/1");
    }
  }

  @Test
  void serviceNeverPublishesPrefixBindingsForIncompleteSourceReads() throws Exception {
    for (var adapter : List.of(limited(1, 4000), limited(10, 300))) {
      try (var service = new IsolatedSessionImportService(agent -> adapter)) {
        String raw = tool("function_call", "x".repeat(1500)) + usage();
        assertThatThrownBy(
                () ->
                    service.create(
                        new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                        "bounded.jsonl",
                        NormalizedAgent.CODEX))
            .isInstanceOf(com.feipi.session.browser.index.api.imports.SessionImportException.class)
            .hasMessageContaining("parse_failed");
      }
    }
  }

  @Test
  void serviceRejectsChangedContentIoFailureAndUnexpectedNeighbors() throws Exception {
    for (String mode : List.of("changed", "directory", "neighbor")) {
      var delegate = new CodexSourceAdapter();
      var first = new java.util.concurrent.atomic.AtomicBoolean(true);
      var adapter =
          (com.feipi.session.browser.source.spi.SourceAdapter)
              java.lang.reflect.Proxy.newProxyInstance(
                  getClass().getClassLoader(),
                  new Class<?>[] {com.feipi.session.browser.source.spi.SourceAdapter.class},
                  (proxy, method, args) -> {
                    if (method.getName().equals("singleFileMetadata") && first.getAndSet(false)) {
                      Path file = (Path) args[0];
                      if (mode.equals("changed")) {
                        var mtime = Files.getLastModifiedTime(file);
                        Files.writeString(file, Files.readString(file).replace("alpha", "bravo"));
                        Files.setLastModifiedTime(file, mtime);
                      } else if (mode.equals("directory")) {
                        Files.delete(file);
                        Files.createDirectory(file);
                      } else {
                        Files.writeString(file.resolveSibling("rollout-neighbor.jsonl"), "");
                      }
                    }
                    return method.invoke(delegate, args);
                  });
      try (var service = new IsolatedSessionImportService(agent -> adapter)) {
        String raw = tool("function_call", "alpha") + usage();
        assertThatThrownBy(
                () ->
                    service.create(
                        new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                        "changed.jsonl",
                        NormalizedAgent.CODEX))
            .isInstanceOf(com.feipi.session.browser.index.api.imports.SessionImportException.class)
            .hasMessageContaining("parse_failed");
        var valid =
            service.create(
                new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                "valid.jsonl",
                NormalizedAgent.CODEX);
        assertThat(valid.artifact().calls().getFirst().sourceUnitRefRanges()).hasSize(1);
      }
    }
  }

  @Test
  void historicalSameIdDeclarationRemainsUnownedAndUndeleted() throws Exception {
    var header = JSON.createObjectNode().put("type", "session_meta").put("ordinal", 0);
    header
        .putObject("payload")
        .put("id", "history")
        .put("history_mode", "paginated")
        .put("subagent_history_start_ordinal", 2);
    var historical =
        (com.fasterxml.jackson.databind.node.ObjectNode)
            JSON.readTree(tool("function_call", "old"));
    historical.put("ordinal", 1);
    var active =
        (com.fasterxml.jackson.databind.node.ObjectNode)
            JSON.readTree(tool("function_call", "new"));
    active.put("ordinal", 2);
    var closing = (com.fasterxml.jackson.databind.node.ObjectNode) JSON.readTree(usage());
    closing.put("ordinal", 3);
    String raw = header + "\n" + historical + "\n" + active + "\n" + closing + "\n";
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      var artifact =
          service
              .create(
                  new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                  "history.jsonl",
                  NormalizedAgent.CODEX)
              .artifact();
      String path = artifact.sourceFiles().getFirst().path().toString();
      assertThat(artifact.calls()).hasSize(1);
      assertThat(artifact.calls().getFirst().sourceUnitRefRanges().getFirst().refs())
          .containsExactly(path + "#raw[2]/tool");
      var old = (Map<?, ?>) artifact.sourceUnitCatalog().get(path + "#raw[1]/tool").payload();
      assertThat(old.get("input")).isEqualTo("old");
      assertThat(old.containsKey("text")).isFalse();
      assertThat(artifact.sourceUnitCatalog()).containsKeys(path + "#raw[1]", path + "#raw[2]");
      assertThat(artifact.sourceUnitCatalog().values())
          .filteredOn(e -> e.unitType().equals("tool_use"))
          .hasSize(2);
    }
  }

  private static void assertImportedCoordinate(String raw, int eventIndex) throws Exception {
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      var artifact =
          service
              .create(
                  new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                  "coordinate.jsonl",
                  NormalizedAgent.CODEX)
              .artifact();
      String path = artifact.sourceFiles().getFirst().path().toString();
      var refs =
          artifact.calls().stream()
              .flatMap(call -> call.sourceUnitRefRanges().stream())
              .flatMap(range -> range.refs().stream())
              .toList();
      assertThat(refs).containsExactly(path + "#raw[" + eventIndex + "]/tool");
      assertThat(artifact.sourceUnitCatalog().get(refs.getFirst()).payload())
          .isIn(artifact.calls().stream().flatMap(call -> call.sourceUnits().stream()).toList());
    }
  }

  private Path validated(String raw, CodexSourceAdapter adapter) throws Exception {
    Path file = Files.createTempFile(directory, "source-", ".jsonl");
    Files.writeString(file, raw);
    try (var lines = Files.lines(file)) {
      assertThat(lines.filter(l -> !l.replace("\uFEFF", "").isBlank()).count()).isPositive();
    }
    Path analysis =
        ImportInputValidator.validate(file, adapter, ImportLimits.defaults()).analysisFile();
    assertThat(analysis).isEqualTo(file);
    return analysis;
  }

  private static long objectCount(Path file) throws Exception {
    try (var lines = Files.lines(file)) {
      var objects = lines.map(l -> l.replace("\uFEFF", "")).filter(l -> !l.isBlank()).toList();
      for (String object : objects) {
        assertThat(JSON.readTree(object).isObject()).isTrue();
      }
      return objects.size();
    }
  }

  private static SourceResult.Success parse(Path file, CodexSourceAdapter adapter)
      throws Exception {
    return (SourceResult.Success)
        adapter.parse(
            new Candidate(adapter.fingerprint(file), "codex:synthetic", "", Map.of()), null);
  }

  private static CodexSourceAdapter limited(int records, int chars) {
    return new CodexSourceAdapter(new JsonlReader(JsonlReaderConfig.of(records, chars, 20)));
  }

  private static String tool(String type, Object input) throws Exception {
    return event(
        "response_item",
        Map.of(
            "type",
            type,
            "call_id",
            type,
            "name",
            "exec_command",
            "function_call".equals(type) ? "arguments" : "input",
            input));
  }

  private static String usage() throws Exception {
    return event(
        "token_usage_record",
        Map.of("response_id", "response", "usage", Map.of("input_tokens", 1, "output_tokens", 1)));
  }

  private static String event(String type, Map<String, Object> payload) throws Exception {
    return JSON.writeValueAsString(Map.of("type", type, "payload", payload)) + "\n";
  }
}
