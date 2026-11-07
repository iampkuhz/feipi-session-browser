package com.feipi.session.browser.cli;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.cli.batch.service.NormalizedBatchRunner;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.domain.source.SourceRecordSequence;
import com.feipi.session.browser.index.store.sqlite.loader.NormalizedArtifactLoader;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import picocli.CommandLine;

/**
 * {@link NormalizedBatchCommand} 单元测试。
 *
 * <p>验证隐藏命令的注册、空输入处理和命令配置。
 */
@DisplayName("NormalizedBatchCommand 测试")
class NormalizedBatchCommandTest {

  @Test
  @DisplayName("原 batch 命令接受超过 small 表示预算的 Codex 记录并完整重开")
  void managedCodexRecordsPassThroughOriginalBatchCommand(@TempDir Path tempDir) throws Exception {
    var root = createCodexFixture(tempDir, 1025);
    var stdout = runOriginalCommand(root, tempDir.resolve("artifacts"));
    var result = singleResult(stdout);
    assertThat(result.path("status").asText())
        .as("synthetic batch result: %s", result)
        .isEqualTo("success");
    var content = NormalizedArtifactLoader.open(Path.of(result.path("artifactPath").asText()));
    assertThat(content.legacyArtifact()).isEmpty();
    assertThat(content.header().totals().get("calls")).isEqualTo(1025L);
    for (int replay = 0; replay < 2; replay++) {
      long calls = 0;
      String tailText = null;
      try (var cursor = content.openCursor()) {
        while (cursor.hasNext()) {
          var unit = cursor.next();
          for (var call : unit.calls()) {
            assertThat(call.callIndex()).isEqualTo((int) calls + 1);
            var assistantTexts =
                call.sourceUnits().stream()
                    .filter(source -> "assistant".equals(source.get("role")))
                    .map(source -> source.get("text"))
                    .toList();
            assertThat(assistantTexts).containsExactly("synthetic answer " + calls);
            tailText = (String) assistantTexts.getFirst();
            calls++;
          }
        }
      }
      assertThat(calls).isEqualTo(1025);
      assertThat(tailText).isEqualTo("synthetic answer 1024");
    }
  }

  @Test
  @DisplayName("原 small batch 保留旧制品格式")
  void smallCodexKeepsLegacyArtifactFormat(@TempDir Path tempDir) throws Exception {
    var result =
        singleResult(
            runOriginalCommand(createCodexFixture(tempDir, 1), tempDir.resolve("artifacts")));
    assertThat(result.path("status").asText()).isEqualTo("success");
    assertThat(
            NormalizedArtifactLoader.open(Path.of(result.path("artifactPath").asText()))
                .legacyArtifact())
        .isPresent();
  }

  @Test
  void managedOwnerClosesBeforeSuccessIsEmitted(@TempDir Path tempDir) throws Exception {
    var run = runManagedCase(tempDir, false, false, false);
    assertThat(singleResult(run.stdout()).path("status").asText()).isEqualTo("success");
    assertThat(run.sequence().closeCount).isEqualTo(1);
    assertThat(run.sequence().activeCursors).isZero();
  }

  @Test
  void managedReadFailureClosesOwnerWithoutEmittingSuccess(@TempDir Path tempDir) throws Exception {
    var run = runManagedCase(tempDir, true, false, false);
    var result = singleResult(run.stdout());
    assertThat(result.path("status").asText()).isEqualTo("error");
    assertThat(result.path("error").asText()).contains("synthetic read failure");
    assertThat(run.sequence().closeCount).isEqualTo(1);
    assertThat(run.sequence().activeCursors).isZero();
  }

  @Test
  void managedWriteFailureClosesOwnerWithoutEmittingSuccess(@TempDir Path tempDir)
      throws Exception {
    var run = runManagedCase(tempDir, false, true, false);
    assertThat(singleResult(run.stdout()).path("status").asText()).isEqualTo("error");
    assertThat(run.sequence().closeCount).isEqualTo(1);
    assertThat(run.sequence().activeCursors).isZero();
  }

  @Test
  void managedCloseFailureOnlyEmitsError(@TempDir Path tempDir) throws Exception {
    var run = runManagedCase(tempDir, false, false, true);
    var result = singleResult(run.stdout());
    assertThat(result.path("status").asText()).isEqualTo("error");
    assertThat(result.path("error").asText()).contains("synthetic close failure");
    assertThat(run.sequence().closeCount).isEqualTo(1);
    assertThat(run.sequence().activeCursors).isZero();
  }

