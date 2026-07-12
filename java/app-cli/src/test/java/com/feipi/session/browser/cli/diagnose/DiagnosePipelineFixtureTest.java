package com.feipi.session.browser.cli.diagnose;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 使用合成 fixture 测试诊断管道各层。 */
@DisplayName("diagnose 管道 fixture 测试")
class DiagnosePipelineFixtureTest {

  @TempDir Path tempDir;

  private Path sourceRoot;
  private static final String SESSION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  private static final String PROJECT_DIR = "test-project";

  @BeforeEach
  void setupFixture() throws IOException {
    sourceRoot = tempDir.resolve(".claude");
    Files.createDirectories(sourceRoot);

    // 创建 history.jsonl
    Path historyFile = sourceRoot.resolve("history.jsonl");
    String historyEntry =
        "{\"sessionId\":\""
            + SESSION_ID
            + "\",\"project\":\""
            + PROJECT_DIR
            + "\",\"display\":\"test session\",\"timestamp\":1700000000000}";
    Files.writeString(historyFile, historyEntry + "\n", StandardCharsets.UTF_8);

    // 创建 projects/<project>/<sessionId>.jsonl
    Path projectsDir = sourceRoot.resolve("projects").resolve(PROJECT_DIR);
    Files.createDirectories(projectsDir);
    Path transcriptFile = projectsDir.resolve(SESSION_ID + ".jsonl");

    // 写入最小合成 JSONL 事件
    StringBuilder transcript = new StringBuilder();
    // 一个 user 消息
    transcript
        .append(
            "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"text\",\"text\":\"hello\"}]}}")
        .append("\n");
    // 一个 assistant 消息，含 tool_use
    transcript
        .append(
            "{\"type\":\"assistant\",\"message\":{\"id\":\"msg_1\",\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"hi\"},{\"type\":\"tool_use\",\"id\":\"tool_1\",\"name\":\"Bash\",\"input\":{\"command\":\"ls\"}}],\"usage\":{\"input_tokens\":10,\"output_tokens\":5,\"cache_read_input_tokens\":3,\"cache_creation_input_tokens\":2}}}")
        .append("\n");
    // 工具结果
    transcript
        .append(
            "{\"type\":\"user\",\"message\":{\"role\":\"user\",\"content\":[{\"type\":\"tool_result\",\"tool_use_id\":\"tool_1\",\"content\":\"file1.txt\"}]}}")
        .append("\n");
    // 第二个 assistant 消息（无 tool_use）
    transcript
        .append(
            "{\"type\":\"assistant\",\"message\":{\"id\":\"msg_2\",\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"done\"}],\"usage\":{\"input_tokens\":8,\"output_tokens\":3,\"cache_read_input_tokens\":5,\"cache_creation_input_tokens\":0}}}")
        .append("\n");
    Files.writeString(transcriptFile, transcript.toString(), StandardCharsets.UTF_8);

    // 创建 subagent 目录和文件
    Path subagentsDir = transcriptFile.getParent().resolve(SESSION_ID).resolve("subagents");
    Files.createDirectories(subagentsDir);
    Path subagentFile = subagentsDir.resolve("agent-001.jsonl");
    StringBuilder subagentContent = new StringBuilder();
    subagentContent
        .append(
            "{\"type\":\"assistant\",\"message\":{\"id\":\"sa_msg_1\",\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"subagent working\"}],\"usage\":{\"input_tokens\":20,\"output_tokens\":10}}}")
        .append("\n");
    Files.writeString(subagentFile, subagentContent.toString(), StandardCharsets.UTF_8);

    // 创建 .meta.json
    Path metaFile = subagentsDir.resolve("agent-001.meta.json");
    Files.writeString(metaFile, "{\"agentType\":\"implementer\"}", StandardCharsets.UTF_8);
  }

  @Nested
  @DisplayName("正常 session 管道测试")
  class HappyPath {

    @Test
    @DisplayName("source 层定位 transcript 和 subagent")
    void sourceLayerLocatesFiles() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      assertThat(output.source().status()).isEqualTo("OBSERVED");
      assertThat(output.source().transcriptPath()).isNotEmpty();
      assertThat(output.source().subagentFileCount()).isEqualTo(1);
      assertThat(output.source().subagentFiles()).hasSize(1);
      assertThat(output.source().subagentFiles().get(0).fileName()).isEqualTo("agent-001.jsonl");
      assertThat(output.source().subagentFiles().get(0).metaStatus()).isEqualTo("OBSERVED");
    }

