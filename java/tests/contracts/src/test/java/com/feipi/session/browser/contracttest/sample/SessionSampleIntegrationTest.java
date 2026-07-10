package com.feipi.session.browser.contracttest.sample;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.CanonicalJsonWriter;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.common.JsonlReader;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.logging.Logger;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/**
 * 会话样例集成测试。
 *
 * <p>驱动真实 Java 生产管线（SourceAdapter -> NormalizationEngine -> CanonicalJsonWriter）， 对 {@code
 * docs/session-samples/} 下的会话样例进行端到端验证， 并与 {@code expected.normalized.jsonc} 参考文件做结构对比。
 */
class SessionSampleIntegrationTest {

  private static final Logger LOG = Logger.getLogger(SessionSampleIntegrationTest.class.getName());
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final JsonlReader JSONL_READER = new JsonlReader();

  private static final Path PROJECT_ROOT = resolveProjectRoot();
  private static final Path SAMPLES_ROOT = PROJECT_ROOT.resolve("docs/session-samples");
  private static final Path REPORTS_DIR = PROJECT_ROOT.resolve("reports");
  private static final Path DRIFT_REPORT_PATH =
      REPORTS_DIR.resolve("session-sample-drift-report.md");

  /** 收集所有漂移条目，供 {@code @AfterAll} 生成漂移报告使用。 */
  private static final List<DriftEntry> allDrifts = new ArrayList<>();

  /**
   * 从 user.dir 向上回溯查找项目根目录。
   *
   * @return 包含 docs/session-samples 的项目根路径
   */
  private static Path resolveProjectRoot() {
    Path dir = Path.of(System.getProperty("user.dir")).toAbsolutePath();
    for (int i = 0; i < 10 && dir != null; i++) {
      if (Files.isDirectory(dir.resolve("docs/session-samples"))) {
        return dir;
      }
      dir = dir.getParent();
    }
    // 回退：假设 user.dir 在项目根目录两级以下（模块构建目录）
    return Path.of(System.getProperty("user.dir")).toAbsolutePath().getParent().getParent();
  }

  @BeforeAll
  static void ensureReportsDir() throws IOException {
    Files.createDirectories(REPORTS_DIR);
  }

  @AfterAll
  static void writeDriftReport() throws IOException {
    StringBuilder sb = new StringBuilder();
    sb.append("# Session Sample Drift Report\n\n");
    sb.append("Generated: ").append(java.time.Instant.now()).append("\n\n");

    if (allDrifts.isEmpty()) {
      sb.append("未检测到漂移。所有样例匹配。\n");
    } else {
      sb.append("漂移条目总数: ").append(allDrifts.size()).append("\n\n");

      Map<String, List<DriftEntry>> bySession = new LinkedHashMap<>();
      for (DriftEntry entry : allDrifts) {
        bySession.computeIfAbsent(entry.sessionPath(), k -> new ArrayList<>()).add(entry);
      }

      for (Map.Entry<String, List<DriftEntry>> sessionEntry : bySession.entrySet()) {
        sb.append("## Session: `").append(sessionEntry.getKey()).append("`\n\n");
        for (DriftEntry drift : sessionEntry.getValue()) {
          sb.append("### [")
              .append(drift.category())
              .append("] ")
              .append(drift.jsonPath())
              .append("\n");
          sb.append("- **分类**: `").append(drift.category()).append("`\n");
          sb.append("- **差异**: ").append(drift.message()).append("\n\n");
        }
      }
    }

    Files.createDirectories(DRIFT_REPORT_PATH.getParent());
    Files.writeString(DRIFT_REPORT_PATH, sb.toString(), StandardCharsets.UTF_8);
    LOG.info("漂移报告已写入 " + DRIFT_REPORT_PATH);
  }

  /**
   * Claude Code 样例管线对比。
   *
   * <p>标记为 {@code sample-integration} 标签，仅在 sampleIntegrationTest task 中执行。
   */
  @Test
  @Tag("sample-integration")
  void claudeCodeSampleMatchesExpected() throws Exception {
    Path sampleDir = SAMPLES_ROOT.resolve("claude-code/8a283a61-e3f0-4e8f-ba06-6711e2fcf2ed");
    Path expectedFile = sampleDir.resolve("expected.normalized.jsonc");
    Path jsonlFile = sampleDir.resolve("8a283a61-e3f0-4e8f-ba06-6711e2fcf2ed.jsonl");

    assertFileExists(jsonlFile, "Claude 样例 JSONL");
    assertFileExists(expectedFile, "Claude 样例 expected.normalized.jsonc");

    runPipelineAndCompare(
        sampleDir,
        jsonlFile,
        expectedFile,
        new ClaudeSourceAdapter(),
        NormalizedAgent.CLAUDE_CODE,
        SourceId.CLAUDE_CODE);
  }