  private static Path createCodexFixture(Path tempDir, int count) throws IOException {
    var root = tempDir.resolve(".codex");
    var sessions = root.resolve("sessions/2026/01/01");
    Files.createDirectories(sessions);
    Files.writeString(
        root.resolve("session_index.jsonl"),
        "{\"id\":\"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\",\"thread_name\":\"synthetic batch\"}\n",
        StandardCharsets.UTF_8);
    var transcript =
        sessions.resolve("rollout-2026-01-01T00-00-00-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl");
    try (var writer = Files.newBufferedWriter(transcript, StandardCharsets.UTF_8)) {
      writer.write(
          "{\"type\":\"session_meta\",\"payload\":{\"id\":\"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\"}}\n");
      for (int i = 0; i < count; i++) {
        writer.write(
            "{\"type\":\"response_item\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\","
                + "\"id\":\"synthetic-message-"
                + i
                + "\",\"content\":[{\"type\":\"output_text\",\"text\":\"synthetic answer "
                + i
                + "\"}]}}\n");
      }
    }
    return root;
  }

  private static String batchRequest(Path root) throws Exception {
    return new ObjectMapper()
            .writeValueAsString(
                Map.of(
                    "requestId", "managed-codex", "sourceId", "CODEX", "rootPath", root.toString()))
        + "\n";
  }

  private static String runOriginalCommand(Path root, Path outputDir) throws Exception {
    var stdoutBytes = new ByteArrayOutputStream();
    InputStream originalIn = System.in;
    PrintStream originalOut = System.out;
    try (var stdout = new PrintStream(stdoutBytes, true, StandardCharsets.UTF_8)) {
      System.setIn(new ByteArrayInputStream(batchRequest(root).getBytes(StandardCharsets.UTF_8)));
      System.setOut(stdout);
      assertThat(
              new CommandLine(new SessionBrowserCommand())
                  .execute("normalized-batch", "--output-dir", outputDir.toString()))
          .isZero();
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
    return stdoutBytes.toString(StandardCharsets.UTF_8);
  }

  private static JsonNode singleResult(String stdout) throws Exception {
    var mapper = new ObjectMapper();
    var results = new ArrayList<JsonNode>();
    for (var line : stdout.lines().toList()) {
      var json = mapper.readTree(line);
      if (json.has("status")) {
        results.add(json);
      }
    }
    assertThat(results).as("synthetic batch stdout: %s", stdout).hasSize(1);
    return results.getFirst();
  }

  private static ManagedRun runManagedCase(
      Path tempDir, boolean failRead, boolean failWrite, boolean failClose) throws Exception {
    var root = createCodexFixture(tempDir, 1);
    var outputDir = tempDir.resolve("artifacts");
    var owner = new AtomicReference<TrackingSequence>();
    var delegate = SourceAdapterRegistry.forSourceId("CODEX");
    SourceAdapter adapter =
        (SourceAdapter)
            Proxy.newProxyInstance(
                SourceAdapter.class.getClassLoader(),
                new Class<?>[] {SourceAdapter.class},
                (proxy, method, args) -> {
                  if (!method.getName().equals("parse")) {
                    return method.invoke(delegate, args);
                  }
                  var parsed = (SourceResult.Success) method.invoke(delegate, args);
                  var sequence = new TrackingSequence(parsed, failRead, failClose);
                  owner.set(sequence);
                  if (failWrite) {
                    Files.delete(outputDir);
                    Files.writeString(
                        outputDir, "synthetic output blocker", StandardCharsets.UTF_8);
                  }
                  return SourceResult.Success.managed(
                      parsed.diagnostics(),
                      parsed.candidateCount(),
                      sequence,
                      parsed.fingerprint(),
                      parsed.locator());
                });
    var bytes = new ByteArrayOutputStream();
    try (var input = new ByteArrayInputStream(batchRequest(root).getBytes(StandardCharsets.UTF_8));
        var output =
            new PrintStream(bytes, true, StandardCharsets.UTF_8) {
              @Override
              public void println(String line) {
                if (line.contains("\"status\":\"success\"")) {
                  assertThat(owner.get().closeCount).isEqualTo(1);
                  assertThat(owner.get().activeCursors).isZero();
                }
                super.println(line);
              }
            }) {
      assertThat(new NormalizedBatchRunner().run(input, output, outputDir, id -> adapter)).isZero();
    }
    assertThat(owner.get()).isNotNull();
    return new ManagedRun(bytes.toString(StandardCharsets.UTF_8), owner.get());
  }

  private record ManagedRun(String stdout, TrackingSequence sequence) {}

  private static final class TrackingSequence implements SourceRecordSequence {
    private final SourceResult.Success original;
    private final boolean failRead;
    private final boolean failClose;
    private int activeCursors;
    private int closeCount;

    private TrackingSequence(SourceResult.Success original, boolean failRead, boolean failClose) {
      this.original = original;
      this.failRead = failRead;
      this.failClose = failClose;
    }

    @Override
    public long recordCount() {
      return original.recordSequence().recordCount();
    }

    @Override
    public RecordCursor openCursor(long ordinal) throws IOException {
      if (failRead) {
        throw new IOException("synthetic read failure");
      }
      var cursor = original.recordSequence().openCursor(ordinal);
      activeCursors++;
      return new RecordCursor() {
        private boolean closed;

        @Override
        public boolean hasNext() throws IOException {
          return cursor.hasNext();
        }

        @Override
        public SourceRecord next() throws IOException {
          return cursor.next();
        }

        @Override
        public void close() throws IOException {
          if (!closed) {
            closed = true;
            try {
              cursor.close();
            } finally {
              activeCursors--;
            }
          }
        }
      };
    }

    @Override
    public void close() throws IOException {
      closeCount++;
      assertThat(activeCursors).isZero();
      original.close();
      if (failClose) {
        throw new IOException("synthetic close failure");
      }
    }
  }

  /**
   * 使用空 stdin 运行批量命令，并捕获 stdout 输出。
   *
   * @param args 命令行参数
   * @return stdout 输出内容
   */
  private static String runWithEmptyStdin(String... args) throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      // 设置空的 stdin
      System.setIn(new ByteArrayInputStream(new byte[0]));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute(args);

      assertThat(exitCode).isZero();
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
    return stdoutBytes.toString();
  }

