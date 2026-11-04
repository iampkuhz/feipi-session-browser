package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionDetail;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedSessionArtifact;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.index.store.sqlite.row.SessionRow;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 上传的溯源字段不具有本机文件读取权限。 */
class ImportedSessionParityTest {

  @TempDir Path tempDir;

  @Test
  void artifactOnlyBranchNeverReadsForgedSourcePathsOrReadableNeighbors() throws Exception {
    Path parent = tempDir.resolve("parent.jsonl");
    Path neighbor = tempDir.resolve("child.jsonl");
    Files.writeString(
        parent,
        """
        {"type":"session_meta","payload":{"id":"parent-session"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"foreign-tool","name":"exec_command"}}
        """);
    Files.writeString(
        neighbor,
        """
        {"type":"session_meta","payload":{"id":"child","parent_thread_id":"parent-session"}}
        {"type":"response_item","payload":{"type":"function_call","call_id":"neighbor-tool","name":"exec_command"}}
        """);
    var artifact =
        new NormalizedSessionArtifact(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            List.of(
                new NormalizedSourceFile(
                    SourceFileRole.TRANSCRIPT, parent, Optional.empty(), Optional.empty())),
            Map.of(),
            List.of(),
            List.of(),
            List.of(),
            Map.of(),
            Map.of());
    for (String forgedRowPath : List.of(parent.toString(), "")) {
      SessionRow row =
          new SessionRow(
              "codex:parent-session",
              "codex",
              "parent-session",
              "Synthetic",
              "/synthetic",
              "synthetic",
              "/synthetic",
              "2026-01-01T00:00:00Z",
              "2026-01-01T00:00:01Z",
              1,
              0,
              0,
              "test",
              "main",
              "codex",
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              0,
              forgedRowPath);
      var detail =
          new SessionDetail(
              row,
              List.of(),
              List.of(),
              PayloadVisibility.STANDARD,
              "forged-artifact-present",
              NormalizedConstants.SCHEMA_VERSION,
              "synthetic");
      var personal = SessionDetailParityAnalyzer.analyze(detail, artifact);
      // 即使个人详情允许源文件补充，空的冻结制品也不能被后来出现的邻居注入工具。
      assertThat(personal.metrics.get("toolCalls")).isEqualTo(0L);
      assertThat(personal.metrics.get("subagentRuns")).isEqualTo(0L);
      if (!forgedRowPath.isBlank()) {
        var withoutArtifact = SessionDetailParityAnalyzer.analyze(detail);
        // 控制分支确实可读取这两个可读源文件；导入分支不能靠测试路径不可读而通过。
        assertThat((List<?>) withoutArtifact.diagnostics.get("agents")).hasSize(2);
        var rawImpact = (Map<?, ?>) withoutArtifact.diagnostics.get("toolImpact");
        assertThat(rawImpact.get("distinctTools")).isEqualTo(1);
      }
      var imported = SessionDetailParityAnalyzer.analyze(detail, artifact, false);
      assertThat(imported.metrics.get("toolCalls")).isEqualTo(0L);
      assertThat(imported.metrics.get("subagentRuns")).isEqualTo(0L);
      assertThat(imported.meta.get("sessionFilePath")).isEqualTo("");
      assertThat(imported.diagnostics.toString())
          .doesNotContain(tempDir.toString(), "foreign-tool", "neighbor-tool");
    }
  }
}
