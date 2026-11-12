package com.feipi.session.browser.web.api;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.application.sessiondetail.SessionContentReader;
import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.ByteRange;
import com.feipi.session.browser.domain.normalized.NormalizedAgent;
import com.feipi.session.browser.domain.normalized.NormalizedCall;
import com.feipi.session.browser.domain.normalized.NormalizedCallRequest;
import com.feipi.session.browser.domain.normalized.NormalizedCallResponse;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedConstants;
import com.feipi.session.browser.domain.normalized.NormalizedContentHeader;
import com.feipi.session.browser.domain.normalized.NormalizedSessionContent;
import com.feipi.session.browser.domain.normalized.NormalizedSessionMetadata;
import com.feipi.session.browser.domain.normalized.NormalizedSourceFile;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.SourceFileRole;
import com.feipi.session.browser.domain.normalized.SourceUnitCatalogEntry;
import com.feipi.session.browser.domain.normalized.SourceUnitDirection;
import com.feipi.session.browser.domain.normalized.SourceUnitRefRange;
import com.feipi.session.browser.query.api.PayloadVisibility;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/** 合成目录引用覆盖首屏摘要、源时间和跨轮消费工具结果；不读取本机原始会话。 */
class SessionTraceEvidenceTest {
  @ParameterizedTest
  @ValueSource(strings = {"tool_result", "function_call_output", "custom_tool_call_output"})
  void catalogOnlyMessagesAndCommandsStayInTheirDeclaringRound(String resultType) throws Exception {
    var content = content(resultType);
    var rows =
        SessionContentProjection.rounds(
            SessionDetailParityAnalyzerTest.healthDetail(false, 0), content);
    assertThat(rows).hasSize(4);
    assertThat(rows.get(0).parity())
        .containsEntry("summary", "检查合成模块")
        .containsEntry("summaryRole", "user")
        .containsEntry("time", "09:02:03");
    assertThat(rows.get(1).parity().get("summary").toString())
        .contains("exec × 2", "printf beta")
        .doesNotContain("alpha", "历史工具输出", "子任务文本", "检查合成模块");
    assertThat(rows.get(1).callCount()).isEqualTo(2);
    assertThat(rows.get(1).toolCallCount()).isEqualTo(2);
    assertThat(rows.get(1).parity()).containsEntry("time", "09:03:04");
    assertThat(rows.get(2).parity())
        .containsEntry("summary", "合成验证完成")
        .containsEntry("summaryRole", "assistant")
        .containsEntry("time", "09:04:05");
    assertThat(rows.get(3).parity()).containsEntry("summary", "").containsEntry("time", "");

    var reader = new SessionContentReader(content, 0);
    String response =
        reader.payload("main:resp:a", PayloadVisibility.STANDARD).orElseThrow().content();
    assertThat(response).contains("alpha", "工具指令").doesNotContain("beta", "child", "历史工具输出");
    assertThat(reader.payload("main:resp:b", PayloadVisibility.STANDARD).orElseThrow().content())
        .contains("beta")
        .doesNotContain("alpha", "child", "历史工具输出");
    assertThat(reader.payload("tool:input:ta", PayloadVisibility.STANDARD).orElseThrow().content())
        .contains("alpha")
        .doesNotContain("beta");
    assertThat(reader.payload("tool:result:ta", PayloadVisibility.STANDARD).orElseThrow().content())
        .isEqualTo("历史工具输出");
    try (var export = reader.exportPayloads()) {
      assertThat(
              export.payload("tool:result:ta", PayloadVisibility.STANDARD).orElseThrow().content())
          .isEqualTo("历史工具输出");
    }
    var previews = SessionContentPreviews.read(content);
    assertThat(reader.payload("main:req:b", PayloadVisibility.STANDARD).orElseThrow().content())
        .contains("检查合成模块", "历史工具输出");
    assertThat(previews.toolInputs(reader.findCall("b").orElseThrow()))
        .containsOnlyKeys("tb")
        .containsEntry("tb", "printf beta");
  }

  @Test
  void materializedDetailsUseTheSameCatalogEvidenceAndDoNotBorrowHistoricalUserText()
      throws Exception {
    var artifact = content().toArtifact();
    var rounds =
        com.feipi.session.browser.application.sessiondetail.SessionDetailAssembler.buildRounds(
            artifact.calls(), artifact.toolExecutions());
    var row = SessionDetailParityAnalyzerTest.healthDetail(false, 0).sessionRow();
    var detail =
        new com.feipi.session.browser.application.sessiondetail.SessionDetail(
            row, rounds, List.of(), PayloadVisibility.STANDARD, "", "", "synthetic");
    var parity = SessionDetailParityAnalyzer.analyze(detail, artifact, false);
    assertThat(parity.round(1).toMap())
        .containsEntry("summary", "检查合成模块")
        .containsEntry("time", "09:02:03");
    assertThat(parity.round(2).toMap().get("summary").toString())
        .contains("printf beta")
        .doesNotContain("alpha", "检查合成模块", "历史工具输出");
    assertThat(parity.round(2).toMap()).containsEntry("time", "09:03:04");
    var rows = RoundIndexProjection.pageDtos(detail, artifact, parity);
    assertThat(rows.getFirst().parity()).containsEntry("summary", "检查合成模块");
    assertThat(rows.get(1).parity().get("summary").toString())
        .contains("printf beta")
        .doesNotContain("alpha", "检查合成模块");
  }

