package com.feipi.session.browser.contracttest.shadow;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.source.SourceRecord;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.json.JsonSourceRecordMapper;
import com.feipi.session.browser.source.json.JsonlReader;
import com.feipi.session.browser.source.json.JsonlReaderResult;
import com.feipi.session.browser.source.spi.SourceDiagnostic;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * Golden fixture shadow 测试。
 *
 * <p>验证 golden fixtures 可以通过 scan (JSONL 读取 + 事件映射) 和 normalize 管线， 并使用 {@link ShadowComparator}
 * 对比两次独立运行结果以验证确定性。
 *
 * <p>测试链路：JSONL fixture --[JsonlReader]--> JsonNode events --[JsonSourceRecordMapper]-->
 * SourceRecord list --[NormalizationEngine]--> NormalizedSessionArtifact --[ShadowComparator]-->
 * ShadowComparisonResult
 */
@DisplayName("Golden fixture shadow 测试")
class ShadowFixtureTest {

  private static final NormalizationEngine ENGINE = new NormalizationEngine();
  private static final JsonlReader READER = new JsonlReader();

  /**
   * 从 classpath 加载 golden fixture 到临时文件。
   *
   * <p>JsonlReader 需要真实文件路径（用于 mtime/size 快照）， 因此先将 classpath 资源复制到临时文件。
   */
  private Path copyFixtureToTemp(String resourcePath) throws IOException {
    Path tempFile = Files.createTempFile("golden-fixture-", ".jsonl");
    tempFile.toFile().deleteOnExit();
    try (InputStream is = getClass().getResourceAsStream(resourcePath)) {
      assertThat(is).as("Fixture resource not found: %s", resourcePath).isNotNull();
      Files.copy(is, tempFile, StandardCopyOption.REPLACE_EXISTING);
    }
    return tempFile;
  }

  /**
   * 简单事件类型提取器：从 JSON 事件的 type 字段提取事件类型。
   *
   * <p>统一将 user/assistant/tool_result/tool_call 映射为归一化引擎可识别的事件类型。
   */
  private static String extractEventType(JsonNode event) {
    JsonNode typeNode = event.get("type");
    if (typeNode != null && typeNode.isTextual()) {
      return typeNode.asText();
    }
    return "unknown";
  }

  /**
   * 将 JSONL fixture 文件解析为 SourceRecord 列表。
   *
   * <p>模拟 scan 阶段的 parse 步骤：先通过 JsonlReader 读取 JSON 事件， 再通过 JsonSourceRecordMapper 映射为源中性记录。
   */
  private ParseResult parseFixture(Path fixturePath, String locator) throws IOException {
    JsonlReaderResult readerResult = READER.read(fixturePath);
    List<SourceRecord> records = new ArrayList<>();
    for (int i = 0; i < readerResult.events().size(); i++) {
      JsonNode event = readerResult.events().get(i);
      String eventType = extractEventType(event);
      records.add(JsonSourceRecordMapper.toSourceRecord(locator, i, event, eventType));
    }
    return new ParseResult(records, readerResult.diagnostics());
  }

  /** 执行完整的 scan-to-normalize 管线。 */
  private NormalizedSessionArtifact runPipeline(
      NormalizedAgent agent, List<SourceRecord> records, List<SourceDiagnostic> diagnostics) {
    NormalizedSourceFile sourceFile =
        new NormalizedSourceFile(
            SourceFileRole.TRANSCRIPT,
            Path.of("golden-fixtures/" + agent.getValue() + "/minimal-session.jsonl"),
            Optional.empty(),
            Optional.empty());
    return ENGINE.normalize(agent, records, diagnostics, List.of(sourceFile));
  }

  record ParseResult(List<SourceRecord> records, List<SourceDiagnostic> diagnostics) {}

  @Nested
  @DisplayName("Claude Code golden fixture")
  class ClaudeCodeFixture {

    @Test
    @DisplayName("scan -> normalize 链路产生有效制品")
    void scanNormalizeProducesValidArtifact() throws IOException {
      Path fixturePath = copyFixtureToTemp("/golden-fixtures/claude-code/minimal-session.jsonl");
      String locator = "golden-fixtures/claude-code/minimal-session.jsonl";

      ParseResult parseResult = parseFixture(fixturePath, locator);
      assertThat(parseResult.records()).isNotEmpty();

      NormalizedSessionArtifact artifact =
          runPipeline(
              NormalizedAgent.CLAUDE_CODE, parseResult.records(), parseResult.diagnostics());

      assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
      assertThat(artifact.agent()).isEqualTo(NormalizedAgent.CLAUDE_CODE);
    }

    @Test
    @DisplayName("两次运行结果通过 shadow 对比验证确定性")
    void determinismViaShadowCompare() throws IOException {
      Path fixturePath = copyFixtureToTemp("/golden-fixtures/claude-code/minimal-session.jsonl");
      String locator = "golden-fixtures/claude-code/minimal-session.jsonl";

      ParseResult parseResult = parseFixture(fixturePath, locator);

      NormalizedSessionArtifact baseline =
          runPipeline(
              NormalizedAgent.CLAUDE_CODE, parseResult.records(), parseResult.diagnostics());
      NormalizedSessionArtifact candidate =
          runPipeline(
              NormalizedAgent.CLAUDE_CODE, parseResult.records(), parseResult.diagnostics());

      ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);

