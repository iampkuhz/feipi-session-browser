package com.feipi.session.browser.scan.artifact;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 合成原始来源的完整参数与唯一声明归属保真检查，不实现热点投影。 */
class SameInputSourceIdentityTest {
  private static final ObjectMapper JSON = new ObjectMapper();
  @TempDir Path directory;

  @Test
  void repeatedNativeStringsSurviveNormalManagedCanonicalAndSqlite() throws Exception {
    Path root = directory.resolve("rollout-root.jsonl");
    Path child = directory.resolve("rollout-child08.jsonl");
    Files.writeString(root, meta("root", "") + spawn("spawn08", "child08") + usage("root"));
    Files.writeString(child, meta("child08", "root") + executions());
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(root), "codex:synthetic", "", Map.of()), null)) {
      var files =
          List.of(
              new NormalizedSourceFile(
                  SourceFileRole.TRANSCRIPT, root, Optional.empty(), Optional.empty()));
      var engine = new NormalizationEngine();
      var normal =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), files);
      var managed =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), files);
      assertThat(managed.toArtifact()).isEqualTo(normal.toArtifact());
      assertInputs(normal.toArtifact());
      assertThat(normal.toArtifact().calls())
          .filteredOn(c -> c.subagentId().filter("child08"::equals).isPresent())
          .hasSize(200)
          .allSatisfy(c -> assertThat(c.parentToolCallId()).contains("spawn08"));
      assertThat(normal.toArtifact().sourceUnitCatalog().values())
          .filteredOn(u -> u.unitType().equals("tool_result"))
          .singleElement()
          .satisfies(
              u -> {
                assertThat(u.text()).contains("{\"agent_id\":\"child08\"}");
                assertThat(((Map<?, ?>) u.payload()).get("tool_call_id")).isEqualTo("spawn08");
              });
      assertInputs(managed.toArtifact());
      var header = managed.header();
      var metadata = new LinkedHashMap<String, Object>(header.session());
      metadata.put("session_key", "codex:synthetic");
      metadata.put("session_id", "synthetic");
      var content =
          managed.withHeader(
              new NormalizedContentHeader(
                  header.schemaVersion(),
                  header.agent(),
                  new NormalizedSessionMetadata(metadata),
                  header.totals()));
      for (boolean units : List.of(false, true)) {
        Path output = Files.createDirectories(directory.resolve("output-" + units));
        var writer = new NormalizedArtifactWriter();
        var written =
            units
                ? writer.writeContent(output, content, Map.of())
                : writer.write(output, content.toArtifact(), Map.of());
        assertInputs(NormalizedArtifactLoader.open(written.dataPath()).toArtifact());
        String url = "jdbc:sqlite:" + output.resolve("index.db");
        try (var connection = DriverManager.getConnection(url)) {
          var index = new SqliteIndexWriter(connection);
          index.ensureSchema();
          long scan = index.startScan(1, "full");
          index.writeNormalizedContent(
              content, written.dataPath(), root.toString(), 1, Files.size(root), Instant.EPOCH);
          index.completeScan(scan, 2, Map.of("codex", 1));
        }
        try (var connection = DriverManager.getConnection(url);
            var statement = connection.createStatement();
            var rows = statement.executeQuery("SELECT path FROM session_artifacts")) {
          assertThat(rows.next()).isTrue();
          assertInputs(NormalizedArtifactLoader.open(Path.of(rows.getString(1))).toArtifact());
          assertThat(rows.next()).isFalse();
        }
      }
    }
  }

  @Test
  void isolatedSingleFileImportsPreserveNativeStrings() throws Exception {
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      String raw = meta("child08", "root") + executions();
      var imported =
          service.create(
              new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
              "synthetic.jsonl",
              NormalizedAgent.CODEX);
      assertInputs(imported.artifact());
    }
  }

  @Test
  void structuredArgumentsLoseTheirRepresentationAndMatchNativeStrings() throws Exception {
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      var inputs = new ArrayList<Object>();
      for (Object argument : List.of(Map.of("cmd", "alpha"), "{\"cmd\":\"alpha\"}")) {
        String raw =
            meta("synthetic", "")
                + event(
                    "response_item",
                    Map.of(
                        "type",
                        "function_call",
                        "call_id",
                        "same",
                        "name",
                        "exec_command",
                        "arguments",
                        argument))
                + usage("response");
        var imported =
            service.create(
                new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                "synthetic-shape.jsonl",
                NormalizedAgent.CODEX);
        var declarations =
            imported.artifact().calls().stream()
                .flatMap(c -> c.sourceUnits().stream())
                .filter(u -> "same".equals(u.get("id")))
                .toList();
        assertThat(declarations).hasSize(1);
        Object input = declarations.getFirst().get("input");
        assertThat(input).isInstanceOf(String.class).isEqualTo("{\"cmd\":\"alpha\"}");
        inputs.add(input);
      }
      assertThat(inputs.getFirst()).isEqualTo(inputs.getLast());
    }
  }

  @Test
  void siblingReusedRawIdsRemainBoundToTheirOwnCalls() throws Exception {
    Path root = directory.resolve("rollout-root.jsonl");
    Files.writeString(
        root,
        meta("root", "")
            + spawn("spawn08", "child08")
            + spawn("spawn09", "child09")
            + usage("root"));
    for (String child : List.of("child08", "child09")) {
      Files.writeString(
          directory.resolve("rollout-" + child + ".jsonl"),
          meta(child, "root")
              + event(
                  "response_item",
                  Map.of(
                      "type",
                      "function_call",
                      "call_id",
                      "reused",
                      "name",
                      "exec_command",
                      "arguments",
                      child))
              + usage(child));
    }
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(root), "codex:synthetic", "", Map.of()), null)) {
      var artifact =
          new NormalizationEngine()
              .normalizeContent(
                  NormalizedAgent.CODEX,
                  parsed.records(),
                  List.of(),
                  List.of(
                      new NormalizedSourceFile(
                          SourceFileRole.TRANSCRIPT, root, Optional.empty(), Optional.empty())))
              .toArtifact();
      var tools =
          artifact.toolExecutions().stream().filter(t -> t.name().equals("exec_command")).toList();
      assertThat(tools).hasSize(2);
      assertThat(tools)
          .extracting(t -> t.toolCallId())
          .doesNotHaveDuplicates()
          .allSatisfy(id -> assertThat(id).startsWith("normalized-tool:"));
      for (var tool : tools) {
        var owners =
            artifact.calls().stream()
                .filter(c -> c.callId().equals(tool.declaredByCallId()))
                .toList();
        assertThat(owners).hasSize(1);
        var owner = owners.getFirst();
        assertThat(owner.subagentId()).contains(tool.subagentId().orElseThrow());
        assertThat(owner.sourceUnits())
            .filteredOn(u -> tool.toolCallId().equals(u.get("id")))
            .singleElement()
            .satisfies(u -> assertThat(u.get("input")).isEqualTo(tool.subagentId().orElseThrow()));
      }
    }
  }

  private static void assertInputs(NormalizedSessionArtifact artifact) {
    var tools =
        artifact.toolExecutions().stream().filter(t -> t.name().equals("exec_command")).toList();
    assertThat(tools).hasSize(200);
    assertThat(tools).extracting(t -> t.toolCallId()).doesNotHaveDuplicates();
    for (int i = 0; i < tools.size(); i++) {
      var tool = tools.get(i);
      assertThat(tool.durationMs()).isEqualTo(500L);
      var owners =
          artifact.calls().stream()
              .filter(c -> c.callId().equals(tool.declaredByCallId()))
              .toList();
      assertThat(owners).hasSize(1);
      var owner = owners.getFirst();
      assertThat(tool.scope()).isEqualTo(owner.scope());
      assertThat(tool.subagentId()).isEqualTo(owner.subagentId());
      assertThat(owner.response().toolCallIds()).contains(tool.toolCallId());
      var keys = new ArrayList<String>();
      for (var range : owner.sourceUnitRefRanges()) {
        keys.addAll(range.refs());
        range
            .sequence()
            .ifPresent(
                s ->
                    keys.addAll(
                        artifact.sourceUnitSequences().get(s).subList(range.start(), range.end())));
      }
      var declarations = new ArrayList<Map<?, ?>>();
      owner.sourceUnits().stream()
          .filter(u -> tool.toolCallId().equals(u.get("id")))
          .forEach(declarations::add);
      keys.stream()
          .distinct()
          .map(artifact.sourceUnitCatalog()::get)
          .filter(u -> u.payload() instanceof Map<?, ?>)
          .map(u -> (Map<?, ?>) u.payload())
          .filter(u -> tool.toolCallId().equals(u.get("id")))
          .forEach(declarations::add);
      assertThat(declarations).hasSize(owner.sourceUnitRefRanges().isEmpty() ? 1 : 2);
      assertThat(declarations.stream().distinct().toList()).hasSize(1);
      var payload = declarations.getFirst();
      assertThat(payload.get("name")).isEqualTo(tool.name());
      Object input = payload.get("input");
      assertThat(input).isInstanceOf(String.class).isEqualTo(arguments(i));
      assertThat(owner.sourceUnits()).isNotEmpty();
    }
  }

  private static String executions() throws Exception {
    var raw = new StringBuilder();
    for (int i = 0; i < 200; i++) {
      String id = "exec-" + i;
      Object input = arguments(i);
      raw.append(
          event(
              "response_item",
              Map.of(
                  "type",
                  "function_call",
                  "call_id",
                  id,
                  "name",
                  "exec_command",
                  "arguments",
                  input)));
      raw.append(usage("response-" + i));
      raw.append(
          event(
              "event_msg",
              Map.of(
                  "type",
                  "exec_command_end",
                  "call_id",
                  id,
                  "duration",
                  Map.of("secs", 0, "nanos", 500000000),
                  "exit_code",
                  0,
                  "status",
                  "completed")));
    }
    return raw.toString();
  }

  private static String arguments(int i) {
    return "{ \"cmd\" : \"node synthetic-operation-"
        + (i < 20 ? "alpha" : "beta")
        + ".js --not-executed\\nprintf 合成é\",  \"yield_time_ms\" : 1000, \"max_output_tokens\": 2500 }";
  }

  private static String event(String type, Map<String, Object> payload) throws Exception {
    return JSON.writeValueAsString(Map.of("type", type, "payload", payload)) + "\n";
  }

  private static String meta(String id, String parent) throws Exception {
    return event(
        "session_meta",
        parent.isEmpty()
            ? Map.of("id", id)
            : Map.of(
                "id",
                id,
                "source",
                Map.of("subagent", Map.of("thread_spawn", Map.of("parent_thread_id", parent)))));
  }

  private static String spawn(String id, String child) throws Exception {
    return event(
            "response_item",
            Map.of(
                "type", "function_call", "call_id", id, "name", "spawn_agent", "arguments", "{}"))
        + event(
            "response_item",
            Map.of(
                "type",
                "function_call_output",
                "call_id",
                id,
                "output",
                Map.of("agent_id", child)));
  }

  private static String usage(String id) throws Exception {
    return event(
        "token_usage_record",
        Map.of("response_id", id, "usage", Map.of("input_tokens", 1, "output_tokens", 1)));
  }

  @Test
  void completedMainCallsExposeNormalAndImportDeclarationShapes() throws Exception {
    for (boolean partial : List.of(false, true)) {
      String raw = completedMainSource(partial);
      Path source = directory.resolve("main-" + partial + ".jsonl");
      Files.writeString(source, raw);
      var adapter = new CodexSourceAdapter();
      try (var parsed =
              (SourceResult.Success)
                  adapter.parse(
                      new Candidate(
                          adapter.fingerprint(source),
                          "codex:synthetic-hotspot-main",
                          "",
                          Map.of()),
                      null);
          var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
        var files =
            List.of(
                new NormalizedSourceFile(
                    SourceFileRole.TRANSCRIPT, source, Optional.empty(), Optional.empty()));
        var normal =
            new NormalizationEngine()
                .normalizeContent(NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), files)
                .toArtifact();
        var imported =
            service
                .create(
                    new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                    "synthetic-main.jsonl",
                    NormalizedAgent.CODEX)
                .artifact();
        assertThat(
                new NormalizationEngine()
                    .normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), files)
                    .toArtifact())
            .isEqualTo(normal);
        observeCompletedShape(normal, partial, false);
        observeCompletedShape(imported, partial, true);
      }
    }
  }

  @Test
  void importOccurrencesBindCatalogMirrors() throws Exception {
    for (boolean partial : List.of(false, true)) {
      try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
        var artifact =
            service
                .create(
                    new ByteArrayInputStream(
                        completedMainSource(partial).getBytes(StandardCharsets.UTF_8)),
                    "occurrences.jsonl",
                    NormalizedAgent.CODEX)
                .artifact();
        assertImportedMirrors(artifact);
        observeCompletedShape(artifact, partial, true);
        Path output = Files.createDirectories(directory.resolve("import-persist-" + partial));
        var content =
            com.feipi.session.browser.domain.normalized.NormalizedSessionContent.fromArtifact(
                artifact);
        var metadata = new LinkedHashMap<String, Object>(content.header().session());
        metadata.put("session_key", "codex:import-" + partial);
        metadata.put("session_id", "import-" + partial);
        var header = content.header();
        content =
            content.withHeader(
                new NormalizedContentHeader(
                    header.schemaVersion(),
                    header.agent(),
                    new NormalizedSessionMetadata(metadata),
                    header.totals()));
        var written = new NormalizedArtifactWriter().writeContent(output, content, Map.of());
        assertImportedMirrors(NormalizedArtifactLoader.open(written.dataPath()).toArtifact());
        String url = "jdbc:sqlite:" + output.resolve("index.db");
        try (var connection = DriverManager.getConnection(url)) {
          var index = new SqliteIndexWriter(connection);
          index.ensureSchema();
          long scan = index.startScan(1, "full");
          index.writeNormalizedContent(
              content,
              written.dataPath(),
              output.toString(),
              1,
              Files.size(written.dataPath()),
              Instant.EPOCH);
          index.completeScan(scan, 2, Map.of("codex", 1));
        }
        try (var connection = DriverManager.getConnection(url);
            var statement = connection.createStatement();
            var rows = statement.executeQuery("SELECT path FROM session_artifacts")) {
          assertThat(rows.next()).isTrue();
          var reopened = NormalizedArtifactLoader.open(Path.of(rows.getString(1))).toArtifact();
          assertImportedMirrors(reopened);
          observeCompletedShape(reopened, partial, true);
          assertThat(rows.next()).isFalse();
        }
      }
    }
  }

  private static void assertImportedMirrors(NormalizedSessionArtifact artifact) {
    assertThat(artifact.calls())
        .hasSize(200)
        .allSatisfy(
            call -> {
              assertThat(call.sourceUnitRefRanges()).hasSize(1);
              assertThat(call.sourceUnitRefRanges().getFirst().refs()).hasSize(1);
              var key = call.sourceUnitRefRanges().getFirst().refs().getFirst();
              assertThat(artifact.sourceUnitCatalog().get(key).payload()).isIn(call.sourceUnits());
            });
    assertThat(artifact.sourceUnitCatalog().values())
        .filteredOn(entry -> entry.unitType().equals("import_raw_event"))
        .hasSize(801);
    assertThat(artifact.sourceUnitCatalog().values())
        .filteredOn(entry -> entry.unitType().equals("tool_result"))
        .hasSize(200);
  }

  @Test
  void repeatedRawIdsKeepPerOccurrenceNormalizedMirrorsAndIndependentNestedDeclarations()
      throws Exception {
    String raw = meta("synthetic", "");
    for (int i = 0; i < 2; i++) {
      raw +=
          event(
                  "response_item",
                  Map.of(
                      "type",
                      "function_call",
                      "call_id",
                      "reused",
                      "name",
                      "exec_command",
                      "arguments",
                      "input-" + i,
                      "content",
                      List.of(
                          Map.of(
                              "type", "tool_use", "id", "nested", "name", "Read", "input", "same"),
                          Map.of(
                              "type",
                              "tool_use",
                              "id",
                              "nested",
                              "name",
                              "Read",
                              "input",
                              "same"))))
              + usage("response-" + i);
    }
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      var artifact =
          service
              .create(
                  new ByteArrayInputStream(raw.getBytes(StandardCharsets.UTF_8)),
                  "repeat.jsonl",
                  NormalizedAgent.CODEX)
              .artifact();
      assertThat(artifact.toolExecutions())
          .hasSize(2)
          .extracting(t -> t.toolCallId())
          .doesNotHaveDuplicates();
      assertThat(artifact.calls()).hasSize(2);
      for (int i = 0; i < 2; i++) {
        var call = artifact.calls().get(i);
        var key = call.sourceUnitRefRanges().getFirst().refs().getFirst();
        var mirror = (Map<?, ?>) artifact.sourceUnitCatalog().get(key).payload();
        assertThat(mirror.get("id"))
            .isEqualTo(call.response().toolCallIds().getFirst())
            .isNotEqualTo("reused");
        assertThat(mirror.get("input")).isEqualTo("input-" + i);
        assertThat(mirror).isIn(call.sourceUnits());
      }
      assertThat(artifact.sourceUnitCatalog().values())
          .filteredOn(e -> e.unitType().equals("tool_use"))
          .hasSize(6);
      assertThat(artifact.sourceUnitCatalog().values())
          .filteredOn(e -> e.payload() instanceof Map<?, ?> m && "nested".equals(m.get("id")))
          .hasSize(4);
    }
  }

  private static String completedMainSource(boolean partial) throws Exception {
    var raw =
        new StringBuilder(
            event("session_meta", Map.of("id", "synthetic-hotspot-main", "source", "cli")));
    for (int i = 0; i < 200; i++) {
      String id = "hotspot-" + i;
      raw.append(
          event(
              "response_item",
              Map.of(
                  "type",
                  "function_call",
                  "call_id",
                  id,
                  "name",
                  "exec_command",
                  "arguments",
                  "{\"cmd\":\"synthetic-" + (i < 20 ? "alpha" : "beta") + "\"}")));
      raw.append(usage(id));
      raw.append(
          event(
              "response_item",
              Map.of(
                  "type",
                  "function_call_output",
                  "call_id",
                  id,
                  "output",
                  "Synthetic hotspot result " + i)));
      var end = new LinkedHashMap<String, Object>();
      end.put("type", "exec_command_end");
      end.put("call_id", id);
      end.put("exit_code", 0);
      end.put("status", "completed");
      if (!partial || i != 199) end.put("duration", Map.of("secs", 0, "nanos", 500000000));
      raw.append(event("event_msg", end));
    }
    return raw.toString();
  }

  private static void observeCompletedShape(
      NormalizedSessionArtifact artifact, boolean partial, boolean imported) throws Exception {
    assertThat(artifact.calls()).hasSize(200);
    assertThat(artifact.toolExecutions()).hasSize(200);
    assertThat(artifact.toolExecutions()).extracting(t -> t.toolCallId()).doesNotHaveDuplicates();
    assertThat(artifact.sourceUnitSequences()).isEmpty();
    assertThat(artifact.calls())
        .allSatisfy(
            c -> {
              if (imported) assertThat(c.sourceUnitRefRanges()).hasSize(1);
              else assertThat(c.sourceUnitRefRanges()).isEmpty();
            });
    var catalogDeclarations =
        artifact.sourceUnitCatalog().values().stream()
            .filter(u -> u.unitType().equals("tool_use"))
            .toList();
    assertThat(catalogDeclarations).hasSize(imported ? 200 : 0);
    assertThat(artifact.toolExecutions().stream().filter(t -> t.durationMs() != null).count())
        .isEqualTo(partial ? 199 : 200);
    for (int i = 0; i < 200; i++) {
      String id = "hotspot-" + i;
      String input = "{\"cmd\":\"synthetic-" + (i < 20 ? "alpha" : "beta") + "\"}";
      var tools =
          artifact.toolExecutions().stream().filter(t -> id.equals(t.toolCallId())).toList();
      assertThat(tools).hasSize(1);
      var tool = tools.getFirst();
      assertThat(tool.name()).isEqualTo("exec_command");
      assertThat(tool.scope().getValue()).isEqualTo("main");
      assertThat(tool.subagentId()).isEmpty();
      assertThat(tool.durationMs()).isEqualTo(partial && i == 199 ? null : 500L);
      var owners =
          artifact.calls().stream()
              .filter(c -> c.callId().equals(tool.declaredByCallId()))
              .toList();
      assertThat(owners).hasSize(1);
      var owner = owners.getFirst();
      assertThat(owner.callId()).isEqualTo("token_usage_record:" + id);
      assertThat(owner.scope()).isEqualTo(tool.scope());
      assertThat(owner.subagentId()).isEqualTo(tool.subagentId());
      assertThat(owner.response().toolCallIds()).containsExactly(id);
      var declarations = owner.sourceUnits().stream().filter(u -> id.equals(u.get("id"))).toList();
      assertThat(declarations).hasSize(1);
      var declaration = declarations.getFirst();
      assertThat(declaration)
          .containsExactlyInAnyOrderEntriesOf(
              Map.of(
                  "type",
                  "tool_use",
                  "role",
                  "assistant",
                  "text",
                  "",
                  "id",
                  id,
                  "name",
                  "exec_command",
                  "input",
                  input));
      assertThat(declaration)
          .doesNotContainKeys("arguments", "call_id", "canonicalSourceLocator", "eventOrder");
      if (imported) {
        String path = artifact.sourceFiles().getFirst().path().toString();
        String key = path + "#raw[" + (1 + 4 * i) + "]/tool";
        var catalog = artifact.sourceUnitCatalog().get(key);
        assertThat(catalog).isNotNull();
        assertThat(catalog.unitKey()).isEqualTo(key);
        assertThat(catalog.canonicalSourceLocator()).isEqualTo(key);
        assertThat(catalog.originPath()).isEqualTo(path);
        assertThat(catalog.direction().getValue()).isEqualTo("response");
        assertThat(catalog.candidate()).isEmpty();
        assertThat(catalog.eventOrder()).isEqualTo(1 + 4 * i);
        assertThat(catalog.partIndex()).isZero();
        assertThat(catalog.payload()).isEqualTo(declaration);
        var raw = artifact.sourceUnitCatalog().get(path + "#raw[" + (1 + 4 * i) + "]");
        assertThat(raw.direction().getValue()).isEqualTo("request");
        assertThat(JSON.readTree((String) raw.payload()).path("payload").path("arguments").asText())
            .isEqualTo(input);
      }
    }
  }
}
