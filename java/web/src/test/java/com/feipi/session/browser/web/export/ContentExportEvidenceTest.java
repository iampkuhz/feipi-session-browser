package com.feipi.session.browser.web.export;

import static org.assertj.core.api.Assertions.assertThat;

import com.feipi.session.browser.domain.enums.CallScope;
import com.feipi.session.browser.domain.normalized.NormalizedCallUsage;
import com.feipi.session.browser.domain.normalized.NormalizedContentUnit;
import com.feipi.session.browser.domain.normalized.NormalizedToolExecution;
import com.feipi.session.browser.domain.normalized.TokenProvenance;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/** 离线导出必须保留公开关系和已存储的计量精度。 */
class ContentExportEvidenceTest {
  @Test
  void scopeParentSubagentAndToolOwnersRemainDistinctAndPayloadsHaveIdentity() throws Exception {
    var main =
        ContentExportReplayTest.call(
            0, CallScope.MAIN, List.of(), Map.of(), NormalizedCallUsage.empty());
    var child =
        ContentExportReplayTest.call(
            1, CallScope.SUBAGENT, List.of(), Map.of(), NormalizedCallUsage.empty());
    var tool =
        new NormalizedToolExecution(
            "tool-1",
            "shell",
            CallScope.SUBAGENT,
            "call-1",
            Optional.of("call-0"),
            Optional.empty(),
            Optional.empty(),
            0,
            List.of(),
            Optional.of("agent-child"));
    var content =
        new ContentExportReplayTest.CountingContent(
            List.of(
                ContentExportReplayTest.unit(0, List.of(main), List.of(), Map.of(), List.of()),
                ContentExportReplayTest.unit(1, List.of(child), List.of(), Map.of(), List.of()),
                ContentExportReplayTest.unit(2, List.of(), List.of(tool), Map.of(), List.of())),
            2,
            1,
            0,
            0);
    String html = ContentExportReplayTest.export(content);
    assertThat(html)
        .contains(
            "main:req:call-0",
            "main:resp:call-0",
            "sa:req:call-1",
            "sa:resp:call-1",
            "tool:input:tool-1",
            "tool:result:tool-1",
            "parent-tool",
            "agent-child",
            "delegate");
    // 关系字段用于区分归属语义，不能仅凭两个调用身份都出现在正文中判定保真。
    assertThat(html)
        .contains(
            "scope",
            "main",
            "subagent",
            "parentCallId",
            "parentToolCallId",
            "declaredByCallId",
            "resultConsumedByCallId",
            "subagentId");
    assertThat(html).doesNotContain("completed", "succeeded");
  }

  @Test
  void unknownUnavailableEstimatedAndProviderReportedZeroKeepDifferentPrecision() throws Exception {
    var states = List.of("unknown", "unavailable", "estimated", "provider_reported");
    var units = new java.util.ArrayList<NormalizedContentUnit>();
    for (int i = 0; i < states.size(); i++) {
      var provenance =
          new TokenProvenance(
              states.get(i),
              states.get(i),
              states.get(i),
              states.get(i),
              i == 2 ? "synthetic-estimator" : "",
              i == 2 ? 1 : 0,
              i == 1 ? 1 : 0,
              i == 0 ? 1 : 0);
      var call =
          ContentExportReplayTest.call(
              i, CallScope.MAIN, List.of(), provenance.toMetadata(), NormalizedCallUsage.empty());
      units.add(ContentExportReplayTest.unit(i, List.of(call), List.of(), Map.of(), List.of()));
    }
    String html =
        ContentExportReplayTest.export(
            new ContentExportReplayTest.CountingContent(units, 4, 0, 0, 0));
    var summaries =
        Pattern.compile("<summary>(.*?)</summary>", Pattern.DOTALL)
            .matcher(html)
            .results()
            .map(match -> match.group(1))
            .toList();
    assertThat(summaries).hasSize(4);
    assertThat(summaries.get(0)).contains("call-0", "N/A", "unknown").doesNotContain("tokens 0");
    assertThat(summaries.get(1))
        .contains("call-1", "N/A", "unavailable")
        .doesNotContain("tokens 0");
    assertThat(summaries.get(2)).contains("call-2", "0", "Estimated");
    assertThat(summaries.get(3)).contains("call-3", "tokens 0", "provider_reported");
    assertThat(html).contains("synthetic-estimator", "Partial");
    assertThat(html).doesNotContain("Total tokens: 0</p>");
  }