  @Test
  void frozenSourcePathIsAvailableOnlyForLocalDetailsAndUnmeasuredBudgetIsNotZero() {
    var detail = SessionDetailParityAnalyzerTest.healthDetail(false, 0);
    var local = SessionDetailParityAnalyzer.analyze(detail, null, content(), true);
    assertThat(local.meta).containsEntry("sessionFilePath", "/synthetic/trace.jsonl");
    assertThat(local.diagnostics)
        .containsEntry("contextSegmentsAvailable", false)
        .containsEntry("issuesAvailable", false)
        .containsEntry("toolImpactAvailable", true);
    assertThat(SessionDetailParityAnalyzer.analyze(detail, null, content(), false).meta)
        .containsEntry("sessionFilePath", "");
  }

  static NormalizedSessionContent content() {
    return content("function_call_output");
  }

  private static NormalizedSessionContent content(String resultType) {
    var catalog =
        Map.of(
            "user", entry("user", "input_text", true, "检查合成模块", "", Map.of("role", "user")),
            "ta",
                entry(
                    "ta",
                    "function_call",
                    false,
                    "",
                    "2026-01-01T01:02:03Z",
                    command("ta", "alpha")),
            "tb",
                entry(
                    "tb",
                    "function_call",
                    false,
                    "",
                    "2026-01-01T01:03:04Z",
                    command("tb", "beta")),
            "tc", entry("tc", "function_call", false, "", "", command("tc", "child")),
            "result",
                entry(
                    "result",
                    resultType,
                    true,
                    "",
                    "",
                    Map.of("type", resultType, "call_id", "ta", "output", "历史工具输出")),
            "text",
                entry(
                    "text",
                    "output_text",
                    false,
                    "合成验证完成",
                    "2026-01-01T01:04:05Z",
                    Map.of("role", "assistant")));
    var calls =
        List.of(
            call(
                "a",
                1,
                List.of("ta"),
                List.of(),
                List.of(
                    new SourceUnitRefRange(
                        Optional.of("messages"), 0, 1, List.of(), Optional.of("user")),
                    range("ta", "assistant")),
                false),
            call(
                "b",
                2,
                List.of("tb"),
                List.of("ta"),
                List.of(range("user", "user"), range("result", "user"), range("tb", "assistant")),
                false),
            call("c", 3, List.of(), List.of(), List.of(range("text", "assistant")), false),
            call("d", 4, List.of(), List.of(), List.of(), false),
            call("child", 5, List.of("tc"), List.of(), List.of(range("tc", "assistant")), true));
    return NormalizedSessionContent.fromLists(
        new NormalizedContentHeader(
            NormalizedConstants.SCHEMA_VERSION,
            NormalizedAgent.CODEX,
            new NormalizedSessionMetadata(Map.of()),
            Map.of(
                "calls",
                5L,
                "toolExecutions",
                3L,
                "diagnostics",
                0L,
                "sourceFiles",
                1L,
                "sourceUnitCatalog",
                6L,
                "sourceUnitSequenceEntries",
                1L)),
        List.of(
            new NormalizedSourceFile(
                SourceFileRole.CODEX_ROLLOUT,
                java.nio.file.Path.of("/synthetic/trace.jsonl"),
                Optional.empty(),
                Optional.empty())),
        calls,
        List.of(tool("ta", "a", false), tool("tb", "b", false), tool("tc", "child", true)),
        List.of(),
        catalog,
        Map.of("messages", List.of("user")));
  }

  private static Map<String, Object> command(String id, String text) {
    return Map.of(
        "type",
        "function_call",
        "call_id",
        id,
        "name",
        "exec",
        "arguments",
        "{\"command\":\"printf " + text + "\"}");
  }

  private static SourceUnitRefRange range(String key, String role) {
    return new SourceUnitRefRange(Optional.empty(), 0, 1, List.of(key), Optional.of(role));
  }

  private static SourceUnitCatalogEntry entry(
      String key,
      String type,
      boolean request,
      String text,
      String timestamp,
      Map<String, Object> payload) {
    return new SourceUnitCatalogEntry(
        key,
        "/synthetic/trace.jsonl",
        "fixture:" + key,
        type,
        "visible",
        request ? SourceUnitDirection.REQUEST : SourceUnitDirection.RESPONSE,
        0,
        0,
        ByteRange.empty(),
        "synthetic-hash",
        timestamp.isEmpty() ? Optional.empty() : Optional.of(timestamp),
        Optional.empty(),
        50,
        Optional.empty(),
        text.isEmpty() ? Optional.empty() : Optional.of(text),
        payload,
        Optional.empty(),
        Optional.empty(),
        List.of());
  }

  private static NormalizedCall call(
      String id,
      int index,
      List<String> declarations,
      List<String> consumed,
      List<SourceUnitRefRange> ranges,
      boolean child) {
    return new NormalizedCall(
        id,
        index,
        "C" + index,
        child ? CallScope.SUBAGENT : CallScope.MAIN,
        child ? Optional.of("b") : Optional.empty(),
        Optional.empty(),
        Optional.of(child ? "turn-b" : "turn-" + id),
        "synthetic-model",
        Optional.empty(),
        new NormalizedCallUsage(1, 0, 0, 1, 2),
        new NormalizedCallRequest(consumed),
        new NormalizedCallResponse(declarations),
        ranges,
        List.of(),
        Map.of(),
        Map.of(),
        child ? Optional.of("synthetic-child") : Optional.empty(),
        Optional.empty());
  }

  private static NormalizedToolExecution tool(String id, String owner, boolean child) {
    return new NormalizedToolExecution(
        id,
        "exec",
        child ? CallScope.SUBAGENT : CallScope.MAIN,
        owner,
        id.equals("ta") ? Optional.of("b") : Optional.empty(),
        Optional.empty(),
        Optional.empty(),
        0,
        List.of(),
        child ? Optional.of("synthetic-child") : Optional.empty());
  }
}