  @Test
  @DisplayName("normalized-batch 存在于 subcommands 中")
  void commandRegistered() {
    CommandLine cmd = new CommandLine(new SessionBrowserCommand());
    assertThat(cmd.getSubcommands()).containsKey("normalized-batch");
  }

  @Test
  @DisplayName("normalized-batch 命令标记为隐藏")
  void commandIsHidden() {
    CommandLine cmd = new CommandLine(new SessionBrowserCommand());
    CommandLine subCmd = cmd.getSubcommands().get("normalized-batch");
    assertThat(subCmd.getCommandSpec().usageMessage().hidden()).isTrue();
  }

  @Test
  @DisplayName("空输入产生空输出")
  void emptyInputProducesEmptyOutput() throws Exception {
    String stdout = runWithEmptyStdin("normalized-batch", "--output-dir", "/tmp/batch-test-empty");
    assertThat(stdout).isEmpty();
  }

  @Test
  @DisplayName("未知 sourceId 输入产生错误输出")
  void unknownSourceIdProducesErrorOutput() throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      String input = "{\"sourceId\":\"UNKNOWN\",\"rootPath\":\"/tmp/nonexistent\"}\n";
      System.setIn(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute("normalized-batch", "--output-dir", "/tmp/batch-test-unknown");

      assertThat(exitCode).isZero();
      assertThat(stdoutBytes.toString()).contains("error");
      assertThat(stdoutBytes.toString()).contains("Unknown source");
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
  }

  @Test
  @DisplayName("无效 JSON 输入产生错误输出")
  void invalidJsonProducesErrorOutput() throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      String input = "not valid json\n";
      System.setIn(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute("normalized-batch", "--output-dir", "/tmp/batch-test-invalid");

      assertThat(exitCode).isZero();
      assertThat(stdoutBytes.toString()).contains("error");
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
  }

  @Test
  @DisplayName("空行输入被跳过不产生输出")
  void emptyLinesAreSkipped() throws Exception {
    InputStream originalIn = System.in;
    ByteArrayOutputStream stdoutBytes = new ByteArrayOutputStream();
    PrintStream originalOut = System.out;
    try {
      String input = "\n\n\n";
      System.setIn(new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)));
      System.setOut(new PrintStream(stdoutBytes));

      CommandLine cmd = new CommandLine(new SessionBrowserCommand());
      int exitCode = cmd.execute("normalized-batch", "--output-dir", "/tmp/batch-test-emptylines");

      assertThat(exitCode).isZero();
      assertThat(stdoutBytes.toString()).isEmpty();
    } finally {
      System.setIn(originalIn);
      System.setOut(originalOut);
    }
  }
}