  /**
   * Codex 样例管线对比。
   *
   * <p>标记为 {@code sample-integration} 标签，仅在 sampleIntegrationTest task 中执行。
   */
  @Test
  @Tag("sample-integration")
  void codexSampleMatchesExpected() throws Exception {
    Path sampleDir = SAMPLES_ROOT.resolve("codex/019ede24-67de-7b11-b46f-7922530907a9");
    Path expectedFile = sampleDir.resolve("expected.normalized.jsonc");
    Path jsonlFile = sampleDir.resolve("019ede24-67de-7b11-b46f-7922530907a9.jsonl");

    assertFileExists(jsonlFile, "Codex 样例 JSONL");
    assertFileExists(expectedFile, "Codex 样例 expected.normalized.jsonc");

    runPipelineAndCompare(
        sampleDir,
        jsonlFile,
        expectedFile,
        new CodexSourceAdapter(),
        NormalizedAgent.CODEX,
        SourceId.CODEX);
  }

  @Test
  void discoverAllSampleDirectories() throws Exception {
    List<SampleSession> sessions = discoverSessions();
    LOG.info("发现 " + sessions.size() + " 个样例会话，位于 " + SAMPLES_ROOT);

    for (SampleSession session : sessions) {
      LOG.info(
          "  - "
              + session.agentDir().getFileName()
              + "/"
              + session.sessionDir().getFileName()
              + " (expected: "
              + Files.exists(session.expectedFile())
              + ")");
    }

    assertTrue(sessions.size() >= 2, "期望至少 2 个样例会话（claude-code + codex）");
  }

  /**
   * 运行完整管线并对比期望输出。
   *
   * <p>管线步骤：SourceAdapter.parse -> NormalizationEngine.normalize ->
   * CanonicalJsonWriter.serialize，然后与 expected.normalized.jsonc 做结构对比。
   *
   * @param sampleDir 样例会话目录
   * @param jsonlFile 输入 JSONL 文件路径
   * @param expectedFile 期望输出 JSONC 文件路径
   * @param adapter 源适配器实例
   * @param agent 归一化 agent 枚举
   * @param sourceId 源标识
   */
  private void runPipelineAndCompare(
      Path sampleDir,
      Path jsonlFile,
      Path expectedFile,
      SourceAdapter adapter,
      NormalizedAgent agent,
      SourceId sourceId)
      throws Exception {

    // 1. 构造指向 JSONL 文件的 Candidate
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            jsonlFile.toAbsolutePath().toString(),
            sourceId,
            Files.size(jsonlFile),
            Files.getLastModifiedTime(jsonlFile).toMillis(),
            Optional.empty(),
            Optional.empty());
    String sessionKey = sampleDir.getFileName().toString();
    Candidate candidate = new Candidate(fingerprint, sessionKey, "", Map.of());

    // 2. 通过 SourceAdapter 解析
    SourceResult result = adapter.parse(candidate, null);
    if (!(result instanceof SourceResult.Success success)) {
      fail(
          "SourceAdapter.parse 未成功: "
              + jsonlFile
              + ": "
              + result.outcome()
              + " - "
              + result.message());
      return;
    }

    List<SourceRecord> records = success.records();
    List<SourceDiagnostic> diagnostics = success.diagnostics();
    LOG.info("解析到 " + records.size() + " 条记录, " + diagnostics.size() + " 条诊断");

    // 3. 构造源文件列表
    List<NormalizedSourceFile> sourceFiles = sourceFilesForSample(sampleDir, jsonlFile, agent);

    // 4. 通过 NormalizationEngine 归一化
    NormalizationEngine engine = new NormalizationEngine();
    NormalizedSessionArtifact artifact = engine.normalize(agent, records, diagnostics, sourceFiles);

