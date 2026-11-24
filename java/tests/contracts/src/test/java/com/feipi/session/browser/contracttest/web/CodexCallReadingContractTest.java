package com.feipi.session.browser.contracttest.web;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.application.sessiondetail.CallReadingEvidence;
import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.contracttest.support.ContractTestComposition;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.index.store.sqlite.connection.IndexConnection;
import com.feipi.session.browser.index.store.sqlite.connection.PragmaConfig;
import com.feipi.session.browser.index.store.sqlite.schema.SchemaVersion;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.query.api.PayloadVisibility;
import com.feipi.session.browser.scan.engine.FullScanEngine;
import com.feipi.session.browser.scan.engine.ScanConfig;
import com.feipi.session.browser.scan.engine.imports.IsolatedSessionImportService;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceResult;
import com.feipi.session.browser.testsupport.sqlite.SqliteTestHelper;
import com.feipi.session.browser.web.api.SessionApiHandler;
import com.feipi.session.browser.web.api.SessionApiRouter;
import com.feipi.session.browser.web.api.SessionApiService;
import io.javalin.Javalin;
import io.javalin.testtools.JavalinTest;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class CodexCallReadingContractTest {
  private static final String ID = "11111111-1111-4111-8111-111111111111";
  private static final ObjectMapper JSON = new ObjectMapper();
  @TempDir Path directory;

  @Test
  void readsRecordedAndReconstructedEvidenceInBothNormalizationPaths() throws Exception {
    var lines = new ArrayList<String>();
    lines.add(
        event(
            "session_meta",
            Map.of(
                "id",
                ID,
                "source",
                "vscode",
                "originator",
                "codex_app",
                "cli_version",
                "9.1",
                "model_provider",
                "synthetic-provider",
                "base_instructions",
                Map.of("text", "Base instruction"),
                "dynamic_tools",
                List.of(Map.of("name", "registered")))));
    lines.add(message("developer", "Base instruction"));
    lines.add(
        message(
            "developer",
            """
        <skills_instructions>
        ## Host skills
        ## Skills
        ### Available skills
        - demo: A synthetic skill. (file: r0/demo/SKILL.md)
        - plugin:other: A synthetic plugin skill. (file: r0/other/SKILL.md)
        ### How to use skills
        Read the skill first.
        </skills_instructions>

        Developer note.
        """));
    lines.add(
        event(
            "response_item",
            Map.of(
                "role",
                "developer",
                "type",
                "additional_tools",
                "tools",
                List.of(Map.of("name", "added")))));
    lines.add(
        event(
            "response_item",
            Map.of(
                "role",
                "user",
                "type",
                "additional_tools",
                "tools",
                List.of(Map.of("name", "not-a-definition")))));
    lines.add(
        message(
            "user",
            """
        # AGENTS.md instructions for /synthetic

        <INSTRUCTIONS>
        Repository instructions
        </INSTRUCTIONS>

        Initial user question
        """));
    String loaded =
        """
        <skill>
        <name>demo</name>
        <path>/synthetic/demo/SKILL.md</path>
        # Recorded skill body
        </skill>
        """;
    lines.add(message("developer", loaded));
    lines.add(message("developer", loaded));
    lines.add(message("developer", "Wrapper discussed: " + loaded));
    lines.add(message("user", loaded.replace("Recorded skill body", "User quoted example")));
    lines.add(collaboration("Initial config guidance"));
    lines.add(message("assistant", "I will use two tools."));
    lines.add(tool("a", "alpha arguments"));
    lines.add(tool("b", "beta arguments"));
    lines.add(usage("first", 2));
    lines.add(result("a", "alpha result"));
    lines.add(result("b", "beta result"));
    lines.add(message("assistant", "Synthetic answer."));
    lines.add(usage("second", 1));
    lines.add(event("compacted", Map.of("replacement_history", List.of("opaque history"))));
    lines.add(collaboration("Future config guidance"));
    lines.add(message("user", "Future user question"));
    lines.add(message("assistant", "Future answer."));
    lines.add(usage("third", 0));
    var root = directory.resolve("source");
    var adapter = ScannedSessionContentContractTest.writeSource("codex_tools", root);
    var file = root.resolve("sessions/2026/09/06/rollout-100-" + ID + ".jsonl");
    Files.write(file, lines);
    var codex = (CodexSourceAdapter) adapter;
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(file), "synthetic", "", Map.of()), null)) {
      assertThat(parsed.recordSequence().recordCount()).isEqualTo(lines.size());
      var metadata = parsed.records().getFirst();
      assertThat(metadata.eventType()).isEqualTo("session_meta");
      assertThat(metadata.content()).isEmpty();
      assertThat(metadata.readingEvidence())
          .anySatisfy(evidence -> assertThat(evidence.kind()).isEqualTo("base"));
      var engine = new NormalizationEngine();
      var normal =
          NormalizedSessionContent.fromArtifact(
              engine.normalize(NormalizedAgent.CODEX, parsed.records(), List.of(), List.of()));
      var managed =
          engine.normalizeContent(
              NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), List.of());
      assertThat(managed.toArtifact()).isEqualTo(normal.toArtifact());
      for (var content : List.of(normal, managed)) verify(content);
    }
    verifyScannedHttp(root, codex);
    verifyImported(codex, lines);
  }

  @ParameterizedTest
  @ValueSource(ints = {-1, 0, 30})
  void exactCompactionDoesNotAttributeUnreportedReasoningAsZero(int reasoning) throws Exception {
    var file = directory.resolve("synthetic-compaction-split.jsonl");
    var usage = new HashMap<>(Map.of("input_tokens", 4000, "output_tokens", 100));
    if (reasoning >= 0) usage.put("reasoning_output_tokens", reasoning);
    Files.write(
        file,
        List.of(
            event("session_meta", Map.of("id", ID)),
            event("token_usage_record", Map.of("response_id", "prep", "usage", usage)),
            event("compacted", Map.of("compaction_response_id", "prep")),
            message("user", "A user question after compacting"),
            message("assistant", "The only real answer"),
            observedResponse("after", 100, 4202)));
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(file), "synthetic", "", Map.of()), null)) {
      var content =
          new NormalizationEngine()
              .normalizeContent(
                  NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), List.of());
      var reader = new SessionContentReader(content, 0);
      var calls = content.toArtifact().calls();
      assertThat(calls).hasSize(2);
      var before = calls.getFirst().callId();
      var after = calls.getLast().callId();
      var response = view(content, reader, "main:resp:" + before);
      assertThat(response.tokens()).containsEntry("output", 100L);
      assertThat(response.blocks())
          .extracting(CallReadingEvidence.Block::kind)
          .containsExactly("response_evidence", "response_compaction");
      if (reasoning < 0) {
        assertThat(response.tokens()).doesNotContainKeys("reasoning", "compactionOutput");
        assertThat(response.blocks().getLast().text()).contains("份额未知");
      } else {
        assertThat(response.tokens())
            .containsEntry("reasoning", (long) reasoning)
            .containsEntry("compactionOutput", 100L - reasoning);
      }
      var prepRequest = view(content, reader, "main:req:" + before);
      assertThat(prepRequest.tokens()).containsEntry("input", 4000L).doesNotContainKey("turnTotal");
      assertThat(prepRequest.blocks()).isEmpty();
      var nextRequest = view(content, reader, "main:req:" + after);
      assertThat(nextRequest.tokens())
          .containsEntry("input", 100L)
          .containsEntry("turnTotal", 4202L);
      assertThat(nextRequest.blocks())
          .extracting(CallReadingEvidence.Block::text)
          .anyMatch(text -> text.contains("无法仅凭这个边界解释"))
          .contains("A user question after compacting");
      assertThat(view(content, reader, "main:resp:" + after).blocks())
          .extracting(CallReadingEvidence.Block::text)
          .containsExactly("The only real answer");
    }
  }

  @Test
  void usageOnlyResponseStaysSeparateFromAdjacentCompactionAndNextResponse() throws Exception {
    var file = directory.resolve("synthetic-compaction.jsonl");
    Files.write(
        file,
        List.of(
            event("session_meta", Map.of("id", ID)),
            observedResponse("prep", 100, 102),
            event(
                "compacted",
                Map.of(
                    "replacement_history",
                    List.of(Map.of("type", "compaction", "id", "opaque-replacement-id")))),
            message("user", "A user question after compacting"),
            message("assistant", "The only real answer"),
            observedResponse("after", 20, 124),
            message("user", "Another question separates frames"),
            event("compacted", Map.of("response_id", "unrelated"))));
    var adapter = new CodexSourceAdapter();
    try (var parsed =
        (SourceResult.Success)
            adapter.parse(
                new Candidate(adapter.fingerprint(file), "synthetic", "", Map.of()), null)) {
      var engine = new NormalizationEngine();
      var content =
          engine.normalizeContent(
              NormalizedAgent.CODEX, parsed.recordSequence(), List.of(), List.of());
      var reader = new SessionContentReader(content, 0);
      var calls = content.toArtifact().calls();
      assertThat(calls).hasSize(2);
      assertThat(CallReadingEvidence.hasObservedResponse(calls.getFirst())).isTrue();
      String preparation = "main:resp:" + calls.getFirst().callId();
      assertThat(reader.payload(preparation, PayloadVisibility.STANDARD).orElseThrow().content())
          .isEmpty();
      var response = view(content, reader, preparation);
      assertThat(response.blocks())
          .extracting(CallReadingEvidence.Block::kind)
          .containsExactly("response_evidence", "response_compaction");
      assertThat(response.tokens()).containsEntry("total", 102L).containsEntry("turnTotal", 102L);
      var answer = view(content, reader, "main:resp:" + calls.getLast().callId());
      assertThat(answer.blocks())
          .extracting(CallReadingEvidence.Block::kind)
          .containsExactly("conversation");
      assertThat(answer.blocks().getFirst().text()).isEqualTo("The only real answer");
      assertThat(answer.tokens()).containsEntry("total", 22L).containsEntry("turnTotal", 124L);
      assertThat(view(content, reader, "main:req:" + calls.getLast().callId()).blocks())
          .extracting(CallReadingEvidence.Block::kind)
          .contains("context_snapshot");
    }
  }

  private static String observedResponse(String id, int input, int turnTotal) throws Exception {
    return event(
        "token_usage_record",
        Map.of(
            "response_id",
            id,
            "turn_id",
            "same-synthetic-turn",
            "usage",
            Map.of(
                "input_tokens",
                input,
                "cached_input_tokens",
                0,
                "cache_write_input_tokens",
                0,
                "output_tokens",
                2,
                "total_tokens",
                input + 2),
            "turn_token_usage",
            Map.of("total_tokens", turnTotal)));
  }

  private static void verifyImported(CodexSourceAdapter adapter, List<String> lines)
      throws Exception {
    // 独立上传不接受压缩快照；只将压缩前的已知调用交给上传校验。
    String jsonl =
        String.join(
                "\n", lines.stream().takeWhile(line -> !line.contains("\"compacted\"")).toList())
            + "\n";
    try (var imports = new IsolatedSessionImportService(source -> adapter);
        var input = new ByteArrayInputStream(jsonl.getBytes(StandardCharsets.UTF_8))) {
      var analysis = imports.create(input, "synthetic.jsonl", NormalizedAgent.CODEX);
      var content = NormalizedSessionContent.fromArtifact(analysis.artifact());
      var reader = new SessionContentReader(content, 0);
      String id = "main:req:" + analysis.artifact().calls().get(1).callId();
      var projection = view(content, reader, id);
      assertThat(projection.protocol()).containsEntry("modelProvider", "synthetic-provider");
      assertThat(projection.skillNames()).containsExactly("demo", "plugin:other");
      assertThat(projection.blocks())
          .filteredOn(block -> "configuration".equals(block.kind()))
          .extracting(CallReadingEvidence.Block::text)
          .containsExactly("Initial config guidance");
      assertThat(reader.payload(id, PayloadVisibility.STANDARD).orElseThrow().content())
          .doesNotContain("Initial user question", "Initial config guidance");
    }
  }

  private void verifyScannedHttp(Path root, CodexSourceAdapter adapter) throws Exception {
    String jdbc = "jdbc:sqlite:" + directory.resolve("index.db");
    try (var connection = DriverManager.getConnection(jdbc)) {
      SqliteTestHelper.configureConnection(connection);
      var report =
          new FullScanEngine()
              .scan(
                  SqliteTestHelper.createIndexWriter(connection),
                  ScanConfig.defaults(
                      List.of(new ScanConfig.SourceEntry(adapter, root)),
                      directory.resolve("artifacts")));
      assertThat(report.errorCount()).as("%s", report.issues()).isZero();
      assertThat(report.successCount()).isEqualTo(1);
    }
    try (var index =
        IndexConnection.create(DriverManager.getConnection(jdbc), PragmaConfig.DEFAULTS, jdbc)) {
      var details = ContractTestComposition.queryRoot(index, new SchemaVersion(1)).sessionDetail();
      var context =
          details.getDetailContext("codex:" + ID, PayloadVisibility.STANDARD).orElseThrow();
      verify(context.content());
      var calls = context.content().toArtifact().calls();
      String id = "main:req:" + calls.get(1).callId();
      var roundIndex = new SessionContentReader(context.content(), 0).roundIndex();
      String roundId =
          "round:req:" + roundIndex.roundIndexForCall(calls.get(1).callId()).orElseThrow();
      var router =
          new SessionApiRouter(
              new SessionApiHandler(new SessionApiService(details::getDetailContext)));
      JavalinTest.test(
          Javalin.create(config -> config.routes.get("/api/sessions/*", router::route)),
          (app, client) -> {
            for (String resource : List.of("content", "payload")) {
              for (String payload : List.of(id, roundId)) {
                var response =
                    client.get("/api/sessions/codex/" + ID + "/" + resource + "/" + payload);
                assertThat(response.code()).isEqualTo(200);
                var json = JSON.readTree(response.body().string());
                assertThat(json.path("skillNames").size()).isEqualTo(2);
                assertThat(json.path("modelProvider").asText()).isEqualTo("synthetic-provider");
                assertThat(json.path("reading"))
                    .anySatisfy(
                        block ->
                            assertThat(block.path("source").asText()).isEqualTo("reconstructed"));
                assertThat(json.path("content").asText()).doesNotContain("Initial user question");
              }
            }
          });
    }
  }

  private static void verify(NormalizedSessionContent content) throws Exception {
    var reader = new SessionContentReader(content, 0);
    var calls = content.toArtifact().calls();
    assertThat(calls).hasSize(3);
    String first = calls.get(0).callId(),
        second = calls.get(1).callId(),
        third = calls.get(2).callId();
    var firstRequest = view(content, reader, "main:req:" + first);
    assertThat(firstRequest.blocks())
        .anySatisfy(
            block -> {
              assertThat(block.kind()).isEqualTo("base_instructions");
              assertThat(block.text()).isEqualTo("Base instruction");
            });
    assertThat(firstRequest.blocks()).noneMatch(block -> "context_snapshot".equals(block.kind()));
    assertThat(
            firstRequest.blocks().stream().filter(block -> "Base instruction".equals(block.text())))
        .hasSize(1);
    assertThat(view(content, reader, "main:req:" + third).blocks())
        .filteredOn(block -> "context_snapshot".equals(block.kind()))
        .singleElement()
        .satisfies(
            block -> {
              assertThat(block.source()).isEqualTo("current");
              assertThat(block.text())
                  .contains("compacted", "replacement_history")
                  .doesNotContain("opaque history");
            });
    var firstResponse = view(content, reader, "main:resp:" + first);
    assertThat(firstResponse.tokens())
        .containsEntry("reasoning", 2L)
        .containsEntry("total", 10L)
        .containsEntry("input", 7L)
        .containsEntry("output", 3L);
    assertThat(firstResponse.blocks())
        .extracting(CallReadingEvidence.Block::text)
        .containsExactly("I will use two tools.", "alpha arguments", "beta arguments");
    var entry = reader.payload("main:req:" + second, PayloadVisibility.STANDARD).orElseThrow();
    assertThat(entry.content())
        .contains("alpha result", "beta result")
        .doesNotContain("Initial user question", "Repository instructions");
    var reconstructed = view(content, reader, "main:req:" + second);
    assertThat(reconstructed.protocol())
        .containsEntry("modelProvider", "synthetic-provider")
        .containsEntry("source", "vscode")
        .containsEntry("originator", "codex_app")
        .containsEntry("cliVersion", "9.1");
    assertThat(reconstructed.blocks())
        .filteredOn(block -> "configuration".equals(block.kind()))
        .satisfiesExactly(
            block -> {
              assertThat(block.text()).isEqualTo("Initial config guidance");
              assertThat(block.source()).isEqualTo("reconstructed");
            });
    assertThat(firstResponse.blocks()).noneMatch(block -> "configuration".equals(block.kind()));
    assertThat(view(content, reader, "main:req:" + third).blocks())
        .filteredOn(block -> "configuration".equals(block.kind()))
        .satisfiesExactly(
            block -> {
              assertThat(block.text()).isEqualTo("Future config guidance");
              assertThat(block.source()).isEqualTo("current");
            });
    assertThat(reconstructed.blocks())
        .filteredOn(block -> "loaded_skill".equals(block.kind()))
        .singleElement()
        .satisfies(
            block -> {
              assertThat(block.label()).isEqualTo("demo");
              assertThat(block.text()).isEqualTo("# Recorded skill body");
              assertThat(block.source()).isEqualTo("reconstructed");
            });
    assertThat(reconstructed.blocks())
        .filteredOn(block -> "conversation".equals(block.kind()))
        .anySatisfy(block -> assertThat(block.text()).contains("User quoted example"));
    assertThat(reconstructed.blocks())
        .filteredOn(block -> "instructions".equals(block.kind()))
        .anySatisfy(block -> assertThat(block.text()).contains("Wrapper discussed:"));
    assertThat(reconstructed.skillNames()).containsExactly("demo", "plugin:other");
    assertThat(reconstructed.blocks())
        .filteredOn(block -> "tools".equals(block.kind()))
        .extracting(CallReadingEvidence.Block::text)
        .hasSize(2)
        .anySatisfy(text -> assertThat(text).contains("\"added\""));
    assertThat(reconstructed.blocks())
        .filteredOn(block -> "reconstructed".equals(block.source()))
        .extracting(block -> block.text().strip())
        .contains("Initial user question", "I will use two tools.");
    assertThat(reconstructed.blocks())
        .allSatisfy(
            block ->
                assertThat(block.text())
                    .doesNotContain("Future user question", "not-a-definition"));
    var declarations =
        reconstructed.blocks().stream().filter(block -> "tool_call".equals(block.kind())).toList();
    assertThat(declarations)
        .extracting(CallReadingEvidence.Block::text)
        .containsExactly("alpha arguments", "beta arguments");
    assertThat(declarations).extracting(CallReadingEvidence.Block::label).containsOnly("Read");
    assertThat(declarations)
        .extracting(CallReadingEvidence.Block::source)
        .containsOnly("reconstructed");
    var results =
        reconstructed.blocks().stream()
            .filter(block -> "tool_result".equals(block.kind()))
            .toList();
    assertThat(results)
        .extracting(CallReadingEvidence.Block::text)
        .containsExactly("alpha result", "beta result");
    assertThat(results)
        .extracting(CallReadingEvidence.Block::toolCallId)
        .containsExactlyElementsOf(
            declarations.stream().map(CallReadingEvidence.Block::toolCallId).toList());
    assertThat(reconstructed.blocks())
        .anySatisfy(block -> assertThat(block.text()).contains("Repository instructions"));
    assertThat(view(content, reader, "main:req:" + third).blocks())
        .extracting(CallReadingEvidence.Block::text)
        .contains("Base instruction", "Future user question")
        .doesNotContain(
            "Initial user question", "I will use two tools.", "alpha result", "alpha arguments");
  }

  private static CallReadingEvidence.View view(
      NormalizedSessionContent content, SessionContentReader reader, String id) throws Exception {
    var entry = reader.payload(id, PayloadVisibility.STANDARD).orElseThrow();
    return CallReadingEvidence.read(content, entry, PayloadVisibility.STANDARD).orElseThrow();
  }

  private static String collaboration(String instructions) throws Exception {
    return event(
        "turn_context",
        Map.of(
            "collaboration_mode",
            Map.of("settings", Map.of("developer_instructions", instructions))));
  }

  private static String message(String role, String content) throws Exception {
    return event("response_item", Map.of("role", role, "type", "message", "content", content));
  }

  private static String tool(String id, String input) throws Exception {
    return event(
        "response_item",
        Map.of("type", "function_call", "call_id", id, "name", "Read", "arguments", input));
  }

  private static String result(String id, String output) throws Exception {
    return event(
        "response_item", Map.of("type", "function_call_output", "call_id", id, "output", output));
  }

  private static String usage(String id, int reasoning) throws Exception {
    return event(
        "token_usage_record",
        Map.of(
            "response_id",
            id,
            "usage",
            Map.of(
                "input_tokens",
                7,
                "cached_input_tokens",
                0,
                "cache_write_input_tokens",
                0,
                "output_tokens",
                3,
                "total_tokens",
                10,
                "reasoning_output_tokens",
                reasoning)));
  }

  private static String event(String type, Object payload) throws Exception {
    return JSON.writeValueAsString(Map.of("type", type, "payload", payload));
  }
}