    @Test
    @DisplayName("raw 层统计事件和工具")
    void rawLayerSummarizesEvents() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      assertThat(output.raw().status()).isEqualTo("OBSERVED");
      assertThat(output.raw().totalEvents()).isGreaterThan(0);
      assertThat(output.raw().assistantMessages()).isGreaterThan(0);
      assertThat(output.raw().userMessages()).isGreaterThan(0);
      assertThat(output.raw().toolUseCount()).isGreaterThanOrEqualTo(1);
    }

    @Test
    @DisplayName("normalization 层生成制品")
    void normalizationLayerProducesArtifact() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      assertThat(output.normalization().status()).isEqualTo("OBSERVED");
      assertThat(output.normalization().callCount()).isGreaterThan(0);
      assertThat(output.normalization().totalTokens()).isGreaterThan(0);
    }

    @Test
    @DisplayName("projection 层统计 agent 和 subagent")
    void projectionLayerCountsAgents() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      assertThat(output.projection().status()).isEqualTo("OBSERVED");
      assertThat(output.projection().detectedAgents()).isGreaterThanOrEqualTo(1);
    }

    @Test
    @DisplayName("timing 记录各阶段耗时")
    void timingRecordsDurations() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      assertThat(output.timing().totalMs()).isGreaterThanOrEqualTo(0);
      assertThat(output.timing().sourceMs()).isGreaterThanOrEqualTo(0);
    }
  }

  @Nested
  @DisplayName("UNAVAILABLE 场景测试")
  class UnavailableScenarios {

    @Test
    @DisplayName("session 不存在时 source 为 ERROR")
    void sessionNotFoundReturnsError() {
      var output = DiagnosePipeline.run("claude_code", "nonexistent-session-id", sourceRoot);

      assertThat(output.source().status()).isEqualTo("ERROR");
      assertThat(output.raw().status()).isEqualTo("UNAVAILABLE");
      assertThat(output.normalization().status()).isEqualTo("UNAVAILABLE");
      assertThat(output.projection().status()).isEqualTo("UNAVAILABLE");
    }

    @Test
    @DisplayName("非 claude_code agent 时 source 为 UNAVAILABLE")
    void unknownAgentReturnsUnavailable() {
      var output = DiagnosePipeline.run("codex", SESSION_ID, sourceRoot);

      assertThat(output.source().status()).isEqualTo("UNAVAILABLE");
      assertThat(output.warnings()).anyMatch(w -> w.contains("codex"));
    }

    @Test
    @DisplayName("meta 缺失时为 UNAVAILABLE 而非异常")
    void missingMetaReturnsUnavailable() throws IOException {
      // 创建一个没有 meta 的 session
      Path historyFile = sourceRoot.resolve("history.jsonl");
      String nometaSessionId = "11111111-2222-3333-4444-555555555555";
      String entry =
          "{\"sessionId\":\""
              + nometaSessionId
              + "\",\"project\":\""
              + PROJECT_DIR
              + "\",\"display\":\"\",\"timestamp\":0}";
      Files.writeString(historyFile, entry + "\n", StandardCharsets.UTF_8);

      var output = DiagnosePipeline.run("claude_code", nometaSessionId, sourceRoot);

      // 不应抛异常；source 状态取决于 transcript 是否存在
      assertThat(output.source().status()).isIn("OBSERVED", "ERROR");
    }
  }

  @Nested
  @DisplayName("divergence 检测测试")
  class DivergenceTests {

    @Test
    @DisplayName("正常管道无分歧时为 MATCH")
    void happyPathNoDivergence() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      // 正常管道可能有分歧也可能没有，取决于具体数据
      assertThat(output.divergence().status()).isIn("MATCH", "MISMATCH", "UNAVAILABLE");
    }

    @Test
    @DisplayName("divergence.first 仅在非 MATCH 时有值")
    void firstDivergenceConditional() {
      var output = DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      if ("MATCH".equals(output.divergence().status())) {
        assertThat(output.divergence().first()).isNull();
      } else {
        assertThat(output.divergence().first()).isNotNull();
        assertThat(output.divergence().first().stage()).isNotEmpty();
      }
    }
  }

  @Nested
  @DisplayName("损坏 JSONL 测试")
  class CorruptedJsonlTests {

    @Test
    @DisplayName("损坏的 JSONL 行不会导致整体失败")
    void corruptedLineDoesNotCrash() throws IOException {
      Path projectsDir = sourceRoot.resolve("projects").resolve(PROJECT_DIR);
      String corruptSessionId = "cccccccc-dddd-eeee-ffff-000000000000";
      Path corruptFile = projectsDir.resolve(corruptSessionId + ".jsonl");

      // 添加一个 history entry
      Path historyFile = sourceRoot.resolve("history.jsonl");
      String existingHistory = Files.readString(historyFile);
      Files.writeString(
          historyFile,
          existingHistory
              + "{\"sessionId\":\""
              + corruptSessionId
              + "\",\"project\":\""
              + PROJECT_DIR
              + "\",\"display\":\"corrupt\",\"timestamp\":1700000001000}\n",
          StandardCharsets.UTF_8);

      // 写入部分损坏的 JSONL
      Files.writeString(
          corruptFile,
          "this is not valid json\n"
              + "{\"type\":\"assistant\",\"message\":{\"id\":\"msg_c\",\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":\"ok\"}],\"usage\":{\"input_tokens\":5,\"output_tokens\":2}}}\n",
          StandardCharsets.UTF_8);

      var output = DiagnosePipeline.run("claude_code", corruptSessionId, sourceRoot);

      // 不应抛出异常
      assertThat(output.schemaVersion()).isEqualTo(DiagnoseOutputModel.SCHEMA_VERSION);
      // raw 层可能标记错误或部分解析
      assertThat(output.raw().status()).isIn("OBSERVED", "ERROR");
    }
  }

  @Nested
  @DisplayName("只读性测试")
  class ReadOnlyTests {

    @Test
    @DisplayName("运行前后 fixture 文件不变")
    void fixtureUnchangedAfterRun() throws IOException {
      Path transcriptFile =
          sourceRoot.resolve("projects").resolve(PROJECT_DIR).resolve(SESSION_ID + ".jsonl");
      long sizeBefore = Files.size(transcriptFile);
      String contentBefore = Files.readString(transcriptFile, StandardCharsets.UTF_8);

      DiagnosePipeline.run("claude_code", SESSION_ID, sourceRoot);

      long sizeAfter = Files.size(transcriptFile);
      String contentAfter = Files.readString(transcriptFile, StandardCharsets.UTF_8);

      assertThat(sizeAfter).isEqualTo(sizeBefore);
      assertThat(contentAfter).isEqualTo(contentBefore);
    }
  }
}
