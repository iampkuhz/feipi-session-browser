package com.feipi.session.browser.contracttest.sample;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.scan.artifact.CanonicalJsonWriter;
import com.feipi.session.browser.source.claude.ClaudeSourceAdapter;
import com.feipi.session.browser.source.codex.CodexSourceAdapter;
import com.feipi.session.browser.source.spi.Candidate;
import com.feipi.session.browser.source.spi.SourceAdapter;
import com.feipi.session.browser.source.spi.SourceFingerprint;
import com.feipi.session.browser.source.spi.SourceId;
import com.feipi.session.browser.source.spi.SourceResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/** 使用最小脱敏 synthetic fixture 验证真实 source-to-canonical 管线。 */
class SessionSampleIntegrationTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Path PROJECT_ROOT = resolveProjectRoot();
  private static final Path SAMPLES_ROOT =
      PROJECT_ROOT.resolve("tests/fixtures/session_samples/synthetic");

  @Test
  @Tag("sample-integration")
  void claudeSyntheticContractIsCanonicalAndDeterministic() throws Exception {
    Path input = SAMPLES_ROOT.resolve("claude-code/synthetic-claude-session.jsonl");
    verifyFixture(
        input,
        new ClaudeSourceAdapter(),
        NormalizedAgent.CLAUDE_CODE,
        SourceId.CLAUDE_CODE,
        List.of(sourceFile(SourceFileRole.MAIN_SESSION, input)));
  }

  @Test
  @Tag("sample-integration")
  void codexSyntheticParentChildContractIsCanonicalAndDeterministic() throws Exception {
    Path sessionDir = SAMPLES_ROOT.resolve("codex/synthetic-codex-session");
    Path parent = sessionDir.resolve("synthetic-codex-parent.jsonl");
    Path child = sessionDir.resolve("rollout-synthetic-child.jsonl");
    JsonNode childMetadata = MAPPER.readTree(Files.readAllLines(child).get(0)).path("payload");
    assertThat(childMetadata.path("id").asText()).isEqualTo("synthetic-codex-child");
    assertThat(
            childMetadata
                .path("source")
                .path("subagent")
                .path("thread_spawn")
                .path("parent_thread_id")
                .asText())
        .isEqualTo("synthetic-codex-parent");
    assertThat(parseFixture(child, new CodexSourceAdapter(), SourceId.CODEX).records())
        .isNotEmpty();

    List<NormalizedSourceFile> sourceFiles =
        List.of(
            sourceFile(SourceFileRole.CODEX_ROLLOUT, parent),
            new NormalizedSourceFile(
                SourceFileRole.SUBAGENT_SESSION,
                relative(child),
                Optional.of("synthetic-codex-child"),
                Optional.of("synthetic-spawn-call")));

    NormalizedSessionArtifact artifact =
        verifyFixture(
            parent, new CodexSourceAdapter(), NormalizedAgent.CODEX, SourceId.CODEX, sourceFiles);

    assertThat(artifact.sourceFiles().get(1).subagentId()).contains("synthetic-codex-child");
    assertThat(artifact.sourceFiles().get(1).parentToolUseId()).contains("synthetic-spawn-call");
  }

  private static NormalizedSessionArtifact verifyFixture(
      Path input,
      SourceAdapter adapter,
      NormalizedAgent agent,
      SourceId sourceId,
      List<NormalizedSourceFile> sourceFiles)
      throws Exception {
    assertThat(input).isRegularFile();
    assertThat(input.toString()).contains("synthetic");
    SourceResult.Success success = parseFixture(input, adapter, sourceId);

    NormalizedSessionArtifact artifact =
        new NormalizationEngine()
            .normalize(agent, success.records(), success.diagnostics(), sourceFiles);
    assertThat(artifact.schemaVersion()).isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(artifact.agent()).isEqualTo(agent);
    assertThat(artifact.calls()).isNotEmpty();
    assertThat(artifact.toolExecutions()).isNotEmpty();
    assertThat(artifact.sourceFiles()).allMatch(file -> !file.path().isAbsolute());

    CanonicalJsonWriter writer = new CanonicalJsonWriter();
    byte[] first = writer.serialize(artifact);
    byte[] second = writer.serialize(artifact);
    assertThat(second).isEqualTo(first);
    JsonNode canonical = MAPPER.readTree(first);
    assertThat(canonical.path("schema_version").asText())
        .isEqualTo(NormalizedConstants.SCHEMA_VERSION);
    assertThat(canonical.path("agent").asText()).isEqualTo(agent.getValue());
    assertThat(canonical.path("source").path("files").isArray()).isTrue();
    assertThat(canonical.path("calls").isArray()).isTrue();
    assertThat(canonical.path("tool_executions").isArray()).isTrue();
    assertThat(canonical.path("diagnostics").isArray()).isTrue();
    return artifact;
  }

  private static SourceResult.Success parseFixture(
      Path input, SourceAdapter adapter, SourceId sourceId) throws Exception {
    // SourceAdapter 读取实际文件，因此直接传入动态解析出的仓库内绝对路径；不要依赖进程工作目录。
    SourceFingerprint fingerprint =
        new SourceFingerprint(
            input.toAbsolutePath().normalize().toString(),
            sourceId,
            Files.size(input),
            Files.getLastModifiedTime(input).toMillis(),
            Optional.empty(),
            Optional.empty());
    SourceResult result =
        adapter.parse(
            new Candidate(fingerprint, input.getFileName().toString(), "", Map.of()), null);
    assertThat(result).isInstanceOf(SourceResult.Success.class);
    return (SourceResult.Success) result;
  }

  private static NormalizedSourceFile sourceFile(SourceFileRole role, Path path) {
    return new NormalizedSourceFile(role, relative(path), Optional.empty(), Optional.empty());
  }

  private static Path relative(Path path) {
    return PROJECT_ROOT.relativize(path.toAbsolutePath().normalize());
  }

  private static Path resolveProjectRoot() {
    Path current = Path.of(System.getProperty("user.dir")).toAbsolutePath();
    while (current != null) {
      if (Files.isDirectory(current.resolve("tests/fixtures/session_samples"))) {
        return current;
      }
      current = current.getParent();
    }
    throw new IllegalStateException("repository root with synthetic session fixtures not found");
  }
}
