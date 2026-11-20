package com.feipi.session.browser.scan.artifact;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertAll;

import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.index.store.sqlite.repository.SqliteIndexWriter;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 真源到普通、惰性、制品、SQLite 重开和隔离导入的协作事实合同。 */
class CollaborationSourcePipelineTest {
  @TempDir Path directory;

  private static void assertResultBodies(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact) {
    assertThat(artifact.toolExecutions())
        .flatExtracting(tool -> tool.collaboration())
        .filteredOn(action -> action.kind().equals("input"))
        .hasSize(4)
        .allSatisfy(
            action ->
                assertThat(action.targetId()).contains("11111111-1111-4111-8111-111111111111"));
    assertThat(artifact.sourceUnitCatalog().values())
        .anySatisfy(
            unit ->
                assertThat(unit.text().orElse(""))
                    .matches(
                        "\\{\"agent_id\":\"(same-target|worker-shared-001)\",\"nickname\":\"same name\"\\}"));
    assertThat(artifact.sourceUnitCatalog().values())
        .anySatisfy(
            unit ->
                assertThat(unit.text())
                    .contains(
                        "{\"status\":{\"worker-shared-001\":{\"completed\":\"synthetic body\"},"
                            + "\"worker-shared-002\":{\"completed\":\"synthetic body\"}}}"));
  }