    // 5. 通过 CanonicalJsonWriter 序列化
    CanonicalJsonWriter writer = new CanonicalJsonWriter();
    byte[] javaOutputBytes = writer.serialize(artifact);
    String javaOutput = new String(javaOutputBytes, StandardCharsets.UTF_8);
    if (Boolean.getBoolean("session.samples.writeExpected")) {
      Files.writeString(
          expectedFile,
          MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(MAPPER.readTree(javaOutput))
              + System.lineSeparator(),
          StandardCharsets.UTF_8);
    }

    // 6. 读取期望输出
    String expectedJsonc = Files.readString(expectedFile, StandardCharsets.UTF_8);
    String expectedJson = JsoncStripper.strip(expectedJsonc);

    // 7. 结构对比
    List<String> differences = StructuralJsonCompare.compare(expectedJson, javaOutput);

    if (!differences.isEmpty()) {
      String relativePath = PROJECT_ROOT.relativize(sampleDir).toString();
      for (String diff : differences) {
        String category = classifyDiff(diff);
        allDrifts.add(new DriftEntry(relativePath, diff, category));
      }

      fail(
          "Schema 漂移: "
              + relativePath
              + ": "
              + differences.size()
              + " 处差异。详见漂移报告 "
              + DRIFT_REPORT_PATH
              + "。前 5 条差异: "
              + differences.subList(0, Math.min(5, differences.size())));
    }
  }

  private static void assertFileExists(Path path, String label) {
    assertTrue(Files.exists(path), label + " 不存在: " + path);
  }

  private static List<NormalizedSourceFile> sourceFilesForSample(
      Path sampleDir, Path jsonlFile, NormalizedAgent agent) throws IOException {
    if (agent == NormalizedAgent.CODEX) {
      return codexSourceFiles(sampleDir, jsonlFile);
    }
    return List.of(
        new NormalizedSourceFile(
            SourceFileRole.MAIN_SESSION,
            PROJECT_ROOT.relativize(jsonlFile.toAbsolutePath()),
            Optional.empty(),
            Optional.empty()));
  }

  private static List<NormalizedSourceFile> codexSourceFiles(Path sampleDir, Path jsonlFile)
      throws IOException {
    String parentThreadId = sampleDir.getFileName().toString();
    Map<String, String> spawnParents = codexSpawnParentToolIds(jsonlFile);
    List<NormalizedSourceFile> sourceFiles = new ArrayList<>();
    sourceFiles.add(
        new NormalizedSourceFile(
            SourceFileRole.CODEX_ROLLOUT,
            PROJECT_ROOT.relativize(jsonlFile.toAbsolutePath()),
            Optional.empty(),
            Optional.empty()));

    List<Path> childFiles = new ArrayList<>();
    try (DirectoryStream<Path> stream = Files.newDirectoryStream(sampleDir, "rollout-*.jsonl")) {
      for (Path candidate : stream) {
        Map<String, String> meta = readFirstSessionMeta(candidate);
        if (parentThreadId.equals(parentThreadId(meta))) {
          childFiles.add(candidate);
        }
      }
    }
    childFiles.sort(Path::compareTo);
    for (Path childFile : childFiles) {
      Map<String, String> meta = readFirstSessionMeta(childFile);
      String childId = meta.getOrDefault("id", "").trim();
      String parentToolUseId = spawnParents.get(childId);
      assertTrue(
          parentToolUseId != null && !parentToolUseId.isBlank(),
          "Codex child rollout 缺少 parent spawn_agent 映射: " + childFile);
      sourceFiles.add(
          new NormalizedSourceFile(
              SourceFileRole.SUBAGENT_SESSION,
              PROJECT_ROOT.relativize(childFile.toAbsolutePath()),
              Optional.of(childId),
              Optional.of(parentToolUseId)));
    }
    return List.copyOf(sourceFiles);
  }

  private static Map<String, String> codexSpawnParentToolIds(Path jsonlFile) throws IOException {
    Map<String, Boolean> spawnCalls = new LinkedHashMap<>();
    Map<String, String> parents = new LinkedHashMap<>();
    for (JsonNode event : JSONL_READER.read(jsonlFile).events()) {
      JsonNode payload = event.path("payload");
      String payloadType = text(payload, "type");
      String callId = text(payload, "call_id");
      if (("function_call".equals(payloadType) || "custom_tool_call".equals(payloadType))
          && "spawn_agent".equals(text(payload, "name"))
          && !callId.isBlank()) {
        spawnCalls.put(callId, Boolean.TRUE);
      }
      if (("function_call_output".equals(payloadType)
              || "custom_tool_call_output".equals(payloadType))
          && spawnCalls.containsKey(callId)) {
        String agentId = spawnAgentId(payload.get("output"));
        if (!agentId.isBlank()) {
          parents.put(agentId, callId);
        }
      }
    }
    return Map.copyOf(parents);
  }

  private static Map<String, String> readFirstSessionMeta(Path file) throws IOException {
    for (JsonNode event : JSONL_READER.read(file).events()) {
      if ("session_meta".equals(text(event, "type"))) {
        JsonNode payload = event.path("payload");
        Map<String, String> values = new LinkedHashMap<>();
        payload
            .fields()
            .forEachRemaining(
                entry -> {
                  JsonNode value = entry.getValue();
                  values.put(entry.getKey(), value.isTextual() ? value.asText() : value.toString());
                });
        return Map.copyOf(values);
      }
    }
    return Map.of();
  }

  private static String parentThreadId(Map<String, String> meta) throws IOException {
    String direct = meta.getOrDefault("parent_thread_id", "").trim();
    if (!direct.isBlank()) {
      return direct;
    }
    String source = meta.getOrDefault("source", "").trim();
    if (source.isBlank() || !source.startsWith("{")) {
      return "";
    }
    JsonNode sourceNode = MAPPER.readTree(source);
    JsonNode parent = sourceNode.path("subagent").path("thread_spawn").get("parent_thread_id");
    return parent != null && parent.isTextual() ? parent.asText().trim() : "";
  }

  private static String spawnAgentId(JsonNode output) throws IOException {
    if (output == null || output.isMissingNode() || output.isNull()) {
      return "";
    }
    JsonNode result = output.isTextual() ? MAPPER.readTree(output.asText()) : output;
    JsonNode agentId = result.get("agent_id");
    return agentId != null && agentId.isTextual() ? agentId.asText().trim() : "";
  }

  private static String text(JsonNode node, String fieldName) {
    JsonNode value = node == null ? null : node.get(fieldName);
    return value != null && value.isTextual() ? value.asText() : "";
  }

  /**
   * 将差异字符串分类为漂移类别。
   *
   * @param diff 差异描述
   * @return 漂移分类标识
   */
  private static String classifyDiff(String diff) {
    if (diff.contains("timestamp")
        || diff.contains("started_at")
        || diff.contains("ended_at")
        || diff.contains("lastModified")
        || diff.contains("path")
        || diff.contains("locator")) {
      return "volatile_field";
    }
    if (diff.contains("缺失") || diff.contains("不存在") || diff.contains("not null")) {
      return "production_bug";
    }
    if (diff.contains("不匹配")) {
      return "unknown";
    }
    return "unknown";
  }

  /**
   * 发现 docs/session-samples/ 下的所有样例会话。
   *
   * @return 包含 expected.normalized.jsonc 的样例会话列表
   */
  private static List<SampleSession> discoverSessions() throws IOException {
    List<SampleSession> sessions = new ArrayList<>();
    if (!Files.isDirectory(SAMPLES_ROOT)) {
      return sessions;
    }

    try (DirectoryStream<Path> agentDirs =
        Files.newDirectoryStream(SAMPLES_ROOT, Files::isDirectory)) {
      for (Path agentDir : agentDirs) {
        try (DirectoryStream<Path> sessionDirs =
            Files.newDirectoryStream(agentDir, Files::isDirectory)) {
          for (Path sessionDir : sessionDirs) {
            Path expected = sessionDir.resolve("expected.normalized.jsonc");
            if (Files.exists(expected)) {
              sessions.add(new SampleSession(agentDir, sessionDir, expected));
            }
          }
        }
      }
    }
    return sessions;
  }

  private record SampleSession(Path agentDir, Path sessionDir, Path expectedFile) {}

  /**
   * 漂移条目记录。
   *
   * @param sessionPath 样例会话相对路径
   * @param message 差异描述
   * @param category 漂移分类
   * @param jsonPath 差异发生的 JSON 路径
   */
  private record DriftEntry(String sessionPath, String message, String category, String jsonPath) {
    DriftEntry(String sessionPath, String diffMessage, String category) {
      this(sessionPath, diffMessage, category, extractPath(diffMessage));
    }

    private static String extractPath(String diffMessage) {
      int colonIdx = diffMessage.indexOf(':');
      return colonIdx > 0 ? diffMessage.substring(0, colonIdx).trim() : diffMessage;
    }
  }
}