  @Test
  void mixedPrecisionWithoutCoverageFlagsNeverBecomesProviderReported() throws Exception {
    var precision =
        Map.<String, Object>of(
            "freshInputTokenPrecision",
            "mixed",
            "cacheReadTokenPrecision",
            "mixed",
            "cacheWriteTokenPrecision",
            "mixed",
            "outputTokenPrecision",
            "mixed");
    var call =
        ContentExportReplayTest.call(
            0, CallScope.MAIN, List.of(), precision, NormalizedCallUsage.empty());
    String html =
        ContentExportReplayTest.export(
            new ContentExportReplayTest.CountingContent(
                List.of(
                    ContentExportReplayTest.unit(0, List.of(call), List.of(), Map.of(), List.of())),
                1,
                0,
                0,
                0));
    var summary =
        Pattern.compile("<summary>(.*?)</summary>", Pattern.DOTALL)
            .matcher(html)
            .results()
            .map(match -> match.group(1))
            .findFirst()
            .orElseThrow();
    assertThat(summary).contains("Partial", "mixed").doesNotContain("provider_reported");
    String total = html.substring(html.lastIndexOf("<p>Total tokens:"));
    assertThat(total).contains("Partial", "mixed").doesNotContain("provider_reported");
  }

  @Test
  void quotedCookieAndApiKeyAreMaskedForBothVisibilities() throws Exception {
    for (var visibility : com.feipi.session.browser.query.api.PayloadVisibility.values()) {
      var call =
          new com.feipi.session.browser.domain.normalized.NormalizedCall(
              "security",
              1,
              "C1",
              CallScope.MAIN,
              Optional.empty(),
              Optional.empty(),
              Optional.of("turn"),
              "synthetic",
              Optional.empty(),
              NormalizedCallUsage.empty(),
              com.feipi.session.browser.domain.normalized.NormalizedCallRequest.empty(),
              com.feipi.session.browser.domain.normalized.NormalizedCallResponse.empty(),
              List.of(),
              List.of(
                  Map.of(
                      "role",
                      "assistant",
                      "type",
                      "text",
                      "text",
                      "{\"Cookie\":\"SID=synthetic-cookie\",\"X-API-Key\":\"synthetic-credential\"}"
                          + " readable-body")),
              Map.of(),
              Map.of());
      var content =
          new ContentExportReplayTest.CountingContent(
              List.of(
                  ContentExportReplayTest.unit(0, List.of(call), List.of(), Map.of(), List.of())),
              1,
              0,
              0,
              0);
      var bytes = new java.io.ByteArrayOutputStream();
      try (var snapshot = ContentExportSnapshot.html(content, 1, visibility, 1024 * 1024)) {
        snapshot.copyTo(bytes);
      }
      assertThat(bytes.toString(java.nio.charset.StandardCharsets.UTF_8))
          .as("quoted credentials at %s", visibility)
          .contains("readable-body", "[REDACTED]")
          .doesNotContain("synthetic-cookie", "synthetic-credential");
    }
  }

  @Test
  void collectorCloseFailureDoesNotPublishOrLeakSnapshot(
      @org.junit.jupiter.api.io.TempDir java.nio.file.Path directory) throws Exception {
    var failure = new java.io.IOException("synthetic close failure");
    var published = new java.util.concurrent.atomic.AtomicBoolean();
    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> {
              try (var snapshot =
                  ContentExportSnapshot.createClosing(
                      directory,
                      1024,
                      output -> output.write(42),
                      () -> {
                        throw failure;
                      })) {
                assertThat(snapshot.size()).isEqualTo(1);
                published.set(true);
              }
            })
        .isSameAs(failure);
    assertThat(published).isFalse();
    try (var files = java.nio.file.Files.list(directory)) {
      assertThat(files.toList()).isEmpty();
    }
  }

  @Test
  void writeAndCloseFailureRetainOriginalAndSuppressedAndCleanSnapshot(
      @org.junit.jupiter.api.io.TempDir java.nio.file.Path directory) throws Exception {
    var write = new java.io.IOException("synthetic write failure");
    var close = new java.io.IOException("synthetic close failure");
    org.assertj.core.api.Assertions.assertThatThrownBy(
            () ->
                ContentExportSnapshot.createClosing(
                    directory,
                    1024,
                    output -> {
                      output.write(42);
                      throw write;
                    },
                    () -> {
                      throw close;
                    }))
        .isSameAs(write)
        .satisfies(failure -> assertThat(failure.getSuppressed()).containsExactly(close));
    try (var files = java.nio.file.Files.list(directory)) {
      assertThat(files.toList()).isEmpty();
    }
  }
}