  @Test
  void sameToolResultOccurrencesKeepTheirRequestsThroughPublication() throws Exception {
    String raw =
        """
        {"synthetic":true,"type":"session_meta","timestamp":"2026-04-24T11:00:00Z","payload":{"id":"synthetic-result-occurrences-v98","cwd":"/synthetic/result-occurrences","source":"cli"}}
        {"synthetic":true,"type":"turn_context","timestamp":"2026-04-24T11:00:01Z","payload":{"turn_id":"synthetic-result-occurrences-turn","model":"synthetic-codex"}}
        {"synthetic":true,"type":"response_item","timestamp":"2026-04-24T11:00:02Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Synthetic causality audit. Read these records only; never execute the recorded command."}]}}
        {"synthetic":true,"type":"response_item","timestamp":"2026-04-24T11:00:03Z","payload":{"type":"function_call","call_id":"synthetic-result-occurrences-tool","name":"exec_command","arguments":"{\\"cmd\\":\\"printf \\\\\\"synthetic-result-occurrences\\\\\\"\\"}"}}
        {"synthetic":true,"type":"token_usage_record","timestamp":"2026-04-24T11:00:04Z","payload":{"response_id":"synthetic-result-occurrences-F1","turn_id":"synthetic-result-occurrences-turn","usage":{"input_tokens":11,"output_tokens":2}}}
        {"synthetic":true,"type":"response_item","timestamp":"2026-04-24T11:00:05Z","payload":{"type":"function_call_output","call_id":"synthetic-result-occurrences-tool","output":"SYNTHETIC_RESULT_OCCURRENCE_R1"}}
        {"synthetic":true,"type":"token_usage_record","timestamp":"2026-04-24T11:00:06Z","payload":{"response_id":"synthetic-result-occurrences-F2","turn_id":"synthetic-result-occurrences-turn","usage":{"input_tokens":13,"output_tokens":3}}}
        {"synthetic":true,"type":"response_item","timestamp":"2026-04-24T11:00:07Z","payload":{"type":"function_call_output","call_id":"synthetic-result-occurrences-tool","output":"SYNTHETIC_RESULT_OCCURRENCE_R2"}}
        {"synthetic":true,"type":"token_usage_record","timestamp":"2026-04-24T11:00:08Z","payload":{"response_id":"synthetic-result-occurrences-F3","turn_id":"synthetic-result-occurrences-turn","usage":{"input_tokens":17,"output_tokens":5}}}
        {"synthetic":true,"type":"event_msg","timestamp":"2026-04-24T11:00:09Z","payload":{"type":"exec_command_end","call_id":"synthetic-result-occurrences-tool","process_id":"synthetic-result-occurrences-process","duration":{"secs":0,"nanos":750000000},"status":"completed","exit_code":0}}
        """;
    byte[] bytes = raw.getBytes(StandardCharsets.UTF_8);
    assertThat(
            java.util.HexFormat.of()
                .formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(bytes)))
        .isEqualTo("07309d407390505e7d31da28c4f230ff2b3aa358ba730ff1a3ec48a320efcac7");
    assertThat(bytes).hasSize(2244);
    assertThat(raw.lines()).hasSize(10);
    Path source = directory.resolve("rollout-synthetic-result-occurrences-v98.jsonl");
    Files.write(source, bytes);
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(
                    adapter.fingerprint(source),
                    "codex:synthetic-result-occurrences-v98",
                    "",
                    Map.of()),
                null)) {
      var files =
          List.of(
              new NormalizedSourceFile(
                  SourceFileRole.TRANSCRIPT, source, Optional.empty(), Optional.empty()));
      var engine = new NormalizationEngine();
      var ordinary =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), files);
      var managed =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), files);
      assertAll(
          "same raw occurrence causality",
          () -> assertOccurrencePublication(ordinary, "ordinary"),
          () -> assertOccurrencePublication(managed, "managed"));
    }
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      var imported =
          service.create(
              new ByteArrayInputStream(bytes), "occurrences.jsonl", NormalizedAgent.CODEX);
      assertOccurrenceArtifact(imported.artifact());
    }
  }

  private void assertOccurrencePublication(NormalizedSessionContent content, String path)
      throws Exception {
    var artifact = content.toArtifact();
    assertOccurrenceArtifact(artifact);
    var wrapped = session(content, "codex:synthetic-result-occurrences-v98");
    var writer = new NormalizedArtifactWriter();
    var canonical =
        writer.write(
            Files.createDirectories(directory.resolve(path + "-occurrence-canonical")),
            wrapped.toArtifact(),
            Map.of());
    var units =
        writer.writeContent(
            Files.createDirectories(directory.resolve(path + "-occurrence-units")),
            wrapped,
            Map.of());
    for (var publication : List.of(canonical, units)) {
      var published = NormalizedArtifactLoader.open(publication.dataPath()).toArtifact();
      assertOccurrenceArtifact(published);
      assertThat(published.calls()).isEqualTo(artifact.calls());
      assertThat(published.toolExecutions()).isEqualTo(artifact.toolExecutions());
      assertThat(published.sourceUnitCatalog()).isEqualTo(artifact.sourceUnitCatalog());
      String url = "jdbc:sqlite:" + publication.dataPath().getParent().resolve("index.db");
      try (var connection = DriverManager.getConnection(url)) {
        var index = new SqliteIndexWriter(connection);
        index.ensureSchema();
        long scan = index.startScan(1, "full");
        index.writeNormalizedContent(
            wrapped,
            publication.dataPath(),
            "rollout-synthetic-result-occurrences-v98.jsonl",
            1,
            1,
            Instant.EPOCH);
        index.completeScan(scan, 1, Map.of("codex", 1));
      }
      try (var connection = DriverManager.getConnection(url);
          var statement = connection.createStatement();
          var rows = statement.executeQuery("SELECT path FROM session_artifacts")) {
        assertThat(rows.next()).isTrue();
        var reopened = NormalizedArtifactLoader.open(Path.of(rows.getString(1))).toArtifact();
        assertOccurrenceArtifact(reopened);
        assertThat(reopened.calls()).isEqualTo(artifact.calls());
        assertThat(reopened.toolExecutions()).isEqualTo(artifact.toolExecutions());
        assertThat(reopened.sourceUnitCatalog()).isEqualTo(artifact.sourceUnitCatalog());
        assertThat(rows.next()).isFalse();
      }
    }
  }

  private static void assertOccurrenceArtifact(
      com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact artifact) {
    assertThat(artifact.calls()).hasSize(3);
    assertThat(artifact.toolExecutions()).hasSize(1);
    assertThat(artifact.calls())
        .extracting(call -> call.usage().fresh())
        .containsExactly(11L, 13L, 17L);
    assertThat(artifact.calls())
        .extracting(call -> call.usage().output())
        .containsExactly(2L, 3L, 5L);
    var owner = artifact.calls().getFirst();
    var second = artifact.calls().get(1);
    var third = artifact.calls().getLast();
    var tool = artifact.toolExecutions().getFirst();
    assertThat(tool.declaredByCallId()).isEqualTo(owner.callId());
    assertThat(owner.response().toolCallIds()).containsExactly(tool.toolCallId());
    assertThat(second.response().toolCallIds()).isEmpty();
    assertThat(third.response().toolCallIds()).isEmpty();
    assertThat(tool.resultConsumedByCallId()).isEmpty();
    assertThat(tool.durationMs()).isEqualTo(750L);
    assertThat(tool.exitCode()).contains(0);
    assertThat(owner.sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit)
                    .containsEntry(
                        "input", "{\"cmd\":\"printf \\\"synthetic-result-occurrences\\\"\"}"));
    assertThat(artifact.sourceUnitCatalog().values())
        .filteredOn(entry -> "tool_result".equals(entry.unitType()))
        .hasSize(2)
        .extracting(entry -> entry.text().orElseThrow())
        .containsExactlyInAnyOrder(
            "SYNTHETIC_RESULT_OCCURRENCE_R1", "SYNTHETIC_RESULT_OCCURRENCE_R2");
    assertThat(owner.request().toolResultIds()).isEmpty();
    assertThat(second.request().toolResultIds()).containsExactly(tool.toolCallId());
    assertThat(third.request().toolResultIds()).containsExactly(tool.toolCallId());
    assertThat(owner.sourceUnits()).noneMatch(unit -> "tool_result".equals(unit.get("type")));
    assertThat(
            second.sourceUnits().stream()
                .filter(unit -> "tool_result".equals(unit.get("type")))
                .map(unit -> unit.get("text"))
                .toList())
        .containsExactly("SYNTHETIC_RESULT_OCCURRENCE_R1");
    assertThat(
            third.sourceUnits().stream()
                .filter(unit -> "tool_result".equals(unit.get("type")))
                .map(unit -> unit.get("text"))
                .toList())
        .containsExactly("SYNTHETIC_RESULT_OCCURRENCE_R2");
  }

  @Test
  void orphanToolInputNormalSourceSurvivesBothNormalizationPathsAndPublication() throws Exception {
    String parentRaw =
        """
        {"type":"session_meta","payload":{"id":"synthetic-orphan-parent-v52"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"orphan-parent-spawn-v54","name":"spawn_agent","arguments":"{\\"message\\":\\"Synthetic interrupted child task: inspect recorded command failure; do not execute a real script.\\"}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"orphan-parent-spawn-v54","output":"{\\"agent_id\\":\\"synthetic-orphan-child-v52\\"}"}}
        {"type":"token_usage_record","payload":{"response_id":"orphan-parent-response-v54","usage":{"input_tokens":1,"output_tokens":1}}}
        """;
    String childRaw =
        """
        {"type":"session_meta","payload":{"id":"synthetic-orphan-child-v52","source":{"subagent":{"thread_spawn":{"parent_thread_id":"synthetic-orphan-parent-v52"}}}}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"orphan-command-v52","name":"exec_command","arguments":"{\\"cmd\\":\\"node synthetic-orphan-check.js --case no-owner\\"}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"orphan-command-v52","output":"Synthetic recorded error, command not executed"}}
        {"type":"event_msg","payload":{"type":"exec_command_end","call_id":"orphan-command-v52","duration":{"secs":0,"nanos":500000000},"exit_code":7,"status":"completed"}}
        """;
    assertThat(
            java.util.HexFormat.of()
                .formatHex(
                    java.security.MessageDigest.getInstance("SHA-256")
                        .digest(parentRaw.getBytes(StandardCharsets.UTF_8))))
        .isEqualTo("9a91aecab70d4979c098507a443cbed720d70bdc70471e843c11ab3a5cfa55fc");
    assertThat(
            java.util.HexFormat.of()
                .formatHex(
                    java.security.MessageDigest.getInstance("SHA-256")
                        .digest(childRaw.getBytes(StandardCharsets.UTF_8))))
        .isEqualTo("61349a6822530652ff636826a8b579d84a2fa27774291bf59867e45255cc969e");
    Path parent = directory.resolve("rollout-synthetic-orphan-parent-v52.jsonl");
    Files.writeString(parent, parentRaw);
    Files.writeString(directory.resolve("rollout-synthetic-orphan-child-v52.jsonl"), childRaw);
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(
                    adapter.fingerprint(parent), "codex:synthetic-orphan-parent-v52", "", Map.of()),
                null)) {
      assertThat(parsed.records())
          .flatExtracting(record -> record.toolCalls())
          .anySatisfy(
              tool ->
                  assertThat(tool.input())
                      .isEqualTo("{\"cmd\":\"node synthetic-orphan-check.js --case no-owner\"}"));
      var files =
          List.of(
              new NormalizedSourceFile(
                  SourceFileRole.TRANSCRIPT, parent, Optional.empty(), Optional.empty()));
      var engine = new NormalizationEngine();
      var ordinary =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), files);
      var managed =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), files);
      assertAll(
          "ordinary and managed preserve the same raw orphan input",
          () -> assertOrphanInputPublished(ordinary, "ordinary"),
          () -> assertOrphanInputPublished(managed, "managed"));
    }
  }

  private void assertOrphanInputPublished(NormalizedSessionContent content, String path)
      throws Exception {
    var artifact = content.toArtifact();
    var parent = artifact.calls().getFirst();
    var spawn =
        artifact.toolExecutions().stream()
            .filter(tool -> tool.name().equals("spawn_agent"))
            .findFirst()
            .orElseThrow();
    assertThat(artifact.calls()).hasSize(1);
    assertThat(parent.usage().fresh()).isEqualTo(1);
    assertThat(parent.usage().output()).isEqualTo(1);
    assertThat(spawn.declaredByCallId()).isEqualTo(parent.callId());
    assertThat(spawn.resultConsumedByCallId()).isEmpty();
    assertThat(parent.request().toolResultIds()).isEmpty();
    assertThat(parent.sourceUnits()).noneMatch(unit -> "tool_result".equals(unit.get("type")));
    assertThat(parent.sourceUnits())
        .anySatisfy(
            unit ->
                assertThat(unit.get("input"))
                    .asString()
                    .contains("Synthetic interrupted child task"));
    assertThat(artifact.sourceUnitCatalog().values())
        .anySatisfy(
            entry -> {
              assertThat(entry.unitType()).isEqualTo("tool_result");
              assertThat(entry.text()).contains("{\"agent_id\":\"synthetic-orphan-child-v52\"}");
            });

    assertThat(artifact.calls()).as(path + " parent call").hasSize(1);
    assertThat(artifact.toolExecutions()).as(path + " executions").hasSize(2);
    var child =
        artifact.toolExecutions().stream()
            .filter(tool -> tool.name().equals("exec_command"))
            .findFirst()
            .orElseThrow();
    assertThat(child.declaredByCallId()).isEqualTo("unknown");
    assertThat(child.scope().getValue()).isEqualTo("subagent");
    assertThat(child.subagentId()).contains("synthetic-orphan-child-v52");
    assertThat(child.durationMs()).isEqualTo(500L);
    assertThat(child.exitCode()).contains(7);
    assertThat(child.resultConsumedByCallId()).isEmpty();
    assertThat(artifact.sourceUnitCatalog().values())
        .anySatisfy(
            entry -> {
              assertThat(entry.unitType()).isEqualTo("tool_result");
              assertThat(entry.label()).contains(child.toolCallId());
              assertThat(entry.text()).contains("Synthetic recorded error, command not executed");
            });
    var written =
        new NormalizedArtifactWriter()
            .write(
                Files.createDirectories(directory.resolve(path + "-orphan-output")),
                session(content, "codex:synthetic-orphan-parent-v52").toArtifact(),
                Map.of());
    var published = NormalizedArtifactLoader.open(written.dataPath()).toArtifact();
    assertThat(published.calls()).isEqualTo(artifact.calls());
    assertThat(published.toolExecutions()).isEqualTo(artifact.toolExecutions());
    assertThat(published.sourceUnitCatalog()).isEqualTo(artifact.sourceUnitCatalog());
    var unitWritten =
        new NormalizedArtifactWriter()
            .writeContent(
                Files.createDirectories(directory.resolve(path + "-orphan-units")),
                session(content, "codex:synthetic-orphan-parent-v52"),
                Map.of());
    var unitPublished = NormalizedArtifactLoader.open(unitWritten.dataPath()).toArtifact();
    assertThat(unitPublished.calls()).isEqualTo(published.calls());
    assertThat(unitPublished.toolExecutions()).isEqualTo(published.toolExecutions());
    assertThat(unitPublished.sourceUnitCatalog()).isEqualTo(published.sourceUnitCatalog());
    for (var publication : List.of(written, unitWritten)) {
      Path data = publication.dataPath();
      String url = "jdbc:sqlite:" + data.getParent().resolve("index.db");
      try (var connection = DriverManager.getConnection(url)) {
        var index = new SqliteIndexWriter(connection);
        index.ensureSchema();
        long scan = index.startScan(1, "full");
        index.writeNormalizedContent(
            session(content, "codex:synthetic-orphan-parent-v52"),
            data,
            "synthetic-orphan-parent-v52.jsonl",
            1,
            1,
            Instant.EPOCH);
        index.completeScan(scan, 2, Map.of("codex", 1));
      }
      try (var connection = DriverManager.getConnection(url);
          var statement = connection.createStatement();
          var rows = statement.executeQuery("SELECT path FROM session_artifacts")) {
        assertThat(rows.next()).isTrue();
        var reopened = NormalizedArtifactLoader.open(Path.of(rows.getString(1))).toArtifact();
        assertThat(reopened.calls()).isEqualTo(artifact.calls());
        assertThat(reopened.toolExecutions()).isEqualTo(artifact.toolExecutions());
        assertThat(reopened.sourceUnitCatalog()).isEqualTo(artifact.sourceUnitCatalog());
        assertThat(reopened.sourceUnitCatalog().values())
            .anySatisfy(
                entry -> {
                  assertThat(entry.payload()).isInstanceOf(Map.class);
                  var payload = (Map<?, ?>) entry.payload();
                  assertThat(payload.get("id")).isEqualTo(child.toolCallId());
                  assertThat(payload.get("input"))
                      .isEqualTo("{\"cmd\":\"node synthetic-orphan-check.js --case no-owner\"}");
                });
        assertThat(rows.next()).isFalse();
      }
    }
    assertThat(published.sourceUnitCatalog().values())
        .as(path + " published orphan tool input must retain the original command")
        .anySatisfy(
            entry -> {
              assertThat(entry.direction().getValue()).isEqualTo("response");
              assertThat(entry.payload()).isInstanceOf(Map.class);
              Map<?, ?> payload = (Map<?, ?>) entry.payload();
              assertThat(payload.get("type")).isEqualTo("tool_use");
              assertThat(payload.get("id")).isEqualTo(child.toolCallId());
              assertThat(payload.get("name")).isEqualTo(child.name());
              assertThat(payload.get("input"))
                  .isEqualTo("{\"cmd\":\"node synthetic-orphan-check.js --case no-owner\"}");
            });
  }

  @Test
  void childInputActorComesFromDeclarationNotItsDifferentTarget() throws Exception {
    String actor = "22222222-2222-4222-8222-222222222222";
    Path parent = directory.resolve("rollout-root.jsonl");
    Path child = directory.resolve("rollout-" + actor + ".jsonl");
    Files.writeString(
        parent,
        meta("root", "")
            + "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"id\":\"parent-response\",\"content\":[{\"type\":\"output_text\",\"text\":\"synthetic parent response\"}]}}\n"
            + spawn("spawn-child", actor)
            + usage("parent-response")
            + waitTail());
    Files.writeString(child, meta(actor, "root") + inputTail());
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(parent), "codex:root", "", Map.of()), null)) {
      var files =
          List.of(
              new NormalizedSourceFile(
                  SourceFileRole.TRANSCRIPT, parent, Optional.empty(), Optional.empty()));
      var engine = new NormalizationEngine();
      var ordinary =
          engine
              .normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), files)
              .toArtifact();
      var managed =
          engine.normalizeContent(NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), files);
      assertThat(managed.toArtifact()).isEqualTo(ordinary);
      assertThat(ordinary.toolExecutions())
          .flatExtracting(tool -> tool.collaboration())
          .filteredOn(action -> action.kind().equals("input"))
          .hasSize(4)
          .allSatisfy(
              action -> {
                assertThat(action.actorId()).contains(actor);
                assertThat(action.targetId()).contains("11111111-1111-4111-8111-111111111111");
                assertThat(action.sourceLocator()).startsWith(child.toString());
              });
      assertThat(ordinary.calls())
          .filteredOn(call -> call.subagentId().filter(actor::equals).isPresent())
          .allSatisfy(call -> assertThat(call.parentToolCallId()).contains("spawn-child"));
      var callIds = ordinary.calls().stream().map(call -> call.callId()).toList();
      var toolIds = ordinary.toolExecutions().stream().map(tool -> tool.toolCallId()).toList();
      assertThat(ordinary.calls())
          .allSatisfy(
              call -> {
                call.parentCallId().ifPresent(id -> assertThat(callIds).contains(id));
                call.parentToolCallId().ifPresent(id -> assertThat(toolIds).contains(id));
                assertThat(toolIds).containsAll(call.response().toolCallIds());
                assertThat(toolIds).containsAll(call.request().toolResultIds());
              });
      assertThat(ordinary.toolExecutions())
          .allSatisfy(
              tool -> {
                assertThat(callIds).contains(tool.declaredByCallId());
                tool.resultConsumedByCallId().ifPresent(id -> assertThat(callIds).contains(id));
              });
      var written =
          new NormalizedArtifactWriter()
              .writeContent(
                  Files.createDirectories(directory.resolve("child-input-output")),
                  session(managed, "codex:child-input"),
                  Map.of());
      assertThat(NormalizedArtifactLoader.open(written.dataPath()).toArtifact().toolExecutions())
          .isEqualTo(ordinary.toolExecutions());
    }
  }

  @Test
  void spooledRawResultsRemainReadableAfterManagedCanonicalReload() throws Exception {
    Path source = directory.resolve("spooled.jsonl");
    String body =
        meta("root", "")
            + spawn("spawn", "same-target")
            + usage("response")
            + waitTail()
            + inputTail();
    Files.writeString(
        source,
        body
            + "{\"type\":\"event_msg\",\"payload\":{\"type\":\"user_message\",\"message\":\""
            + "x".repeat(2 * 1024 * 1024 + 1)
            + "\"}}\n");
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(source), "codex:spooled", "", Map.of()), null)) {
      assertThat(parsed.hasManagedRecords()).isTrue();
      var content =
          new NormalizationEngine()
              .normalizeContent(
                  NormalizedAgent.CODEX,
                  parsed.recordSequence(),
                  List.of(),
                  List.of(
                      new NormalizedSourceFile(
                          SourceFileRole.TRANSCRIPT, source, Optional.empty(), Optional.empty())));
      assertResultBodies(content.toArtifact());
      var written =
          new NormalizedArtifactWriter()
              .writeContent(
                  Files.createDirectories(directory.resolve("spooled-output")),
                  session(content, "codex:spooled"),
                  Map.of());
      assertResultBodies(NormalizedArtifactLoader.open(written.dataPath()).toArtifact());
    }
  }

  @Test
  void nestedAndSiblingSourceFactsSurviveBothPathsCanonicalAndSqliteReopen() throws Exception {
    for (boolean nested : List.of(false, true)) {
      Path root = Files.createDirectories(directory.resolve(nested ? "nested" : "siblings"));
      Path parent = root.resolve("rollout-root.jsonl");
      Path a = root.resolve("rollout-worker-shared-001.jsonl");
      Path b = root.resolve("rollout-worker-shared-002.jsonl");
      Files.writeString(
          parent,
          meta("root", "")
              + spawn("shared-spawn", "worker-shared-001")
              + (nested ? "" : spawn("second-spawn", "worker-shared-002"))
              + usage("root-response")
              + inputTail()
              + waitTail());
      Files.writeString(
          a,
          meta("worker-shared-001", "root")
              + (nested ? spawn("shared-spawn", "worker-shared-002") : "")
              + usage("a-response"));
      Files.writeString(
          b,
          meta("worker-shared-002", nested ? "worker-shared-001" : "root") + usage("b-response"));
      var adapter = new CodexSourceAdapter();
      try (var parsed =
          (SourceResult.Success)
              adapter.parse(
                  new Candidate(adapter.fingerprint(parent), "codex:root", "", Map.of()), null)) {
        var files =
            List.of(
                new NormalizedSourceFile(
                    SourceFileRole.TRANSCRIPT, parent, Optional.empty(), Optional.empty()));
        var engine = new NormalizationEngine();
        var ordinary =
            engine.normalizeContent(NormalizedAgent.CODEX, parsed.records(), List.of(), files);
        var managed =
            engine.normalizeContent(
                NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), files);
        var expected = ordinary.toArtifact();
        assertResultBodies(expected);
        assertThat(expected.calls().stream().mapToLong(call -> call.usage().fresh()).sum())
            .isEqualTo(42);
        assertThat(expected.calls().stream().mapToLong(call -> call.usage().output()).sum())
            .isEqualTo(8);
        assertThat(managed.toArtifact()).isEqualTo(expected);
        assertThat(expected.calls())
            .extracting(call -> call.subagentId().orElse("main"))
            .contains("main", "worker-shared-001", "worker-shared-002");
        var target =
            expected.calls().stream()
                .filter(call -> call.subagentId().filter("worker-shared-002"::equals).isPresent())
                .findFirst()
                .orElseThrow();
        var parentTool =
            expected.toolExecutions().stream()
                .filter(
                    tool -> target.parentToolCallId().filter(tool.toolCallId()::equals).isPresent())
                .findFirst()
                .orElseThrow();
        var owner =
            expected.calls().stream()
                .filter(call -> call.callId().equals(parentTool.declaredByCallId()))
                .findFirst()
                .orElseThrow();
        assertThat(owner.subagentId())
            .isEqualTo(nested ? Optional.of("worker-shared-001") : Optional.empty());
        assertThat(parentTool.collaboration())
            .anySatisfy(
                fact -> {
                  assertThat(fact.targetId()).contains("worker-shared-002");
                  assertThat(fact.actorId()).isEqualTo(owner.subagentId());
                  assertThat(fact.sourceLocator()).contains("#event[");
                });
        var wait =
            expected.toolExecutions().stream()
                .filter(tool -> tool.name().equals("wait_agent"))
                .findFirst()
                .orElseThrow();
        assertThat(wait.collaboration()).hasSize(4);
        assertThat(wait.collaboration())
            .filteredOn(fact -> fact.phase().equals("result_report"))
            .allSatisfy(fact -> assertThat(fact.reportedStatus()).contains("completed"));
        assertThat(wait.resultConsumedByCallId()).isEmpty();
        for (boolean units : List.of(false, true)) {
          Path output = Files.createDirectories(root.resolve(units ? "units" : "compact"));
          var content = session(managed, "codex:synthetic-" + nested + "-" + units);
          var writer = new NormalizedArtifactWriter();
          var written =
              units
                  ? writer.writeContent(output, content, Map.of())
                  : writer.write(output, content.toArtifact(), Map.of());
          String url = "jdbc:sqlite:" + output.resolve("index.db");
          try (var connection = DriverManager.getConnection(url)) {
            var index = new SqliteIndexWriter(connection);
            index.ensureSchema();
            long scan = index.startScan(1, "full");
            index.writeNormalizedContent(
                content,
                written.dataPath(),
                parent.toString(),
                1,
                Files.size(parent),
                Instant.EPOCH);
            index.completeScan(scan, 2, Map.of("codex", 1));
          }
          try (var connection = DriverManager.getConnection(url);
              var statement = connection.createStatement();
              var rows = statement.executeQuery("SELECT path FROM session_artifacts")) {
            assertThat(rows.next()).isTrue();
            var reopened = NormalizedArtifactLoader.open(Path.of(rows.getString(1))).toArtifact();
            assertThat(reopened.toolExecutions()).isEqualTo(expected.toolExecutions());
            assertThat(reopened.calls()).isEqualTo(expected.calls());
            assertResultBodies(reopened);
          }
        }
      }
    }
  }

  @Test
  void sameIdsInSeparateSingleFileImportsKeepLogicalAnchorsAndMissingChildren() throws Exception {
    String source =
        meta("root", "")
            + spawn("spawn", "same-target")
            + usage("root-response")
            + waitTail()
            + inputTail();
    try (var service = new IsolatedSessionImportService(agent -> new CodexSourceAdapter())) {
      var first =
          service.create(
              new ByteArrayInputStream(source.getBytes(StandardCharsets.UTF_8)),
              "one.jsonl",
              NormalizedAgent.CODEX);
      var second =
          service.create(
              new ByteArrayInputStream(source.getBytes(StandardCharsets.UTF_8)),
              "two.jsonl",
              NormalizedAgent.CODEX);
      assertThat(first.metadata().importId()).isNotEqualTo(second.metadata().importId());
      for (var imported : List.of(first, second)) {
        assertResultBodies(imported.artifact());
        assertThat(imported.artifact().calls())
            .allSatisfy(call -> assertThat(call.subagentId()).isEmpty());
        assertThat(imported.artifact().toolExecutions())
            .flatExtracting(tool -> tool.collaboration())
            .allSatisfy(
                fact ->
                    assertThat(fact.sourceLocator())
                        .startsWith(
                            "imports/" + imported.metadata().importId() + "/upload.jsonl#event["));
        assertThat(imported.artifact().toolExecutions())
            .filteredOn(tool -> tool.name().equals("spawn_agent"))
            .flatExtracting(tool -> tool.collaboration())
            .allSatisfy(fact -> assertThat(fact.reason()).isEqualTo("single_file_not_included"));
      }
    }
  }

  @Test
  void claudeExplicitParentToolsAndAnonymousSidechainsAreNotGuessedOrMerged() throws Exception {
    Path input = directory.resolve("claude.jsonl");
    Files.writeString(
        input,
        """
        {"type":"assistant","uuid":"parent","sessionId":"synthetic","message":{"id":"p","role":"assistant","content":[{"type":"tool_use","id":"a","name":"Agent","input":{"prompt":"synthetic"}},{"type":"tool_use","id":"b","name":"Agent","input":{"prompt":"synthetic"}},{"type":"tool_use","id":"reused","name":"Agent","input":{"prompt":"synthetic"}}]}}
        {"type":"assistant","uuid":"child-a","sessionId":"synthetic","agentId":"worker-shared-001","isSidechain":true,"parent_tool_use_id":"a","message":{"id":"ca","role":"assistant","content":[{"type":"text","text":"synthetic"},{"type":"tool_use","id":"reused","name":"Agent","input":{"prompt":"synthetic"}}]}}
        {"type":"assistant","uuid":"child-b","sessionId":"synthetic","agentId":"worker-shared-002","isSidechain":true,"parent_tool_use_id":"b","message":{"id":"cb","role":"assistant","content":[{"type":"text","text":"synthetic"}]}}
        {"type":"assistant","uuid":"unknown-a","sessionId":"synthetic","isSidechain":true,"message":{"id":"ua","role":"assistant","content":[{"type":"text","text":"synthetic"},{"type":"tool_use","id":"anonymous-delegate","name":"Agent","input":{"prompt":"synthetic"}}]}}
        {"type":"assistant","uuid":"unknown-b","sessionId":"synthetic","isSidechain":true,"message":{"id":"ub","role":"assistant","content":[{"type":"text","text":"synthetic"}]}}
        """);
    var adapter = new ClaudeSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(input), "claude_code:synthetic", "", Map.of()),
                null)) {
      var files =
          List.of(
              new NormalizedSourceFile(
                  SourceFileRole.TRANSCRIPT, input, Optional.empty(), Optional.empty()));
      var engine = new NormalizationEngine();
      var artifact =
          engine
              .normalizeContent(NormalizedAgent.CLAUDE_CODE, parsed.records(), List.of(), files)
              .toArtifact();

      assertThat(artifact.calls())
          .filteredOn(call -> call.subagentId().filter("worker-shared-001"::equals).isPresent())
          .singleElement()
          .satisfies(call -> assertThat(call.parentToolCallId()).contains("a"));
      assertThat(artifact.calls())
          .filteredOn(call -> call.subagentId().filter("worker-shared-002"::equals).isPresent())
          .singleElement()
          .satisfies(call -> assertThat(call.parentToolCallId()).contains("b"));
      assertThat(artifact.calls())
          .filteredOn(
              call ->
                  call.subagentId().filter(id -> id.startsWith("unknown-sidechain:")).isPresent())
          .hasSize(2)
          .extracting(call -> call.subagentId().orElseThrow())
          .doesNotHaveDuplicates();
      assertThat(artifact.toolExecutions()).flatExtracting(tool -> tool.collaboration()).hasSize(5);
      var actions =
          artifact.toolExecutions().stream()
              .flatMap(tool -> tool.collaboration().stream())
              .toList();
      assertThat(actions)
          .filteredOn(action -> action.actorId().filter("worker-shared-001"::equals).isPresent())
          .hasSize(1);
      assertThat(actions)
          .filteredOn(action -> action.actorIdentityReason().equals("anonymous_sidechain"))
          .singleElement()
          .satisfies(action -> assertThat(action.actorId()).isEmpty());
    }
  }

  @Test
  void claudeDuplicateDeclarationsKeepConflictFactsForEachCanonicalOccurrence() throws Exception {
    Path input = directory.resolve("claude-conflict.jsonl");
    Files.writeString(
        input,
        """
        {"type":"assistant","uuid":"parent","sessionId":"synthetic","message":{"id":"p","role":"assistant","content":[{"type":"tool_use","id":"duplicate","name":"Agent","input":{"prompt":"synthetic"}},{"type":"tool_use","id":"duplicate","name":"Task","input":{"prompt":"synthetic"}}]}}
        """);
    var adapter = new ClaudeSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(input), "claude_code:synthetic", "", Map.of()),
                null)) {
      var artifact =
          new NormalizationEngine()
              .normalizeContent(NormalizedAgent.CLAUDE_CODE, parsed.records(), List.of(), List.of())
              .toArtifact();
      assertThat(artifact.toolExecutions())
          .hasSize(2)
          .extracting(tool -> tool.toolCallId())
          .doesNotHaveDuplicates();
      assertThat(artifact.toolExecutions())
          .allSatisfy(
              tool -> {
                assertThat(tool.collaboration())
                    .singleElement()
                    .satisfies(
                        action -> {
                          assertThat(action.reason()).isEqualTo("conflicting_tool_identity");
                          assertThat(action.targetId()).isEmpty();
                        });
              });
    }
  }

  @Test
  void oversizedTargetSetsKeepCompactBoundsAndExplicitTruncationWithoutBodies() throws Exception {
    var targets = new java.util.ArrayList<String>();
    var statuses = new LinkedHashMap<String, Object>();
    String body = "synthetic body".repeat(10000);
    for (int i = 0; i < 300; i++) {
      targets.add("target-shared-" + i);
      statuses.put("target-shared-" + i, Map.of("completed", i == 0 ? body : "synthetic"));
    }
    var json = new com.fasterxml.jackson.databind.ObjectMapper();
    var declaration =
        Map.of(
            "type",
            "response_item",
            "payload",
            Map.of(
                "type",
                "function_call",
                "call_id",
                "wait",
                "name",
                "wait_agent",
                "arguments",
                Map.of("targets", targets)));
    var result =
        Map.of(
            "type",
            "response_item",
            "payload",
            Map.of(
                "type",
                "function_call_output",
                "call_id",
                "wait",
                "output",
                Map.of("status", statuses)));
    Path input = directory.resolve("rollout-large.jsonl");
    Files.writeString(
        input,
        meta("root", "")
            + json.writeValueAsString(declaration)
            + "\n"
            + usage("response")
            + json.writeValueAsString(result)
            + "\n");
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(input), "codex:synthetic-large", "", Map.of()),
                null)) {
      var content =
          new NormalizationEngine()
              .normalizeContent(
                  NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), List.of());
      var actions = content.toArtifact().toolExecutions().getFirst().collaboration();
      assertThat(actions).hasSize(256);
      assertThat(actions)
          .extracting(action -> action.reason())
          .contains("targets_truncated", "facts_truncated");
      assertThat(actions.toString()).doesNotContain("synthetic body");
      assertThat(actions.toString().length()).isLessThan(150000);
    }
  }

  private static NormalizedSessionContent session(NormalizedSessionContent content, String key) {
    var header = content.header();
    var metadata = new LinkedHashMap<String, Object>(header.session());
    metadata.put("session_key", key);
    metadata.put("session_id", key);
    return content.withHeader(
        new NormalizedContentHeader(
            header.schemaVersion(),
            header.agent(),
            new NormalizedSessionMetadata(metadata),
            header.totals()));
  }

  private static String meta(String id, String parent) {
    return "{\"type\":\"session_meta\",\"payload\":{\"id\":\""
        + id
        + "\""
        + (parent.isEmpty()
            ? ""
            : ",\"source\":{\"subagent\":{\"thread_spawn\":{\"parent_thread_id\":\""
                + parent
                + "\"}}}")
        + "}}\n";
  }

  private static String spawn(String id, String target) {
    return "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\""
        + id
        + "\",\"name\":\"spawn_agent\",\"arguments\":\"{\\\"message\\\":\\\"synthetic task\\\"}\"}}\n"
        + "{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\""
        + id
        + "\",\"output\":{\"agent_id\":\""
        + target
        + "\",\"nickname\":\"same name\"}}}\n";
  }

  private static String usage(String id) {
    return "{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\""
        + id
        + "\",\"usage\":{\"input_tokens\":10,\"output_tokens\":2}}}\n";
  }

  private static String inputTail() {
    return """
        {"type":"response_item","payload":{"type":"function_call","namespace":"multi_agent_v1","name":"send_input","call_id":"follow-message","arguments":"{\\\"target\\\":\\\"11111111-1111-4111-8111-111111111111\\\",\\\"message\\\":\\\"synthetic followup\\\"}"}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"follow-message","output":{"submission_id":"synthetic-one"}}}
        {"type":"response_item","payload":{"type":"function_call","namespace":"multi_agent_v1","name":"send_input","call_id":"follow-items","arguments":{"target":"11111111-1111-4111-8111-111111111111","items":[{"type":"text","text":"synthetic followup items"}],"interrupt":true}}}
        {"type":"token_usage_record","payload":{"response_id":"input-response","usage":{"input_tokens":0,"output_tokens":0}}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"follow-items","output":"{\\\"submission_id\\\":\\\"synthetic-two\\\"}"}}
        """;
  }

  private static String waitTail() {
    return """
        {"type":"response_item","payload":{"type":"function_call","call_id":"wait","name":"wait_agent","arguments":{"targets":["worker-shared-001","worker-shared-002"]}}}
        {"type":"token_usage_record","payload":{"response_id":"wait-response","usage":{"input_tokens":12,"output_tokens":2}}}
        {"type":"response_item","payload":{"type":"function_call_output","call_id":"wait","output":{"status":{"worker-shared-001":{"completed":"synthetic body"},"worker-shared-002":{"completed":"synthetic body"}}}}}
        """;
  }
}