      assertThat(result.category())
          .as("两次运行应完全一致: %s", result.differences())
          .isEqualTo(ShadowDiffCategory.EXACT_MATCH);
      assertThat(result.isCutoverSafe()).isTrue();
    }
  }

  @Nested
  @DisplayName("Codex golden fixture")
  class CodexFixture {

    @Test
    @DisplayName("scan -> normalize 链路产生有效制品")
    void scanNormalizeProducesValidArtifact() throws IOException {
      Path fixturePath = copyFixtureToTemp("/golden-fixtures/codex/minimal-session.jsonl");
      String locator = "golden-fixtures/codex/minimal-session.jsonl";

      ParseResult parseResult = parseFixture(fixturePath, locator);
      assertThat(parseResult.records()).isNotEmpty();

      NormalizedSessionArtifact artifact =
          runPipeline(NormalizedAgent.CODEX, parseResult.records(), parseResult.diagnostics());

      assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
      assertThat(artifact.agent()).isEqualTo(NormalizedAgent.CODEX);
    }

    @Test
    @DisplayName("两次运行结果通过 shadow 对比验证确定性")
    void determinismViaShadowCompare() throws IOException {
      Path fixturePath = copyFixtureToTemp("/golden-fixtures/codex/minimal-session.jsonl");
      String locator = "golden-fixtures/codex/minimal-session.jsonl";

      ParseResult parseResult = parseFixture(fixturePath, locator);

      NormalizedSessionArtifact baseline =
          runPipeline(NormalizedAgent.CODEX, parseResult.records(), parseResult.diagnostics());
      NormalizedSessionArtifact candidate =
          runPipeline(NormalizedAgent.CODEX, parseResult.records(), parseResult.diagnostics());

      ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);

      assertThat(result.category())
          .as("两次运行应完全一致: %s", result.differences())
          .isEqualTo(ShadowDiffCategory.EXACT_MATCH);
    }
  }

  @Nested
  @DisplayName("Qoder golden fixture")
  class QoderFixture {

    @Test
    @DisplayName("scan -> normalize 链路产生有效制品")
    void scanNormalizeProducesValidArtifact() throws IOException {
      Path fixturePath = copyFixtureToTemp("/golden-fixtures/qoder/minimal-session.jsonl");
      String locator = "golden-fixtures/qoder/minimal-session.jsonl";

      ParseResult parseResult = parseFixture(fixturePath, locator);
      assertThat(parseResult.records()).isNotEmpty();

      NormalizedSessionArtifact artifact =
          runPipeline(NormalizedAgent.QODER, parseResult.records(), parseResult.diagnostics());

      assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
      assertThat(artifact.agent()).isEqualTo(NormalizedAgent.QODER);
    }

    @Test
    @DisplayName("两次运行结果通过 shadow 对比验证确定性")
    void determinismViaShadowCompare() throws IOException {
      Path fixturePath = copyFixtureToTemp("/golden-fixtures/qoder/minimal-session.jsonl");
      String locator = "golden-fixtures/qoder/minimal-session.jsonl";

      ParseResult parseResult = parseFixture(fixturePath, locator);

      NormalizedSessionArtifact baseline =
          runPipeline(NormalizedAgent.QODER, parseResult.records(), parseResult.diagnostics());
      NormalizedSessionArtifact candidate =
          runPipeline(NormalizedAgent.QODER, parseResult.records(), parseResult.diagnostics());

      ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);

      assertThat(result.category())
          .as("两次运行应完全一致: %s", result.differences())
          .isEqualTo(ShadowDiffCategory.EXACT_MATCH);
    }
  }

  @Nested
  @DisplayName("Shadow comparator 差异分类")
  class ShadowComparatorClassification {

    @Test
    @DisplayName("不同 agent 的制品归类为 INCOMPARABLE")
    void differentAgentsAreIncomparable() {
      NormalizedSessionArtifact baseline =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());
      NormalizedSessionArtifact candidate =
          ENGINE.normalize(NormalizedAgent.CODEX, List.of(), List.of(), List.of());

      ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);

      assertThat(result.category()).isEqualTo(ShadowDiffCategory.INCOMPARABLE);
      assertThat(result.isCutoverSafe()).isFalse();
    }

    @Test
    @DisplayName("空事件列表产生 EXACT_MATCH")
    void emptyEventsExactMatch() {
      NormalizedSessionArtifact baseline =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());
      NormalizedSessionArtifact candidate =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());

      ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);

      assertThat(result.category()).isEqualTo(ShadowDiffCategory.EXACT_MATCH);
      assertThat(result.isCutoverSafe()).isTrue();
    }

    @Test
    @DisplayName("null 制品归类为 INCOMPARABLE")
    void nullArtifactIsIncomparable() {
      NormalizedSessionArtifact baseline =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(), List.of(), List.of());

      assertThat(ShadowComparator.compare(null, baseline).category())
          .isEqualTo(ShadowDiffCategory.INCOMPARABLE);
      assertThat(ShadowComparator.compare(baseline, null).category())
          .isEqualTo(ShadowDiffCategory.INCOMPARABLE);
    }

    @Test
    @DisplayName("不同事件数量产生 BREAKING_DIFFERENCE")
    void differentEventCountsProduceBreakingDifference() {
      SourceRecord record1 = SourceRecord.of("loc#e0", 0, "assistant");
      SourceRecord record2 = SourceRecord.of("loc#e1", 1, "assistant");

      NormalizedSessionArtifact baseline =
          ENGINE.normalize(NormalizedAgent.CLAUDE_CODE, List.of(record1), List.of(), List.of());
      NormalizedSessionArtifact candidate =
          ENGINE.normalize(
              NormalizedAgent.CLAUDE_CODE, List.of(record1, record2), List.of(), List.of());

      ShadowComparisonResult result = ShadowComparator.compare(baseline, candidate);

      assertThat(result.category()).isEqualTo(ShadowDiffCategory.BREAKING_DIFFERENCE);
      assertThat(result.isCutoverSafe()).isFalse();
    }
  }
}
