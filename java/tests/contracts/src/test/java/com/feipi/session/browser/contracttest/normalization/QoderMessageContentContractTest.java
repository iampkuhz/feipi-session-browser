package com.feipi.session.browser.contracttest.normalization;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.normalization.NormalizationEngine;
import com.feipi.session.browser.source.qoder.QoderSourceAdapter;
import com.feipi.session.browser.source.spi.SourceResult;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

/** 合成 message/role/parts 内容须经真实 Qoder parser 保留到调用与轮次。 */
class QoderMessageContentContractTest {
  @TempDir Path directory;

  @Test
  void messagePartsReachCallsAndRoundsWithoutInventedUsage() throws IOException {
    Path project = directory.resolve("projects/synthetic");
    Files.createDirectories(project);
    Files.writeString(
        project.resolve("message-parts.jsonl"),
        """
        {"type":"message","role":"user","parts":[{"type":"text","text":"Synthetic Qoder parts user"}],"timestamp":"2026-11-05T08:00:01Z"}
        {"type":"message","role":"assistant","parts":[{"type":"text","text":"Synthetic Qoder parts answer"}],"timestamp":"2026-11-05T08:00:02Z"}
        {"type":"message","message":{"role":"user","parts":[{"type":"text","text":"Synthetic envelope user"}]},"timestamp":"2026-11-05T08:00:03Z"}
        {"type":"message","message":{"role":"assistant","parts":[{"type":"text","text":"Synthetic envelope answer"}]} ,"timestamp":"2026-11-05T08:00:04Z"}
        """);
    var adapter = new QoderSourceAdapter();
    var candidate = adapter.discover(directory).orderedItems().getFirst();
    var parsed = (SourceResult.Success) adapter.parse(candidate, null);
    var artifact =
        new NormalizationEngine()
            .normalize(NormalizedAgent.QODER, parsed.records(), parsed.diagnostics(), List.of());

    assertThat(artifact.calls()).hasSize(2);
    assertThat(artifact.session())
        .containsEntry("userMessageCount", 2L)
        .containsEntry("assistantMessageCount", 2L)
        .containsEntry("totalTokens", 0L);
    assertThat(artifact.calls().get(0).sourceUnits())
        .extracting(unit -> unit.get("text"))
        .contains("Synthetic Qoder parts user", "Synthetic Qoder parts answer");
    assertThat(artifact.calls().get(1).sourceUnits())
        .extracting(unit -> unit.get("text"))
        .contains("Synthetic envelope user", "Synthetic envelope answer");
    assertThat(SessionDetailAssembler.buildRounds(artifact.calls(), artifact.toolExecutions()))
        .hasSize(2);
  }
}
